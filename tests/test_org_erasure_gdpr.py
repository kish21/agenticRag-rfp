"""
tests/test_org_erasure_gdpr.py
==============================
SC-001 (#119) — GDPR Mode B whole-tenant erasure.

Covers the exit criteria from docs/dev/119.md:
  - seed an org across EVERY org-scoped table, call the endpoint, assert every
    one returns 0 for that org_id and the `organisations` row is gone;
  - Qdrant delete_org_data is invoked;
  - on-disk drop folders are removed;
  - the org_settings cache is invalidated;
  - a retained, anonymized `org.erased` receipt row survives with counts +
    requester (and is the ONLY audit_log row left for the org);
  - RBAC: non-admin → 403; company_admin erasing a *different* org → 403;
  - safety: confirm_org_name mismatch → 400; a 'running' run → 409.

Needs a live Postgres (conftest routes get_engine()/get_admin_engine() to the
owner role). Qdrant is mocked — no vector backend required.

Run:
    python -m pytest tests/test_org_erasure_gdpr.py -v
"""
from __future__ import annotations

import json
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
import sqlalchemy as sa
from fastapi import FastAPI
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.api.admin_routes import router as admin_router  # noqa: E402
from app.auth.dependencies import get_current_user  # noqa: E402
from app.auth.jwt import TokenData  # noqa: E402
from app.config import settings  # noqa: E402
from app.db.fact_store import get_admin_engine  # noqa: E402

app = FastAPI()
app.include_router(admin_router)

ORG_NAME = "Departing Customer Ltd"

