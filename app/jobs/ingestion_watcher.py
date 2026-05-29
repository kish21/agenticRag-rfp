"""
Phase 5 receive-only watcher service.

Watches `{drops_root}/{rfp_id}/{vendor_id}/*` for new files and inserts an
`ingestion_jobs` row per file. Does NOT trigger LLM, Qdrant, or extraction
work — that is the deadline_processor's job (PR-D).

Run:
    python -m app.jobs.ingestion_watcher

Architecture:
- `handle_dropped_file()` is the **pure entry point** — given a file path on
  disk it does SHA256, attribution, DB writes, and returns a typed result.
  Tests drive this directly without spawning watchdog.
- `IngestionEventHandler` is the thin watchdog wrapper that calls into
  `handle_dropped_file()` on filesystem events.
- `main()` configures the observer for every immediate child of drops_root
  and survives PostgreSQL reconnects via on-demand engine resolution.
"""
from __future__ import annotations

import asyncio
import hashlib
import logging
import signal
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import sqlalchemy as sa
from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer

from app.config import settings
from app.db.fact_store import (
    enqueue_ingestion_job,
    get_engine,
    get_rfp_lifecycle,
    is_invited_vendor,
    supersede_prior_received,
)

logger = logging.getLogger("phase5.watcher")


# ── Result type ──────────────────────────────────────────────────────


@dataclass(frozen=True)
class IngestionResult:
    """What the watcher produced for a single dropped file."""

    status: str            # one of the ingestion_jobs status enum values
    job_id: Optional[str]
    rfp_id: Optional[str]
    vendor_id: Optional[str]
    reason: str            # human-readable for logs / admin queue


# ── Helpers ──────────────────────────────────────────────────────────


def _sha256_of_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _parse_drop_path(path: Path) -> tuple[Optional[str], Optional[str]]:
    """
    Returns (rfp_id, vendor_id) parsed from a path of the form
    `{drops_root}/{rfp_id}/{vendor_id}/<file>` or `{drops_root}/{rfp_id}/<file>`.
    vendor_id is None if the file sat at the rfp_id root.
    """
    drops_root = Path(settings.platform.ingestion.drops_root).resolve()
    try:
        rel = path.resolve().relative_to(drops_root)
    except ValueError:
        return None, None
    parts = rel.parts
    if len(parts) == 2:
        return parts[0], None          # rfp_id root drop
    if len(parts) >= 3:
        return parts[0], parts[1]
    return None, None


# ── Pure entry point — tests call this directly ─────────────────────


def handle_dropped_file(path: Path) -> IngestionResult:
    """
    Process a single dropped file synchronously.

    Order of checks (any failing one short-circuits to the right job status):
      1. Path parses to (rfp_id, vendor_id?). Otherwise: ignored.
      2. RFP exists.                       Otherwise: `needs_attribution`.
      3. submission_status is one of {open}.
         - 'open' beyond deadline → also rejected_late
         - 'closed'/'processing'/'facts_ready'/'evaluated' → 'rejected_late'
      4. vendor_id known: must be in invited_vendors.
         vendor_id absent: requires LLM attribution (PR-C: enqueued as
         `needs_attribution`; LLM is invoked asynchronously by the
         attribution_resolver — separate code path).
      5. INSERT ingestion_jobs(status='received').
      6. If a prior 'received' row exists for (rfp_id, vendor_id), mark it
         superseded → new row stays the active one.
    """
    rfp_id, vendor_id = _parse_drop_path(path)
    if rfp_id is None:
        return IngestionResult("ignored", None, None, None, "path outside drops_root")

    rfp = get_rfp_lifecycle(rfp_id=rfp_id)
    if rfp is None:
        return IngestionResult(
            "needs_attribution",
            _enqueue_orphan(path, rfp_id, vendor_id, reason="unknown rfp_id"),
            rfp_id, vendor_id,
            "rfp_id has no rfps row",
        )

    # Deadline + lifecycle gate
    if rfp["submission_status"] != "open":
        return _enqueue_terminal(
            path, rfp_id, vendor_id or "_unknown_", rfp["org_id"],
            status="rejected_late",
            reason=f"submission_status={rfp['submission_status']}",
        )
    deadline = rfp["submission_deadline"]
    if deadline is not None and _aware(deadline) < datetime.now(timezone.utc):
        return _enqueue_terminal(
            path, rfp_id, vendor_id or "_unknown_", rfp["org_id"],
            status="rejected_late",
            reason="past deadline",
        )

    # Path-derived vendor: must be invited.
    if vendor_id is not None:
        if not is_invited_vendor(rfp_id=rfp_id, vendor_id=vendor_id):
            return _enqueue_terminal(
                path, rfp_id, vendor_id, rfp["org_id"],
                status="needs_attribution",
                reason="vendor_id not in invited_vendors",
            )
        return _ingest_received(path, rfp_id, vendor_id, rfp["org_id"])

    # No vendor folder → defer to LLM attribution queue.
    return _enqueue_terminal(
        path, rfp_id, "_unknown_", rfp["org_id"],
        status="needs_attribution",
        reason="file dropped at rfp_id root; requires LLM attribution",
    )


