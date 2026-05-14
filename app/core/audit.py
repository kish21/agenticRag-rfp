"""
Append-only audit log writer.

Usage:
    from app.core.audit import audit

    audit(
        org_id     = user.org_id,
        run_id     = run_id,
        event_type = "run.created",
        actor      = user.email,
        detail     = {"rfp_title": rfp_title, "vendor_count": 2},
    )

Rules:
- Never UPDATE or DELETE rows in audit_log.
- Failures are swallowed so they never kill the main request.
- agent= is only set for agent.* events.
"""
import json
import logging
from typing import Any

import sqlalchemy as sa

from app.db.fact_store import get_engine

log = logging.getLogger(__name__)

# Valid event types — extend here as new flows are added
EVENTS = {
    "run.created",       # user uploaded RFP + vendor files
    "run.confirmed",     # user approved the setup and started the pipeline
    "run.completed",     # pipeline finished successfully
    "run.blocked",       # pipeline blocked by critic or agent failure
    "run.interrupted",   # server restarted mid-run
    "agent.started",     # individual agent began
    "agent.completed",   # individual agent finished
    "agent.blocked",     # individual agent failed
    "override.submitted",# human overrode an agent decision
    "approval.requested",# approval workflow triggered
    "approval.responded",# approver accepted or rejected
    "retrieval_critic.verdict",  # retrieval critic judged chunk adequacy
    "extraction_critic.verdict", # extraction critic judged a single extracted fact
}


def audit(
    org_id:     str,
    event_type: str,
    actor:      str = "system",
    run_id:     str | None = None,
    agent:      str | None = None,
    detail:     dict[str, Any] | None = None,
) -> None:
    """
    Insert one immutable row into audit_log.
    Never raises — swallows all errors to avoid killing the caller.
    """
    if event_type not in EVENTS:
        log.warning("audit: unknown event_type %r — writing anyway", event_type)
    try:
        engine = get_engine()
        with engine.begin() as conn:
            conn.execute(
                sa.text("""
                    INSERT INTO audit_log
                        (org_id, run_id, event_type, actor, agent, detail)
                    VALUES
                        (CAST(:org_id AS uuid),
                         CAST(:run_id AS uuid),
                         :event_type, :actor, :agent,
                         CAST(:detail AS jsonb))
                """),
                {
                    "org_id":     org_id,
                    "run_id":     run_id,
                    "event_type": event_type,
                    "actor":      actor,
                    "agent":      agent,
                    "detail":     json.dumps(detail or {}),
                },
            )
    except Exception as exc:
        log.error("audit write failed: %s", exc)


def log_retrieval(
    *,
    org_id:             str,
    vendor_id:          str,
    query_text:         str,
    retrieval_strategy: str,
    chunks:             list,
    run_id:             str | None = None,
    criterion_id:       str | None = None,
    rewritten_query:    str | None = None,
    scores:             dict | None = None,
    timing_ms:          int | None = None,
) -> None:
    """
    Insert one row into retrieval_log.
    Never raises — swallows errors to avoid killing the caller.
    """
    try:
        chunk_rows = [
            {
                "chunk_id":   c.chunk_id if hasattr(c, "chunk_id") else c.get("chunk_id", ""),
                "text":       (c.text if hasattr(c, "text") else c.get("text", ""))[:500],
                "score":      c.final_score if hasattr(c, "final_score") else c.get("score", 0.0),
                "page":       c.page_number if hasattr(c, "page_number") else c.get("page_number"),
                "filename":   c.filename if hasattr(c, "filename") else c.get("filename", ""),
            }
            for c in chunks
        ]
        engine = get_engine()
        with engine.begin() as conn:
            conn.execute(
                sa.text("""
                    INSERT INTO retrieval_log
                        (run_id, org_id, vendor_id, criterion_id,
                         query_text, rewritten_query, retrieval_strategy,
                         chunks, scores, timing_ms)
                    VALUES
                        (CAST(:run_id AS uuid),
                         CAST(:org_id AS uuid),
                         :vendor_id, :criterion_id,
                         :query_text, :rewritten_query, :retrieval_strategy,
                         CAST(:chunks AS jsonb),
                         CAST(:scores AS jsonb),
                         :timing_ms)
                """),
                {
                    "run_id":             run_id,
                    "org_id":             org_id,
                    "vendor_id":          vendor_id,
                    "criterion_id":       criterion_id,
                    "query_text":         query_text,
                    "rewritten_query":    rewritten_query,
                    "retrieval_strategy": retrieval_strategy,
                    "chunks":             json.dumps(chunk_rows),
                    "scores":             json.dumps(scores or {}),
                    "timing_ms":          timing_ms,
                },
            )
    except Exception as exc:
        log.error("log_retrieval write failed: %s", exc)
