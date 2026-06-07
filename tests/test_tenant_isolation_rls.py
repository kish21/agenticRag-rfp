"""
tests/test_tenant_isolation_rls.py
==================================
P0.16 — proves PostgreSQL Row-Level Security ACTUALLY enforces tenant isolation.

Before the fix these tests fail by design:
  • the app connected as a superuser/owner that RLS exempts,
  • two audit tables had RLS enabled but no policy,
  • org_settings used a different GUC name (app.org_id).

Unlike the rest of the suite (which runs as the owner via conftest so it can
seed freely — see tests/conftest.py), this module builds an EXPLICIT
``platform_app`` engine — the same NON-superuser role the app uses at runtime —
so the assertions reflect production behaviour. Seeding is done through the
owner engine (a privileged harness), exactly as DDL/identity/cron do in prod.

Requires a running Postgres provisioned by app/db/schema.sql (creates the
platform_app role, FORCEs RLS, adds the audit policies). Cleans up its own data.
"""
from __future__ import annotations

import uuid

import pytest
import sqlalchemy as sa

from app.auth.dependencies import COOKIE_NAME
from app.db.fact_store import get_admin_engine
from app.db.session import app_engine_url, install_org_listener, org_context

ORG_A = str(uuid.uuid4())
ORG_B = str(uuid.uuid4())


@pytest.fixture(scope="module")
def admin_engine():
    return get_admin_engine()


@pytest.fixture(scope="module")
def app_engine():
    """The real RLS-governed application engine (role: platform_app)."""
    eng = sa.create_engine(app_engine_url())
    install_org_listener(eng)
    yield eng
    eng.dispose()


@pytest.fixture(scope="module", autouse=True)
def seed(admin_engine):
    """Seed two orgs (admin engine bypasses RLS) and tear them down."""
    with admin_engine.begin() as c:
        for o in (ORG_A, ORG_B):
            c.execute(sa.text(
                "INSERT INTO organisations (org_id, org_name, industry, "
                "subscription_tier, is_active) VALUES "
                "(CAST(:o AS uuid), :n, 'Test', 'trial', TRUE) "
                "ON CONFLICT DO NOTHING"
            ), {"o": o, "n": f"org-{o[:8]}"})
            c.execute(sa.text(
                "INSERT INTO evaluation_runs (org_id, rfp_id, status, vendor_ids) "
                "VALUES (CAST(:o AS uuid), :r, 'complete', ARRAY['v1'])"
            ), {"o": o, "r": f"rfp-{o[:8]}"})
            c.execute(sa.text(
                "INSERT INTO audit_log (org_id, event_type, actor) "
                "VALUES (CAST(:o AS uuid), 'run.created', 'test')"
            ), {"o": o})
            # P1.9 (#60) — one few-shot correction per org for read-isolation.
            c.execute(sa.text(
                "INSERT INTO evaluation_corrections "
                "(correction_id, org_id, target_type, target_id, corrected_value, "
                " reason, corrected_by) VALUES "
                "(gen_random_uuid(), CAST(:o AS uuid), 'criterion', 'crit-1', "
                " '{\"raw_score\": 8}'::jsonb, :reason, 'test@x.test')"
            ), {"o": o, "reason": "seeded correction for the rls isolation test (20+ chars)"})
    yield
    with admin_engine.begin() as c:
        for o in (ORG_A, ORG_B):
            c.execute(sa.text("DELETE FROM evaluation_corrections WHERE org_id = CAST(:o AS uuid)"), {"o": o})
            c.execute(sa.text("DELETE FROM audit_log WHERE org_id = CAST(:o AS uuid)"), {"o": o})
            c.execute(sa.text("DELETE FROM evaluation_runs WHERE org_id = CAST(:o AS uuid)"), {"o": o})
            c.execute(sa.text("DELETE FROM organisations WHERE org_id = CAST(:o AS uuid)"), {"o": o})


# ── Role + schema invariants ────────────────────────────────────────────────

def test_app_role_is_not_privileged(admin_engine):
    """platform_app must be a login role that RLS can constrain: NOT superuser,
    NOT BYPASSRLS. If it were either, every policy below would be inert."""
    with admin_engine.connect() as c:
        row = c.execute(sa.text(
            "SELECT rolsuper, rolbypassrls, rolcanlogin FROM pg_roles "
            "WHERE rolname = 'platform_app'"
        )).fetchone()
    assert row is not None, "platform_app role does not exist — run app/db/schema.sql"
    assert row.rolsuper is False, "platform_app is a SUPERUSER → RLS is bypassed"
    assert row.rolbypassrls is False, "platform_app has BYPASSRLS → RLS is bypassed"
    assert row.rolcanlogin is True, "platform_app cannot log in"


