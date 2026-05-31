"""
Authentication endpoints.

POST /api/v1/auth/signup                  — create org + owner user in one txn
POST /api/v1/auth/token                   — exchange credentials for JWT
POST /api/v1/auth/verify                  — verify token (used by frontend)
GET  /api/v1/auth/me                      — current user record from DB
POST /api/v1/auth/logout                  — clear cookie + revoke this session
POST /api/v1/auth/invite                  — admin issues a one-time invite token
POST /api/v1/auth/invite/accept           — invitee sets their own password
POST /api/v1/auth/password-reset/request  — request a one-time reset token
POST /api/v1/auth/password-reset/confirm  — set a new password with the token

E2 auth hardening (2026-05-31):
  • Cookies are Secure in production (settings.cookie_secure).
  • Email is unique platform-wide (one account per email) — code now agrees
    with the schema's UNIQUE(email); duplicate signup returns 409.
  • Every issued token registers a session (jti); logout/reset revoke it, so a
    JWT can be invalidated before it expires.
  • Invites and resets use one-time, expiring, hash-at-rest tokens. No endpoint
    ever returns a plaintext or temporary password.
"""
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, HTTPException, Response, status, Depends
from pydantic import BaseModel
import sqlalchemy as sa
from app.auth.jwt import (
    verify_password, create_access_token,
    hash_password, Token, TokenData,
)
from app.auth.dependencies import get_current_user, get_admin_db, COOKIE_NAME
from app.auth.sessions import issue_session, revoke_session, revoke_user_sessions
from app.auth import tokens
from app.config import settings

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])

COOKIE_MAX_AGE = settings.jwt_expiry_minutes * 60
MIN_PASSWORD_LENGTH = 8


def _is_production() -> bool:
    return settings.environment.lower() in ("production", "prod", "staging", "stage")


def _set_auth_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        key=COOKIE_NAME,
        value=token,
        httponly=True,
        samesite="lax",
        secure=settings.cookie_secure,   # True in production (HTTPS-only)
        path="/",
        max_age=COOKIE_MAX_AGE,
    )


def _clear_auth_cookie(response: Response) -> None:
    response.delete_cookie(key=COOKIE_NAME, path="/")


def _validate_password(password: str) -> None:
    if len(password or "") < MIN_PASSWORD_LENGTH:
        raise HTTPException(
            status_code=422,
            detail=f"Password must be at least {MIN_PASSWORD_LENGTH} characters",
        )


def _register_session(db, token: Token, user_id: str, org_id: str) -> None:
    """Record the freshly minted token in the session allowlist.

    Commits the connection's current transaction (login runs a SELECT first,
    which autobegins one) — so we never call begin() on an already-open txn.
    """
    expires_at = datetime.now(timezone.utc) + timedelta(
        minutes=settings.jwt_expiry_minutes
    )
    issue_session(
        db, jti=token.jti, user_id=user_id, org_id=org_id, expires_at=expires_at
    )
    db.commit()


# ── Request / Response models ──────────────────────────────────────────────────

class SignupRequest(BaseModel):
    org_name:  str
    industry:  str = "General"
    email:     str
    password:  str
    full_name: str = ""


class LoginRequest(BaseModel):
    email:    str
    password: str


class InviteRequest(BaseModel):
    email:   str
    role:    str = "department_user"
    dept_id: str | None = None


class InviteAcceptRequest(BaseModel):
    token:     str
    password:  str
    full_name: str = ""


class PasswordResetRequest(BaseModel):
    email: str


class PasswordResetConfirm(BaseModel):
    token:    str
    password: str


class UserInfo(BaseModel):
    user_id:  str
    email:    str
    org_id:   str
    role:     str
    dept_id:  str | None = None
    is_active: bool


# ── Helpers ────────────────────────────────────────────────────────────────────

def _get_user_by_email(conn, email: str) -> dict | None:
    row = conn.execute(
        sa.text("""
            SELECT user_id::text, email, hashed_pw, org_id::text,
                   role, dept_id::text, is_active
            FROM users
            WHERE email = :email
        """),
        {"email": email},
    ).fetchone()
    if row is None:
        return None
    return dict(zip(["user_id","email","hashed_pw","org_id","role","dept_id","is_active"], row))


def _email_taken(conn, email: str) -> bool:
    return conn.execute(
        sa.text("SELECT 1 FROM users WHERE email = :email LIMIT 1"),
        {"email": email},
    ).fetchone() is not None


# ── Endpoints ──────────────────────────────────────────────────────────────────

