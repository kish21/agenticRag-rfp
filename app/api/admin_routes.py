from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.domain.agent_registry import register_agent, get_agent_config, list_agents
from app.auth.dependencies import get_current_user
from app.auth.jwt import require_role, TokenData
from app.api.openapi_responses import (
    responses, UNAUTHORIZED, FORBIDDEN, NOT_FOUND, CONFLICT, BAD_REQUEST,
)

router = APIRouter(prefix="/api/v1/admin", tags=["admin"])


class RegisterAgentRequest(BaseModel):
    config: dict


class RegisterAgentResponse(BaseModel):
    agent_id: str
    message: str


@router.post(
    "/agents",
    response_model=RegisterAgentResponse,
    summary="Register a new agent config",
    responses=responses(UNAUTHORIZED, FORBIDDEN),
)
async def register_new_agent(
    body: RegisterAgentRequest,
    user: TokenData = Depends(get_current_user),
    _: None = Depends(require_role("platform_admin", "company_admin")),
):
    """Register a new agent config for the caller's org. One API call — zero code changes."""
    try:
        agent_id = register_agent(org_id=user.org_id, config=body.config)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    return RegisterAgentResponse(agent_id=agent_id, message="Agent registered successfully")


@router.get(
    "/agents",
    summary="List agents for the caller's org",
    responses=responses(UNAUTHORIZED, FORBIDDEN),
)
async def list_org_agents(
    user: TokenData = Depends(get_current_user),
    _: None = Depends(require_role("platform_admin", "company_admin", "department_admin")),
):
    """List all active agents for the caller's org."""
    return {"agents": list_agents(org_id=user.org_id)}


@router.get(
    "/agents/{agent_id}",
    summary="Get an agent's config",
    responses=responses(UNAUTHORIZED, NOT_FOUND),
)
async def get_agent(
    agent_id: str,
    user: TokenData = Depends(get_current_user),
):
    """Retrieve the config for a specific agent."""
    config = get_agent_config(agent_id=agent_id)
    if config is None:
        raise HTTPException(status_code=404, detail="Agent not found")
    return {"agent_id": agent_id, "config": config}


# ═══════════════════════════════════════════════════════════════════════════
# Phase 9 — Multi-user RFP visibility administration
# ═══════════════════════════════════════════════════════════════════════════
# Endpoints for admins to manage matrix department membership and approval
# assignments. These NEVER run autonomously; access lists are decided by
# humans and inherited by runs (see Phase 9 invariant).

from app.domain.visibility import (
    add_user_to_department as _add_user_to_dept,
    assign_approver as _assign_approver,
)


class UserDeptAssignment(BaseModel):
    user_id: str
    department_id: str
    role_in_dept: str = "member"   # 'member' | 'lead' | 'observer'


@router.post(
    "/user-departments",
    summary="Add a user to a department",
    responses=responses(UNAUTHORIZED, FORBIDDEN, BAD_REQUEST),
)
async def add_user_department(
    body: UserDeptAssignment,
    user: TokenData = Depends(get_current_user),
    _: None = Depends(require_role("platform_admin", "company_admin", "department_admin")),
):
    """Grant a user membership in a department. Idempotent — re-adding with a
    different role updates the role_in_dept."""
    try:
        _add_user_to_dept(body.user_id, body.department_id, body.role_in_dept)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"status": "ok", "user_id": body.user_id, "department_id": body.department_id}


class ApprovalAssignmentRequest(BaseModel):
    run_id: str
    approver_user_id: str
    approver_role: str  # 'cfo' | 'cto' | 'cpo' | 'legal' | etc.


@router.post(
    "/approval-assignments",
    summary="Assign an approver to a run",
    responses=responses(UNAUTHORIZED, FORBIDDEN, BAD_REQUEST),
)
async def add_approval_assignment(
    body: ApprovalAssignmentRequest,
    user: TokenData = Depends(get_current_user),
    _: None = Depends(require_role("platform_admin", "company_admin", "department_admin")),
):
    """Assign an approver to an evaluation_run. Re-assigning the same user
    resets status to 'pending'."""
    try:
        _assign_approver(body.run_id, body.approver_user_id, body.approver_role)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"status": "ok", "run_id": body.run_id, "approver_user_id": body.approver_user_id}