def test_every_rls_table_is_forced(admin_engine):
    """Single source of truth: EVERY table with RLS enabled must also be FORCEd,
    so the policy applies to the owner too. No hardcoded table list — this
    derives the set from the catalog, so a newly-protected table is covered
    automatically (and this test fails if someone enables RLS without FORCE)."""
    with admin_engine.connect() as c:
        not_forced = [r.relname for r in c.execute(sa.text(
            "SELECT relname FROM pg_class "
            "WHERE relnamespace = 'public'::regnamespace "
            "AND relrowsecurity = true AND relforcerowsecurity = false"
        ))]
    assert not not_forced, f"RLS-enabled but not FORCEd: {sorted(not_forced)}"


def test_hot_path_policies_are_index_friendly(admin_engine):
    """The evaluation hot-path tables must compare org_id as uuid (not ::text),
    so the org filter can use the (org_id, …) btree index at scale rather than
    a sequential scan."""
    hot = ("extracted_facts", "extracted_certifications", "evaluation_runs")
    with admin_engine.connect() as c:
        rows = {r.tablename: r.qual for r in c.execute(sa.text(
            "SELECT tablename, qual FROM pg_policies WHERE tablename = ANY(:t)"
        ), {"t": list(hot)})}
    for t in hot:
        assert t in rows, f"no policy on {t}"
        assert "::text =" not in rows[t], f"{t} policy still casts org_id to text: {rows[t]}"
        assert "::uuid" in rows[t], f"{t} policy not uuid-compared: {rows[t]}"


def test_no_legacy_app_org_id_guc_remains(admin_engine):
    """All policies must read app.current_org_id — the old app.org_id GUC
    (org_settings) must be gone, or those rows fall open under the wrong name."""
    with admin_engine.connect() as c:
        rows = c.execute(sa.text(
            "SELECT policyname, qual FROM pg_policies WHERE schemaname = 'public'"
        )).fetchall()
    legacy = [r.policyname for r in rows if r.qual and "app.org_id" in r.qual
              and "app.current_org_id" not in r.qual]
    assert not legacy, f"policies still using legacy app.org_id GUC: {legacy}"
    # And the org_settings policies must now reference the standard GUC.
    org_pols = {r.policyname: r.qual for r in rows
                if r.policyname in ("org_settings_isolation", "org_settings_audit_isolation")}
    assert org_pols, "org_settings RLS policies missing"
    for name, qual in org_pols.items():
        assert "app.current_org_id" in qual, f"{name} not on app.current_org_id: {qual}"


def test_audit_tables_have_policies(admin_engine):
    """audit_log + access_audit_log had RLS enabled but NO policy (= deny-all
    for a non-owner). They must now carry an org-isolation policy."""
    with admin_engine.connect() as c:
        names = {r.policyname for r in c.execute(sa.text(
            "SELECT policyname FROM pg_policies WHERE schemaname = 'public'"
        )).fetchall()}
    assert "rls_audit_log" in names
    assert "rls_access_audit_log" in names


# ── Read isolation (the core property) ───────────────────────────────────────

def test_read_isolation_evaluation_runs(app_engine):
    """As platform_app, org A sees only org A's runs; org B's are invisible."""
    with org_context(ORG_A), app_engine.connect() as c:
        total = c.execute(sa.text("SELECT count(*) FROM evaluation_runs")).scalar()
        b_via_a = c.execute(sa.text(
            "SELECT count(*) FROM evaluation_runs WHERE org_id = CAST(:o AS uuid)"
        ), {"o": ORG_B}).scalar()
    assert b_via_a == 0, "org A can see org B's runs — RLS is not enforcing"
    assert total >= 1, "org A cannot even see its own run"


def test_missing_context_sees_zero_rows(app_engine):
    """No tenant context → RLS matches the empty string → zero protected rows
    (fails closed, not open)."""
    with org_context(None), app_engine.connect() as c:
        assert c.execute(sa.text("SELECT count(*) FROM evaluation_runs")).scalar() == 0


def test_audit_log_isolation(app_engine):
    with org_context(ORG_A), app_engine.connect() as c:
        b_rows = c.execute(sa.text(
            "SELECT count(*) FROM audit_log WHERE org_id = CAST(:o AS uuid)"
        ), {"o": ORG_B}).scalar()
    assert b_rows == 0, "org A can read org B's audit_log rows"


