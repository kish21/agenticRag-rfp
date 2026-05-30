"""
Phase 8b Step 1 — delivery service + payload bridge (offline).

The delivery module's public API: build a DeliveryPayload from a run, then
deliver it to recipients via channels. No network (fake SMTP), no Postgres.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.delivery.payload import build_payload_from_run  # noqa: E402
from app.delivery.service import deliver_report_for_run  # noqa: E402

# A completed run row (subset of what _db_get_run returns) — enough for the report.
RUN = {
    "run_id": "11111111-1111-1111-1111-111111111111",
    "rfp_title": "IT Managed Services 2026",
    "rfp_id": "rfp-it-2026",
    "vendor_names": {"acme": "Acme ClearPath", "apex": "Apex Technology"},
    "completed_at": "2026-05-30T07:00:00Z",
    "agent_events": [{"agent": "planner", "status": "done"}],
    "decision_output": {
        "decision_id": "dec-1", "decision_confidence": 0.86,
        "approval_routing": {"approval_tier": 2},
        "shortlisted_vendors": [
            {"vendor_id": "acme", "vendor_name": "Acme ClearPath", "rank": 1,
             "total_score": 82.0, "recommendation": "strongly_recommended",
             "criterion_breakdown": [{"criterion_id": "security", "vendor_id": "acme", "raw_score": 9}]},
        ],
        "rejected_vendors": [],
    },
    "explanation_output": {"executive_summary": "Acme leads.", "grounding_completeness": 1.0,
                           "vendor_narratives": []},
}


# ── payload bridge ───────────────────────────────────────────────────────────

def test_build_payload_from_run():
    p = build_payload_from_run(RUN)
    assert p.run_id == RUN["run_id"]
    assert p.rfp_title == "IT Managed Services 2026"
    assert "Acme ClearPath" in p.summary           # winner declaration
    assert "Ranked Shortlist" in p.html_body       # the real report HTML
    assert p.filename.startswith("evaluation-report-")
    # pdf_bytes is bytes where weasyprint is present, else None — both valid.
    assert p.pdf_bytes is None or p.pdf_bytes[:4] == b"%PDF"


# ── service: deliver to channels ─────────────────────────────────────────────

def test_deliver_to_folder(tmp_path):
    results = deliver_report_for_run(RUN, [{"channel": "folder", "path": str(tmp_path / "acme")}])
    assert len(results) == 1 and results[0].ok
    assert Path(results[0].target).exists()


class _FakeSMTP:
    sent: list = []
    def __init__(self, *a, **k): pass
    def __enter__(self): return self
    def __exit__(self, *a): return False
    def starttls(self): pass
    def login(self, *a): pass
    def send_message(self, msg): _FakeSMTP.sent.append(msg)


def test_deliver_to_email(monkeypatch):
    _FakeSMTP.sent.clear()
    monkeypatch.setenv("SMTP_HOST", "smtp.test")
    monkeypatch.setenv("SMTP_USERNAME", "reports@meridian.test")
    monkeypatch.setattr("app.delivery.email_smtp.smtplib.SMTP", _FakeSMTP)

    results = deliver_report_for_run(RUN, [{"channel": "email", "email": "cfo@acme.com"}])
    assert len(results) == 1 and results[0].ok
    assert len(_FakeSMTP.sent) == 1
    assert _FakeSMTP.sent[0]["To"] == "cfo@acme.com"


def test_deliver_to_multiple_recipients(tmp_path):
    results = deliver_report_for_run(RUN, [
        {"channel": "folder", "path": str(tmp_path / "a")},
        {"channel": "folder", "path": str(tmp_path / "b")},
    ])
    assert len(results) == 2 and all(r.ok for r in results)


def test_unknown_channel_yields_failure_not_raise(tmp_path):
    results = deliver_report_for_run(RUN, [{"channel": "carrier-pigeon", "email": "x@y"}])
    assert len(results) == 1 and not results[0].ok
    assert "Unknown delivery channel" in results[0].error


def test_no_recipients_returns_empty():
    assert deliver_report_for_run(RUN, []) == []
