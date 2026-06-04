import datetime
import sqlalchemy as sa
from sqlalchemy.engine import Engine

from app.retrieval.qdrant import delete_org_data
from app.providers.observability import log_evaluation_run


_DEFAULT_RETENTION_DAYS = 90


async def run_cleanup(engine: Engine, retention_days: int = _DEFAULT_RETENTION_DAYS) -> dict:
    """
    Deletes Qdrant collections and PostgreSQL rows for expired evaluations.
    Retention period: retention_days (default 90). Run daily via Modal.
    Returns a summary dict for LangFuse logging.
    """
    cutoff = datetime.datetime.utcnow() - datetime.timedelta(days=retention_days)
    deleted_collections: list[str] = []
    deleted_pg_rows: int = 0
    purged_orgs: set[str] = set()

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

            # One collection per org (E215): purge the org's vectors via the
            # qdrant wrapper (which deletes points by org_id and drops the now-
            # empty collection) — keeping the Qdrant SDK out of this job module
            # (ADR-001). Done once per org. NOTE: granularity is org-level (a
            # point carries no setup_id), matching the previous prefix-delete
            # semantics — see BACKLOG P2.27 on multi-setup-per-org precision.
            org_key = str(org_id)
            if org_key not in purged_orgs:
                purged_orgs.add(org_key)
                try:
                    _, dropped = delete_org_data(org_key)
                    if dropped:
                        deleted_collections.append(org_key)
                except Exception:
                    pass

            # Delete PostgreSQL rows (cascade deletes facts/docs via FK)
            result = conn.execute(
                sa.text("DELETE FROM evaluation_setups WHERE setup_id = :sid"),
                {"sid": setup_id},
            )
            deleted_pg_rows += result.rowcount

        conn.commit()

    summary = {
        "cutoff_date": cutoff.isoformat(),
        "deleted_collections": deleted_collections,
        "deleted_pg_rows": deleted_pg_rows,
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