def _aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _enqueue_orphan(path: Path, rfp_id: str, vendor_id: Optional[str], reason: str) -> Optional[str]:
    """
    Orphan = unknown rfp_id. We have no org_id to attribute it to, so write
    an event_log row in a system org bucket so admins can review.
    For now we return None — true orphan files are NOT inserted into
    ingestion_jobs because the FK contract requires a known org_id.
    """
    logger.warning("Orphan drop ignored: %s — %s", path, reason)
    return None


def _ingest_received(
    path: Path, rfp_id: str, vendor_id: str, org_id: str
) -> IngestionResult:
    """The happy path: known RFP, open window, invited vendor."""
    content_hash = _sha256_of_file(path)
    job_id = enqueue_ingestion_job(
        org_id=org_id,
        rfp_id=rfp_id,
        vendor_id=vendor_id,
        content_hash=content_hash,
        filename=path.name,
        source_uri=str(path),
        status="received",
    )
    if job_id is None:
        return IngestionResult(
            "duplicate", None, rfp_id, vendor_id,
            "identical content_hash already received",
        )
    superseded = supersede_prior_received(
        rfp_id=rfp_id, vendor_id=vendor_id, new_job_id=job_id,
    )
    msg = "received" if superseded == 0 else f"received (superseded {superseded} prior)"
    return IngestionResult("received", job_id, rfp_id, vendor_id, msg)


def _enqueue_terminal(
    path: Path,
    rfp_id: str,
    vendor_id: str,
    org_id: str,
    *,
    status: str,
    reason: str,
) -> IngestionResult:
    """Insert a terminal-status row (rejected_late / needs_attribution)."""
    content_hash = _sha256_of_file(path)
    job_id = enqueue_ingestion_job(
        org_id=org_id,
        rfp_id=rfp_id,
        vendor_id=vendor_id,
        content_hash=content_hash,
        filename=path.name,
        source_uri=str(path),
        status=status,
    )
    return IngestionResult(
        status, job_id, rfp_id, vendor_id if vendor_id != "_unknown_" else None,
        reason,
    )


# ── watchdog wrapper ─────────────────────────────────────────────────


class IngestionEventHandler(FileSystemEventHandler):
    """Reacts to file creation events; ignores directory events + moves."""

    def __init__(self) -> None:
        super().__init__()

    def on_created(self, event: FileSystemEvent) -> None:
        if event.is_directory:
            return
        path = Path(str(event.src_path))
        # Brief settle delay so partially-written files don't get hashed.
        time.sleep(0.25)
        if not path.exists():
            return
        try:
            result = handle_dropped_file(path)
            logger.info(
                "drop %s -> status=%s rfp=%s vendor=%s reason=%s",
                path.name, result.status, result.rfp_id, result.vendor_id, result.reason,
            )
        except sa.exc.OperationalError as exc:
            # PG reconnect race — retry once after a short backoff.
            logger.warning("DB error on %s: %s — retrying once", path, exc)
            time.sleep(1.0)
            try:
                handle_dropped_file(path)
            except Exception as exc2:  # pragma: no cover
                logger.error("Retry failed for %s: %s", path, exc2)
        except Exception as exc:  # pragma: no cover — log + continue
            logger.exception("Unexpected error processing %s: %s", path, exc)


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s — %(message)s",
    )
    drops_root = Path(settings.platform.ingestion.drops_root).resolve()
    drops_root.mkdir(parents=True, exist_ok=True)
    logger.info("Watching %s (recursive)", drops_root)

    handler = IngestionEventHandler()
    observer = Observer()
    observer.schedule(handler, str(drops_root), recursive=True)
    observer.start()

    stop = asyncio.Event()

    def _shutdown(*_args: object) -> None:
        logger.info("Shutdown signal received")
        stop.set()

    signal.signal(signal.SIGINT, _shutdown)
    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, _shutdown)

    try:
        while not stop.is_set():
            time.sleep(0.5)
    finally:
        observer.stop()
        observer.join(timeout=5.0)
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
