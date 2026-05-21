"""
Role-based access control helpers for evaluation runs.

Access model:
  platform_admin    → all runs in org
  company_admin     → all runs in org
  department_admin  → all runs in org (they manage criteria + approvals)
  department_user   → only runs they created (created_by_email == user.email)

Override actions (confirm / override endpoint) require department_admin or above.
"""
import json
from fastapi import HTTPException
from app.core.auth import TokenData

_WIDE_ROLES = {"platform_admin", "company_admin", "department_admin"}


def can_view_run(user: TokenData, run: dict) -> bool:
    if user.role in _WIDE_ROLES:
        return True
    return run.get("created_by_email") == user.email


def require_run_access(user: TokenData, run: dict) -> None:
    if not can_view_run(user, run):
        raise HTTPException(status_code=403, detail="You do not have access to this evaluation run")


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
