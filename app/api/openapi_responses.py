"""Reusable OpenAPI error-response specs (DX-001, #128).

These dicts are passed to a route's ``responses=`` decorator kwarg so Swagger /
ReDoc render the error envelopes a route can actually return. They are PURE
DOCUMENTATION — FastAPI only uses them to enrich the generated OpenAPI schema;
they do not change runtime behaviour (no status code, body, or validation is
altered). Every ``HTTPException`` raised in this app serialises as
``{"detail": <string>}``, so each spec documents exactly that shape.

Only attach a code a route can genuinely raise — documenting a 403 on a route
that never checks a role would be a lie in the docs. Read the handler first.
"""
from typing import Any

ErrorSpec = dict[int, dict[str, Any]]


def _err(description: str, example_detail: str) -> dict[str, Any]:
    return {
        "description": description,
        "content": {"application/json": {"example": {"detail": example_detail}}},
    }


#: Missing / invalid / expired credentials — any route behind ``get_current_user``.
UNAUTHORIZED: ErrorSpec = {
    401: _err("Missing or invalid authentication token.", "Invalid or expired token"),
}
#: Authenticated, but the caller's role/permission is insufficient for the action.
FORBIDDEN: ErrorSpec = {
    403: _err("Authenticated, but the caller lacks the required role or permission.", "Insufficient role"),
}
#: The requested resource does not exist, or is not visible to the caller's org.
NOT_FOUND: ErrorSpec = {
    404: _err("The requested resource does not exist or is not visible to this organisation.", "Resource not found"),
}
#: The request conflicts with the resource's current state (wrong status, duplicate, race).
CONFLICT: ErrorSpec = {
    409: _err("The request conflicts with the resource's current state.", "Conflicting state"),
}
#: The request was malformed or failed a documented precondition.
BAD_REQUEST: ErrorSpec = {
    400: _err("The request was malformed or failed a precondition.", "Bad request"),
}
#: Request body or parameters failed validation.
UNPROCESSABLE: ErrorSpec = {
    422: _err("Request body or parameters failed validation.", "Validation error"),
}
#: An upstream dependency is unavailable (e.g. PDF rendering libs not installed).
SERVICE_UNAVAILABLE: ErrorSpec = {
    503: _err("A required service dependency is currently unavailable.", "Service unavailable"),
}
#: Uploaded payload exceeds the route's size limit.
PAYLOAD_TOO_LARGE: ErrorSpec = {
    413: _err("The uploaded payload exceeds the allowed size limit.", "File too large"),
}


def responses(*specs: ErrorSpec) -> ErrorSpec:
    """Merge one or more error specs into a single ``responses=`` dict.

    Later specs win on key collision (none overlap today). Keeps route
    decorators readable: ``responses=responses(UNAUTHORIZED, FORBIDDEN, NOT_FOUND)``.
    """
    out: ErrorSpec = {}
    for spec in specs:
        out.update(spec)
    return out
