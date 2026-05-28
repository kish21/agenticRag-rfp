"""
Phase 9 — Multi-user RFP visibility.

Single source of truth for "which runs can this user see?". All list endpoints
and individual run-access checks should go through this module rather than
re-implementing the WHERE clause.

Authorisation model (default-deny):
  A user sees a run IFF any of the following predicates is true (OR'd):
    1. Wide org-level role: platform_admin OR company_admin.
    2. The user created the run (created_by_email match).
    3. The user belongs to the run's department (user_departments join).
    4. The user was explicitly invited (rfp_collaborators join).
    5. The user is an assigned approver (approval_assignments join).

If none match, the user sees nothing — even within the same org.

This logic mirrors the SQL function `runs_visible_to()` in schema.sql; that
function is the canonical implementation, this Python module is the wrapper.
"""
from typing import Literal, Optional

import sqlalchemy as sa

from app.auth.jwt import TokenData
from app.db.fact_store import get_engine


Scope = Literal["mine", "department", "approvals", "shared", "all"]
_WIDE_ROLES = {"platform_admin", "company_admin"}


def _lookup_user_id(email: str, org_id: str) -> Optional[str]:
    """Look up users.user_id by (email, org_id). Returns None if no match —
    the visibility query will then only match predicates 1, 2 (not the ones
    that require a user_id like dept membership / collaborators / approvers)."""
    engine = get_engine()
    with engine.connect() as conn:
        row = conn.execute(
            sa.text("""
                SELECT user_id::text FROM users
                WHERE email = :email AND org_id = CAST(:org_id AS uuid)
                LIMIT 1
            """),
            {"email": email, "org_id": org_id},
        ).fetchone()
    return row[0] if row else None


def visible_runs(user: TokenData, scope: Scope = "mine", limit: int = 200) -> list[dict]:
    """Return the list of evaluation_runs rows the user can see for the given scope.

    Scopes:
      - mine        : runs the user personally created
      - department  : runs in any department the user belongs to
      - approvals   : runs where the user has a pending approval_assignment
      - shared      : runs the user was explicitly invited to
      - all         : every run the user is permitted to see (wide-role users
                      get the entire org; everyone else gets the union of the
                      four scopes above)

    Permission to use scope='all' is checked at the API layer; this function
    simply returns the full visible set when called with scope='all'.
    """
    if scope == "all" and user.role not in _WIDE_ROLES:
        # Defensive: don't return all-org data to non-wide-role users.
        # The route layer should already have rejected this; double-deny here.
        return []

    user_id = _lookup_user_id(user.email, user.org_id)

    # Base query — calls the canonical SQL function. We pass an empty UUID for
    # user_id when the user record can't be resolved; predicates depending on
    # user_id will then never match (correct default-deny behaviour).
    # NOTE: run_id stays as UUID inside the CTE so EXISTS subqueries against
    # rfp_collaborators / approval_assignments (which key on UUID) type-match.
    # We cast to text only in the final SELECT projection below.
    base = """
        SELECT run_id, org_id, rfp_id, rfp_title, department,
               status, created_at, completed_at, created_by_email,
               creator_dept_id
        FROM runs_visible_to(
            CAST(:user_id AS uuid),
            :user_email,
            :user_role,
            CAST(:org_id AS uuid)
        )
    """
    params = {
        "user_id":    user_id or "00000000-0000-0000-0000-000000000000",
        "user_email": user.email,
        "user_role":  user.role,
        "org_id":     user.org_id,
    }

    # Apply scope filter as an additional WHERE on top of the visibility set.
    # CTE renamed to `visible` to avoid shadowing the `runs_visible_to()` SQL function
    # (Postgres can't tell CTE-name vs function-name apart in EXISTS subqueries).
    if scope == "mine":
        scope_filter = " WHERE created_by_email = :user_email"
    elif scope == "department":
        scope_filter = """
            WHERE creator_dept_id IN (
                SELECT department_id FROM user_departments WHERE user_id = CAST(:user_id AS uuid)
            )
        """
    elif scope == "approvals":
        scope_filter = """
            WHERE EXISTS (
                SELECT 1 FROM approval_assignments
                WHERE run_id = visible.run_id
                  AND approver_user_id = CAST(:user_id AS uuid)
                  AND status = 'pending'
            )
        """
    elif scope == "shared":
        scope_filter = """
            WHERE EXISTS (
                SELECT 1 FROM rfp_collaborators
                WHERE run_id = visible.run_id
                  AND user_id = CAST(:user_id AS uuid)
            )
        """
    else:  # 'all'
        scope_filter = ""

    sql = f"WITH visible AS ({base}) SELECT * FROM visible {scope_filter} ORDER BY created_at DESC LIMIT :limit"
    params["limit"] = limit

    engine = get_engine()
    with engine.connect() as conn:
        rows = conn.execute(sa.text(sql), params).fetchall()
    return [dict(r._mapping) for r in rows]