# ── Phase 5 PR-E: attribution queue + late-addendum acceptance ───────
# These endpoints let an admin resolve ingestion_jobs that landed in a
# terminal state requiring human review. RBAC: any procurement admin.

from typing import Optional  # noqa: E402
import sqlalchemy as sa  # noqa: E402

from app.api.rfp_routes import _ensure_safe_id, provision_drop_folder  # noqa: E402
from app.config import settings  # noqa: E402
from app.db.fact_store import (  # noqa: E402
    get_engine,
    get_rfp_lifecycle,
    invite_vendor,
    is_invited_vendor,
)


def _require_admin_attribution_role(
    user: TokenData = Depends(get_current_user),
) -> TokenData:
    if user.role not in set(settings.product.rfp_defaults.write_roles):
        raise HTTPException(status_code=403, detail="Insufficient role")
    return user


class AssignVendorRequest(BaseModel):
    vendor_id: str
    invite_if_missing: bool = True


@router.get(
    "/attribution-queue",
    summary="List ingestion jobs needing attribution",
    responses=responses(UNAUTHORIZED, FORBIDDEN),
)
async def list_attribution_queue(
    user: TokenData = Depends(_require_admin_attribution_role),
) -> dict:
    """E3 — Returns all ingestion_jobs with status='needs_attribution' or
    'rejected_late' scoped to the caller's org."""
    engine = get_engine()
    with engine.connect() as conn:
        rows = conn.execute(
            sa.text(
                """
                SELECT job_id::text AS job_id, rfp_id, vendor_id, filename,
                       source_uri, status, received_at, attribution_confidence,
                       error
                FROM ingestion_jobs
                WHERE org_id = :o
                  AND status IN ('needs_attribution', 'rejected_late')
                ORDER BY received_at DESC
                """
            ),
            {"o": user.org_id},
        ).fetchall()
    return {"jobs": [dict(r._mapping) for r in rows]}


@router.post(
    "/attribution-queue/{job_id}/assign",
    summary="Assign a vendor to an attribution job",
    responses=responses(UNAUTHORIZED, FORBIDDEN, NOT_FOUND, CONFLICT),
)
async def assign_attribution(
    job_id: str,
    body: AssignVendorRequest,
    user: TokenData = Depends(_require_admin_attribution_role),
) -> dict:
    """E4 — Assign a needs_attribution job to a vendor.

    - If the vendor isn't on the RFP's invited_vendors and invite_if_missing
      is True, the vendor is auto-invited (drop folder provisioned).
    - Job flips to 'received' if RFP is still open, otherwise to 'queued'
      (so the next deadline_processor tick will pick it up). This treats
      admin-resolved attribution as an accepted late addendum when the
      window is already closed.
    """
    _ensure_safe_id(body.vendor_id, "vendor_id")
    engine = get_engine()
    with engine.connect() as conn:
        job = conn.execute(
            sa.text(
                """
                SELECT rfp_id, status, org_id::text AS org_id
                FROM ingestion_jobs WHERE job_id = :j
                """
            ),
            {"j": job_id},
        ).fetchone()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.org_id != user.org_id:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.status != "needs_attribution":
        raise HTTPException(
            status_code=409,
            detail=f"Job is {job.status}; only needs_attribution can be assigned.",
        )

    rfp = get_rfp_lifecycle(rfp_id=job.rfp_id)
    if rfp is None:
        raise HTTPException(status_code=409, detail="RFP no longer exists")

    if not is_invited_vendor(rfp_id=job.rfp_id, vendor_id=body.vendor_id):
        if not body.invite_if_missing:
            raise HTTPException(
                status_code=409,
                detail=f"vendor_id '{body.vendor_id}' is not invited.",
            )
        invite_vendor(
            rfp_id=job.rfp_id, vendor_id=body.vendor_id, invited_by=user.email,
        )
        provision_drop_folder(job.rfp_id, body.vendor_id)

    new_status = "received" if rfp["submission_status"] == "open" else "queued"
    with engine.begin() as conn:
        conn.execute(
            sa.text(
                """
                UPDATE ingestion_jobs
                SET vendor_id = :v, status = :s, error = NULL
                WHERE job_id = :j AND status = 'needs_attribution'
                """
            ),
            {"v": body.vendor_id, "s": new_status, "j": job_id},
        )
    return {"job_id": job_id, "vendor_id": body.vendor_id, "status": new_status}


