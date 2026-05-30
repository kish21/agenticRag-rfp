"""
Phase 8a — delivery channel tests (all offline; no real SMTP, no network).

Covers the channel layer: email MIME construction + send (fake SMTP), folder
drop (tmp dir), graceful failures, and the channel registry.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.delivery import get_channel, available_channels, DeliveryPayload  # noqa: E402
from app.delivery.email_smtp import build_email_message, EmailSmtpChannel  # noqa: E402
from app.delivery.folder_drop import FolderDropChannel  # noqa: E402


def _payload(pdf=b"%PDF-1.4 fake") -> DeliveryPayload:
    return DeliveryPayload(
        run_id="run-1", rfp_title="IT Managed Services 2026",
        summary="Acme recommended.", html_body="<html><body>Report</body></html>",
        pdf_bytes=pdf, filename="evaluation-report-run1.pdf",
    )


# ── Email MIME construction (pure) ───────────────────────────────────────────

def test_build_email_message_has_headers_html_and_attachment():
    msg = build_email_message(_payload(), "cfo@acme.com", "reports@meridian.test")
    assert msg["To"] == "cfo@acme.com"
    assert msg["From"] == "reports@meridian.test"
    assert "IT Managed Services 2026" in msg["Subject"]

    parts = list(msg.walk())
    # HTML alternative present
    assert any(p.get_content_type() == "text/html" for p in parts)
    # PDF attachment present with the right filename + bytes
    attachments = [p for p in parts if p.get_content_disposition() == "attachment"]
    assert len(attachments) == 1
    att = attachments[0]
    assert att.get_filename() == "evaluation-report-run1.pdf"
    assert att.get_content_type() == "application/pdf"
    assert att.get_payload(decode=True) == b"%PDF-1.4 fake"


def test_build_email_message_without_pdf_still_builds():
    msg = build_email_message(_payload(pdf=None), "x@y.com", "f@m.com")
    assert not [p for p in msg.walk() if p.get_content_disposition() == "attachment"]
    assert any(p.get_content_type() == "text/html" for p in msg.walk())


# ── Email dispatch (fake SMTP) ───────────────────────────────────────────────

class _FakeSMTP:
    sent: list = []

    def __init__(self, host, port, timeout=0):
        self.host, self.port = host, port

    def __enter__(self): return self
    def __exit__(self, *a): return False
    def starttls(self): self.tls = True
    def login(self, u, p): self.creds = (u, p)
    def send_message(self, msg): _FakeSMTP.sent.append(msg)


def test_email_dispatch_sends_via_smtp(monkeypatch):
    _FakeSMTP.sent.clear()
    monkeypatch.setenv("SMTP_HOST", "smtp.test")
    monkeypatch.setenv("SMTP_PORT", "587")
    monkeypatch.setenv("SMTP_USERNAME", "reports@meridian.test")
    monkeypatch.setenv("SMTP_PASSWORD", "secret")
    monkeypatch.setattr("app.delivery.email_smtp.smtplib.SMTP", _FakeSMTP)

    res = EmailSmtpChannel().dispatch(_payload(), {"email": "cfo@acme.com"})
    assert res.ok and res.target == "cfo@acme.com"
    assert len(_FakeSMTP.sent) == 1
    assert _FakeSMTP.sent[0]["To"] == "cfo@acme.com"


def test_email_dispatch_no_host_fails_gracefully(monkeypatch):
    monkeypatch.delenv("SMTP_HOST", raising=False)
    res = EmailSmtpChannel().dispatch(_payload(), {"email": "x@y.com"})
    assert not res.ok and "SMTP_HOST" in res.error


def test_email_dispatch_no_recipient_fails():
    res = EmailSmtpChannel().dispatch(_payload(), {})
    assert not res.ok and "recipient" in res.error


# ── Folder drop ──────────────────────────────────────────────────────────────

def test_folder_dispatch_writes_pdf(tmp_path):
    res = FolderDropChannel().dispatch(_payload(), {"path": str(tmp_path / "acme")})
    assert res.ok
    out = Path(res.target)
    assert out.exists() and out.read_bytes() == b"%PDF-1.4 fake"
    assert out.name == "evaluation-report-run1.pdf"


def test_folder_dispatch_html_fallback_when_no_pdf(tmp_path):
    res = FolderDropChannel().dispatch(_payload(pdf=None), {"path": str(tmp_path / "acme")})
    assert res.ok
    out = Path(res.target)
    assert out.suffix == ".html" and "Report" in out.read_text(encoding="utf-8")


def test_folder_dispatch_no_path_fails():
    res = FolderDropChannel().dispatch(_payload(), {})
    assert not res.ok and "path" in res.error


# ── Registry ─────────────────────────────────────────────────────────────────

def test_registry_resolves_known_channels():
    assert isinstance(get_channel("email"), EmailSmtpChannel)
    assert isinstance(get_channel("folder"), FolderDropChannel)
    assert set(available_channels()) >= {"email", "folder"}


def test_registry_unknown_channel_raises():
    with pytest.raises(ValueError):
        get_channel("carrier-pigeon")
