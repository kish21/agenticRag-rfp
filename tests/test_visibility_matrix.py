"""
tests/test_visibility_matrix.py
================================
Phase 9 exit-criterion test: verifies the 5-persona visibility matrix using a
live PostgreSQL fixture.

Personas (single org, mixed departments):
  - admin       : platform_admin — sees everything in org
  - anita       : department_user in IT — sees own + IT department runs
  - bob         : department_user in HR — must NOT see IT runs (default-deny)
  - carla       : approver — sees only runs she's assigned to approve
  - dan         : invited reviewer — sees only the RFP he was invited to

Fixture: 6 evaluation_runs total — 3 in IT, 2 in HR, 1 in Finance. Each
persona's expected visible set is asserted exactly via the visibility wrapper
and the runs_visible_to() SQL function.

Requires running Postgres. Cleans up its own fixture data on teardown.

Run:
    python -m pytest tests/test_visibility_matrix.py -v
"""
import os
import sys
import uuid
from pathlib import Path

import pytest
import sqlalchemy as sa

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.auth.jwt import TokenData  # noqa: E402
from app.db.fact_store import get_engine  # noqa: E402
from app.domain.visibility import (  # noqa: E402
    visible_runs,
    can_view_run,
    add_collaborator,
    add_user_to_department,
    assign_approver,
)


# Fixture IDs — deterministic so cleanup is reliable.
_ORG_ID = "00000000-0000-0000-0000-000000000099"

_USERS = {
    "admin": ("admin@meridian-test.local", "platform_admin",  None),
    "anita": ("anita@meridian-test.local", "department_user", "IT"),
    "bob":   ("bob@meridian-test.local",   "department_user", "HR"),
    "carla": ("carla@meridian-test.local", "department_user", "Finance"),
    "dan":   ("dan@meridian-test.local",   "department_user", None),  # security, no home dept
}

# 6 runs: 3 in IT (one created by anita), 2 in HR (created by bob), 1 in Finance
_RUNS = [
    ("rfp-test-it-1",  "IT",      "anita@meridian-test.local"),
    ("rfp-test-it-2",  "IT",      "someone_else_it@meridian-test.local"),
    ("rfp-test-it-3",  "IT",      "another_it@meridian-test.local"),
    ("rfp-test-hr-1",  "HR",      "bob@meridian-test.local"),
    ("rfp-test-hr-2",  "HR",      "other_hr@meridian-test.local"),
    ("rfp-test-fin-1", "Finance", "fin_owner@meridian-test.local"),
]

_RUN_IDS: dict[str, str] = {}      # rfp_id -> run_id (UUID)
_USER_IDS: dict[str, str] = {}     # nickname -> user_id


@pytest.fixture(scope="module", autouse=True)
def _fixture_data():
    """Seed the org + users + runs + memberships. Tear down on exit."""
    engine = get_engine()
    with engine.begin() as conn:
        # Org
        conn.execute(
            sa.text("""
                INSERT INTO organisations (org_id, org_name)
                VALUES (CAST(:oid AS uuid), :name)
                ON CONFLICT (org_id) DO NOTHING
            """),
            {"oid": _ORG_ID, "name": "Meridian Test Org"},
        )

        # Users
        for nick, (email, role, dept) in _USERS.items():
            uid = str(uuid.uuid4())
            _USER_IDS[nick] = uid
            conn.execute(
                sa.text("""
                    INSERT INTO users (user_id, org_id, email, hashed_pw, role)
                    VALUES (CAST(:uid AS uuid), CAST(:oid AS uuid), :email, 'x', :role)
                    ON CONFLICT (email) DO UPDATE SET org_id = EXCLUDED.org_id, role = EXCLUDED.role
                    RETURNING user_id::text
                """),
                {"uid": uid, "oid": _ORG_ID, "email": email, "role": role},
            )
            # Look up actual user_id (in case ON CONFLICT preserved an existing one)
            row = conn.execute(
                sa.text("SELECT user_id::text FROM users WHERE email = :email"),
                {"email": email},
            ).fetchone()
            _USER_IDS[nick] = row[0]

        # Evaluation runs
        for rfp_id, dept, creator_email in _RUNS:
            rid = str(uuid.uuid4())
            _RUN_IDS[rfp_id] = rid
            conn.execute(
                sa.text("""
                    INSERT INTO evaluation_runs
                        (run_id, org_id, setup_id, rfp_id, rfp_title, department,
                         status, vendor_ids, created_by_email, creator_dept_id)
                    VALUES
                        (CAST(:rid AS uuid), CAST(:oid AS uuid), NULL, :rfp_id,
                         :title, :dept, 'complete', ARRAY['v1','v2'],
                         :email, :dept)
                """),
                {"rid": rid, "oid": _ORG_ID, "rfp_id": rfp_id,
                 "title": f"Test RFP {rfp_id}", "dept": dept, "email": creator_email},
            )

    # Membership: anita in IT, bob in HR, carla in Finance
    add_user_to_department(_USER_IDS["anita"], "IT", "member")
    add_user_to_department(_USER_IDS["bob"],   "HR", "member")
    add_user_to_department(_USER_IDS["carla"], "Finance", "member")
    # Dan is a security reviewer with no home department — only sees what he's invited to.

    # Dan invited to rfp-test-it-1 as a reviewer
    add_collaborator(_RUN_IDS["rfp-test-it-1"], _USER_IDS["dan"], "reviewer", _USER_IDS["anita"])

    # Carla assigned as approver on rfp-test-it-3 (cross-department approval queue)
    assign_approver(_RUN_IDS["rfp-test-it-3"], _USER_IDS["carla"], "cfo")

    yield

    # Teardown — delete fixture data (cast to UUID[] for ANY())
    with engine.begin() as conn:
        conn.execute(sa.text("DELETE FROM rfp_collaborators WHERE run_id = ANY(CAST(:ids AS uuid[]))"),
                     {"ids": list(_RUN_IDS.values())})
        conn.execute(sa.text("DELETE FROM approval_assignments WHERE run_id = ANY(CAST(:ids AS uuid[]))"),
                     {"ids": list(_RUN_IDS.values())})
        conn.execute(sa.text("DELETE FROM user_departments WHERE user_id = ANY(CAST(:uids AS uuid[]))"),
                     {"uids": list(_USER_IDS.values())})
        conn.execute(sa.text("DELETE FROM evaluation_runs WHERE run_id = ANY(CAST(:ids AS uuid[]))"),
                     {"ids": list(_RUN_IDS.values())})
        conn.execute(sa.text("DELETE FROM users WHERE user_id = ANY(CAST(:ids AS uuid[]))"),
                     {"ids": list(_USER_IDS.values())})
        conn.execute(sa.text("DELETE FROM organisations WHERE org_id = CAST(:oid AS uuid)"),
                     {"oid": _ORG_ID})


