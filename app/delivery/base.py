"""Delivery channel contract — the ABC every channel implements."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any


@dataclass
class DeliveryPayload:
    """Everything a channel needs to deliver one report. Bundles the plan's
    (run_id, pdf_bytes, summary, ...) into one object so channels share a stable
    signature as the report grows.

    `pdf_bytes` may be None (e.g. weasyprint unavailable in a deployment); a
    channel should still deliver the HTML body / summary in that case.
    """
    run_id: str
    rfp_title: str
    summary: str                       # short plain-text summary (subject/preview)
    html_body: str = ""                # the full report HTML (email body / preview)
    pdf_bytes: bytes | None = None      # the report PDF (attachment)
    filename: str = "evaluation-report.pdf"


@dataclass
class DeliveryResult:
    ok: bool
    channel: str
    target: str
    error: str = ""

    @classmethod
    def success(cls, channel: str, target: str) -> "DeliveryResult":
        return cls(ok=True, channel=channel, target=target)

    @classmethod
    def failure(cls, channel: str, target: str, error: str) -> "DeliveryResult":
        return cls(ok=False, channel=channel, target=target, error=error)


class DeliveryChannel(ABC):
    """A pluggable delivery destination (email, folder, Teams, …)."""

    #: registry key — must be unique across channels
    name: str = ""

    @abstractmethod
    def dispatch(self, payload: DeliveryPayload, target: dict[str, Any]) -> DeliveryResult:
        """Deliver `payload` to `target`. MUST NOT raise — capture failures in
        the returned DeliveryResult so the dispatcher can record + retry."""
        raise NotImplementedError
