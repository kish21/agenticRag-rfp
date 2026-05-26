"""SSE event stream — polls PostgreSQL for new agent_events."""
import asyncio
import json
from typing import AsyncGenerator

import sqlalchemy as sa

from app.db.fact_store import get_engine


async def _event_stream(run_id: str, org_id: str) -> AsyncGenerator[str, None]:
    """Poll PostgreSQL for new agent_events and stream them as SSE."""
    seen = 0
    while True:
        try:
            engine = get_engine()
            with engine.connect() as conn:
                row = conn.execute(
                    sa.text("""
                        SELECT agent_events, status
                        FROM evaluation_runs
                        WHERE run_id = CAST(:rid AS uuid)
                          AND org_id = CAST(:oid AS uuid)
                    """),
                    {"rid": run_id, "oid": org_id},
                ).fetchone()
        except Exception:
            yield f"data: {json.dumps({'type': 'heartbeat'})}\n\n"
            await asyncio.sleep(2)
            continue

        if not row:
            yield f"data: {json.dumps({'type': 'error', 'message': 'run not found'})}\n\n"
            return

        events, status = row[0] or [], row[1]

        for event in events[seen:]:
            yield f"data: {json.dumps(event)}\n\n"
            seen += 1

        if status in ("complete", "blocked", "failed", "interrupted"):
            yield f"data: {json.dumps({'type': 'done', 'status': status})}\n\n"
            return

        yield f"data: {json.dumps({'type': 'heartbeat'})}\n\n"
        await asyncio.sleep(2)