# Every table the purge clears, with a COUNT predicate scoped to the seeded org.
# Subquery-scoped children are checked by their seeded key directly (proves the
# row is gone, not merely orphaned). audit_log is asserted separately (the
# receipt is expected to remain).
def _verification_counts(conn, ctx: dict) -> dict[str, int]:
    oid = ctx["org_id"]
    checks = {
        "extracted_certifications": "SELECT count(*) FROM extracted_certifications WHERE org_id = CAST(:o AS uuid)",
        "extracted_insurance":      "SELECT count(*) FROM extracted_insurance      WHERE org_id = CAST(:o AS uuid)",
        "extracted_slas":           "SELECT count(*) FROM extracted_slas           WHERE org_id = CAST(:o AS uuid)",
        "extracted_projects":       "SELECT count(*) FROM extracted_projects       WHERE org_id = CAST(:o AS uuid)",
        "extracted_pricing":        "SELECT count(*) FROM extracted_pricing        WHERE org_id = CAST(:o AS uuid)",
        "extracted_facts":          "SELECT count(*) FROM extracted_facts          WHERE org_id = CAST(:o AS uuid)",
        "decisions":                "SELECT count(*) FROM decisions                WHERE org_id = CAST(:o AS uuid)",
        "approvals":                "SELECT count(*) FROM approvals                WHERE org_id = CAST(:o AS uuid)",
        "access_audit_log":         "SELECT count(*) FROM access_audit_log         WHERE org_id = CAST(:o AS uuid)",
        "retrieval_log":            "SELECT count(*) FROM retrieval_log            WHERE org_id = CAST(:o AS uuid)",
        "audit_overrides":          "SELECT count(*) FROM audit_overrides          WHERE org_id = CAST(:o AS uuid)",
        "ingestion_jobs":           "SELECT count(*) FROM ingestion_jobs           WHERE org_id = CAST(:o AS uuid)",
        "event_log":                "SELECT count(*) FROM event_log                WHERE org_id = CAST(:o AS uuid)",
        "vendor_documents":         "SELECT count(*) FROM vendor_documents         WHERE org_id = CAST(:o AS uuid)",
        "evaluation_runs":          "SELECT count(*) FROM evaluation_runs          WHERE org_id = CAST(:o AS uuid)",
        "evaluation_setups":        "SELECT count(*) FROM evaluation_setups        WHERE org_id = CAST(:o AS uuid)",
        "rfps":                     "SELECT count(*) FROM rfps                     WHERE org_id = CAST(:o AS uuid)",
        "agent_registry":           "SELECT count(*) FROM agent_registry           WHERE org_id = CAST(:o AS uuid)",
        "org_criteria_templates":   "SELECT count(*) FROM org_criteria_templates   WHERE org_id = CAST(:o AS uuid)",
        "dept_criteria_templates":  "SELECT count(*) FROM dept_criteria_templates  WHERE org_id = CAST(:o AS uuid)",
        "tenant_modules":           "SELECT count(*) FROM tenant_modules           WHERE org_id = CAST(:o AS uuid)",
        "tenant_billing":           "SELECT count(*) FROM tenant_billing           WHERE org_id = CAST(:o AS uuid)",
        "auth_sessions":            "SELECT count(*) FROM auth_sessions            WHERE org_id = CAST(:o AS uuid)",
        "auth_onetime_tokens":      "SELECT count(*) FROM auth_onetime_tokens      WHERE org_id = CAST(:o AS uuid)",
        "users":                    "SELECT count(*) FROM users                    WHERE org_id = CAST(:o AS uuid)",
        "organisations":            "SELECT count(*) FROM organisations            WHERE org_id = CAST(:o AS uuid)",
    }
    out = {t: conn.execute(sa.text(q), {"o": oid}).scalar() for t, q in checks.items()}
    # TEXT org_id tables (org_settings / org_settings_audit)
    out["org_settings"] = conn.execute(
        sa.text("SELECT count(*) FROM org_settings WHERE org_id = :o"), {"o": oid}).scalar()
    out["org_settings_audit"] = conn.execute(
        sa.text("SELECT count(*) FROM org_settings_audit WHERE org_id = :o"), {"o": oid}).scalar()
    # Subquery-scoped children — checked by their seeded keys.
    out["invited_vendors"] = conn.execute(
        sa.text("SELECT count(*) FROM invited_vendors WHERE rfp_id = :r"), {"r": ctx["rfp_id"]}).scalar()
    out["user_departments"] = conn.execute(
        sa.text("SELECT count(*) FROM user_departments WHERE user_id = CAST(:u AS uuid)"),
        {"u": ctx["user_id"]}).scalar()
    out["rfp_collaborators"] = conn.execute(
        sa.text("SELECT count(*) FROM rfp_collaborators WHERE run_id = CAST(:r AS uuid)"),
        {"r": ctx["run_id"]}).scalar()
    out["approval_assignments"] = conn.execute(
        sa.text("SELECT count(*) FROM approval_assignments WHERE run_id = CAST(:r AS uuid)"),
        {"r": ctx["run_id"]}).scalar()
    return out