def test_evaluation_corrections_isolation():
    """P1.9 (#60) — a tenant only ever learns from its OWN corrections: org A
    cannot read org B's evaluation_corrections rows (the few-shot bank source),
    and DOES see its own.

    Uses a dedicated platform_app engine (not the module-shared one) so the
    owner-visibility assertion is immune to pooled-connection GUC state left by
    sibling tests (e.g. the org_context(None) test) — a test-harness artifact,
    not a production path. The seed (admin) fixture already inserted one
    correction per org."""
    eng = sa.create_engine(app_engine_url())
    install_org_listener(eng)
    try:
        with org_context(ORG_A), eng.connect() as c:
            b_rows = c.execute(sa.text(
                "SELECT count(*) FROM evaluation_corrections WHERE org_id = CAST(:o AS uuid)"
            ), {"o": ORG_B}).scalar()
            own = c.execute(sa.text("SELECT count(*) FROM evaluation_corrections")).scalar()
    finally:
        eng.dispose()
    assert b_rows == 0, "org A can read org B's corrections — RLS not enforcing"
    assert own >= 1, "org A cannot see its own corrections"


# ── Write isolation ──────────────────────────────────────────────────────────

def test_write_isolation_cannot_update_other_org(app_engine):
    """org A's UPDATE/DELETE cannot touch org B's rows (they're invisible)."""
    with org_context(ORG_A), app_engine.begin() as c:
        updated = c.execute(sa.text(
            "UPDATE evaluation_runs SET status = 'hacked' "
            "WHERE org_id = CAST(:o AS uuid)"
        ), {"o": ORG_B}).rowcount
    assert updated == 0, "org A modified org B's rows — RLS UPDATE not enforced"


def test_db_get_run_sets_own_org_context(admin_engine):
    """Regression for 'Run not found' on click: _db_get_run must stamp the tenant
    on its own connection, so an existing run is found even with NO ambient
    request context (an unstamped pooled connection otherwise makes RLS hide it)."""
    from app.api._evaluation.db import _db_get_run
    with admin_engine.connect() as c:
        rid = c.execute(sa.text(
            "SELECT run_id::text FROM evaluation_runs WHERE org_id = CAST(:o AS uuid) LIMIT 1"
        ), {"o": ORG_A}).scalar()
    assert rid, "seed did not create an ORG_A run"
    with org_context(None):  # simulate an unstamped connection
        run = _db_get_run(rid, ORG_A)
    assert run["run_id"] == rid


def test_run_insert_without_org_context_is_blocked():
    """Regression for the /start 500: an evaluation_runs INSERT with NO org
    context on the connection is rejected by RLS WITH CHECK — which is why
    /start (and every writer) must SET LOCAL app.current_org_id explicitly
    rather than rely on the pooled-connection listener alone. The same insert
    succeeds once the context is set. Dedicated engine to avoid pool-state
    bleed from sibling tests."""
    eng = sa.create_engine(app_engine_url())
    install_org_listener(eng)
    try:
        # No context → blocked.
        with pytest.raises(Exception) as exc:
            with org_context(None), eng.begin() as c:
                c.execute(sa.text(
                    "INSERT INTO evaluation_runs (org_id, rfp_id, status) "
                    "VALUES (CAST(:o AS uuid), 'rfp-rls-z', 'pending_confirm')"
                ), {"o": ORG_A})
        assert "row-level security" in str(exc.value).lower()

        # Context set explicitly (what the fix does) → succeeds.
        with org_context(None), eng.begin() as c:
            c.execute(sa.text("SET LOCAL app.current_org_id = :o"), {"o": ORG_A})
            rid = c.execute(sa.text(
                "INSERT INTO evaluation_runs (org_id, rfp_id, status) "
                "VALUES (CAST(:o AS uuid), 'rfp-rls-z2', 'pending_confirm') RETURNING run_id"
            ), {"o": ORG_A}).scalar()
        assert rid is not None
    finally:
        with get_admin_engine().begin() as c:
            c.execute(sa.text("DELETE FROM evaluation_runs WHERE rfp_id IN ('rfp-rls-z','rfp-rls-z2')"))
        eng.dispose()


