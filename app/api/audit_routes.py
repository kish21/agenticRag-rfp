"""Org-wide audit-trail API — read-only compliance surface (#55).

The per-run audit trail (`GET /api/v1/evaluate/{run_id}/audit`) is gated by
`require_run_access`, so a user only sees runs they own / collaborate on. That is
correct for operators but useless for a compliance reviewer, who must inspect the
WHOLE org's trail without being able to open any individual evaluation.

This router serves that need:
  GET /api/v1/audit/access-log   — who accessed which run, and when (access_audit_log)
  GET /api/v1/audit/events       — override / state-change events    (audit_log)

Both are read-only SELECTs, org-scoped (explicit `org_id` filter + Postgres RLS),
and gated by `require_audit_read` (config-driven `product.yaml rbac.audit_read_roles`
— default: auditor, company_admin, platform_admin). No run content is exposed:
only trail metadata (run_id, accessor/actor, action/event_type, timestamp).
"""
import sqlalchemy as sa
from fastapi import APIRouter, Depends, Query

from app.auth.dependencies import get_current_user
from app.auth.jwt import TokenData
from app.auth.rbac import require_audit_read
from app.db.fact_store import get_engine
from app.api.openapi_responses import responses, UNAUTHORIZED, FORBIDDEN

router = APIRouter(prefix="/api/v1/audit", tags=["audit"])

# Page-size guardrail — keep a single compliance query bounded.
_MAX_LIMIT = 500
_DEFAULT_LIMIT = 100


def _scoped_where(org_id: str, limit: int, offset: int, run_id: str | None) -> tuple[str, dict]:
    """Build the org-scoped (+ optional run_id) WHERE clause and bound params
    shared by both audit endpoints. All values are bound parameters — the only
    interpolated text is constant SQL — so the two compliance queries cannot
    drift in their filtering/scoping."""
    where = "org_id = CAST(:oid AS uuid)"
    params: dict = {"oid": org_id, "limit": limit, "offset": offset}
    if run_id:
        where += " AND run_id = CAST(:rid AS uuid)"
        params["rid"] = run_id
    return where, params


@router.get(
    "/access-log",
    summary="Read the org-wide access audit trail (who viewed which run)",
    responses=responses(UNAUTHORIZED, FORBIDDEN),
)
async def get_access_log(
    user: TokenData = Depends(get_current_user),
    limit: int = Query(_DEFAULT_LIMIT, ge=1, le=_MAX_LIMIT),
    offset: int = Query(0, ge=0),
    run_id: str | None = Query(None, description="Optional filter to a single run_id"),
):
    """Return access_audit_log entries for the caller's org, newest first.

    Records every sensitive read (view_setup, view_results, …) logged by
    `app.auth.rbac.log_access`. Read-only; auditor/admin only."""
    require_audit_read(user)
    where, params = _scoped_where(user.org_id, limit, offset, run_id)
    engine = get_engine()
    with engine.connect() as conn:
        rows = conn.execute(
            sa.text(f"""
                SELECT log_id::text, run_id::text, accessed_by, action, created_at
                FROM access_audit_log
                WHERE {where}
                ORDER BY created_at DESC
                LIMIT :limit OFFSET :offset
            """),
            params,
        ).fetchall()
    return {
        "org_id": user.org_id,
        "limit": limit,
        "offset": offset,
        "entries": [
            {
                "log_id":      r[0],
                "run_id":      r[1],
                "accessed_by": r[2],
                "action":      r[3],
                "ts":          r[4].isoformat() if r[4] else "",
            }
            for r in rows
        ],
    }


@router.get(
    "/events",
    summary="Read the org-wide audit event log (overrides, state changes)",
    responses=responses(UNAUTHORIZED, FORBIDDEN),
)
async def get_audit_events(
    user: TokenData = Depends(get_current_user),
    limit: int = Query(_DEFAULT_LIMIT, ge=1, le=_MAX_LIMIT),
    offset: int = Query(0, ge=0),
    run_id: str | None = Query(None, description="Optional filter to a single run_id"),
):
    """Return audit_log events for the caller's org, newest first.

    The append-only record of state changes (overrides, agent actions, decisions)
    written by `app.infra.audit`. Read-only; auditor/admin only."""
    require_audit_read(user)
    where, params = _scoped_where(user.org_id, limit, offset, run_id)
    engine = get_engine()
    with engine.connect() as conn:
        rows = conn.execute(
            sa.text(f"""
                SELECT log_id::text, run_id::text, event_type, actor, agent, detail, created_at
                FROM audit_log
                WHERE {where}
                ORDER BY created_at DESC
                LIMIT :limit OFFSET :offset
            """),
            params,
        ).fetchall()
    return {
        "org_id": user.org_id,
        "limit": limit,
        "offset": offset,
        "events": [
            {
                "log_id":     r[0],
                "run_id":     r[1],
                "event_type": r[2],
                "actor":      r[3],
                "agent":      r[4],
                "detail":     r[5] or {},
                "ts":         r[6].isoformat() if r[6] else "",
            }
            for r in rows
        ],
    }
