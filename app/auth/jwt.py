"""
JWT authentication and user role management.

Five roles:
  platform_admin   — operator level, cross-org visibility, no customer data
  company_admin    — all departments within their org
  department_admin — sets criteria templates, sees all evals in their dept
  department_user  — runs evaluations, can override with documented reason
  auditor          — read-only compliance persona (#55). Sees the org's audit
                     trail (who-accessed-what + override/state-change events) but
                     NOT evaluation content, and cannot run/override evaluations.

Token payload:
  sub          — user email
  org_id       — organisation identifier
  role         — one of the five roles above
  dept_id      — department identifier (optional, for dept-scoped roles)
  exp          — expiry timestamp
"""
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional
import bcrypt
import jwt
from pydantic import BaseModel, Field
from app.config import settings

# bcrypt operates on at most 72 bytes of input. We truncate longer passwords
# explicitly because bcrypt 5.x *raises* on >72 bytes (4.x silently truncated),
# and because this matches the behaviour of the now-unmaintained passlib backend
# this code used previously — so password hashes created before the migration
# still verify. This module is the ONLY place that knows we use the bcrypt
# library, so swapping it again stays a one-file change (same as TokenError/PyJWT).
_BCRYPT_MAX_BYTES = 72


def _bcrypt_bytes(password: str) -> bytes:
    return password.encode("utf-8")[:_BCRYPT_MAX_BYTES]


class TokenError(Exception):
    """Raised when a JWT cannot be decoded or fails validation.

    App-level exception so callers (dependencies, middleware) never import the
    underlying JWT library's error type — this module is the ONLY place that
    knows we use PyJWT, so swapping libraries again stays a one-file change."""


VALID_ROLES = {
    "platform_admin",
    "company_admin",
    "department_admin",
    "department_user",
    "auditor",
}


class TokenData(BaseModel):
    email: str
    org_id: str
    role: str
    dept_id: Optional[str] = None
    # Unique token id ("jti"). Present on all tokens minted after the E2 auth
    # hardening; None for legacy tokens. Used to look the session up in the
    # auth_sessions allowlist so a token can be revoked server-side.
    jti: Optional[str] = None


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    org_id: str
    role: str
    # The token's jti, exposed to the caller so it can record the session.
    # Excluded from API responses (it is already inside the signed JWT).
    jti: Optional[str] = Field(default=None, exclude=True)


def hash_password(password: str) -> str:
    return bcrypt.hashpw(_bcrypt_bytes(password), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    # Fail CLOSED: a malformed stored hash (e.g. not a bcrypt string) makes
    # bcrypt.checkpw raise — treat that as "does not match", never as success.
    try:
        return bcrypt.checkpw(
            _bcrypt_bytes(plain_password), hashed_password.encode("utf-8")
        )
    except (ValueError, TypeError):
        return False


def create_access_token(
    email: str,
    org_id: str,
    role: str,
    dept_id: Optional[str] = None,
    jti: Optional[str] = None,
) -> Token:
    """Creates a signed JWT token with org_id, role and a unique jti in payload.

    The jti is returned on the Token so the caller can register the session in
    the auth_sessions allowlist (enabling server-side revocation). A jti is
    generated when not supplied.
    """
    if role not in VALID_ROLES:
        raise ValueError(f"Invalid role: {role}. Must be one of {VALID_ROLES}")

    jti = jti or str(uuid.uuid4())
    expiry = datetime.now(timezone.utc) + timedelta(
        minutes=settings.jwt_expiry_minutes
    )

    payload = {
        "sub": email,
        "org_id": org_id,
        "role": role,
        "jti": jti,
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
        role=role,
        jti=jti,
    )


def decode_token(token: str) -> TokenData:
    """
    Decodes and validates a JWT token.
    Raises TokenError if the token is invalid, expired, or missing fields.
    """
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret_key,
            algorithms=[settings.jwt_algorithm]
        )
    except jwt.PyJWTError as exc:
        # Signature/expiry/format failures (incl. ExpiredSignatureError) all
        # subclass PyJWTError — surface them as our app-level TokenError.
        raise TokenError(str(exc)) from exc

    email = payload.get("sub")
    org_id = payload.get("org_id")
    role = payload.get("role")
    dept_id = payload.get("dept_id")
    jti = payload.get("jti")

    if not email or not org_id or not role:
        raise TokenError("Missing required fields in token")

    if role not in VALID_ROLES:
        raise TokenError(f"Invalid role in token: {role}")

    return TokenData(
        email=email,
        org_id=org_id,
        role=role,
        dept_id=dept_id,
        jti=jti,
    )


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