@router.post(
    "/late-addendum/{job_id}/accept",
    summary="Accept a late vendor addendum",
    responses=responses(UNAUTHORIZED, FORBIDDEN, CONFLICT),
)
async def accept_late_addendum(
    job_id: str,
    user: TokenData = Depends(_require_admin_attribution_role),
) -> dict:
    """E5 — Promote a rejected_late job to queued so the next
    deadline_processor tick re-runs ingestion for it."""
    engine = get_engine()
    with engine.begin() as conn:
        row = conn.execute(
            sa.text(
                """
                UPDATE ingestion_jobs
                SET status = 'queued', error = NULL
                WHERE job_id = :j AND status = 'rejected_late' AND org_id = :o
                RETURNING job_id::text AS job_id, rfp_id, vendor_id
                """
            ),
            {"j": job_id, "o": user.org_id},
        ).fetchone()
    if not row:
        raise HTTPException(
            status_code=409,
            detail="Job not found, wrong org, or not in rejected_late state.",
        )
    return {"job_id": row.job_id, "rfp_id": row.rfp_id, "vendor_id": row.vendor_id, "status": "queued"}


# ── Phase 3 PR-B: LLM cache admin invalidation (3.15) ────────────────


@router.delete(
    "/llm-cache",
    summary="Purge cached LLM responses",
    responses=responses(UNAUTHORIZED, FORBIDDEN, BAD_REQUEST),
)
async def purge_llm_cache(
    model: Optional[str] = None,
    before: Optional[str] = None,    # ISO timestamp string
    cache_key: Optional[str] = None,
    user: TokenData = Depends(_require_admin_attribution_role),
) -> dict:
    """
    3.15 — Bulk-delete cached LLM responses.

    Filters (any combination, all AND'd):
      - cache_key: delete exactly one entry by key
      - model:     delete all entries for that provider model
      - before:    delete entries created strictly before this ISO timestamp

    At least one filter is required (no bare "delete everything" call).
    Returns the number of rows deleted. Audit-logged via app.infra.audit.
    """
    from datetime import datetime

    from app.infra.audit import audit

    if cache_key is None and model is None and before is None:
        raise HTTPException(
            status_code=400,
            detail="At least one of cache_key, model, before is required.",
        )

    where_parts: list[str] = []
    params: dict = {}
    if cache_key is not None:
        where_parts.append("cache_key = :k")
        params["k"] = cache_key
    if model is not None:
        where_parts.append("model = :m")
        params["m"] = model
    if before is not None:
        try:
            cutoff = datetime.fromisoformat(before.replace("Z", "+00:00"))
        except ValueError as exc:
            raise HTTPException(
                status_code=400, detail=f"Invalid 'before' timestamp: {exc}",
            ) from exc
        where_parts.append("created_at < :before")
        params["before"] = cutoff

    sql = "DELETE FROM llm_response_cache WHERE " + " AND ".join(where_parts)
    engine = get_engine()
    with engine.begin() as conn:
        result = conn.execute(sa.text(sql), params)
        deleted = result.rowcount

    audit(
        org_id=user.org_id, run_id=None, event_type="admin.llm_cache_purge",
        actor=user.email,
        detail={
            "deleted": deleted, "filters": {
                "cache_key": cache_key, "model": model, "before": before,
            },
        },
    )
    return {"deleted": deleted, "filters": {
        "cache_key": cache_key, "model": model, "before": before,
    }}