def _seed_full_org(*, with_running_run: bool = False) -> dict:
    """Insert one row in every org-scoped table. Returns key ids as a context."""
    org_id = str(uuid.uuid4())
    user_id = str(uuid.uuid4())
    agent_id = str(uuid.uuid4())
    setup_id = f"setup-{uuid.uuid4().hex}"
    run_id = str(uuid.uuid4())
    doc_id = str(uuid.uuid4())
    rfp_id = f"rfp-{uuid.uuid4().hex}"
    vendor_id = "acme"
    run_status = "running" if with_running_run else "completed"
    email = f"user-{uuid.uuid4().hex}@departing.test"
    ctx = dict(org_id=org_id, user_id=user_id, run_id=run_id, rfp_id=rfp_id,
               setup_id=setup_id, doc_id=doc_id, agent_id=agent_id, email=email)

    engine = get_admin_engine()
    with engine.begin() as c:
        c.execute(sa.text(
            "INSERT INTO organisations (org_id, org_name) VALUES (CAST(:o AS uuid), :n)"),
            {"o": org_id, "n": ORG_NAME})
        c.execute(sa.text(
            "INSERT INTO users (user_id, org_id, email, hashed_pw, role) "
            "VALUES (CAST(:u AS uuid), CAST(:o AS uuid), :e, 'x', 'company_admin')"),
            {"u": user_id, "o": org_id, "e": email})
        c.execute(sa.text(
            "INSERT INTO agent_registry (agent_id, org_id, agent_name, agent_type, config) "
            "VALUES (CAST(:a AS uuid), CAST(:o AS uuid), 'proc', 'procurement', '{}'::jsonb)"),
            {"a": agent_id, "o": org_id})
        c.execute(sa.text(
            "INSERT INTO evaluation_setups (setup_id, org_id, department, rfp_id, setup_json, confirmed_by, source) "
            "VALUES (:s, CAST(:o AS uuid), 'proc', :r, '{}'::jsonb, :e, 'mixed')"),
            {"s": setup_id, "o": org_id, "r": rfp_id, "e": email})
        c.execute(sa.text(
            "INSERT INTO evaluation_runs (run_id, org_id, setup_id, rfp_id, agent_id, status) "
            "VALUES (CAST(:run AS uuid), CAST(:o AS uuid), :s, :r, CAST(:a AS uuid), :st)"),
            {"run": run_id, "o": org_id, "s": setup_id, "r": rfp_id, "a": agent_id, "st": run_status})
        c.execute(sa.text(
            "INSERT INTO vendor_documents (doc_id, org_id, vendor_id, rfp_id, setup_id, filename, content_hash) "
            "VALUES (CAST(:d AS uuid), CAST(:o AS uuid), :v, :r, :s, 'f.pdf', :h)"),
            {"d": doc_id, "o": org_id, "v": vendor_id, "r": rfp_id, "s": setup_id, "h": uuid.uuid4().hex})
        # extracted_* (typed + generic)
        for tbl in ("extracted_certifications", "extracted_insurance", "extracted_slas",
                    "extracted_projects", "extracted_pricing"):
            c.execute(sa.text(
                f"INSERT INTO {tbl} (doc_id, org_id, vendor_id, grounding_quote, source_chunk_id) "
                "VALUES (CAST(:d AS uuid), CAST(:o AS uuid), :v, 'q', 'chunk-1')"),
                {"d": doc_id, "o": org_id, "v": vendor_id})
        c.execute(sa.text(
            "INSERT INTO extracted_facts (doc_id, org_id, vendor_id, setup_id, target_id, fact_type, "
            "fact_name, grounding_quote, source_chunk_id) "
            "VALUES (CAST(:d AS uuid), CAST(:o AS uuid), :v, :s, 't1', 'numeric', 'fleet', 'q', 'chunk-1')"),
            {"d": doc_id, "o": org_id, "v": vendor_id, "s": setup_id})
        # run-scoped children
        c.execute(sa.text(
            "INSERT INTO decisions (run_id, org_id, vendor_id, decision_type, decision) "
            "VALUES (CAST(:run AS uuid), CAST(:o AS uuid), :v, 'final', 'pass')"),
            {"run": run_id, "o": org_id, "v": vendor_id})
        c.execute(sa.text(
            "INSERT INTO approvals (run_id, org_id, approval_tier, approver_role) "
            "VALUES (CAST(:run AS uuid), CAST(:o AS uuid), 1, 'cfo')"),
            {"run": run_id, "o": org_id})
        c.execute(sa.text(
            "INSERT INTO approval_assignments (run_id, approver_user_id, approver_role) "
            "VALUES (CAST(:run AS uuid), CAST(:u AS uuid), 'cfo')"),
            {"run": run_id, "u": user_id})
        c.execute(sa.text(
            "INSERT INTO rfp_collaborators (run_id, user_id, role) "
            "VALUES (CAST(:run AS uuid), CAST(:u AS uuid), 'viewer')"),
            {"run": run_id, "u": user_id})
        c.execute(sa.text(
            "INSERT INTO access_audit_log (org_id, run_id, accessed_by, action) "
            "VALUES (CAST(:o AS uuid), CAST(:run AS uuid), :e, 'view')"),
            {"o": org_id, "run": run_id, "e": email})
        c.execute(sa.text(
            "INSERT INTO retrieval_log (org_id, run_id, vendor_id, query_text, retrieval_strategy) "
            "VALUES (CAST(:o AS uuid), CAST(:run AS uuid), :v, 'q', 'hybrid')"),
            {"o": org_id, "run": run_id, "v": vendor_id})
        c.execute(sa.text(
            "INSERT INTO audit_overrides (override_id, org_id, run_id, overridden_by, original_decision, "
            "new_decision, reason, timestamp) VALUES (CAST(:ov AS uuid), CAST(:o AS uuid), CAST(:run AS uuid), "
            ":e, '{}'::jsonb, '{}'::jsonb, 'a reason long enough to pass the check', now())"),
            {"ov": str(uuid.uuid4()), "o": org_id, "run": run_id, "e": email})
        c.execute(sa.text(
            "INSERT INTO audit_log (org_id, run_id, event_type, actor) "
            "VALUES (CAST(:o AS uuid), CAST(:run AS uuid), 'run.created', :e)"),
            {"o": org_id, "run": run_id, "e": email})
        # rfp lifecycle
        c.execute(sa.text(
            "INSERT INTO rfps (rfp_id, org_id, title, created_by_email) "
            "VALUES (:r, CAST(:o AS uuid), 'RFP', :e)"),
            {"r": rfp_id, "o": org_id, "e": email})
        c.execute(sa.text(
            "INSERT INTO invited_vendors (rfp_id, vendor_id, invited_by) VALUES (:r, :v, :e)"),
            {"r": rfp_id, "v": vendor_id, "e": email})
        c.execute(sa.text(
            "INSERT INTO ingestion_jobs (org_id, rfp_id, vendor_id, content_hash, status, doc_id) "
            "VALUES (CAST(:o AS uuid), :r, :v, :h, 'facts_ready', CAST(:d AS uuid))"),
            {"o": org_id, "r": rfp_id, "v": vendor_id, "h": uuid.uuid4().hex, "d": doc_id})
        c.execute(sa.text(
            "INSERT INTO event_log (event_type, org_id, rfp_id) VALUES ('x', CAST(:o AS uuid), :r)"),
            {"o": org_id, "r": rfp_id})
        # org config / billing / templates
        c.execute(sa.text(
            "INSERT INTO org_settings (org_id) VALUES (:o)"), {"o": org_id})
        c.execute(sa.text(
            "INSERT INTO org_settings_audit (org_id, changed_by, field_name) VALUES (:o, :e, 'tier')"),
            {"o": org_id, "e": email})
        c.execute(sa.text(
            "INSERT INTO tenant_modules (org_id, module_key, enabled) VALUES (CAST(:o AS uuid), 'rfp', true)"),
            {"o": org_id})
        c.execute(sa.text(
            "INSERT INTO tenant_billing (org_id, plan) VALUES (CAST(:o AS uuid), 'enterprise')"),
            {"o": org_id})
        c.execute(sa.text(
            "INSERT INTO org_criteria_templates (org_id, check_type, name) "
            "VALUES (CAST(:o AS uuid), 'mandatory', 'ISO')"), {"o": org_id})
        c.execute(sa.text(
            "INSERT INTO dept_criteria_templates (org_id, department, check_type, name) "
            "VALUES (CAST(:o AS uuid), 'proc', 'scoring', 'price')"), {"o": org_id})
        # user auth artefacts
        c.execute(sa.text(
            "INSERT INTO user_departments (user_id, department_id) VALUES (CAST(:u AS uuid), 'proc')"),
            {"u": user_id})
        c.execute(sa.text(
            "INSERT INTO auth_sessions (jti, user_id, org_id, expires_at) "
            "VALUES (CAST(:j AS uuid), CAST(:u AS uuid), CAST(:o AS uuid), :exp)"),
            {"j": str(uuid.uuid4()), "u": user_id, "o": org_id,
             "exp": datetime.now(timezone.utc) + timedelta(days=1)})
        c.execute(sa.text(
            "INSERT INTO auth_onetime_tokens (token_hash, purpose, email, org_id, user_id, expires_at) "
            "VALUES (:th, 'invite', :e, CAST(:o AS uuid), CAST(:u AS uuid), :exp)"),
            {"th": uuid.uuid4().hex, "e": email, "o": org_id, "u": user_id,
             "exp": datetime.now(timezone.utc) + timedelta(days=1)})
    return ctx


