"""
Delivery service — the delivery module's single public entry point.

The rest of the app (pipeline, jobs, API) calls ONLY this; it never imports
smtplib, channels, or recipient logic. That keeps delivery a self-contained
module: future subscriptions / dispatcher / extra channels / notifications are
added INSIDE app/delivery without touching the caller.

    from app.delivery.service import deliver_report_for_run
    results = deliver_report_for_run(run, [{"channel": "email", "email": "cfo@acme.com"}])
"""
from __future__ import annotations

from typing import Any

from app.delivery import get_channel
from app.delivery.base import DeliveryResult
from app.delivery.payload import build_payload_from_run


def deliver_report_for_run(
    run: dict,
    recipients: list[dict[str, Any]],
    org_name: str = "Meridian Financial Services",
) -> list[DeliveryResult]:
    """Build the report once, deliver it to each recipient.

    `recipients` is a list of channel targets, e.g.
        [{"channel": "email",  "email": "cfo@acme.com"},
         {"channel": "folder", "path":  "/srv/reports/acme"}]
    Channel defaults to "email". Never raises — each recipient yields a
    DeliveryResult (ok or failure) so the caller can log/retry per recipient.
    """
    if not recipients:
        return []

    payload = build_payload_from_run(run, org_name=org_name)

    results: list[DeliveryResult] = []
    for target in recipients:
        channel_name = target.get("channel", "email")
        try:
            channel = get_channel(channel_name)
        except ValueError as exc:
            addr = str(target.get("email") or target.get("path") or "")
            results.append(DeliveryResult.failure(channel_name, addr, str(exc)))
            continue
        results.append(channel.dispatch(payload, target))
    return results
