"""
Per-request tenant-context middleware for PostgreSQL RLS (P0.16).

Reads org_id from the verified JWT (cookie or Bearer header) and binds it to
the request's ContextVar so the app-engine connection listener stamps
``app.current_org_id`` onto every connection the request opens. RLS policies
(``org_id::text = current_setting('app.current_org_id', true)``) then enforce
tenant isolation at the database, underneath the application's WHERE filters.

This is implemented as a PURE ASGI middleware on purpose. Starlette's
``BaseHTTPMiddleware`` runs the downstream app in a separate anyio task, so a
ContextVar set in its ``dispatch`` does NOT propagate to the route handler —
which is exactly the silent no-op this fix replaces. A pure ASGI middleware
sets the ContextVar in the same context that schedules the endpoint, so it
propagates to both async and threadpool-run sync handlers.

The org_id always comes from the cryptographically verified token — never from
the request body or a header the client controls directly.
"""
from jose import JWTError
from starlette.requests import HTTPConnection

from app.auth.dependencies import COOKIE_NAME
from app.auth.jwt import decode_token
from app.db.session import _current_org_id

# Routes that do not require auth and carry no tenant context.
PUBLIC_ROUTES = {
    "/health",
    "/api/v1/auth/token",
    "/api/v1/auth/signup",
    "/api/v1/auth/invite/accept",
    "/api/v1/auth/password-reset/request",
    "/api/v1/auth/password-reset/confirm",
    "/docs",
    "/openapi.json",
    "/redoc",
}


def _extract_org_id(scope) -> str | None:
    """Best-effort org_id from the request's JWT. Returns None when absent or
    invalid — the handler's own auth dependency will still 401 as appropriate."""
    conn = HTTPConnection(scope)
    token = conn.cookies.get(COOKIE_NAME)
    if not token:
        auth = conn.headers.get("authorization", "")
        if auth.startswith("Bearer "):
            token = auth[7:]
    if not token:
        return None
    try:
        return decode_token(token).org_id
    except JWTError:
        return None


class OrgContextMiddleware:
    """Pure ASGI middleware: bind the request's tenant to the org ContextVar."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope.get("path") in PUBLIC_ROUTES:
            return await self.app(scope, receive, send)

        org_id = _extract_org_id(scope)
        token = _current_org_id.set(org_id)
        try:
            await self.app(scope, receive, send)
        finally:
            _current_org_id.reset(token)
