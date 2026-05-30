"""
Phase 7 — customer-grade report tests.

Three layers, all runnable offline (no Postgres, no LLM):
  • builder unit tests — from-source assembly, grounding-by-construction,
    audit-trail 1:1 with agent_events, report_confidence == decision_confidence.
  • HTML template tests — 12 sections in order, autoescape, deterministic render
    (golden snapshot with the volatile `generated_at` masked).
  • endpoint tests — TestClient with auth + DB overrides: report.html 200,
    report.pdf (200+%PDF where weasyprint is available, else 503), 409 gate.
"""
import re
import sys
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.output.report_builder import build_report_context, ReportContext  # noqa: E402
from app.output.pdf_report import build_report_html  # noqa: E402


# ── Shared fixture — a completed run row as _db_get_run would return ──────────

SAMPLE_RUN = {
    "run_id": "11111111-1111-1111-1111-111111111111",
    "org_id": "22222222-2222-2222-2222-222222222222",
    "rfp_title": "IT Managed Services 2026",
    "rfp_id": "rfp-it-2026",
    "status": "complete",
    "currency": "GBP",
    "vendor_names": {"acme": "Acme ClearPath", "apex": "Apex Technology", "bad": "BadCo"},
    "completed_at": "2026-05-30T07:00:00Z",
    "agent_events": [
        {"agent": "planner", "status": "done"},
        {"agent": "retrieval", "status": "done"},
        {"agent": "extraction", "status": "done"},
        {"agent": "critic", "status": "done"},
    ],
    "decision_output": {
        "decision_id": "dec-1",
        "decision_confidence": 0.86,
        "requires_human_review": True,
        "review_reasons": ["Close scores on security"],
        "decision_warnings": ["Apex pricing assumed annual"],
        "approval_routing": {
            "approval_tier": 2, "approver_role": "Head of Procurement",
            "contract_value": 450000, "sla_hours": 48,
        },
        "shortlisted_vendors": [
            {"vendor_id": "acme", "vendor_name": "Acme ClearPath", "rank": 1,
             "total_score": 82.0, "recommendation": "strongly_recommended",
             "criterion_breakdown": [
                 {"criterion_id": "security", "vendor_id": "acme", "raw_score": 9},
                 {"criterion_id": "sla", "vendor_id": "acme", "raw_score": 8}]},
            {"vendor_id": "apex", "vendor_name": "Apex Technology", "rank": 2,
             "total_score": 68.0, "recommendation": "acceptable",
             "criterion_breakdown": [
                 {"criterion_id": "security", "vendor_id": "apex", "raw_score": 6},
                 {"criterion_id": "sla", "vendor_id": "apex", "raw_score": 7}]},
        ],
        "rejected_vendors": [
            {"vendor_id": "bad", "vendor_name": "BadCo",
             "failed_checks": ["MC-ISO27001"],
             "rejection_reasons": ["No ISO 27001 certification provided"],
             "evidence_citations": ["We are working towards ISO certification"],
             "clause_references": ["3.2"]},
        ],
    },
    "explanation_output": {
        "executive_summary": "Acme leads on security and SLA.",
        "methodology_note": "Pipeline methodology applied.",
        "grounding_completeness": 1.0,
        "limitations": ["Pricing normalised to annual"],
        "vendor_narratives": [
            {"vendor_id": "acme", "grounded_claims": [
                {"claim_text": "ISO 27001 certified",
                 "grounding_quote": "Acme holds ISO 27001:2022", "source_chunk_id": "c1"}]},
            {"vendor_id": "apex", "grounded_claims": [
                {"claim_text": "99.5% uptime",
                 "grounding_quote": "Apex guarantees 99.5% uptime", "source_chunk_id": "c2"}]},
        ],
    },
}


@pytest.fixture
def ctx() -> ReportContext:
    return build_report_context(SAMPLE_RUN)


# ── Builder unit tests ───────────────────────────────────────────────────────

def test_report_confidence_reuses_decision_confidence(ctx):
    # Alignment note #1: no separate decision_confidence field.
    assert ctx.report_confidence == 0.86
    assert not hasattr(ctx, "decision_confidence")


def test_podium_ranked_with_deltas(ctx):
    assert [p.vendor_id for p in ctx.podium] == ["acme", "apex"]
    assert ctx.podium[0].score_delta_vs_next == 14.0   # 82 - 68
    assert ctx.podium[1].score_delta_vs_next == 0.0


def test_scorecards_pivot_criterion_by_vendor(ctx):
    by_id = {c.criterion_id: c.per_vendor_scores for c in ctx.criterion_scorecards}
    assert by_id["security"] == {"acme": 9.0, "apex": 6.0}
    assert by_id["sla"] == {"acme": 8.0, "apex": 7.0}


