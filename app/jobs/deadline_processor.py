"""
Phase 5 deadline processor — Modal cron, runs every 5 minutes.

Atomically advances RFPs through the submission lifecycle:

    open  --(deadline passed)-->  closed
    closed --(jobs queued)-->     processing
    processing --(all jobs done)--> facts_ready

For autonomy_mode='auto_to_evaluate' (default): stops at facts_ready and
emits a `rfp.facts_ready` event for Phase 8 delivery channels to consume.

For autonomy_mode='auto_to_report': SCHEMA accepts this value, but the
scheduler emits `rfp.evaluation_failed` reason 'Phase 7 PDF not yet
implemented' until Phase 7 ships. Status still advances to facts_ready.

For autonomy_mode='manual': COMPLETELY SKIPPED. Files stay in 'received'
until the customer clicks Evaluate via the existing /api/v1/evaluate/start
manual upload path.
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Optional

import sqlalchemy as sa

from app.db.fact_store import emit_event, get_engine
from app.pipeline.ingestion_graph import IngestionAgents, process_job

logger = logging.getLogger("phase5.deadline_processor")


# ── Tick result ──────────────────────────────────────────────────────


@dataclass
class TickReport:
    rfps_closed: int = 0
    rfps_queued_for_processing: int = 0
    rfps_facts_ready: int = 0
    jobs_processed: int = 0
    jobs_failed: int = 0
    events_emitted: int = 0


# ── Pure tick entry point ────────────────────────────────────────────


async def tick(*, agents: IngestionAgents) -> TickReport:
    """
    One scheduler iteration. Idempotent and safe to call concurrently
    (every state-changing query is conditional on the prior status).
    """
    report = TickReport()
    report.rfps_closed = _close_expired_rfps()
    report.rfps_queued_for_processing = _queue_received_jobs()
    queued = _list_queued_jobs()
    if queued:
        report.jobs_processed, report.jobs_failed = await _process_jobs_in_parallel(
            queued, agents,
        )
    report.rfps_facts_ready, report.events_emitted = _finalize_completed_rfps()
    return report


# ── Lifecycle transitions ────────────────────────────────────────────


def _close_expired_rfps() -> int:
    """open -> closed for RFPs past deadline.
    Excludes autonomy_mode='manual' (those stay open forever from the
    scheduler's POV; the customer drives them manually)."""
    engine = get_engine()
    with engine.begin() as conn:
        result = conn.execute(
            sa.text(
                """
                UPDATE rfps
                SET submission_status = 'closed'
                WHERE submission_status = 'open'
                  AND submission_deadline IS NOT NULL
                  AND submission_deadline < now()
                  AND autonomy_mode <> 'manual'
                """
            )
        )
        return result.rowcount


def _queue_received_jobs() -> int:
    """For every RFP newly in 'closed', queue all its 'received' jobs and
    flip the RFP to 'processing'. Returns the number of RFPs advanced."""
    engine = get_engine()
    advanced = 0
    with engine.begin() as conn:
        closed_rfps = conn.execute(
            sa.text(
                "SELECT rfp_id FROM rfps WHERE submission_status = 'closed' "
                "AND autonomy_mode <> 'manual'"
            )
        ).fetchall()
        for row in closed_rfps:
            conn.execute(
                sa.text(
                    """
                    UPDATE ingestion_jobs SET status = 'queued'
                    WHERE rfp_id = :r AND status = 'received'
                    """
                ),
                {"r": row.rfp_id},
            )
            conn.execute(
                sa.text(
                    """
                    UPDATE rfps SET submission_status = 'processing'
                    WHERE rfp_id = :r AND submission_status = 'closed'
                    """
                ),
                {"r": row.rfp_id},
            )
            advanced += 1
    return advanced


def _list_queued_jobs() -> list[str]:
    engine = get_engine()
    with engine.connect() as conn:
        rows = conn.execute(
            sa.text(
                "SELECT job_id::text AS job_id FROM ingestion_jobs "
                "WHERE status = 'queued'"
            )
        ).fetchall()
    return [r.job_id for r in rows]


async def _process_jobs_in_parallel(
    job_ids: list[str], agents: IngestionAgents
) -> tuple[int, int]:
    results = await asyncio.gather(
        *(process_job(job_id=jid, agents=agents) for jid in job_ids),
        return_exceptions=False,
    )
    ok = sum(1 for r in results if r.status == "facts_ready")
    fail = sum(1 for r in results if r.status == "failed")
    return ok, fail


def _finalize_completed_rfps() -> tuple[int, int]:
    """
    For every RFP whose ingestion_jobs are all in terminal states
    (facts_ready / duplicate / superseded / failed / needs_attribution /
    rejected_late) AND at least one is 'facts_ready', flip RFP to
    'facts_ready' and emit the lifecycle event.

    Returns (rfps_finalized, events_emitted).
    """
    engine = get_engine()
    finalized = 0
    events = 0
    with engine.begin() as conn:
        candidates = conn.execute(
            sa.text(
                """
                SELECT rfp_id, org_id::text AS org_id, autonomy_mode
                FROM rfps
                WHERE submission_status = 'processing'
                """
            )
        ).fetchall()
        for r in candidates:
            counts = conn.execute(
                sa.text(
                    """
                    SELECT
                      COUNT(*) FILTER (WHERE status IN
                          ('received','queued','processing'))            AS open_jobs,
                      COUNT(*) FILTER (WHERE status = 'facts_ready')     AS ready_jobs
                    FROM ingestion_jobs WHERE rfp_id = :r
                    """
                ),
                {"r": r.rfp_id},
            ).fetchone()
            if counts.open_jobs > 0:
                continue
            if counts.ready_jobs == 0:
                # All jobs ended in non-success terminal states; do not
                # advance — admin needs to triage.
                continue

            conn.execute(
                sa.text(
                    "UPDATE rfps SET submission_status = 'facts_ready' "
                    "WHERE rfp_id = :r AND submission_status = 'processing'"
                ),
                {"r": r.rfp_id},
            )
            finalized += 1
        # Emit events OUTSIDE the candidates loop so the UPDATE commit happens
        # before downstream readers (event_log already commits per-row).

    # Second pass for events — separate txn so emit_event's own commit is clean.
    with engine.connect() as conn:
        ready = conn.execute(
            sa.text(
                """
                SELECT rfp_id, org_id::text AS org_id, autonomy_mode
                FROM rfps
                WHERE submission_status = 'facts_ready'
                  AND NOT EXISTS (
                    SELECT 1 FROM event_log e
                    WHERE e.rfp_id = rfps.rfp_id
                      AND e.event_type IN ('rfp.facts_ready','rfp.evaluation_failed')
                  )
                """
            )
        ).fetchall()

    for r in ready:
        if r.autonomy_mode == "auto_to_report":
            # Phase 7 not yet implemented — emit failure event and stop.
            emit_event(
                event_type="rfp.evaluation_failed",
                org_id=r.org_id,
                rfp_id=r.rfp_id,
                payload={"reason": "Phase 7 PDF not yet implemented"},
            )
        else:
            emit_event(
                event_type="rfp.facts_ready",
                org_id=r.org_id,
                rfp_id=r.rfp_id,
                payload={"autonomy_mode": r.autonomy_mode},
            )
        events += 1
    return finalized, events


# ── Main loop (for local + Modal cron invocation) ────────────────────


async def main_once() -> TickReport:
    from app.pipeline.ingestion_graph import real_agents  # local import

    return await tick(agents=real_agents())


if __name__ == "__main__":  # pragma: no cover
    logging.basicConfig(level=logging.INFO)
    report = asyncio.run(main_once())
    logger.info("Deadline tick report: %s", report)
