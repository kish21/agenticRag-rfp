"""
RFP-creation API for Phase 5 (background ingestion workflow).

Endpoints
---------
POST /api/v1/rfps                          create RFP shell
GET  /api/v1/rfps/{rfp_id}                 RFP rollup (status, vendors, jobs)
POST /api/v1/rfps/{rfp_id}/vendors         invite a vendor (provisions drop folder)
POST /api/v1/rfps/{rfp_id}/deadline        set or extend deadline (only while open)

Phase 9 invariant: NONE of these endpoints write to user_departments,
rfp_collaborators, or approval_assignments. Access is decided at the
existing org/department layer; vendor invites are a separate concept
that does NOT grant any human visibility — they only authorise file
uploads into a drop folder.
"""
from __future__ import annotations

import re
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

import sqlalchemy as sa
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from app.auth.dependencies import get_current_user
from app.auth.jwt import TokenData
from app.api.openapi_responses import (
    responses, UNAUTHORIZED, FORBIDDEN, NOT_FOUND, CONFLICT, BAD_REQUEST,
)
from app.config import settings
from app.db.fact_store import (
    create_rfp,
    get_engine,
    get_rfp_rollup,
    invite_vendor,
    set_deadline,
)


router = APIRouter(prefix="/api/v1/rfps", tags=["rfps"])


def _safe_id_pattern() -> re.Pattern:
    """Compiled regex from platform.ingestion.safe_id_pattern. Re-read each call so
    tests/runtime can mutate settings via dependency overrides without re-importing."""
    return re.compile(settings.platform.ingestion.safe_id_pattern)


def _drops_root() -> Path:
    return Path(settings.platform.ingestion.drops_root)


def _ensure_safe_id(value: str, label: str) -> None:
    if not _safe_id_pattern().fullmatch(value or ""):
        raise HTTPException(
            status_code=400,
            detail=f"Invalid {label}: must match {settings.platform.ingestion.safe_id_pattern}",
        )


def provision_drop_folder(rfp_id: str, vendor_id: str) -> Path:
    """Creates {drops_root}/{rfp_id}/{vendor_id}/ on disk. Idempotent."""
    _ensure_safe_id(rfp_id, "rfp_id")
    _ensure_safe_id(vendor_id, "vendor_id")
    target = _drops_root() / rfp_id / vendor_id
    target.mkdir(parents=True, exist_ok=True)
    return target


# ── Request / response models ────────────────────────────────────────


class CreateRFPRequest(BaseModel):
    title: str = Field(min_length=1, max_length=512)
    department: Optional[str] = None
    submission_deadline: Optional[datetime] = None
    autonomy_mode: Optional[str] = None    # validated by DB CHECK constraint
    rfp_id: Optional[str] = None           # caller-supplied or auto-generated


class CreateRFPResponse(BaseModel):
    rfp_id: str
    submission_deadline: datetime
    submission_status: str
    autonomy_mode: str


class InviteVendorRequest(BaseModel):
    vendor_id: str
    vendor_name: Optional[str] = None


class InviteVendorResponse(BaseModel):
    rfp_id: str
    vendor_id: str
    drop_folder: str


class SetDeadlineRequest(BaseModel):
    submission_deadline: datetime


# ── RBAC helper ──────────────────────────────────────────────────────


def _require_rfp_write_role(user: TokenData = Depends(get_current_user)) -> TokenData:
    """RFP create / invite / deadline endpoints require a procurement-side role.
    Allowed roles are sourced from product.rfp_defaults.write_roles."""
    if user.role not in set(settings.product.rfp_defaults.write_roles):
        raise HTTPException(status_code=403, detail="Insufficient role for RFP write")
    return user


def _load_rfp_or_404(rfp_id: str, org_id: str) -> dict:
    engine = get_engine()
    with engine.connect() as conn:
        row = conn.execute(
            sa.text(
                """
                SELECT rfp_id, org_id::text AS org_id, submission_status
                FROM rfps WHERE rfp_id = :r
                """
            ),
            {"r": rfp_id},
        ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="RFP not found")
    if row.org_id != org_id:
        # Cross-org access is a 404, not 403, to avoid leaking existence.
        raise HTTPException(status_code=404, detail="RFP not found")
    return {"rfp_id": row.rfp_id, "submission_status": row.submission_status}