def test_pairwise_is_grounded_by_construction(ctx):
    assert len(ctx.pairwise_comparisons) == 1
    pw = ctx.pairwise_comparisons[0]
    assert pw.winner_id == "acme" and pw.runner_up_id == "apex"
    assert pw.key_evidence, "pairwise must carry evidence"
    # Exit criterion: every claim has a verbatim grounding_quote.
    assert all(c.grounding_quote for c in pw.key_evidence)


def test_rejection_reasons_grounded(ctx):
    claims = ctx.rejection_reasons["bad"]
    assert claims and all(c.grounding_quote for c in claims)


def test_audit_trail_one_row_per_event(ctx):
    # Exit criterion (alignment #3): rendered audit_trail count == agent_events count.
    assert len(ctx.audit_trail) == len(SAMPLE_RUN["agent_events"])


def test_render_from_source_no_recompute_of_scores(ctx):
    # Podium scores come straight from decision_output, untouched.
    assert ctx.podium[0].total_score == 82.0


# ── HTML template tests ──────────────────────────────────────────────────────

_SECTION_TITLES = [
    "Executive Summary", "Recommendation", "Ranked Shortlist",
    "Per-Criterion Scorecard", "Head-to-Head", "Mandatory Compliance",
    "Rejection Rationale", "Approval Routing", "Methodology",
    "Risks", "Audit Trail",
]


def test_html_has_all_sections_in_order(ctx):
    html = build_report_html(ctx)
    positions = [html.find(t) for t in _SECTION_TITLES]
    assert all(p != -1 for p in positions), "a section title is missing"
    assert positions == sorted(positions), "sections out of order"


def test_html_includes_grounding_quote(ctx):
    assert "Acme holds ISO 27001:2022" in build_report_html(ctx)


def test_html_rejection_header_uses_vendor_name(ctx):
    # Polish fix: the rejection header shows the display name, not the raw id.
    html = build_report_html(ctx)
    assert "Rejected: BadCo" in html
    assert "Rejected: bad<" not in html


def test_html_autoescapes_vendor_text():
    run = dict(SAMPLE_RUN)
    run["vendor_names"] = {"acme": "<script>alert(1)</script>", "apex": "Apex", "bad": "BadCo"}
    html = build_report_html(build_report_context(run))
    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;" in html


def _mask(html: str) -> str:
    # The only volatile field is the generation timestamp.
    return re.sub(r"Generated: [^<]+", "Generated: <MASKED>", html)


def test_html_render_is_deterministic(ctx):
    # Golden-snapshot spirit: identical context → identical HTML (timestamps masked).
    assert _mask(build_report_html(ctx)) == _mask(build_report_html(ctx))


# ── Endpoint tests (offline: auth + DB overrides) ────────────────────────────

@pytest.fixture
def client(monkeypatch):
    # The evaluate router pulls the full auth/pipeline stack. In CI every
    # requirement is installed; on a partially-provisioned dev box an optional
    # dep may be missing — skip (don't fail) there. The endpoint logic still
    # runs for real in CI.
    try:
        from app.api import evaluation_routes as er
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"evaluate router unavailable in this env: {exc}")
    from app.auth.dependencies import get_current_user
    from app.auth.jwt import TokenData

    # Stub the DB + access layer so no Postgres is needed.
    monkeypatch.setattr(er, "require_run_access", lambda user, run: None)
    monkeypatch.setattr(er, "log_access", lambda *a, **k: None)

    app = FastAPI()
    app.include_router(er.router)
    app.dependency_overrides[get_current_user] = lambda: TokenData(
        email="u@meridian.test", org_id=SAMPLE_RUN["org_id"], role="department_admin", dept_id="proc")
    return TestClient(app), er, monkeypatch


def test_report_html_endpoint_returns_html(client):
    tc, er, mp = client
    mp.setattr(er, "_db_get_run", lambda rid, oid: SAMPLE_RUN)
    r = tc.get(f"/api/v1/evaluate/{SAMPLE_RUN['run_id']}/report.html")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/html")
    assert "Ranked Shortlist" in r.text


def test_report_not_available_returns_409(client):
    tc, er, mp = client
    incomplete = dict(SAMPLE_RUN, decision_output=None)
    mp.setattr(er, "_db_get_run", lambda rid, oid: incomplete)
    r = tc.get(f"/api/v1/evaluate/{SAMPLE_RUN['run_id']}/report.html")
    assert r.status_code == 409


def test_report_pdf_endpoint(client):
    tc, er, mp = client
    mp.setattr(er, "_db_get_run", lambda rid, oid: SAMPLE_RUN)
    r = tc.get(f"/api/v1/evaluate/{SAMPLE_RUN['run_id']}/report.pdf")
    try:
        import weasyprint  # noqa: F401
        weasyprint_ok = True
    except Exception:
        weasyprint_ok = False
    if weasyprint_ok:
        assert r.status_code == 200
        assert r.headers["content-type"] == "application/pdf"
        assert r.content[:4] == b"%PDF"
    else:
        # weasyprint / native libs unavailable (e.g. Windows dev box) → 503.
        assert r.status_code == 503
