"""
JWT authentication and user role management.

Four roles:
  platform_admin   — operator level, cross-org visibility, no customer data
  company_admin    — all departments within their org
  department_admin — sets criteria templates, sees all evals in their dept
  department_user  — runs evaluations, can override with documented reason

Token payload:
  sub          — user email
  org_id       — organisation identifier
  role         — one of the four roles above
  dept_id      — department identifier (optional, for dept-scoped roles)
  exp          — expiry timestamp
"""
from datetime import datetime, timedelta, timezone
from typing import Optional
from jose import JWTError, jwt
from passlib.context import CryptContext
from pydantic import BaseModel
from app.config import settings

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

VALID_ROLES = {
    "platform_admin",
    "company_admin",
    "department_admin",
    "department_user"
}


class TokenData(BaseModel):
    email: str
    org_id: str
    role: str
    dept_id: Optional[str] = None


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    org_id: str
    role: str


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


def create_access_token(
    email: str,
    org_id: str,
    role: str,
    dept_id: Optional[str] = None
) -> Token:
    """Creates a signed JWT token with org_id and role in payload."""
    if role not in VALID_ROLES:
        raise ValueError(f"Invalid role: {role}. Must be one of {VALID_ROLES}")

    expiry = datetime.now(timezone.utc) + timedelta(
        minutes=settings.jwt_expiry_minutes
    )

    payload = {
        "sub": email,
        "org_id": org_id,
        "role": role,
        "exp": expiry,
    }
    if dept_id:
        payload["dept_id"] = dept_id

    token = jwt.encode(
        payload,
        settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm
    )

    return Token(
        access_token=token,
        token_type="bearer",
        expires_in=settings.jwt_expiry_minutes * 60,
        org_id=org_id,
        role=role
    )


def decode_token(token: str) -> TokenData:
    """
    Decodes and validates a JWT token.
    Raises JWTError if token is invalid or expired.
    """
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret_key,
            algorithms=[settings.jwt_algorithm]
        )
        email = payload.get("sub")
        org_id = payload.get("org_id")
        role = payload.get("role")
        dept_id = payload.get("dept_id")

        if not email or not org_id or not role:
            raise JWTError("Missing required fields in token")

        if role not in VALID_ROLES:
            raise JWTError(f"Invalid role in token: {role}")

        return TokenData(
            email=email,
            org_id=org_id,
            role=role,
            dept_id=dept_id
        )
    except JWTError:
        raise


def require_role(*allowed_roles: str):
    """
    Returns a dependency function that enforces role requirements.
    Usage: Depends(require_role("company_admin", "department_admin"))
    """
    def check_role(token_data: TokenData) -> TokenData:
        if token_data.role not in allowed_roles:
            from fastapi import HTTPException, status
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Role '{token_data.role}' is not permitted. "
                       f"Required: {list(allowed_roles)}"
            )
        return token_data
    return check_role
