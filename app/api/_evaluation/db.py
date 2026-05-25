"""PostgreSQL helpers for evaluation runs — all SQL lives here."""
import json

import sqlalchemy as sa
from fastapi import HTTPException

from app.db.fact_store import get_engine


def _db_get_run(run_id: str, org_id: str) -> dict:
    """Load a run row from PostgreSQL. Raises 404/403 on miss/mismatch."""
    engine = get_engine()
    with engine.connect() as conn:
        row = conn.execute(
            sa.text("""
                SELECT run_id::text, org_id::text, setup_id, rfp_id,
                       rfp_title, department, rfp_filename,
                       status, vendor_ids, contract_value,
                       agent_events, agent_log, decision_output,
                       created_at, completed_at,
                       vendor_names, created_by_email, creator_dept_id,
                       currency, gaps_report
                FROM evaluation_runs
                WHERE run_id = CAST(:rid AS uuid)
                  AND org_id = CAST(:oid AS uuid)
            """),
            {"rid": run_id, "oid": org_id},
        ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Run not found")
    return dict(row._mapping)


def _db_update_status(run_id: str, status: str, completed: bool = False) -> None:
    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(
            sa.text("""
                UPDATE evaluation_runs
                SET status = :status,
                    completed_at = CASE WHEN :completed THEN now() ELSE completed_at END
                WHERE run_id = CAST(:rid AS uuid)
            """),
            {"rid": run_id, "status": status, "completed": completed},
        )


def _db_append_event(run_id: str, event: dict) -> None:
    """Append one agent SSE event to evaluation_runs.agent_events."""
    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(
            sa.text("""
                UPDATE evaluation_runs
                SET agent_events = agent_events || CAST(:ev AS jsonb)
                WHERE run_id = CAST(:rid AS uuid)
            """),
            {"ev": json.dumps(event).replace("\\u0000", ""), "rid": run_id},
        )


def _db_append_log(run_id: str, entry: dict) -> None:
    """Append one plain-English log entry to evaluation_runs.agent_log."""
    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(
            sa.text("""
                UPDATE evaluation_runs
                SET agent_log = agent_log || CAST(:entry AS jsonb)
                WHERE run_id = CAST(:rid AS uuid)
            """),
            {"entry": json.dumps(entry).replace("\\u0000", ""), "rid": run_id},
        )


def _db_save_decision(run_id: str, decision: dict) -> None:
    engine = get_engine()
    # PostgreSQL rejects null bytes in jsonb.
    # json.dumps encodes chr(0) as the 6-char literal  — must strip that,
    # not chr(0), which is no longer present in the serialized string.
    dec_json = json.dumps(decision).replace("\\u0000", "")
    with engine.begin() as conn:
        conn.execute(
            sa.text("""
                UPDATE evaluation_runs
                SET decision_output = CAST(:dec AS jsonb),
                    status = 'complete',
                    completed_at = now()
                WHERE run_id = CAST(:rid AS uuid)
            """),
            {"dec": dec_json, "rid": run_id},
        )


def _db_load_vendor_files(run_id: str) -> dict[str, tuple[bytes, str]]:
    """Load vendor file bytes from vendor_documents for this run's rfp_id."""
    engine = get_engine()
    with engine.connect() as conn:
        row = conn.execute(
            sa.text("SELECT rfp_id FROM evaluation_runs WHERE run_id = CAST(:rid AS uuid)"),
            {"rid": run_id},
        ).fetchone()
        if not row:
            return {}
        rfp_id = row[0]
        rows = conn.execute(
            sa.text("""
                SELECT vendor_id, file_bytes, file_name
                FROM vendor_documents
                WHERE rfp_id = :rfp_id AND vendor_id != 'rfp' AND file_bytes IS NOT NULL
            """),
            {"rfp_id": rfp_id},
        ).fetchall()
    return {r[0]: (bytes(r[1]), r[2] or r[0]) for r in rows if r[1]}


def _db_get_setup(setup_id: str) -> dict | None:
    engine = get_engine()
    with engine.connect() as conn:
        row = conn.execute(
            sa.text("SELECT setup_json FROM evaluation_setups WHERE setup_id = :sid"),
            {"sid": setup_id},
        ).fetchone()
    return row[0] if row else None