def _cleanup(org_id: str) -> None:
    """Best-effort teardown for tests that do NOT erase (RBAC/safety cases)."""
    from app.db.fact_store import purge_org_postgres
    try:
        purge_org_postgres(org_id)
    except Exception:
        pass


def _user(role: str, org_id: str) -> TokenData:
    return TokenData(email=f"{role}@erase.test", org_id=org_id, role=role, dept_id="proc")


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture(autouse=True)
def _mock_qdrant(monkeypatch):
    """No vector backend in CI — record the call and return a plausible result."""
    calls = {}

    def _fake_delete_org_data(org_id):
        calls["org_id"] = org_id
        return (7, True)

    monkeypatch.setattr("app.domain.org_erasure.delete_org_data", _fake_delete_org_data)
    return calls


@pytest.fixture(autouse=True)
def _spy_cache(monkeypatch):
    """Record that the org_settings cache was invalidated."""
    calls = {}
    import app.domain.org_erasure as oe
    real = oe.invalidate_org_settings

    def _spy(org_id):
        calls["org_id"] = org_id
        return real(org_id)

    monkeypatch.setattr(oe, "invalidate_org_settings", _spy)
    return calls


# ── happy path — full wipe ───────────────────────────────────────────────


def test_erase_wipes_every_table(client, _mock_qdrant, _spy_cache):
    ctx = _seed_full_org()
    app.dependency_overrides[get_current_user] = lambda: _user("platform_admin", str(uuid.uuid4()))

    # Drop folder on disk for one of the org's RFPs.
    drops_root = Path(settings.platform.ingestion.drops_root)
    folder = drops_root / ctx["rfp_id"]
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "x.pdf").write_text("data")

    resp = client.request(
        "DELETE", f"/api/v1/admin/org/{ctx['org_id']}/data",
        json={"confirm_org_name": ORG_NAME, "reason": "Customer offboarded under MSA clause 12."},
    )
    app.dependency_overrides.clear()

    assert resp.status_code == 200, resp.text
    body = resp.json()

    # every org-scoped table empty, organisations gone
    engine = get_admin_engine()
    with engine.connect() as conn:
        counts = _verification_counts(conn, ctx)
    nonzero = {t: n for t, n in counts.items() if n != 0}
    assert not nonzero, f"rows survived erasure: {nonzero}"

    # Qdrant invoked + cache invalidated
    assert _mock_qdrant["org_id"] == ctx["org_id"]
    assert _spy_cache["org_id"] == ctx["org_id"]
    assert body["qdrant_points_deleted"] == 7
    assert body["qdrant_collection_dropped"] is True

    # disk folder removed
    assert not folder.exists()
    assert body["drop_folders_deleted"] == 1

    # retained receipt — the ONLY audit_log row left for the org
    with engine.connect() as conn:
        rows = conn.execute(
            sa.text("SELECT event_type, actor, detail FROM audit_log WHERE org_id = CAST(:o AS uuid)"),
            {"o": ctx["org_id"]},
        ).fetchall()
    assert len(rows) == 1
    assert rows[0][0] == "org.erased"
    assert rows[0][1] == "platform_admin@erase.test"
    detail = rows[0][2] if isinstance(rows[0][2], dict) else json.loads(rows[0][2])
    assert detail["postgres_deleted"]["users"] == 1
    assert detail["requested_by"] == "platform_admin@erase.test"
    assert body["receipt_persisted"] is True
    # Receipt row is itself the only audit trace → clean up so it doesn't linger.
    with engine.begin() as conn:
        conn.execute(sa.text("DELETE FROM audit_log WHERE org_id = CAST(:o AS uuid)"), {"o": ctx["org_id"]})


