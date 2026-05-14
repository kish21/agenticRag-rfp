from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Any

from app.core.org_settings import get_org_settings, upsert_org_settings, OrgSettings
from app.core.dependencies import get_current_user
from app.core.auth import require_role, TokenData

router = APIRouter(prefix="/api/v1/org", tags=["org-settings"])


class UpdateOrgSettingsRequest(BaseModel):
    fields: dict[str, Any]


@router.get("/settings", response_model=OrgSettings)
async def read_org_settings(
    user: TokenData = Depends(get_current_user),
):
    """Return the current org settings for the caller's org."""
    return get_org_settings(user.org_id)


@router.patch("/settings", response_model=OrgSettings)
async def update_org_settings(
    body: UpdateOrgSettingsRequest,
    user: TokenData = Depends(get_current_user),
    _: None = Depends(require_role("platform_admin", "company_admin")),
):
    """Update one or more org settings fields. Preset fields are applied atomically."""
    try:
        return upsert_org_settings(user.org_id, updated_by=user.sub, **body.fields)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/settings/reset", response_model=OrgSettings)
async def reset_org_settings(
    user: TokenData = Depends(get_current_user),
    _: None = Depends(require_role("platform_admin", "company_admin")),
):
    """Reset org to the default preset (from product.yaml new_org_defaults)."""
    from app.core.org_settings import invalidate_org_settings
    import sqlalchemy as sa
    from app.db.fact_store import get_engine

    eng = get_engine()
    with eng.begin() as conn:
        conn.execute(sa.text("SET LOCAL app.org_id = :o"), {"o": user.org_id})
        conn.execute(
            sa.text("DELETE FROM org_settings WHERE org_id = :o"),
            {"o": user.org_id},
        )
    invalidate_org_settings(user.org_id)
    return get_org_settings(user.org_id)
