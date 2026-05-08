"""
Authentication endpoints.

POST /api/v1/auth/signup — create org + owner user in one transaction
POST /api/v1/auth/token  — exchange credentials for JWT
POST /api/v1/auth/verify — verify token (used by frontend)
POST /api/v1/auth/invite — company_admin invites a team member
GET  /api/v1/auth/me     — current user record from DB
"""
from fastapi import APIRouter, HTTPException, status, Depends
from pydantic import BaseModel, EmailStr
import sqlalchemy as sa
from app.core.auth import (
    verify_password, create_access_token,
    hash_password, Token, TokenData,
)
from app.core.dependencies import get_current_user, get_db
from app.config import settings

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


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


# ── Endpoints ──────────────────────────────────────────────────────────────────

@router.post("/signup", response_model=Token, status_code=status.HTTP_201_CREATED)
async def signup(req: SignupRequest, db=Depends(get_db)):
    """
    Create a new organisation and its first owner user in one transaction.
    Returns a JWT for the new owner.
    """
    with db.begin():
        # Check email not already used anywhere (platform-wide uniqueness is optional;
        # here we just prevent duplicate (email, org) pairs — schema enforces UNIQUE)
        existing = db.execute(
            sa.text("SELECT 1 FROM users WHERE email = :email LIMIT 1"),
            {"email": req.email},
        ).fetchone()
        # Allow same email in different orgs, but warn if already has an account
        # (UX: show "already have an account?" on frontend — not blocked here)

        # Create org
        org_row = db.execute(
            sa.text("""
                INSERT INTO organisations (org_name, industry, subscription_tier, is_active)
                VALUES (:name, :industry, 'trial', TRUE)
                RETURNING org_id::text
            """),
            {"name": req.org_name, "industry": req.industry},
        ).fetchone()
        org_id = org_row[0]

        # Create owner user
        db.execute(
            sa.text("""
                INSERT INTO users (org_id, email, hashed_pw, role, is_active)
                VALUES (CAST(:org_id AS uuid), :email, :hashed_pw, 'company_admin', TRUE)
            """),
            {
                "org_id":    org_id,
                "email":     req.email,
                "hashed_pw": hash_password(req.password),
            },
        )

        # Seed rfp_evaluation module as enabled for the new org
        db.execute(
            sa.text("""
                INSERT INTO tenant_modules (org_id, module_key, enabled, activated_at)
                VALUES (CAST(:org_id AS uuid), 'rfp_evaluation', TRUE, now())
                ON CONFLICT DO NOTHING
            """),
            {"org_id": org_id},
        )

        # Seed billing record
        db.execute(
            sa.text("""
                INSERT INTO tenant_billing (org_id, plan, modules_active)
                VALUES (CAST(:org_id AS uuid), 'trial', ARRAY['rfp_evaluation'])
                ON CONFLICT DO NOTHING
            """),
            {"org_id": org_id},
        )

    return create_access_token(
        email=req.email,
        org_id=org_id,
        role="company_admin",
        dept_id=None,
    )


@router.post("/token", response_model=Token)
async def login(req: LoginRequest, db=Depends(get_db)):
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

    return create_access_token(
        email=user["email"],
        org_id=user["org_id"],
        role=user["role"],
        dept_id=user["dept_id"],
    )


def _ensure_dev_user(db) -> None:
    """Idempotently creates the dev seed user + org if absent."""
    org_id = settings.dev_org_id
    with db.begin():
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
                ON CONFLICT (email, org_id) DO NOTHING
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
    db=Depends(get_db),
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
    db=Depends(get_db),
):
    """
    company_admin or department_admin invites a new team member to their org.
    The invited user must set their password on first login (future: email flow).
    For now, a temporary password is returned in the response.
    """
    if current_user.role not in ("platform_admin", "company_admin", "department_admin"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient role")

    # department_admin can only invite department_user
    if current_user.role == "department_admin" and req.role not in ("department_user",):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Cannot assign that role")

    temp_password = f"Change{hash_password(req.email)[:8]}!"
    try:
        with db.begin():
            db.execute(
                sa.text("""
                    INSERT INTO users (org_id, email, hashed_pw, role, dept_id, is_active)
                    VALUES (
                        CAST(:org_id AS uuid), :email, :hashed_pw, :role,
                        CAST(:dept_id AS uuid), TRUE
                    )
                """),
                {
                    "org_id":    current_user.org_id,
                    "email":     req.email,
                    "hashed_pw": hash_password(temp_password),
                    "role":      req.role,
                    "dept_id":   req.dept_id,
                },
            )
    except Exception as exc:
        if "unique" in str(exc).lower():
            raise HTTPException(status_code=409, detail="A user with that email already exists")
        raise

    return {
        "message":        f"User {req.email} invited",
        "temp_password":  temp_password,
        "note":           "Provide this to the user — they should change it immediately",
    }