# ── RBAC ──────────────────────────────────────────────────────────────────


def test_non_admin_forbidden(client):
    ctx = _seed_full_org()
    try:
        app.dependency_overrides[get_current_user] = lambda: _user("department_user", ctx["org_id"])
        resp = client.request(
            "DELETE", f"/api/v1/admin/org/{ctx['org_id']}/data",
            json={"confirm_org_name": ORG_NAME, "reason": "x"})
        assert resp.status_code == 403
    finally:
        app.dependency_overrides.clear()
        _cleanup(ctx["org_id"])


def test_company_admin_other_org_forbidden(client):
    ctx = _seed_full_org()
    try:
        # company_admin from a DIFFERENT org
        app.dependency_overrides[get_current_user] = lambda: _user("company_admin", str(uuid.uuid4()))
        resp = client.request(
            "DELETE", f"/api/v1/admin/org/{ctx['org_id']}/data",
            json={"confirm_org_name": ORG_NAME, "reason": "x"})
        assert resp.status_code == 403
    finally:
        app.dependency_overrides.clear()
        _cleanup(ctx["org_id"])


# ── safety ────────────────────────────────────────────────────────────────


def test_name_mismatch_rejected(client):
    ctx = _seed_full_org()
    try:
        app.dependency_overrides[get_current_user] = lambda: _user("platform_admin", str(uuid.uuid4()))
        resp = client.request(
            "DELETE", f"/api/v1/admin/org/{ctx['org_id']}/data",
            json={"confirm_org_name": "Wrong Name", "reason": "x"})
        assert resp.status_code == 400
    finally:
        app.dependency_overrides.clear()
        _cleanup(ctx["org_id"])


