"""
Evaluation API routes — wires the 9-agent pipeline to HTTP + SSE.

Endpoints consumed by the Next.js frontend:
  POST /api/v1/evaluate/start          — upload RFP + vendor docs, returns run_id
  GET  /api/v1/evaluate/list           — dashboard: all runs for org
  GET  /api/v1/evaluate/{runId}/setup  — confirm page: EvaluationSetup details
  GET  /api/v1/evaluate/{runId}/status — progress page: SSE agent status stream
  GET  /api/v1/evaluate/{runId}/results — results page: decision output
  GET  /api/v1/evaluate/{runId}/decision?vendor=<id> — override page: current decision
  POST /api/v1/evaluate/{runId}/override — override page: submit human override
"""
import asyncio
import json
import uuid
from datetime import datetime
from typing import AsyncGenerator

import sqlalchemy as sa
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.core.dependencies import get_current_user
from app.core.auth import TokenData
from app.core.output_models import AuditOverride
from app.db.fact_store import get_engine, save_evaluation_setup
from app.agents.planner import run_planner

router = APIRouter(prefix="/api/v1/evaluate", tags=["evaluate"])

# In-memory run state — replaced by PostgreSQL in production
# Key: run_id, Value: dict with status, agent events, decision output
_run_store: dict[str, dict] = {}


# ── Helpers ────────────────────────────────────────────────────────────────

