"""DX-001 (#128) — OpenAPI/Swagger annotation meta-tests.

These are *meta-tests*: they iterate the generated OpenAPI schema and the app's
route table rather than calling any endpoint, so they need no database, no auth
and no network. They enforce the documentation bar AND act as anti-regression
gates — a new route that ships without a summary, or one that adds a
behaviour-changing ``response_model``, fails CI here.

Why these specific gates (and not "every route documents 401/403/404"):
  • 401 is required only on routes that actually sit behind ``get_current_user``
    — documenting 401 on a public route (e.g. /auth/token, /health) would be a
    lie in the docs.
  • 403 cannot be detected reliably from the route table (most role checks live
    in the handler body, not in a dependency), so it is annotated by hand
    per-route and not auto-gated here.
  • A path-parameter route documents the "resource not found / wrong state"
    envelope (404 or 409) — both are present across the codebase, so this is a
    true, non-flaky gate.
"""
from fastapi.routing import APIRoute

from app.main import app
from app.auth.dependencies import get_current_user

OPENAPI = app.openapi()
_HTTP_METHODS = {"get", "post", "put", "patch", "delete"}


def _api_routes():
    return [r for r in app.routes if isinstance(r, APIRoute)]


def _operations():
    """Yield (path, method, operation) for every documented HTTP operation."""
    for path, methods in OPENAPI["paths"].items():
        for method, op in methods.items():
            if method.lower() in _HTTP_METHODS:
                yield path, method.lower(), op


def _dependant_calls(dependant):
    """All dependency callables in a route's dependant tree (transitive)."""
    calls, stack = [], [dependant]
    while stack:
        d = stack.pop()
        if getattr(d, "call", None) is not None:
            calls.append(d.call)
        stack.extend(d.dependencies)
    return calls


def _is_authenticated(route: APIRoute) -> bool:
    return get_current_user in _dependant_calls(route.dependant)


def _route_methods(route: APIRoute):
    return [m.lower() for m in route.methods if m.lower() in _HTTP_METHODS]


# Routes whose response is bound to a model — either via an explicit
# `response_model=` (Pydantic envelope) or a `-> dict`/`-> Model` return
# annotation that FastAPI infers. DX-001 added NO new entries here (the one
# behaviour-change footgun): the `response_model=` edits only reformatted the
# existing value onto its own line, and no return annotation was touched.
# If this set changes, a contributor added/removed a response_model: prove with
# a before/after response-body snapshot that nothing is filtered, then update
# this baseline deliberately.
RESPONSE_MODEL_BASELINE = {
    # explicit response_model= envelopes
    ("post", "/api/v1/auth/signup"),
    ("post", "/api/v1/auth/token"),
    ("get", "/api/v1/auth/me"),
    ("post", "/api/v1/auth/invite/accept"),
    ("post", "/api/v1/admin/agents"),
    ("get", "/api/v1/org/settings"),
    ("patch", "/api/v1/org/settings"),
    ("post", "/api/v1/org/settings/reset"),
    ("post", "/api/v1/chat/document"),
    ("get", "/api/v1/chat/criteria"),
    ("post", "/api/v1/chat/criteria"),
    ("post", "/api/v1/rfps"),
    ("post", "/api/v1/rfps/{rfp_id}/vendors"),
    # response_model inferred from a `-> dict` / `-> Model` return annotation
    ("get", "/api/v1/rfps/{rfp_id}"),
    ("post", "/api/v1/rfps/{rfp_id}/deadline"),
    ("get", "/api/v1/admin/attribution-queue"),
    ("post", "/api/v1/admin/attribution-queue/{job_id}/assign"),
    ("post", "/api/v1/admin/late-addendum/{job_id}/accept"),
    ("delete", "/api/v1/admin/llm-cache"),
    ("delete", "/api/v1/admin/org/{org_id}/data"),  # SC-001 #119 — returns erasure-receipt dict
}


# ── Criterion #5 — schema generates cleanly as OpenAPI 3.1 ──────────────────

