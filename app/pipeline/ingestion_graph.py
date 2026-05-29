"""
Phase 5 ingestion sub-graph.

For each queued ingestion_jobs row, runs the minimal 3-step sub-graph:

    1. plan      — capture (org_id, rfp_id, vendor_id, setup_id snapshot)
    2. ingest    — read file from source_uri, run the ingestion agent,
                   index chunks into Qdrant, write a vendor_documents row.
    3. extract   — run retrieval + extraction agents, write extracted_facts
                   tagged with the setup_id snapshot.

Lives separately from `app/pipeline/graph.py` because:
  - It is triggered by the deadline_processor (Modal cron), not by a user
    clicking Evaluate.
  - It runs at the (rfp_id, vendor_id) grain, not the whole RFP.
  - It does NOT include retrieval refresh, evaluation, comparator, decision,
    explanation, or critic-routing — those are still on the user-triggered
    path in graph.py.

The actual ingestion/extraction agents are injected via the `IngestionAgents`
protocol so tests can substitute fast stubs. Production wiring passes the
real agents at startup.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Awaitable, Callable, Optional, Protocol

import sqlalchemy as sa

from app.db.fact_store import get_engine

logger = logging.getLogger("phase5.ingestion_graph")


# ── Agent contracts (injected) ───────────────────────────────────────


class IngestRunner(Protocol):
    async def __call__(
        self,
        *,
        content: bytes,
        filename: str,
        vendor_id: str,
        org_id: str,
        rfp_id: str,
        setup_id: str,
    ) -> str:
        """Returns the doc_id for the vendor_documents row written."""


class ExtractRunner(Protocol):
    async def __call__(
        self,
        *,
        doc_id: str,
        vendor_id: str,
        org_id: str,
        rfp_id: str,
        setup_id: str,
    ) -> int:
        """Returns the number of extracted_facts rows written."""


@dataclass
class IngestionAgents:
    """Bundle of injected runners. Wire the real agents at startup."""
    ingest: IngestRunner
    extract: ExtractRunner


# ── Per-job state machine ────────────────────────────────────────────


@dataclass(frozen=True)
class JobResult:
    job_id: str
    status: str          # 'facts_ready' | 'failed'
    facts_written: int
    error: Optional[str]
    duration_ms: int


async def process_job(
    *,
    job_id: str,
    agents: IngestionAgents,
) -> JobResult:
    """
    Runs the 3-node sub-graph for ONE ingestion job.

    State transitions (atomic at each step):
      queued -> processing -> facts_ready (happy path)
      queued -> processing -> failed     (on any exception)
    """
    started = time.monotonic()
    job = _claim_for_processing(job_id)
    if job is None:
        return JobResult(job_id, "failed", 0, "job_id not found or not queued", 0)

    try:
        setup_id = _resolve_setup_id(job["rfp_id"])
        if setup_id is None:
            return _mark_failed(job_id, "no evaluation_setup for this rfp_id", started)

        content = _read_source(Path(job["source_uri"]))
        if content is None:
            return _mark_failed(job_id, f"file missing: {job['source_uri']}", started)

        doc_id = await agents.ingest(
            content=content,
            filename=job["filename"] or Path(job["source_uri"]).name,
            vendor_id=job["vendor_id"],
            org_id=job["org_id"],
            rfp_id=job["rfp_id"],
            setup_id=setup_id,
        )

        facts_written = await agents.extract(
            doc_id=doc_id,
            vendor_id=job["vendor_id"],
            org_id=job["org_id"],
            rfp_id=job["rfp_id"],
            setup_id=setup_id,
        )

        duration_ms = int((time.monotonic() - started) * 1000)
        _mark_facts_ready(job_id, doc_id, duration_ms)
        return JobResult(job_id, "facts_ready", facts_written, None, duration_ms)

    except Exception as exc:  # pylint: disable=broad-except
        logger.exception("process_job failed for %s", job_id)
        return _mark_failed(job_id, str(exc), started)


# ── Internals ────────────────────────────────────────────────────────


def _claim_for_processing(job_id: str) -> Optional[dict]:
    """Atomically flips 'queued' -> 'processing' and returns the row."""
    engine = get_engine()
    with engine.begin() as conn:
        row = conn.execute(
            sa.text(
                """
                UPDATE ingestion_jobs
                SET status = 'processing', attempted_at = now()
                WHERE job_id = :j AND status = 'queued'
                RETURNING rfp_id, vendor_id, org_id::text AS org_id,
                          source_uri, filename
                """
            ),
            {"j": job_id},
        ).fetchone()
    if not row:
        return None
    return {
        "rfp_id": row.rfp_id,
        "vendor_id": row.vendor_id,
        "org_id": row.org_id,
        "source_uri": row.source_uri,
        "filename": row.filename,
    }


def _resolve_setup_id(rfp_id: str) -> Optional[str]:
    """Returns the most recent confirmed evaluation_setups.setup_id for the RFP."""
    engine = get_engine()
    with engine.connect() as conn:
        row = conn.execute(
            sa.text(
                """
                SELECT setup_id FROM evaluation_setups
                WHERE rfp_id = :r AND confirmed_at IS NOT NULL
                ORDER BY created_at DESC
                LIMIT 1
                """
            ),
            {"r": rfp_id},
        ).fetchone()
    return row.setup_id if row else None


def _read_source(path: Path) -> Optional[bytes]:
    if not path.exists() or not path.is_file():
        return None
    return path.read_bytes()


def _mark_facts_ready(job_id: str, doc_id: str, duration_ms: int) -> None:
    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(
            sa.text(
                """
                UPDATE ingestion_jobs
                SET status = 'facts_ready', completed_at = now(), doc_id = :d
                WHERE job_id = :j
                """
            ),
            {"j": job_id, "d": doc_id},
        )
    logger.info("job %s -> facts_ready in %dms", job_id, duration_ms)


def _mark_failed(job_id: str, reason: str, started_at: float) -> JobResult:
    duration_ms = int((time.monotonic() - started_at) * 1000)
    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(
            sa.text(
                """
                UPDATE ingestion_jobs
                SET status = 'failed', completed_at = now(), error = :e
                WHERE job_id = :j
                """
            ),
            {"j": job_id, "e": reason[:1000]},
        )
    logger.warning("job %s -> failed: %s", job_id, reason)
    return JobResult(job_id, "failed", 0, reason, duration_ms)


# ── Production wiring helper ─────────────────────────────────────────


def real_agents() -> IngestionAgents:
    """
    Wires the production ingestion + extraction agents. Imported lazily
    so module import does not pull in Qdrant / LLM provider deps.
    """
    from app.agents.ingestion import run_ingestion_agent  # noqa: WPS433
    from app.agents.extraction import run_extraction_agent  # noqa: WPS433
    from app.agents.retrieval import run_retrieval_agent  # noqa: WPS433
    from app.db.fact_store import get_evaluation_setup, save_extraction_output  # noqa: WPS433

    async def _ingest(*, content, filename, vendor_id, org_id, rfp_id, setup_id) -> str:
        setup = get_evaluation_setup(setup_id, org_id=org_id)
        ingestion_out, _critic = await run_ingestion_agent(
            content=content,
            filename=filename,
            vendor_id=vendor_id,
            org_id=org_id,
            rfp_id=rfp_id,
            evaluation_setup=setup,
        )
        return ingestion_out.doc_id

    async def _extract(*, doc_id, vendor_id, org_id, rfp_id, setup_id) -> int:
        setup = get_evaluation_setup(setup_id, org_id=org_id)
        retrieval_out, _crit = await run_retrieval_agent(
            doc_id=doc_id,
            vendor_id=vendor_id,
            org_id=org_id,
            rfp_id=rfp_id,
            evaluation_setup=setup,
        )
        extraction_out, _ec = await run_extraction_agent(
            retrieval_output=retrieval_out,
            vendor_id=vendor_id,
            org_id=org_id,
            doc_id=doc_id,
            setup_id=setup_id,
            evaluation_setup=setup,
        )
        save_extraction_output(extraction_out, doc_id=doc_id)
        n = 0
        for attr in (
            "certifications", "insurance", "slas", "projects", "pricing", "facts",
        ):
            n += len(getattr(extraction_out, attr, []) or [])
        return n

    return IngestionAgents(ingest=_ingest, extract=_extract)
