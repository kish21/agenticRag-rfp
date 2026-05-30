"""
SMTP email delivery channel.

Sends the report as an HTML email with the PDF attached. Config is read from
the environment so a customer just sets these in `.env` (e.g. Hostinger mail):

    SMTP_HOST       smtp.hostinger.com
    SMTP_PORT       587
    SMTP_USERNAME   reports@yourdomain.com
    SMTP_PASSWORD   ********
    SMTP_FROM       reports@yourdomain.com   (defaults to SMTP_USERNAME)
    SMTP_USE_TLS    true                     (STARTTLS on 587; SMTP_SSL on 465)

`build_email_message()` is pure (no network) so it is unit-testable; `dispatch()`
adds the actual send.
"""
from __future__ import annotations

import os
import smtplib
from email.message import EmailMessage
from typing import Any

from app.delivery.base import DeliveryChannel, DeliveryPayload, DeliveryResult


def _smtp_config() -> dict[str, Any]:
    port = int(os.getenv("SMTP_PORT", "587"))
    username = os.getenv("SMTP_USERNAME", "")
    return {
        "host": os.getenv("SMTP_HOST", ""),
        "port": port,
        "username": username,
        "password": os.getenv("SMTP_PASSWORD", ""),
        "from_addr": os.getenv("SMTP_FROM", "") or username,
        "use_tls": os.getenv("SMTP_USE_TLS", "true").lower() != "false",
        "use_ssl": port == 465,
    }


def build_email_message(payload: DeliveryPayload, to_addr: str, from_addr: str) -> EmailMessage:
    """Build the MIME message: HTML body (report) + plain-text fallback, with the
    PDF attached when present. Pure — no network."""
    msg = EmailMessage()
    msg["Subject"] = f"Evaluation report — {payload.rfp_title}"
    msg["From"] = from_addr
    msg["To"] = to_addr

    msg.set_content(payload.summary or f"Evaluation report for {payload.rfp_title} attached.")
    if payload.html_body:
        msg.add_alternative(payload.html_body, subtype="html")

    if payload.pdf_bytes:
        msg.add_attachment(
            payload.pdf_bytes,
            maintype="application",
            subtype="pdf",
            filename=payload.filename,
        )
    return msg


class EmailSmtpChannel(DeliveryChannel):
    name = "email"

    def dispatch(self, payload: DeliveryPayload, target: dict[str, Any]) -> DeliveryResult:
        to_addr = (target or {}).get("email", "").strip()
        if not to_addr:
            return DeliveryResult.failure(self.name, "", "no recipient email in target")

        cfg = _smtp_config()
        if not cfg["host"]:
            return DeliveryResult.failure(self.name, to_addr, "SMTP_HOST not configured")

        try:
            msg = build_email_message(payload, to_addr, cfg["from_addr"] or cfg["username"])
            if cfg["use_ssl"]:
                server = smtplib.SMTP_SSL(cfg["host"], cfg["port"], timeout=30)
            else:
                server = smtplib.SMTP(cfg["host"], cfg["port"], timeout=30)
            with server:
                if cfg["use_tls"] and not cfg["use_ssl"]:
                    server.starttls()
                if cfg["username"]:
                    server.login(cfg["username"], cfg["password"])
                server.send_message(msg)
        except Exception as exc:  # noqa: BLE001 — never raise; the dispatcher retries
            return DeliveryResult.failure(self.name, to_addr, f"{type(exc).__name__}: {exc}")

        return DeliveryResult.success(self.name, to_addr)
