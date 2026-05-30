"""
Bridge: a finished evaluation run → a DeliveryPayload.

This is the single place that turns a run-row dict (as `_db_get_run` returns)
into the report artifacts a channel delivers. It reuses Phase 7's report
builder + renderer, so delivery never re-implements report logic.

`pdf_bytes` is None when weasyprint/native libs are unavailable in the
deployment — channels still deliver the HTML body / summary in that case.
"""
from __future__ import annotations

from app.delivery.base import DeliveryPayload
from app.output.report_builder import build_report_context
from app.output.pdf_report import build_report_html, render_pdf


def build_payload_from_run(run: dict, org_name: str = "Meridian Financial Services") -> DeliveryPayload:
    ctx = build_report_context(run, org_name=org_name)
    html = build_report_html(ctx)

    try:
        pdf: bytes | None = render_pdf(html)
    except RuntimeError:
        pdf = None  # weasyprint/native libs absent — HTML still delivered

    run_id = str(run.get("run_id", ""))
    summary = ctx.winner_declaration or f"Evaluation report for {ctx.rfp_title}."
    return DeliveryPayload(
        run_id=run_id,
        rfp_title=ctx.rfp_title,
        summary=summary,
        html_body=html,
        pdf_bytes=pdf,
        filename=f"evaluation-report-{run_id[:8] or 'report'}.pdf",
    )
