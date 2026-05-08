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
