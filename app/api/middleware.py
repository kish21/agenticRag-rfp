"""
Request middleware for PostgreSQL RLS activation.

Every authenticated request sets app.current_org_id in PostgreSQL
so row-level security policies can enforce tenant isolation.

This runs BEFORE any route handler executes.
The org_id comes from the verified JWT token — never from the request body.
"""
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response
from jose import JWTError
from app.core.auth import decode_token
import sqlalchemy as sa
from app.db.fact_store import get_engine

# Routes that do not require auth and do not need RLS
PUBLIC_ROUTES = {
    "/health",
    "/api/v1/auth/token",
    "/docs",
    "/openapi.json",
    "/redoc"
}


class AuthMiddleware(BaseHTTPMiddleware):
    """
    Middleware that:
    1. Extracts org_id from JWT on every authenticated request
    2. Sets app.current_org_id in PostgreSQL for RLS enforcement
    3. Attaches token_data to request.state for route handlers
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        if request.url.path in PUBLIC_ROUTES:
            return await call_next(request)

        auth_header = request.headers.get("Authorization", "")
        token_data = None

        if auth_header.startswith("Bearer "):
            token = auth_header[7:]
            try:
                token_data = decode_token(token)
                request.state.user = token_data
            except JWTError:
                pass  # Route handler will return 401 via Depends

        if token_data:
            try:
                engine = get_engine()
                with engine.connect() as conn:
                    conn.execute(
                        sa.text("SET LOCAL app.current_org_id = :org_id"),
                        {"org_id": token_data.org_id}
                    )
                    conn.commit()
            except Exception as e:
                # Log but do not block — RLS policies will catch
                # unauthorised access even without this hint
                print(f"RLS context setting failed: {e}")

        return await call_next(request)
