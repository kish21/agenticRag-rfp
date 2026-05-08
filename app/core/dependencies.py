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
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError
from app.core.auth import decode_token, TokenData
from app.db.fact_store import get_engine

security = HTTPBearer()


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security)
) -> TokenData:
    """
    Extracts and validates the bearer token from the Authorization header.
    Returns TokenData with org_id and role verified.
    Raises 401 if token is missing, invalid, or expired.
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired token",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        token_data = decode_token(credentials.credentials)
        return token_data
    except JWTError:
        raise credentials_exception


def get_db() -> Generator:
    """Yields a SQLAlchemy connection; commits on exit, rolls back on error."""
    engine = get_engine()
    with engine.connect() as conn:
        yield conn


async def get_current_user_optional(
    credentials: HTTPAuthorizationCredentials = Depends(
        HTTPBearer(auto_error=False)
    )
) -> TokenData | None:
    """
    Same as get_current_user but returns None if no token provided.
    Used for endpoints that work with or without auth (e.g. health check).
    """
    if not credentials:
        return None
    try:
        return decode_token(credentials.credentials)
    except JWTError:
        return None
