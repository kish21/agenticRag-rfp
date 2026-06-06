"""
Role-based access control helpers for evaluation runs.

Access model (Phase 9 — extended from the original creator-only model):
  platform_admin    → all runs in org
  company_admin     → all runs in org
  department_admin  → all runs in org (they manage criteria + approvals)
  department_user   → runs they match in runs_visible_to() SQL function:
                        - runs they created (created_by_email match), OR
                        - runs in any department they belong to
                          (user_departments table), OR
                        - runs they were explicitly invited to
                          (rfp_collaborators table), OR
                        - runs they are an assigned approver on
                          (approval_assignments table)

Override actions (confirm / override endpoint) require department_admin or above.

The detailed access matrix is implemented in `app/domain/visibility.py` and the
canonical SQL function `runs_visible_to()`. This module is a thin wrapper that
preserves the existing API used by the rest of the codebase.
"""
import json
from fastapi import HTTPException
from app.auth.jwt import TokenData

_WIDE_ROLES = {"platform_admin", "company_admin", "department_admin"}


def can_view_run(user: TokenData, run: dict) -> bool:
    """Returns True iff the user is permitted to view the given run.

    Wide-role users see everything in their org (existing behaviour preserved).
    For department_user, delegates to `app/domain/visibility.py:can_view_run`
    which consults the user_departments / rfp_collaborators / approval_assignments
    tables in addition to the legacy `created_by_email` ownership check.
    """
    if user.role in _WIDE_ROLES:
        return True
    # Legacy fast-path: own runs always visible. Avoids a DB roundtrip in the
    # common case where a user is loading a run they created.
    if run.get("created_by_email") == user.email:
        return True
    # Phase 9: delegate to visibility function for collaborators / dept members /
    # approvers. Import lazily to avoid a circular import at module load.
    from app.domain.visibility import can_view_run as _phase9_can_view
    run_id = run.get("run_id")
    if not run_id:
        return False
    return _phase9_can_view(user, str(run_id))


def require_run_access(user: TokenData, run: dict) -> None:
    if not can_view_run(user, run):
        raise HTTPException(status_code=403, detail="You do not have access to this evaluation run")


def require_audit_read(user: TokenData) -> None:
    """Gate the org-wide audit-trail endpoints (#55).

    Allowed roles are config-driven via `product.yaml rbac.audit_read_roles`
    (default: auditor, company_admin, platform_admin) so product can widen or
    narrow the compliance-read surface without an engineering change. The
    `auditor` role is read-only — it reaches the audit trail through here, never
    through the per-run endpoints (default-deny blocks it from run content)."""
    from app.config import settings
    allowed = set(settings.product.rbac.audit_read_roles)
    if user.role not in allowed:
        raise HTTPException(
            status_code=403,
            detail="Reading the audit trail requires an audit-read role",
        )


def require_write_role(user: TokenData) -> None:
    """Gate run-launching / write actions (start, confirm, re-evaluate, rerun).

    Config-driven via `product.yaml rfp_defaults.write_roles` — the operational
    roles permitted to create or mutate runs. Read-only roles (e.g. `auditor`,
    or any future compliance role) are absent from that set and so are blocked
    here, independently of whether they happen to have run *visibility*. This
    keeps the 'a read-only role cannot launch evaluations' invariant enforced at
    one place rather than re-derived per endpoint."""
    from app.config import settings
    if user.role not in set(settings.product.rfp_defaults.write_roles):
        raise HTTPException(status_code=403, detail="Your role cannot perform this action")


def require_admin_role(user: TokenData) -> None:
    if user.role not in _WIDE_ROLES:
        raise HTTPException(
            status_code=403,
            detail="Override and approval actions require department_admin role or above",
        )


def log_access(run_id: str, org_id: str, accessed_by: str, action: str) -> None:
    """Append an access event to access_audit_log. Fire-and-forget — never raises."""
    try:
        import sqlalchemy as sa
        from app.db.fact_store import get_engine
        engine = get_engine()
        with engine.begin() as conn:
            conn.execute(
                sa.text("""
                    INSERT INTO access_audit_log (org_id, run_id, accessed_by, action)
                    VALUES (CAST(:org_id AS uuid), CAST(:run_id AS uuid), :accessed_by, :action)
                """),
                {"org_id": org_id, "run_id": run_id, "accessed_by": accessed_by, "action": action},
            )
    except Exception:
        pass