def _token(nick: str) -> TokenData:
    email, role, dept = _USERS[nick]
    return TokenData(email=email, org_id=_ORG_ID, role=role, dept_id=dept)


def _rfp_ids(runs: list[dict]) -> set[str]:
    return {r["rfp_id"] for r in runs}


# ── Persona tests ────────────────────────────────────────────────────────────

class TestAdminVisibility:
    def test_admin_sees_all_six_runs_with_scope_all(self):
        runs = visible_runs(_token("admin"), scope="all")
        assert _rfp_ids(runs) == {r[0] for r in _RUNS}

    def test_admin_sees_zero_with_scope_mine_since_didnt_create_any(self):
        runs = visible_runs(_token("admin"), scope="mine")
        assert runs == []


class TestAnitaITDeptUser:
    def test_mine_returns_only_runs_anita_created(self):
        runs = visible_runs(_token("anita"), scope="mine")
        assert _rfp_ids(runs) == {"rfp-test-it-1"}

    def test_department_returns_all_three_IT_runs(self):
        runs = visible_runs(_token("anita"), scope="department")
        assert _rfp_ids(runs) == {"rfp-test-it-1", "rfp-test-it-2", "rfp-test-it-3"}

    def test_anita_cannot_use_scope_all(self):
        runs = visible_runs(_token("anita"), scope="all")
        # 'all' for non-wide-role yields empty (defensive double-deny)
        assert runs == []

    def test_anita_cannot_view_hr_run_via_can_view_run(self):
        assert not can_view_run(_token("anita"), _RUN_IDS["rfp-test-hr-1"])


class TestBobHRDeptUser_DefaultDeny:
    """Critical: Bob in HR must NOT see IT runs even though same org."""
    def test_bob_department_returns_only_HR(self):
        runs = visible_runs(_token("bob"), scope="department")
        assert _rfp_ids(runs) == {"rfp-test-hr-1", "rfp-test-hr-2"}

    def test_bob_cannot_view_any_IT_run(self):
        for it_rfp in ("rfp-test-it-1", "rfp-test-it-2", "rfp-test-it-3"):
            assert not can_view_run(_token("bob"), _RUN_IDS[it_rfp]), \
                f"DEFAULT-DENY VIOLATED: bob can see {it_rfp}"


class TestCarlaApprover:
    """Carla is a Finance dept_user but has an approval_assignment on an IT run."""
    def test_approvals_scope_returns_only_assigned_run(self):
        runs = visible_runs(_token("carla"), scope="approvals")
        assert _rfp_ids(runs) == {"rfp-test-it-3"}

    def test_carla_can_view_the_IT_run_she_approves(self):
        assert can_view_run(_token("carla"), _RUN_IDS["rfp-test-it-3"])

    def test_carla_cannot_view_other_IT_runs(self):
        assert not can_view_run(_token("carla"), _RUN_IDS["rfp-test-it-2"])


class TestDanInvitedReviewer:
    """Dan has no department, only an explicit collaborator invite."""
    def test_shared_scope_returns_only_invited_run(self):
        runs = visible_runs(_token("dan"), scope="shared")
        assert _rfp_ids(runs) == {"rfp-test-it-1"}

    def test_dan_can_view_invited_run(self):
        assert can_view_run(_token("dan"), _RUN_IDS["rfp-test-it-1"])

    def test_dan_cannot_view_other_runs(self):
        for other in ("rfp-test-it-2", "rfp-test-hr-1", "rfp-test-fin-1"):
            assert not can_view_run(_token("dan"), _RUN_IDS[other]), \
                f"DEFAULT-DENY VIOLATED: dan can see {other}"