def _get_run(run_id: str, org_id: str) -> dict:
    run = _run_store.get(run_id)
    if not run:
        # Fall back to PostgreSQL
        engine = get_engine()
        with engine.connect() as conn:
            row = conn.execute(
                sa.text(
                    "SELECT * FROM evaluation_runs "
                    "WHERE run_id = :rid AND org_id = :oid::uuid"
                ),
                {"rid": run_id, "oid": org_id},
            ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Run not found")
        return dict(row._mapping)
    if run.get("org_id") != org_id:
        raise HTTPException(status_code=403, detail="Access denied")
    return run


def _persist_run(run_id: str, org_id: str, rfp_id: str, status: str, setup_id: str) -> None:
    engine = get_engine()
    with engine.connect() as conn:
        conn.execute(
            sa.text("""
                INSERT INTO evaluation_runs (run_id, org_id, rfp_id, setup_id, status)
                VALUES (:run_id, :org_id::uuid, :rfp_id, :setup_id, :status)
                ON CONFLICT (run_id) DO UPDATE SET status = :status
            """),
            {"run_id": run_id, "org_id": org_id, "rfp_id": rfp_id,
             "setup_id": setup_id, "status": status},
        )
        conn.commit()


# ── POST /start ─────────────────────────────────────────────────────────────

class StartRequest(BaseModel):
    rfp_title: str
    department: str
    contract_value: float
    vendor_ids: list[str]
    setup_id: str | None = None


@router.post("/start")
async def start_evaluation(
    rfp_title: str = Form(...),
    department: str = Form(...),
    contract_value: float = Form(...),
    vendor_ids: str = Form(...),           # JSON array string from form
    rfp_file: UploadFile = File(...),
    user: TokenData = Depends(get_current_user),
):
    """
    Accepts the RFP document + metadata from the upload page.
    Seeds evaluation_setups, creates an evaluation_runs row, returns run_id.
    The pipeline runs asynchronously — poll /status for progress.
    """
    run_id = str(uuid.uuid4())
    rfp_id = f"rfp-{run_id[:8]}"
    setup_id = f"setup-{run_id[:8]}"
    vendor_list: list[str] = json.loads(vendor_ids)

    # Seed evaluation setup using Planner
    rfp_bytes = await rfp_file.read()
    setup = await run_planner(
        rfp_content=rfp_bytes.decode("utf-8", errors="ignore"),
        org_id=user.org_id,
        rfp_id=rfp_id,
        department=department,
        contract_value=contract_value,
        vendor_ids=vendor_list,
    )
    setup_dict = setup.model_dump()
    setup_dict["setup_id"] = setup_id
    save_evaluation_setup(setup_dict, org_id=user.org_id)

    # Register run in memory + PostgreSQL
    _run_store[run_id] = {
        "run_id": run_id,
        "org_id": user.org_id,
        "rfp_id": rfp_id,
        "rfp_title": rfp_title,
        "department": department,
        "setup_id": setup_id,
        "status": "running",
        "vendor_ids": vendor_list,
        "contract_value": contract_value,
        "agent_events": [],
        "decision": None,
        "started_at": datetime.utcnow().isoformat(),
    }
    _persist_run(run_id, user.org_id, rfp_id, "running", setup_id)

    return {"run_id": run_id, "setup_id": setup_id, "rfp_id": rfp_id}


# ── GET /list ───────────────────────────────────────────────────────────────

@router.get("/list")
async def list_runs(user: TokenData = Depends(get_current_user)):
    """Dashboard: returns all evaluation runs for the caller's org."""
    engine = get_engine()
    with engine.connect() as conn:
        rows = conn.execute(
            sa.text("""
                SELECT
                    r.run_id, r.rfp_id, r.status, r.created_at,
                    r.approval_tier, r.contract_value,
                    s.config->>'rfp_title'      AS rfp_title,
                    s.config->>'department'     AS department,
                    s.config->>'vendor_count'   AS vendor_count
                FROM evaluation_runs r
                LEFT JOIN evaluation_setups s ON s.setup_id = r.setup_id
                WHERE r.org_id = :oid::uuid
                ORDER BY r.created_at DESC
                LIMIT 100
            """),
            {"oid": user.org_id},
        ).fetchall()

    runs = []
    for row in rows:
        r = dict(row._mapping)
        # Merge in-memory data for running runs (has richer state)
        mem = _run_store.get(str(r["run_id"]), {})
        decision = mem.get("decision") or {}
        shortlisted = decision.get("shortlisted_vendors", []) if decision else []
        rejected = decision.get("rejected_vendors", []) if decision else []
        runs.append({
            "run_id":            str(r["run_id"]),
            "rfp_title":         mem.get("rfp_title") or r.get("rfp_title") or r["rfp_id"],
            "department":        mem.get("department") or r.get("department") or "",
            "status":            r["status"],
            "vendor_count":      len(mem.get("vendor_ids", [])) or 0,
            "shortlisted_count": len(shortlisted),
            "rejected_count":    len(rejected),
            "approval_tier":     r.get("approval_tier"),
            "approver_role":     decision.get("approval_routing", {}).get("approver_role") if decision else None,
            "sla_deadline":      decision.get("approval_routing", {}).get("sla_deadline") if decision else None,
            "started_at":        r["created_at"].isoformat() if r["created_at"] else mem.get("started_at", ""),
        })

    return {"runs": runs}


# ── GET /{runId}/setup ──────────────────────────────────────────────────────

@router.get("/{run_id}/setup")
async def get_setup(run_id: str, user: TokenData = Depends(get_current_user)):
    """Confirm page: returns EvaluationSetup for the run."""
    run = _get_run(run_id, user.org_id)
    setup_id = run.get("setup_id")
    if not setup_id:
        raise HTTPException(status_code=404, detail="Setup not found for this run")

    engine = get_engine()
    with engine.connect() as conn:
        row = conn.execute(
            sa.text("SELECT config FROM evaluation_setups WHERE setup_id = :sid"),
            {"sid": setup_id},
        ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="EvaluationSetup not found")
    return row.config


# ── GET /{runId}/status — SSE ───────────────────────────────────────────────

async def _event_stream(run_id: str, org_id: str) -> AsyncGenerator[str, None]:
    """Server-Sent Events: yields agent status updates until run completes."""
    _AGENTS = [
        "planner", "ingestion", "retrieval", "extraction",
        "evaluation", "comparator", "decision", "explanation",
    ]
    seen_count = 0
    while True:
        run = _run_store.get(run_id)
        if not run:
            yield f"data: {json.dumps({'error': 'run not found'})}\n\n"
            return

        events = run.get("agent_events", [])
        for event in events[seen_count:]:
            yield f"data: {json.dumps(event)}\n\n"
            seen_count += 1

        status = run.get("status", "running")
        if status in ("complete", "blocked", "failed"):
            yield f"data: {json.dumps({'type': 'done', 'status': status})}\n\n"
            return

        yield f"data: {json.dumps({'type': 'heartbeat'})}\n\n"
        await asyncio.sleep(2)


@router.get("/{run_id}/status")
async def run_status_stream(run_id: str, user: TokenData = Depends(get_current_user)):
    """Progress page: SSE stream of agent events for the given run."""
    _get_run(run_id, user.org_id)  # 403/404 guard
    return StreamingResponse(
        _event_stream(run_id, user.org_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


# ── GET /{runId}/results ────────────────────────────────────────────────────

@router.get("/{run_id}/results")
async def get_results(run_id: str, user: TokenData = Depends(get_current_user)):
    """Results page: returns the DecisionOutput + ApprovalRouting for a completed run."""
    run = _get_run(run_id, user.org_id)
    decision = run.get("decision")
    if not decision:
        # Run may still be in progress
        return {
            "run_id": run_id,
            "status": run.get("status", "running"),
            "decision": None,
        }
    return {
        "run_id":     run_id,
        "status":     run.get("status"),
        "rfp_title":  run.get("rfp_title", ""),
        "department": run.get("department", ""),
        "decision":   decision,
    }


# ── GET /{runId}/decision ───────────────────────────────────────────────────

@router.get("/{run_id}/decision")
async def get_vendor_decision(
    run_id: str,
    vendor: str,
    user: TokenData = Depends(get_current_user),
):
    """Override page: returns the current decision for a specific vendor."""
    run = _get_run(run_id, user.org_id)
    decision = run.get("decision") or {}

    for v in decision.get("shortlisted_vendors", []):
        if v["vendor_id"] == vendor:
            return {
                "vendor_id":          v["vendor_id"],
                "vendor_name":        v["vendor_name"],
                "decision_type":      "shortlisted",
                "rank":               v["rank"],
                "total_score":        v["total_score"],
                "evidence_citations": [],
            }

    for v in decision.get("rejected_vendors", []):
        if v["vendor_id"] == vendor:
            return {
                "vendor_id":          v["vendor_id"],
                "vendor_name":        v["vendor_name"],
                "decision_type":      "rejected",
                "rejection_reasons":  v.get("rejection_reasons", []),
                "evidence_citations": v.get("evidence_citations", []),
            }

    raise HTTPException(status_code=404, detail=f"Vendor {vendor} not found in run {run_id}")


# ── POST /{runId}/override ──────────────────────────────────────────────────

class OverrideRequest(BaseModel):
    vendor_id: str
    reason: str


@router.post("/{run_id}/override")
async def submit_override(
    run_id: str,
    body: OverrideRequest,
    user: TokenData = Depends(get_current_user),
):
    """Override page: records a human override with full audit trail."""
    run = _get_run(run_id, user.org_id)
    decision = run.get("decision") or {}

    # Find current decision for this vendor
    original: dict = {}
    for v in decision.get("shortlisted_vendors", []) + decision.get("rejected_vendors", []):
        if v["vendor_id"] == body.vendor_id:
            original = dict(v)
            break
    if not original:
        raise HTTPException(status_code=404, detail=f"Vendor {body.vendor_id} not found")

    override = AuditOverride(
        override_id=str(uuid.uuid4()),
        org_id=user.org_id,
        run_id=run_id,
        overridden_by=user.email,
        original_decision=original,
        new_decision={"vendor_id": body.vendor_id, "override": True, "reason": body.reason},
        reason=body.reason,
        timestamp=datetime.utcnow(),
    )

    # Persist to audit_overrides table
    engine = get_engine()
    with engine.connect() as conn:
        conn.execute(
            sa.text("""
                INSERT INTO audit_overrides
                    (override_id, org_id, run_id, overridden_by,
                     original_decision, new_decision, reason, timestamp)
                VALUES
                    (:override_id, :org_id::uuid, :run_id::uuid, :overridden_by,
                     :original::jsonb, :new_decision::jsonb, :reason, :timestamp)
            """),
            {
                "override_id":    override.override_id,
                "org_id":         user.org_id,
                "run_id":         run_id,
                "overridden_by":  override.overridden_by,
                "original":       json.dumps(override.original_decision),
                "new_decision":   json.dumps(override.new_decision),
                "reason":         override.reason,
                "timestamp":      override.timestamp,
            },
        )
        conn.commit()

    return {"override_id": override.override_id, "status": "recorded"}