def test_running_run_blocks_erasure(client):
    ctx = _seed_full_org(with_running_run=True)
    try:
        app.dependency_overrides[get_current_user] = lambda: _user("platform_admin", str(uuid.uuid4()))
        resp = client.request(
            "DELETE", f"/api/v1/admin/org/{ctx['org_id']}/data",
            json={"confirm_org_name": ORG_NAME, "reason": "x"})
        assert resp.status_code == 409
    finally:
        app.dependency_overrides.clear()
        _cleanup(ctx["org_id"])


# ── completeness guard — no org-scoped table may silently escape the wipe ──


def test_purge_order_covers_every_org_scoped_table():
    """Schema-drift guard: every table in schema.sql that has an `org_id` column
    MUST appear in fact_store._PURGE_ORDER, or a future table would survive a
    'complete' GDPR erasure with no failure. `llm_response_cache` is the one
    documented exception (tenant-blind by design — no org_id, see docs/dev/119.md)."""
    import re

    from app.db.fact_store import _PURGE_ORDER

    schema = (Path(__file__).parent.parent / "app" / "db" / "schema.sql").read_text(encoding="utf-8")
    # Split into CREATE TABLE blocks; a block "has org_id" if an org_id column is declared.
    blocks = re.split(r"CREATE TABLE IF NOT EXISTS\s+", schema)[1:]
    org_scoped = set()
    for blk in blocks:
        name = re.match(r"(\w+)", blk).group(1)
        body = blk[: blk.find(";")]
        if re.search(r"\borg_id\b", body):
            org_scoped.add(name)

    covered = {t for t, _ in _PURGE_ORDER}
    missing = org_scoped - covered
    assert not missing, (
        f"org-scoped tables missing from _PURGE_ORDER (would survive a GDPR wipe): {missing}. "
        "Add them in FK-safe order, or document an explicit tenant-blind exception."
    )


def test_unknown_org_404(client):
    app.dependency_overrides[get_current_user] = lambda: _user("platform_admin", str(uuid.uuid4()))
    resp = client.request(
        "DELETE", f"/api/v1/admin/org/{uuid.uuid4()}/data",
        json={"confirm_org_name": "x", "reason": "y"})
    app.dependency_overrides.clear()
    assert resp.status_code == 404
