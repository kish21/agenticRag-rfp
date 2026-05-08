"""
Tenant management endpoints.

GET  /api/v1/tenant/profile              — org info + plan
PUT  /api/v1/tenant/profile              — update org name
GET  /api/v1/tenant/users                — list users in org (company_admin+)
PUT  /api/v1/tenant/users/{user_id}/role — change a user's role
DELETE /api/v1/tenant/users/{user_id}    — deactivate user
"""
from fastapi import APIRouter, HTTPException, status, Depends
from pydantic import BaseModel
import sqlalchemy as sa
from app.core.dependencies import get_current_user, get_db
from app.core.auth import TokenData

router = APIRouter(prefix="/api/v1/tenant", tags=["tenant"])

ADMIN_ROLES = {"platform_admin", "company_admin"}


class ProfileUpdate(BaseModel):
    org_name:  str | None = None
    industry:  str | None = None


class RoleUpdate(BaseModel):
    role: str


# ── Profile ────────────────────────────────────────────────────────────────────

@router.get("/profile")
async def get_profile(
    current_user: TokenData = Depends(get_current_user),
    db=Depends(get_db),
):
    row = db.execute(
        sa.text("""
            SELECT o.org_id::text, o.org_name, o.industry, o.subscription_tier,
                   b.plan, b.modules_active, b.next_billing
            FROM organisations o
            LEFT JOIN tenant_billing b ON b.org_id = o.org_id
            WHERE o.org_id = CAST(:org_id AS uuid)
        """),
        {"org_id": current_user.org_id},
    ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Organisation not found")

    keys = ["org_id","org_name","industry","subscription_tier","plan","modules_active","next_billing"]
    return dict(zip(keys, row))


@router.put("/profile")
async def update_profile(
    req: ProfileUpdate,
    current_user: TokenData = Depends(get_current_user),
    db=Depends(get_db),
):
    if current_user.role not in ADMIN_ROLES:
        raise HTTPException(status_code=403, detail="Insufficient role")

    updates, params = [], {"org_id": current_user.org_id}
    if req.org_name is not None:
        updates.append("org_name = :org_name")
        params["org_name"] = req.org_name
    if req.industry is not None:
        updates.append("industry = :industry")
        params["industry"] = req.industry
    if not updates:
        return {"message": "No changes"}

    with db.begin():
        db.execute(
            sa.text(f"UPDATE organisations SET {', '.join(updates)} WHERE org_id = CAST(:org_id AS uuid)"),
            params,
        )
    return {"message": "Profile updated"}


# ── Users ──────────────────────────────────────────────────────────────────────

@router.get("/users")
async def list_users(
    current_user: TokenData = Depends(get_current_user),
    db=Depends(get_db),
):
    if current_user.role not in ADMIN_ROLES | {"department_admin"}:
        raise HTTPException(status_code=403, detail="Insufficient role")

    rows = db.execute(
        sa.text("""
            SELECT user_id::text, email, role, dept_id::text, is_active, created_at
            FROM users
            WHERE org_id = CAST(:org_id AS uuid)
            ORDER BY created_at
        """),
        {"org_id": current_user.org_id},
    ).fetchall()

    keys = ["user_id","email","role","dept_id","is_active","created_at"]
    return [dict(zip(keys, r)) for r in rows]


@router.put("/users/{user_id}/role")
async def update_role(
    user_id: str,
    req: RoleUpdate,
    current_user: TokenData = Depends(get_current_user),
    db=Depends(get_db),
):
    if current_user.role not in ADMIN_ROLES:
        raise HTTPException(status_code=403, detail="Insufficient role")

    valid_roles = {"platform_admin","company_admin","department_admin","department_user"}
    if req.role not in valid_roles:
        raise HTTPException(status_code=422, detail=f"Invalid role. Must be one of {valid_roles}")

    with db.begin():
        result = db.execute(
            sa.text("""
                UPDATE users SET role = :role
                WHERE user_id = CAST(:user_id AS uuid)
                  AND org_id  = CAST(:org_id AS uuid)
            """),
            {"role": req.role, "user_id": user_id, "org_id": current_user.org_id},
        )
    if result.rowcount == 0:
        raise HTTPException(status_code=404, detail="User not found")
    return {"message": "Role updated"}


@router.delete("/users/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def deactivate_user(
    user_id: str,
    current_user: TokenData = Depends(get_current_user),
    db=Depends(get_db),
):
    if current_user.role not in ADMIN_ROLES:
        raise HTTPException(status_code=403, detail="Insufficient role")

    with db.begin():
        result = db.execute(
            sa.text("""
                UPDATE users SET is_active = FALSE
                WHERE user_id = CAST(:user_id AS uuid)
                  AND org_id  = CAST(:org_id AS uuid)
            """),
            {"user_id": user_id, "org_id": current_user.org_id},
        )
    if result.rowcount == 0:
        raise HTTPException(status_code=404, detail="User not found")
