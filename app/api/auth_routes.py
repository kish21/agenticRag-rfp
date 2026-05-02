"""
Authentication endpoints.

POST /api/v1/auth/token  — exchange credentials for JWT token
POST /api/v1/auth/verify — verify a token is valid (used by frontend)
GET  /api/v1/auth/me     — get current user info from token
"""
from fastapi import APIRouter, HTTPException, status, Depends
from pydantic import BaseModel
from app.core.auth import (
    verify_password, create_access_token,
    hash_password, Token, TokenData
)
from app.core.dependencies import get_current_user
from app.config import settings

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


class LoginRequest(BaseModel):
    email: str
    password: str
    org_id: str


class UserInfo(BaseModel):
    email: str
    org_id: str
    role: str
    dept_id: str | None = None


# In-memory user store for development.
# Replace with PostgreSQL users table in production (Skill 01b extension).
_DEV_USERS: dict[str, dict] = {}


def _init_dev_user():
    """Creates the development user on startup if it does not exist."""
    email = settings.dev_user_email
    if email not in _DEV_USERS:
        _DEV_USERS[email] = {
            "email": email,
            "hashed_password": hash_password(settings.dev_user_password),
            "org_id": settings.dev_org_id,
            "role": settings.dev_user_role,
            "dept_id": None,
            "is_active": True
        }


_init_dev_user()


@router.post("/token", response_model=Token)
async def login(request: LoginRequest):
    """
    Exchange email + password + org_id for a JWT token.

    For development: use the credentials from .env
        email: dev@platform.local
        password: devpassword2026
        org_id: test-org
    """
    user = _DEV_USERS.get(request.email)

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials"
        )

    if user["org_id"] != request.org_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials"
        )

    if not verify_password(request.password, user["hashed_password"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials"
        )

    if not user.get("is_active", True):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is inactive"
        )

    return create_access_token(
        email=user["email"],
        org_id=user["org_id"],
        role=user["role"],
        dept_id=user.get("dept_id")
    )


@router.post("/verify")
async def verify_token(
    current_user: TokenData = Depends(get_current_user)
):
    """Verifies a token is valid and returns the token payload."""
    return {
        "valid": True,
        "email": current_user.email,
        "org_id": current_user.org_id,
        "role": current_user.role
    }


@router.get("/me", response_model=UserInfo)
async def get_me(
    current_user: TokenData = Depends(get_current_user)
):
    """Returns current user information extracted from the token."""
    return UserInfo(
        email=current_user.email,
        org_id=current_user.org_id,
        role=current_user.role,
        dept_id=current_user.dept_id
    )
