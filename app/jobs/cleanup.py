import datetime
import sqlalchemy as sa
from sqlalchemy.engine import Engine

from app.retrieval.qdrant import delete_setup_data
from app.providers.observability import log_evaluation_run


_DEFAULT_RETENTION_DAYS = 90


async def run_cleanup(engine: Engine, retention_days: int = _DEFAULT_RETENTION_DAYS) -> dict:
    """
    Deletes Qdrant vectors and PostgreSQL rows for expired evaluations.
    Retention period: retention_days (default 90). Run daily via Modal.
    Returns a summary dict for LangFuse logging.
    """
    cutoff = datetime.datetime.utcnow() - datetime.timedelta(days=retention_days)
    deleted_collections: list[str] = []
    purged_setups: int = 0
    deleted_points: int = 0
    deleted_pg_rows: int = 0
    failed_setups: int = 0

    with engine.connect() as conn:
        # Find expired setups
        rows = conn.execute(
            sa.text(
                "SELECT setup_id, org_id FROM evaluation_setups "
                "WHERE created_at < :cutoff"
            ),
            {"cutoff": cutoff},
        ).fetchall()

        for row in rows:
            setup_id, org_id = row.setup_id, row.org_id

            # Per-setup precision (P2.27): delete ONLY this expired setup's
            # vectors (points stamped with setup_id at ingestion), leaving the
            # org's other live setups in the shared per-org collection (E215)
            # untouched; the collection is dropped only when its last setup goes.
            # The Qdrant SDK stays out of this job module (ADR-001) — the wrapper
            # owns it.
            try:
                matched, dropped = delete_setup_data(str(org_id), str(setup_id))
            except Exception:
                # Vector delete failed (e.g. transient Qdrant outage). KEEP the
                # PostgreSQL row so a future run retries this setup, rather than
                # deleting the tracking row and orphaning its vectors forever.
                failed_setups += 1
                continue

            purged_setups += 1
            deleted_points += matched
            if dropped:
                deleted_collections.append(str(org_id))

            # Vectors gone — now delete PostgreSQL rows (cascade deletes
            # facts/docs via FK).
            result = conn.execute(
                sa.text("DELETE FROM evaluation_setups WHERE setup_id = :sid"),
                {"sid": setup_id},
            )
            deleted_pg_rows += result.rowcount

        conn.commit()

    summary = {
        "cutoff_date": cutoff.isoformat(),
        "deleted_collections": deleted_collections,
        "purged_setups": purged_setups,
        "deleted_points": deleted_points,
        "deleted_pg_rows": deleted_pg_rows,
        "failed_setups": failed_setups,
    }

    log_evaluation_run(
        run_id=f"cleanup_{datetime.datetime.utcnow().date()}",
        agent_name="cleanup_job",
        input_data={"retention_days": retention_days},
        output_data=summary,
        critic_verdict="n/a",
        latency_ms=0,
        org_id="platform",
    )

    return summary
