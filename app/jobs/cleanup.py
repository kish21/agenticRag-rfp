import datetime
import sqlalchemy as sa
from sqlalchemy.engine import Engine

from app.core.qdrant_client import get_qdrant_client
from app.core.observability_provider import log_evaluation_run


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

    qdrant = get_qdrant_client()

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

            # Delete matching Qdrant collections (named <org_id>_<vendor_id>)
            all_cols = qdrant.get_collections().collections
            for col in all_cols:
                if col.name.startswith(f"platform_{org_id}_"):
                    try:
                        qdrant.delete_collection(col.name)
                        deleted_collections.append(col.name)
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