def test_openapi_schema_builds_as_3_1():
    assert OPENAPI["openapi"].startswith("3.1")


# ── Criterion #1 — completeness (HARD gate, decision B) ─────────────────────

def test_every_operation_has_summary_and_description():
    missing = [
        f"{method.upper()} {path}"
        for path, method, op in _operations()
        if not op.get("summary") or not op.get("description")
    ]
    assert not missing, (
        "Every route must declare a non-empty summary and description "
        f"(docstring or description=). Missing on: {missing}"
    )


# ── Criterion #2 — error responses ──────────────────────────────────────────

def test_authenticated_routes_document_401():
    offenders = []
    for route in _api_routes():
        if not _is_authenticated(route):
            continue
        # Routes excluded from the schema (include_in_schema=False) have no
        # documented operation to gate — skip rather than KeyError on them.
        if route.path not in OPENAPI["paths"]:
            continue
        for method in _route_methods(route):
            op = OPENAPI["paths"][route.path][method]
            if "401" not in op.get("responses", {}):
                offenders.append(f"{method.upper()} {route.path}")
    assert not offenders, (
        "Routes behind get_current_user must document a 401 response. "
        f"Missing on: {offenders}"
    )


def test_path_param_routes_document_not_found_or_conflict():
    offenders = []
    for path, method, op in _operations():
        if "{" not in path:
            continue
        codes = set(op.get("responses", {}).keys())
        if not ({"404", "409"} & codes):
            offenders.append(f"{method.upper()} {path}")
    assert not offenders, (
        "Routes with a path parameter must document the not-found/conflict "
        f"envelope (404 or 409). Missing on: {offenders}"
    )


def test_error_responses_use_detail_envelope():
    """Every documented 4xx/5xx example must match the app's {'detail': str}
    HTTPException envelope, so the docs don't promise a shape we never return.
    FastAPI's auto-generated 422 (HTTPValidationError) is exempt."""
    bad = []
    for path, method, op in _operations():
        for code, spec in op.get("responses", {}).items():
            if not (code.startswith("4") or code.startswith("5")):
                continue
            if code == "422":  # FastAPI's own validation schema — leave it.
                continue
            example = (
                spec.get("content", {})
                .get("application/json", {})
                .get("example")
            )
            if example is None:
                continue
            if list(example.keys()) != ["detail"]:
                bad.append(f"{method.upper()} {path} [{code}] -> {example}")
    assert not bad, f"Error examples must be {{'detail': ...}}: {bad}"


# ── Criterion #4 — app-level metadata ───────────────────────────────────────

def test_app_info_metadata_present():
    info = OPENAPI["info"]
    assert info.get("description"), "app description missing"
    assert info.get("contact", {}).get("email"), "contact email missing"
    # FastAPI serialises license_info under the OpenAPI 'license' key.
    assert info.get("license", {}).get("name"), "license_info missing"


def test_every_router_tag_has_a_description():
    tag_desc = {t["name"]: t.get("description") for t in OPENAPI.get("tags", [])}
    required = {
        "auth", "admin", "evaluate", "tenant", "org-settings",
        "chat", "rfps", "logs", "system",
    }
    missing = [t for t in required if not tag_desc.get(t)]
    assert not missing, f"Tags missing a description in openapi_tags: {missing}"


# ── Criterion #3 — no NEW response_model (anti-footgun guard) ───────────────

def test_response_model_set_is_unchanged():
    actual = {
        (method, route.path)
        for route in _api_routes()
        if route.response_model is not None
        for method in _route_methods(route)
    }
    assert actual == RESPONSE_MODEL_BASELINE, (
        "The set of routes with a response_model changed. Adding response_model "
        "to a route that returns a raw dict silently filters its response body "
        "(a behaviour change). Verify with a before/after body snapshot, then "
        f"update RESPONSE_MODEL_BASELINE.\n  added:   {actual - RESPONSE_MODEL_BASELINE}"
        f"\n  removed: {RESPONSE_MODEL_BASELINE - actual}"
    )