# ── Endpoints ────────────────────────────────────────────────────────


@router.post(
    "",
    response_model=CreateRFPResponse,
    status_code=201,
    summary="Create an RFP shell",
    responses=responses(UNAUTHORIZED, FORBIDDEN, BAD_REQUEST),
)
async def create_rfp_endpoint(
    body: CreateRFPRequest,
    user: TokenData = Depends(_require_rfp_write_role),
) -> CreateRFPResponse:
    """Creates an RFP shell. submission_deadline defaults to now + 14 days."""
    rfp_id = body.rfp_id or f"rfp-{uuid.uuid4().hex[:8]}"
    _ensure_safe_id(rfp_id, "rfp_id")
    defaults = settings.product.rfp_defaults
    deadline = body.submission_deadline or (
        datetime.now(timezone.utc) + timedelta(days=defaults.default_deadline_days)
    )
    mode = body.autonomy_mode or defaults.default_autonomy_mode
    if mode not in set(defaults.allowed_autonomy_modes):
        raise HTTPException(
            status_code=400,
            detail=f"autonomy_mode must be one of {defaults.allowed_autonomy_modes}",
        )
    try:
        create_rfp(
            rfp_id=rfp_id,
            org_id=user.org_id,
            title=body.title,
            department=body.department,
            created_by_email=user.email,
            submission_deadline=deadline,
            autonomy_mode=mode,
        )
    except sa.exc.IntegrityError as e:
        # Most likely autonomy_mode CHECK constraint, or PK collision
        raise HTTPException(status_code=400, detail=str(e.orig)) from e
    return CreateRFPResponse(
        rfp_id=rfp_id,
        submission_deadline=deadline,
        submission_status="open",
        autonomy_mode=mode,
    )


@router.get(
    "/{rfp_id}",
    summary="Get an RFP rollup",
    responses=responses(UNAUTHORIZED, NOT_FOUND),
)
async def get_rfp_endpoint(
    rfp_id: str,
    user: TokenData = Depends(get_current_user),
) -> dict:
    """Returns RFP rollup. Scoped to org_id; cross-org reads are 404."""
    _load_rfp_or_404(rfp_id, user.org_id)
    rollup = get_rfp_rollup(rfp_id=rfp_id)
    return rollup


@router.post(
    "/{rfp_id}/vendors",
    response_model=InviteVendorResponse,
    status_code=201,
    summary="Invite a vendor to an RFP",
    responses=responses(UNAUTHORIZED, FORBIDDEN, NOT_FOUND, BAD_REQUEST),
)
async def invite_vendor_endpoint(
    rfp_id: str,
    body: InviteVendorRequest,
    user: TokenData = Depends(_require_rfp_write_role),
) -> InviteVendorResponse:
    """Invites a vendor and provisions drops/{rfp_id}/{vendor_id}/."""
    _load_rfp_or_404(rfp_id, user.org_id)
    _ensure_safe_id(body.vendor_id, "vendor_id")
    invite_vendor(
        rfp_id=rfp_id,
        vendor_id=body.vendor_id,
        vendor_name=body.vendor_name,
        invited_by=user.email,
    )
    folder = provision_drop_folder(rfp_id, body.vendor_id)
    return InviteVendorResponse(
        rfp_id=rfp_id,
        vendor_id=body.vendor_id,
        drop_folder=str(folder),
    )


@router.post(
    "/{rfp_id}/deadline",
    status_code=200,
    summary="Set or extend an RFP deadline",
    responses=responses(UNAUTHORIZED, FORBIDDEN, NOT_FOUND, CONFLICT),
)
async def set_deadline_endpoint(
    rfp_id: str,
    body: SetDeadlineRequest,
    user: TokenData = Depends(_require_rfp_write_role),
) -> dict:
    """Sets/extends the submission deadline. 409 if RFP is no longer open."""
    rfp = _load_rfp_or_404(rfp_id, user.org_id)
    if rfp["submission_status"] != "open":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Cannot change deadline: RFP is {rfp['submission_status']}",
        )
    updated = set_deadline(rfp_id=rfp_id, submission_deadline=body.submission_deadline)
    if not updated:
        # Race condition: status flipped between our check and the UPDATE.
        raise HTTPException(status_code=409, detail="RFP locked")
    return {"rfp_id": rfp_id, "submission_deadline": body.submission_deadline}