@router.post("/signup", response_model=Token, status_code=status.HTTP_201_CREATED)
async def signup(req: SignupRequest, response: Response, db=Depends(get_admin_db)):
    """
    Create a new organisation and its first owner user in one transaction.
    Email is unique platform-wide (one account per email) — a duplicate is 409.
    Returns a JWT for the new owner.
    """
    _validate_password(req.password)

    with db.begin():
        if _email_taken(db, req.email):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="An account with that email already exists",
            )

        org_row = db.execute(
            sa.text("""
                INSERT INTO organisations (org_name, industry, subscription_tier, is_active)
                VALUES (:name, :industry, 'trial', TRUE)
                RETURNING org_id::text
            """),
            {"name": req.org_name, "industry": req.industry},
        ).fetchone()
        org_id = org_row[0]

        user_row = db.execute(
            sa.text("""
                INSERT INTO users (org_id, email, hashed_pw, role, is_active)
                VALUES (CAST(:org_id AS uuid), :email, :hashed_pw, 'company_admin', TRUE)
                RETURNING user_id::text
            """),
            {
                "org_id":    org_id,
                "email":     req.email,
                "hashed_pw": hash_password(req.password),
            },
        ).fetchone()
        user_id = user_row[0]

        db.execute(
            sa.text("""
                INSERT INTO tenant_modules (org_id, module_key, enabled, activated_at)
                VALUES (CAST(:org_id AS uuid), 'rfp_evaluation', TRUE, now())
                ON CONFLICT DO NOTHING
            """),
            {"org_id": org_id},
        )

        db.execute(
            sa.text("""
                INSERT INTO tenant_billing (org_id, plan, modules_active)
                VALUES (CAST(:org_id AS uuid), 'trial', ARRAY['rfp_evaluation'])
                ON CONFLICT DO NOTHING
            """),
            {"org_id": org_id},
        )

    token = create_access_token(
        email=req.email,
        org_id=org_id,
        role="company_admin",
        dept_id=None,
    )
    _register_session(db, token, user_id=user_id, org_id=org_id)
    _set_auth_cookie(response, token.access_token)
    return token


@router.post("/token", response_model=Token)
async def login(req: LoginRequest, response: Response, db=Depends(get_admin_db)):
    """Exchange email + password for a JWT token."""
    user = _get_user_by_email(db, req.email)

    if user is None:
        # First boot: seed dev user if credentials match settings
        if (req.email == settings.dev_user_email
                and verify_password(req.password, hash_password(settings.dev_user_password))):
            _ensure_dev_user(db)
            user = _get_user_by_email(db, req.email)

    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    if not verify_password(req.password, user["hashed_pw"]):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    if not user["is_active"]:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account is inactive")

    token = create_access_token(
        email=user["email"],
        org_id=user["org_id"],
        role=user["role"],
        dept_id=user["dept_id"],
    )
    _register_session(db, token, user_id=user["user_id"], org_id=user["org_id"])
    _set_auth_cookie(response, token.access_token)
    return token


def _ensure_dev_user(db) -> None:
    """Idempotently creates the dev seed user + org if absent.

    Commits the connection's current transaction rather than opening a new one:
    login() runs a SELECT first (which autobegins a txn on the get_admin_db
    connection), so a `with db.begin()` here would raise InvalidRequestError.
    """
    org_id = settings.dev_org_id
    db.execute(
        sa.text("""
            INSERT INTO organisations (org_id, org_name, industry, subscription_tier, is_active)
            VALUES (CAST(:org_id AS uuid), 'Dev Organisation', 'Technology', 'trial', TRUE)
            ON CONFLICT (org_id) DO NOTHING
        """),
        {"org_id": org_id},
    )
    db.execute(
        sa.text("""
            INSERT INTO users (org_id, email, hashed_pw, role, is_active)
            VALUES (CAST(:org_id AS uuid), :email, :hashed_pw, :role, TRUE)
            ON CONFLICT (email) DO NOTHING
        """),
        {
            "org_id":    org_id,
            "email":     settings.dev_user_email,
            "hashed_pw": hash_password(settings.dev_user_password),
            "role":      settings.dev_user_role,
        },
    )
    db.execute(
        sa.text("""
            INSERT INTO tenant_modules (org_id, module_key, enabled, activated_at)
            VALUES (CAST(:org_id AS uuid), 'rfp_evaluation', TRUE, now())
            ON CONFLICT DO NOTHING
        """),
        {"org_id": org_id},
    )
    db.execute(
        sa.text("""
            INSERT INTO tenant_billing (org_id, plan, modules_active)
            VALUES (CAST(:org_id AS uuid), 'trial', ARRAY['rfp_evaluation'])
            ON CONFLICT DO NOTHING
        """),
        {"org_id": org_id},
    )
    db.commit()


@router.post("/logout")
async def logout(
    response: Response,
    current_user: TokenData = Depends(get_current_user),
    db=Depends(get_admin_db),
):
    """Clears the cookie AND revokes this token's session so it can't be reused."""
    if current_user.jti:
        with db.begin():
            revoke_session(db, current_user.jti, reason="logout")
    _clear_auth_cookie(response)
    return {"message": "Logged out"}


@router.post("/verify")
async def verify_token(current_user: TokenData = Depends(get_current_user)):
    return {
        "valid": True,
        "email": current_user.email,
        "org_id": current_user.org_id,
        "role": current_user.role,
    }


