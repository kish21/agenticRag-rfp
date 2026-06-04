import datetime
import sqlalchemy as sa
from sqlalchemy.engine import Engine

from qdrant_client.models import Filter, FieldCondition, MatchValue, FilterSelector

from app.retrieval.qdrant import get_qdrant_client, org_collection_name
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

            # One collection per org (E215): delete the org's points by filter
            # rather than dropping the whole collection, then drop it if it is
            # now empty. NOTE: granularity is org-level (a point carries no
            # setup_id), matching the previous prefix-delete semantics — see the
            # BACKLOG note on multi-setup-per-org precision.
            name = org_collection_name(str(org_id))
            existing = [c.name for c in qdrant.get_collections().collections]
            if name in existing:
                try:
                    qdrant.delete(
                        collection_name=name,
                        points_selector=FilterSelector(
                            filter=Filter(must=[
                                FieldCondition(
                                    key="org_id",
                                    match=MatchValue(value=str(org_id)),
                                )
                            ])
                        ),
                    )
                    if qdrant.count(collection_name=name, exact=True).count == 0:
                        qdrant.delete_collection(name)
                        deleted_collections.append(name)
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