def test_write_isolation_cannot_insert_for_other_org(app_engine):
    """org A cannot INSERT a row stamped with org B (WITH CHECK rejects it)."""
    with pytest.raises(Exception) as exc:
        with org_context(ORG_A), app_engine.begin() as c:
            c.execute(sa.text(
                "INSERT INTO evaluation_runs (org_id, rfp_id, status) "
                "VALUES (CAST(:o AS uuid), 'rfp-x', 'running')"
            ), {"o": ORG_B})
    assert "row-level security" in str(exc.value).lower()


# ── API-layer ownership guard (defense in depth above RLS) ───────────────────
# Route helpers scope every run lookup by the caller's org_id (WHERE org_id =
# :oid AND run_id = :rid), so a cross-org run_id matches nothing → the route
# raises 404 even before RLS. This is the application filter the README claims;
# RLS is the backstop beneath it. We assert that predicate directly (the engine
# here is RLS-exempt via conftest, isolating the app-layer filter under test).

def _run_id_for(admin_engine, org_id: str) -> str:
    with admin_engine.connect() as c:
        return str(c.execute(sa.text(
            "SELECT run_id FROM evaluation_runs WHERE org_id = CAST(:o AS uuid) LIMIT 1"
        ), {"o": org_id}).scalar())


def test_run_lookup_is_org_scoped(admin_engine):
    """The org_id filter that every run route uses rejects a cross-org run_id."""
    run_b = _run_id_for(admin_engine, ORG_B)
    lookup = sa.text(
        "SELECT run_id FROM evaluation_runs "
        "WHERE run_id = CAST(:rid AS uuid) AND org_id = CAST(:oid AS uuid)"
    )
    with admin_engine.connect() as c:
        # org A cannot resolve org B's run → empty → route would 404.
        assert c.execute(lookup, {"rid": run_b, "oid": ORG_A}).fetchone() is None
        # org B resolves its own run.
        assert c.execute(lookup, {"rid": run_b, "oid": ORG_B}).fetchone() is not None


# ── End-to-end request path: JWT → middleware → listener → RLS ───────────────

def test_request_path_isolation_end_to_end(monkeypatch):
    """Drive a real request through OrgContextMiddleware as the platform_app
    role and confirm the chain (cookie JWT → ContextVar → connection listener →
    RLS) confines the query to the caller's org — and that no token = no rows.

    This is the one test that exercises the production request path as the app
    role (the rest of the suite runs as the owner via conftest)."""
    import app.db.fact_store as fs
    from app.db import session as dbsession

    # Restore the REAL app-role engine for this test (conftest routes get_engine
    # to the owner). monkeypatch + cache reset are undone after the test.
    monkeypatch.setattr(fs, "app_engine_url", dbsession.app_engine_url)
    fs._engine = None
    try:
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from app.api.middleware import OrgContextMiddleware
        from app.auth.jwt import create_access_token

        app = FastAPI()
        app.add_middleware(OrgContextMiddleware)

        @app.get("/_t/run_count")
        def _run_count():
            with fs.get_engine().connect() as c:
                return {"n": c.execute(sa.text("SELECT count(*) FROM evaluation_runs")).scalar()}

        client = TestClient(app)
        tok = create_access_token(email="a@x.test", org_id=ORG_A,
                                  role="company_admin", dept_id=None)

        client.cookies.set(COOKIE_NAME, tok.access_token)
        assert client.get("/_t/run_count").json()["n"] == 1   # only org A's run

        client.cookies.clear()
        assert client.get("/_t/run_count").json()["n"] == 0   # no token → no rows
    finally:
        fs._engine = None  # next test rebuilds via conftest's owner routing


def test_operational_table_rfps_isolated(admin_engine, app_engine):
    """rfps (brought under RLS in this change) isolates by org too."""
    with admin_engine.begin() as c:
        c.execute(sa.text(
            "INSERT INTO rfps (rfp_id, org_id, title, created_by_email) "
            "VALUES (:r, CAST(:o AS uuid), 'B rfp', 'b@x.test')"
        ), {"r": f"rfpiso-{ORG_B[:8]}", "o": ORG_B})
    try:
        with org_context(ORG_A), app_engine.connect() as c:
            seen = c.execute(sa.text(
                "SELECT count(*) FROM rfps WHERE org_id = CAST(:o AS uuid)"
            ), {"o": ORG_B}).scalar()
        assert seen == 0, "org A can see org B's rfps — RLS not enforcing on rfps"
    finally:
        with admin_engine.begin() as c:
            c.execute(sa.text("DELETE FROM rfps WHERE rfp_id = :r"),
                      {"r": f"rfpiso-{ORG_B[:8]}"})