@router.get("/me", response_model=UserInfo)
async def get_me(
    current_user: TokenData = Depends(get_current_user),
    db=Depends(get_admin_db),
):
    """Returns the current user's stored record (not just token claims)."""
    user = _get_user_by_email(db, current_user.email)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return UserInfo(**user)


@router.post("/invite", status_code=status.HTTP_201_CREATED)
async def invite_user(
    req: InviteRequest,
    current_user: TokenData = Depends(get_current_user),
    db=Depends(get_admin_db),
):
    """
    company_admin / department_admin invites a team member to their org.

    Returns a one-time, expiring INVITE TOKEN (never a password). The invitee
    redeems it at POST /invite/accept to set their own password. The token is
    delivered to the admin (and, in production, would also be emailed).
    """
    if current_user.role not in ("platform_admin", "company_admin", "department_admin"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient role")

    # department_admin can only invite department_user
    if current_user.role == "department_admin" and req.role not in ("department_user",):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Cannot assign that role")

    with db.begin():
        if _email_taken(db, req.email):
            raise HTTPException(status_code=409, detail="A user with that email already exists")
        invite_token = tokens.create_onetime_token(
            db,
            purpose=tokens.INVITE,
            email=req.email,
            org_id=current_user.org_id,
            role=req.role,
            dept_id=req.dept_id,
        )

    return {
        "message":      f"Invite created for {req.email}",
        "invite_token": invite_token,
        "expires_in_hours": tokens.INVITE_TTL_HOURS,
        "note": "Share this one-time link; the invitee sets their own password "
                "at /api/v1/auth/invite/accept. It is not a password.",
    }


@router.post("/invite/accept", response_model=Token, status_code=status.HTTP_201_CREATED)
async def accept_invite(req: InviteAcceptRequest, response: Response, db=Depends(get_admin_db)):
    """Redeem a one-time invite token and set the invitee's own password."""
    _validate_password(req.password)

    with db.begin():
        payload = tokens.consume_token(db, req.token, tokens.INVITE)
        if payload is None:
            raise HTTPException(status_code=400, detail="Invalid or expired invite token")
        if _email_taken(db, payload["email"]):
            raise HTTPException(status_code=409, detail="A user with that email already exists")

        user_row = db.execute(
            sa.text("""
                INSERT INTO users (org_id, email, hashed_pw, role, dept_id, is_active)
                VALUES (
                    CAST(:org_id AS uuid), :email, :hashed_pw, :role,
                    CAST(NULLIF(:dept_id, '') AS uuid), TRUE
                )
                RETURNING user_id::text
            """),
            {
                "org_id":    payload["org_id"],
                "email":     payload["email"],
                "hashed_pw": hash_password(req.password),
                "role":      payload["role"] or "department_user",
                "dept_id":   payload["dept_id"] or "",
            },
        ).fetchone()
        user_id = user_row[0]

    token = create_access_token(
        email=payload["email"],
        org_id=payload["org_id"],
        role=payload["role"] or "department_user",
        dept_id=payload["dept_id"],
    )
    _register_session(db, token, user_id=user_id, org_id=payload["org_id"])
    _set_auth_cookie(response, token.access_token)
    return token


@router.post("/password-reset/request", status_code=status.HTTP_202_ACCEPTED)
async def request_password_reset(req: PasswordResetRequest, db=Depends(get_admin_db)):
    """
    Begin a password reset. Always returns 202 with a generic message so the
    endpoint cannot be used to enumerate which emails have accounts. When an
    account exists, a one-time expiring reset token is created (and, in
    production, emailed). In non-production the token is returned for testing.
    """
    generic = {"message": "If an account exists for that email, a reset link has been sent."}
    with db.begin():
        user = _get_user_by_email(db, req.email)
        if user is None:
            return generic
        reset_token = tokens.create_onetime_token(
            db,
            purpose=tokens.PASSWORD_RESET,
            email=user["email"],
            org_id=user["org_id"],
            user_id=user["user_id"],
        )
    if _is_production():
        return generic
    # Dev/test convenience only — never leak the token in production.
    return {**generic, "reset_token": reset_token, "expires_in_hours": tokens.RESET_TTL_HOURS}


@router.post("/password-reset/confirm")
async def confirm_password_reset(req: PasswordResetConfirm, db=Depends(get_admin_db)):
    """Set a new password with a one-time reset token, then revoke all sessions."""
    _validate_password(req.password)
    with db.begin():
        payload = tokens.consume_token(db, req.token, tokens.PASSWORD_RESET)
        if payload is None:
            raise HTTPException(status_code=400, detail="Invalid or expired reset token")
        db.execute(
            sa.text("UPDATE users SET hashed_pw = :pw WHERE user_id = CAST(:uid AS uuid)"),
            {"pw": hash_password(req.password), "uid": payload["user_id"]},
        )
        # Force re-login everywhere: any token issued before the reset is dead.
        revoke_user_sessions(db, payload["user_id"], reason="password_reset")
    return {"message": "Password updated. Please sign in again."}
