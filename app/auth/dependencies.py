"""
FastAPI dependency injection for authentication.

Usage in route:
    @router.get("/evaluations")
    async def list_evaluations(
        current_user: TokenData = Depends(get_current_user)
    ):
        # current_user.org_id is verified from JWT
        # current_user.role is verified from JWT
        ...
"""
from typing import Generator
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError
from app.auth.jwt import decode_token, TokenData
from app.db.fact_store import get_engine, get_admin_engine

security = HTTPBearer(auto_error=False)

COOKIE_NAME = "meridian_session"


async def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
) -> TokenData:
    """
    Resolves the current user from either:
      1. HttpOnly cookie  `meridian_session` (browser clients)
      2. Authorization: Bearer <token> header (API clients / Postman)
    Raises 401 if neither is present or the token is invalid/expired.
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired token",
        headers={"WWW-Authenticate": "Bearer"},
    )

    token: str | None = None

    # 1 — cookie (preferred, set by browser)
    cookie_token = request.cookies.get(COOKIE_NAME)
    if cookie_token:
        token = cookie_token

    # 2 — Authorization header fallback (API clients)
    if token is None and credentials:
        token = credentials.credentials

    if token is None:
        raise credentials_exception

    try:
        return decode_token(token)
    except JWTError:
        raise credentials_exception


def get_db() -> Generator:
    """Yields a tenant-scoped (RLS-governed) connection from the app engine.

    The connection is auto-stamped with app.current_org_id from the request's
    ContextVar (set by OrgContextMiddleware), so RLS confines it to the
    caller's org. Use for all tenant route handlers."""
    engine = get_engine()
    with engine.connect() as conn:
        yield conn


def get_admin_db() -> Generator:
    """Yields an RLS-EXEMPT connection from the owner engine.

    Use ONLY for the identity/auth path, which must resolve which org an email
    belongs to BEFORE any tenant context exists (and reads the RLS-protected
    `users` table). Never use for tenant data access."""
    engine = get_admin_engine()
    with engine.connect() as conn:
        yield conn


async def get_current_user_optional(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(
        HTTPBearer(auto_error=False)
    ),
) -> TokenData | None:
    """
    Same as get_current_user but returns None if no token provided.
    Used for endpoints that work with or without auth (e.g. health check).
    """
    token: str | None = request.cookies.get(COOKIE_NAME)
    if token is None and credentials:
        token = credentials.credentials
    if token is None:
        return None
    try:
        return decode_token(token)
    except JWTError:
        return None