def can_view_run(user: TokenData, run_id: str) -> bool:
    """Single-run access check used by GET /runs/{id} and related endpoints.

    Same authorisation model as visible_runs(); returns True iff the user is
    permitted to see this particular run. Calls runs_visible_to() filtered
    to the single run_id for efficiency."""
    user_id = _lookup_user_id(user.email, user.org_id)
    engine = get_engine()
    with engine.connect() as conn:
        row = conn.execute(
            sa.text("""
                SELECT 1 FROM runs_visible_to(
                    CAST(:user_id AS uuid),
                    :user_email,
                    :user_role,
                    CAST(:org_id AS uuid)
                )
                WHERE run_id = CAST(:run_id AS uuid)
                LIMIT 1
            """),
            {
                "user_id":    user_id or "00000000-0000-0000-0000-000000000000",
                "user_email": user.email,
                "user_role":  user.role,
                "org_id":     user.org_id,
                "run_id":     run_id,
            },
        ).fetchone()
    return row is not None


# ── Collaborator + approval-assignment + dept-membership mutators ─────────────

def add_collaborator(run_id: str, user_id: str, role: str, added_by_user_id: str) -> None:
    """Invite a user to collaborate on an evaluation_run. Idempotent via ON
    CONFLICT — re-inviting the same user is a no-op, not an error."""
    if role not in ("viewer", "reviewer", "editor"):
        raise ValueError(f"Invalid collaborator role: {role}")
    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(
            sa.text("""
                INSERT INTO rfp_collaborators (run_id, user_id, role, added_by)
                VALUES (CAST(:run_id AS uuid), CAST(:user_id AS uuid), :role,
                        CAST(:added_by AS uuid))
                ON CONFLICT (run_id, user_id) DO UPDATE SET role = EXCLUDED.role
            """),
            {"run_id": run_id, "user_id": user_id, "role": role, "added_by": added_by_user_id},
        )


def remove_collaborator(run_id: str, user_id: str) -> None:
    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(
            sa.text("""
                DELETE FROM rfp_collaborators
                WHERE run_id = CAST(:run_id AS uuid) AND user_id = CAST(:user_id AS uuid)
            """),
            {"run_id": run_id, "user_id": user_id},
        )


def add_user_to_department(user_id: str, department_id: str, role_in_dept: str = "member") -> None:
    if role_in_dept not in ("member", "lead", "observer"):
        raise ValueError(f"Invalid role_in_dept: {role_in_dept}")
    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(
            sa.text("""
                INSERT INTO user_departments (user_id, department_id, role_in_dept)
                VALUES (CAST(:user_id AS uuid), :department_id, :role_in_dept)
                ON CONFLICT (user_id, department_id) DO UPDATE
                  SET role_in_dept = EXCLUDED.role_in_dept
            """),
            {"user_id": user_id, "department_id": department_id, "role_in_dept": role_in_dept},
        )


def assign_approver(run_id: str, approver_user_id: str, approver_role: str) -> None:
    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(
            sa.text("""
                INSERT INTO approval_assignments (run_id, approver_user_id, approver_role)
                VALUES (CAST(:run_id AS uuid), CAST(:approver_id AS uuid), :role)
                ON CONFLICT (run_id, approver_user_id) DO UPDATE
                  SET approver_role = EXCLUDED.approver_role,
                      status = 'pending',
                      resolved_at = NULL
            """),
            {"run_id": run_id, "approver_id": approver_user_id, "role": approver_role},
        )
