"""
Evaluation API routes — wires the 9-agent pipeline to HTTP + SSE.

All run state is persisted in PostgreSQL. No in-memory store.

Endpoints:
  POST /api/v1/evaluate/start             — upload RFP + vendor docs, returns run_id
  GET  /api/v1/evaluate/list              — dashboard: all runs for org
  GET  /api/v1/evaluate/{runId}/setup     — confirm page: EvaluationSetup details
  POST /api/v1/evaluate/{runId}/confirm   — start the pipeline
  GET  /api/v1/evaluate/{runId}/status    — SSE agent status stream
  GET  /api/v1/evaluate/{runId}/stream    — SSE alias with ?token= query param
  GET  /api/v1/evaluate/{runId}/results   — results page: decision output
  GET  /api/v1/evaluate/{runId}/decision  — override page: vendor decision
  POST /api/v1/evaluate/{runId}/override  — submit human override
"""
import asyncio
import json
import uuid
from datetime import datetime, timezone
from typing import AsyncGenerator

import sqlalchemy as sa
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, UploadFile, File, Form
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.core.dependencies import get_current_user
from app.core.auth import TokenData, decode_token
from app.core.audit import audit
from app.core.output_models import (
    AuditOverride, EvaluationSetup, MandatoryCheck,
    ScoringCriterion, ExtractionTarget, RetrievalOutput,
)
from app.db.fact_store import get_engine, save_evaluation_setup
from app.agents.planner import run_planner
from app.agents.ingestion import run_ingestion_agent
from app.agents.retrieval import run_retrieval_agent
from app.agents.extraction import run_extraction_agent
from app.agents.evaluation import run_evaluation_agent
from app.agents.comparator import run_comparator_agent
from app.agents.decision import run_decision_agent
from app.agents.explanation import run_explanation_agent

router = APIRouter(prefix="/api/v1/evaluate", tags=["evaluate"])


# ── DB helpers ─────────────────────────────────────────────────────────────────

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
                       vendor_names
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
            {"ev": json.dumps(event), "rid": run_id},
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
            {"entry": json.dumps(entry), "rid": run_id},
        )


def _db_save_decision(run_id: str, decision: dict) -> None:
    engine = get_engine()
    # PostgreSQL rejects  (null byte) in jsonb — strip before saving
    dec_json = json.dumps(decision).replace(chr(0), "")
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


def _db_load_rfp_bytes(run_id: str) -> tuple[bytes, str]:
    """Load RFP file bytes from evaluation_runs."""
    engine = get_engine()
    with engine.connect() as conn:
        row = conn.execute(
            sa.text("SELECT rfp_bytes, rfp_filename FROM evaluation_runs WHERE run_id = CAST(:rid AS uuid)"),
            {"rid": run_id},
        ).fetchone()
    if not row or not row[0]:
        return b"", "rfp.pdf"
    return bytes(row[0]), row[1] or "rfp.pdf"


def _db_get_setup(setup_id: str) -> dict | None:
    engine = get_engine()
    with engine.connect() as conn:
        row = conn.execute(
            sa.text("SELECT setup_json FROM evaluation_setups WHERE setup_id = :sid"),
            {"sid": setup_id},
        ).fetchone()
    return row[0] if row else None


# ── POST /start ─────────────────────────────────────────────────────────────

@router.post("/start")
async def start_evaluation(
    background_tasks: BackgroundTasks,
    rfp_title: str = Form(...),
    department: str = Form(...),
    contract_value: float = Form(...),
    vendor_ids: str = Form(default="[]"),
    vendor_names: str = Form(default="{}"),
    rfp_file: UploadFile = File(...),
    vendor_files: list[UploadFile] = File(default=[]),
    user: TokenData = Depends(get_current_user),
):
    """
    Upload RFP + vendor PDFs. Stores everything in PostgreSQL immediately.
    Returns run_id. No data is kept in memory.
    """
    run_id   = str(uuid.uuid4())
    rfp_id   = f"rfp-{run_id[:8]}"
    setup_id = f"setup-{run_id[:8]}"

    try:
        vendor_list: list[str] = json.loads(vendor_ids) if vendor_ids.strip() else []
    except json.JSONDecodeError:
        vendor_list = [v.strip().strip('"') for v in vendor_ids.strip("[]").split(",") if v.strip().strip('"')]

    # Read all bytes upfront
    rfp_bytes = await rfp_file.read()
    vendor_file_map: dict[str, tuple[bytes, str]] = {}
    for vf in vendor_files:
        vbytes = await vf.read()
        vid = (vf.filename or "vendor").rsplit(".", 1)[0]
        vendor_file_map[vid] = (vbytes, vf.filename or vid)

    if vendor_file_map and not any(vendor_list):
        vendor_list = list(vendor_file_map.keys())

    # ── Build EvaluationSetup via criteria merger ──────────
    from app.core.criteria_merger import (
        get_org_criteria, get_dept_criteria,
        extract_rfp_text, extract_criteria_from_rfp,
        merge_criteria,
    )

    # Extract text from RFP for PDF parsing (no LLM — fast)
    rfp_text = extract_rfp_text(rfp_bytes)

    # Load org and department criteria templates (DB only — fast)
    org_criteria  = get_org_criteria(user.org_id)
    dept_criteria = get_dept_criteria(user.org_id, department)

    # Merge org+dept templates only — RFP LLM extraction runs in background
    merged = merge_criteria(
        org_criteria=org_criteria,
        dept_criteria=dept_criteria,
        rfp_criteria={},           # empty — LLM extraction not yet run
        department=department,
        rfp_id=rfp_id,
        org_id=user.org_id,
    )

    # Build initial EvaluationSetup with defaults — overwritten by background task once LLM finishes
    mandatory_checks = merged["mandatory_checks"] or [
        MandatoryCheck(
            check_id="chk-default-001",
            name="Legal entity registration",
            description="Vendor must be a registered legal entity.",
            what_passes="Registration number provided.",
            extraction_target_id="ext-legal-default",
        )
    ]
    scoring_criteria_list = merged["scoring_criteria"] or [
        ScoringCriterion(
            criterion_id="crit-default-tech",
            name="Technical capability",
            weight=0.50,
            rubric_9_10="Fully meets requirements.",
            rubric_6_8="Meets most requirements.",
            rubric_3_5="Partially meets requirements.",
            rubric_0_2="Does not meet requirements.",
            extraction_target_ids=["ext-sla-default"],
        ),
        ScoringCriterion(
            criterion_id="crit-default-commercial",
            name="Commercial value",
            weight=0.50,
            rubric_9_10="Best value, transparent pricing.",
            rubric_6_8="Competitive pricing.",
            rubric_3_5="Above-market pricing.",
            rubric_0_2="Pricing absent.",
            extraction_target_ids=["ext-pricing-default"],
        ),
    ]
    extraction_targets_list = merged["extraction_targets"] or [
        ExtractionTarget(
            target_id="ext-legal-default",
            name="Legal registration",
            description="Company registration number.",
            fact_type="certification",
            is_mandatory=True,
            feeds_check_id="chk-default-001",
        ),
    ]

    evaluation_setup = EvaluationSetup(
        setup_id=setup_id,
        org_id=user.org_id,
        department=department,
        rfp_id=rfp_id,
        rfp_confirmed=False,
        confirmed_by="pending",
        confirmed_at=None,
        source=merged.get("source", "merged"),
        mandatory_checks=mandatory_checks,
        scoring_criteria=scoring_criteria_list,
        extraction_targets=extraction_targets_list,
        total_weight=round(
            sum(float(c.get("weight", 0)) if hasattr(c, "get") else float(c.weight)
                for c in scoring_criteria_list), 3
        ),
    )

    setup_dict = evaluation_setup.model_dump(mode="json")
    save_evaluation_setup(setup_dict, org_id=user.org_id)

    # Persist run to PostgreSQL — including file bytes
    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(
            sa.text("""
                INSERT INTO evaluation_runs
                    (run_id, org_id, rfp_id, setup_id, rfp_title, department,
                     rfp_filename, rfp_bytes, status, vendor_ids, contract_value,
                     vendor_names)
                VALUES
                    (CAST(:run_id AS uuid), CAST(:org_id AS uuid), :rfp_id, :setup_id,
                     :rfp_title, :department, :rfp_filename, :rfp_bytes,
                     'pending_confirm', :vendor_ids, :contract_value,
                     CAST(:vendor_names AS jsonb))
            """),
            {
                "run_id":       run_id,
                "org_id":       user.org_id,
                "rfp_id":       rfp_id,
                "setup_id":     setup_id,
                "rfp_title":    rfp_title,
                "department":   department,
                "rfp_filename": rfp_file.filename or "rfp.pdf",
                "rfp_bytes":    rfp_bytes,
                "vendor_ids":   vendor_list,
                "contract_value": contract_value,
                "vendor_names": vendor_names if vendor_names.strip() else "{}",
            },
        )
        # Store each vendor file in vendor_documents
        for vid, (vbytes, vfilename) in vendor_file_map.items():
            import hashlib
            content_hash = hashlib.sha256(vbytes).hexdigest()
            conn.execute(
                sa.text("""
                    INSERT INTO vendor_documents
                        (org_id, vendor_id, rfp_id, setup_id, filename,
                         file_name, file_bytes, content_hash)
                    VALUES
                        (CAST(:org_id AS uuid), :vendor_id, :rfp_id, :setup_id,
                         :filename, :file_name, :file_bytes, :content_hash)
                    ON CONFLICT (org_id, vendor_id, rfp_id, content_hash) DO NOTHING
                """),
                {
                    "org_id":       user.org_id,
                    "vendor_id":    vid,
                    "rfp_id":       rfp_id,
                    "setup_id":     setup_id,
                    "filename":     vfilename,
                    "file_name":    vfilename,
                    "file_bytes":   vbytes,
                    "content_hash": content_hash,
                },
            )

    audit(org_id=user.org_id, run_id=run_id, event_type="run.created", actor=user.email,
          detail={"rfp_title": rfp_title, "department": department,
                  "rfp_filename": rfp_file.filename, "vendor_count": len(vendor_file_map),
                  "vendor_files": list(vendor_file_map.keys()),
                  "contract_value": contract_value})

    # Run LLM criteria extraction in background — updates setup once Modal responds
    background_tasks.add_task(
        _refine_setup_with_llm,
        setup_id, rfp_text, org_criteria, dept_criteria,
        department, rfp_id, user.org_id,
    )

    return {"run_id": run_id, "setup_id": setup_id, "rfp_id": rfp_id}


# ── GET /list ──────────────────────────────────────────────────────────────────

@router.get("/list")
async def list_runs(user: TokenData = Depends(get_current_user)):
    """Dashboard: returns all evaluation runs for the caller's org."""
    engine = get_engine()
    with engine.connect() as conn:
        rows = conn.execute(
            sa.text("""
                SELECT
                    r.run_id::text, r.rfp_id, r.status, r.created_at,
                    r.approval_tier, r.contract_value,
                    r.rfp_title, r.department,
                    array_length(r.vendor_ids, 1) AS vendor_count,
                    r.decision_output
                FROM evaluation_runs r
                WHERE r.org_id = CAST(:oid AS uuid)
                ORDER BY r.created_at DESC
                LIMIT 100
            """),
            {"oid": user.org_id},
        ).fetchall()

    runs = []
    for row in rows:
        r = dict(row._mapping)
        dec = r.get("decision_output") or {}
        shortlisted = dec.get("shortlisted_vendors", []) if dec else []
        rejected    = dec.get("rejected_vendors",    []) if dec else []
        runs.append({
            "run_id":            str(r["run_id"]),
            "rfp_title":         r.get("rfp_title") or r["rfp_id"],
            "department":        r.get("department") or "",
            "status":            r["status"],
            "vendor_count":      r.get("vendor_count") or 0,
            "shortlisted_count": len(shortlisted),
            "rejected_count":    len(rejected),
            "approval_tier":     r.get("approval_tier"),
            "approver_role":     dec.get("approval_routing", {}).get("approver_role") if dec else None,
            "sla_deadline":      dec.get("approval_routing", {}).get("sla_deadline") if dec else None,
            "started_at":        r["created_at"].isoformat() if r["created_at"] else "",
        })

    return {"runs": runs}


# ── GET /{runId}/setup ─────────────────────────────────────────────────────────

@router.get("/{run_id}/setup")
async def get_setup(run_id: str, user: TokenData = Depends(get_current_user)):
    """Confirm page: returns the EvaluationSetup for this run."""
    run = _db_get_run(run_id, user.org_id)
    setup = _db_get_setup(run["setup_id"])
    if not setup:
        raise HTTPException(status_code=404, detail="Setup not found")
    return setup


# ── PUT /{runId}/setup ────────────────────────────────────────────────────────

class UpdateSetupRequest(BaseModel):
    scoring_criteria: list[dict]
    mandatory_checks: list[dict]
    extraction_targets: list[dict] | None = None


@router.put("/{run_id}/setup")
async def update_setup(
    run_id: str,
    body: UpdateSetupRequest,
    user: TokenData = Depends(get_current_user),
):
    """Customer edits criteria on confirm page before pipeline starts."""
    run = _db_get_run(run_id, user.org_id)
    if run["status"] not in ("pending", "pending_confirm"):
        raise HTTPException(
            409,
            "Cannot edit setup after pipeline has started"
        )
    existing = _db_get_setup(run["setup_id"])

    # Start from the existing extraction_targets so we don't lose them
    extraction_targets: list[dict] = list(
        body.extraction_targets if body.extraction_targets
        else existing.get("extraction_targets") or []
    )
    existing_target_ids = {t["target_id"] for t in extraction_targets}

    # For any user-added mandatory check that has no extraction_target_id,
    # auto-generate a placeholder extraction target so the model validator passes.
    checks_out = []
    for chk in body.mandatory_checks:
        if not chk.get("extraction_target_id"):
            auto_tid = f"ext-user-{chk['check_id'].lower()}"
            chk = dict(chk)
            chk["extraction_target_id"] = auto_tid
            if auto_tid not in existing_target_ids:
                extraction_targets.append({
                    "target_id":   auto_tid,
                    "name":        chk.get("name", "User check"),
                    "description": chk.get("description", ""),
                    "fact_type":   "custom",
                    "is_mandatory": True,
                    "feeds_check_id": chk["check_id"],
                })
                existing_target_ids.add(auto_tid)
        checks_out.append(chk)

    existing["mandatory_checks"]   = checks_out
    existing["scoring_criteria"]   = body.scoring_criteria
    existing["extraction_targets"] = extraction_targets
    existing["source"] = "manually_edited"

    # Recompute total_weight so the ge=0.99 validator doesn't fire on edited weights
    criteria = existing["scoring_criteria"]
    if criteria:
        existing["total_weight"] = round(
            sum(float(c.get("weight", 0)) for c in criteria), 3
        )

    try:
        EvaluationSetup(**existing)
    except Exception as e:
        raise HTTPException(422, f"Invalid setup: {e}")
    save_evaluation_setup(existing, org_id=user.org_id)
    return {"status": "updated"}


# ── Background: LLM criteria refinement ───────────────────────────────────────

async def _refine_setup_with_llm(
    setup_id: str,
    rfp_text: str,
    org_criteria: dict,
    dept_criteria: dict,
    department: str,
    rfp_id: str,
    org_id: str,
) -> None:
    """
    Runs after /start returns. Calls the LLM to extract RFP-specific criteria
    and overwrites the default setup in the DB. The confirm page shows defaults
    until this completes, then refreshes with LLM-extracted criteria.
    """
    from app.core.criteria_merger import extract_criteria_from_rfp, merge_criteria
    from app.core.output_models import MandatoryCheck, ScoringCriterion, ExtractionTarget
    from app.db.fact_store import save_evaluation_setup
    try:
        rfp_criteria = await extract_criteria_from_rfp(rfp_text)
        merged = merge_criteria(
            org_criteria=org_criteria,
            dept_criteria=dept_criteria,
            rfp_criteria=rfp_criteria,
            department=department,
            rfp_id=rfp_id,
            org_id=org_id,
        )
        if not merged["mandatory_checks"] and not merged["scoring_criteria"]:
            return  # nothing better than defaults — leave as-is

        from app.db.fact_store import get_engine
        import sqlalchemy as sa
        engine = get_engine()
        with engine.connect() as conn:
            row = conn.execute(
                sa.text("SELECT setup_json FROM evaluation_setups WHERE setup_id = :sid"),
                {"sid": setup_id},
            ).fetchone()
        if not row:
            return
        import json
        existing = json.loads(row[0]) if isinstance(row[0], str) else row[0]
        if merged["mandatory_checks"]:
            existing["mandatory_checks"] = [
                m if isinstance(m, dict) else m.model_dump() for m in merged["mandatory_checks"]
            ]
        if merged["scoring_criteria"]:
            existing["scoring_criteria"] = [
                c if isinstance(c, dict) else c.model_dump() for c in merged["scoring_criteria"]
            ]
        if merged.get("extraction_targets"):
            existing["extraction_targets"] = [
                t if isinstance(t, dict) else t.model_dump() for t in merged["extraction_targets"]
            ]
        else:
            # Auto-create a minimal ExtractionTarget for every mandatory check
            # whose extraction_target_id has no matching entry in extraction_targets
            existing_target_ids = {t["target_id"] for t in existing.get("extraction_targets", [])}
            for mc in existing.get("mandatory_checks", []):
                mc = mc if isinstance(mc, dict) else mc.model_dump()
                et_id = mc.get("extraction_target_id")
                if et_id and et_id not in existing_target_ids:
                    existing.setdefault("extraction_targets", []).append({
                        "target_id": et_id,
                        "name": mc.get("name", et_id),
                        "description": mc.get("description", ""),
                        "fact_type": "certification",
                        "is_mandatory": True,
                        "feeds_check_id": mc.get("check_id", ""),
                    })
                    existing_target_ids.add(et_id)
        existing["source"] = merged.get("source", "llm_refined")
        save_evaluation_setup(existing, org_id=org_id)
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning(f"LLM criteria refinement failed for {setup_id}: {e}")


# ── POST /{runId}/confirm ──────────────────────────────────────────────────────

@router.post("/{run_id}/confirm")
async def confirm_run(
    run_id: str,
    background_tasks: BackgroundTasks,
    user: TokenData = Depends(get_current_user),
):
    """Confirm page: user approved. Updates status and starts the pipeline."""
    run = _db_get_run(run_id, user.org_id)
    if run["status"] not in ("pending_confirm",):
        raise HTTPException(status_code=409, detail=f"Run already in status: {run['status']}")

    _db_update_status(run_id, "running")
    audit(org_id=user.org_id, run_id=run_id, event_type="run.confirmed", actor=user.email,
          detail={"rfp_title": run.get("rfp_title"), "department": run.get("department")})
    background_tasks.add_task(_run_pipeline, run_id, user.org_id)
    return {"run_id": run_id, "status": "running"}


# ── Pipeline ───────────────────────────────────────────────────────────────────

async def _run_pipeline(run_id: str, org_id: str) -> None:
    """9-agent pipeline. All state read from and written to PostgreSQL."""

    def _emit(agent: str, status: str, message: str = "", log_msg: str = "") -> None:
        event = {"agent": agent, "status": status, "message": message, "log_msg": log_msg or message}
        try:
            _db_append_event(run_id, event)
        except Exception:
            pass
        if log_msg:
            entry = {"ts": datetime.now(timezone.utc).isoformat(),
                     "agent": agent, "status": status, "message": log_msg}
            try:
                _db_append_log(run_id, entry)
            except Exception:
                pass
        # Audit every agent transition
        event_type = "agent.started" if status == "running" else \
                     "agent.completed" if status == "done" else \
                     "agent.blocked" if status == "blocked" else None
        if event_type:
            audit(org_id=org_id, run_id=run_id, event_type=event_type,
                  actor="system", agent=agent, detail={"message": message})

    def _fail(agent: str, err: Exception) -> None:
        _emit(agent, "blocked", str(err),
              log_msg=f"Something went wrong in the {agent} step. The evaluation could not continue.")
        try:
            _db_update_status(run_id, "blocked", completed=True)
        except Exception:
            pass
        audit(org_id=org_id, run_id=run_id, event_type="run.blocked",
              actor="system", detail={"agent": agent, "error": str(err)})

    try:
        # Load everything from DB — no memory store
        engine = get_engine()
        with engine.connect() as conn:
            row = conn.execute(
                sa.text("""
                    SELECT rfp_id, rfp_title, department, rfp_filename,
                           rfp_bytes, vendor_ids, contract_value, setup_id
                    FROM evaluation_runs
                    WHERE run_id = CAST(:rid AS uuid)
                """),
                {"rid": run_id},
            ).fetchone()
        if not row:
            raise RuntimeError("Run not found in DB")

        rfp_id         = row[0]
        rfp_title      = row[1]
        department     = row[2]
        rfp_filename   = row[3] or "rfp.pdf"
        rfp_bytes      = bytes(row[4]) if row[4] else b""
        vendor_ids     = list(row[5] or [])
        contract_value = float(row[6] or 0)
        setup_id       = row[7]

        setup_json = _db_get_setup(setup_id)
        if not setup_json:
            raise RuntimeError("EvaluationSetup not found")
        evaluation_setup = EvaluationSetup(**setup_json)

        vendor_file_map = _db_load_vendor_files(run_id)
        n_vendors = len(vendor_ids)

        # ── 1. Planner ────────────────────────────────────────────────────────
        _emit("planner", "running", "Decomposing evaluation into task DAG",
              log_msg=f"Reading the RFP and planning how to evaluate {n_vendors} vendor{'s' if n_vendors != 1 else ''}.")
        await run_planner(rfp_id=rfp_id, org_id=org_id, vendor_ids=vendor_ids,
                          evaluation_setup=evaluation_setup)
        _emit("planner", "done", "Task DAG ready",
              log_msg=f"Evaluation plan created — {len(evaluation_setup.mandatory_checks)} compliance checks and {len(evaluation_setup.scoring_criteria)} scoring criteria defined.")

        # ── 2. Ingestion ──────────────────────────────────────────────────────
        _emit("ingestion", "running", f"Ingesting RFP + {len(vendor_file_map)} vendor docs",
              log_msg=f"Reading and indexing the RFP document plus {len(vendor_file_map)} vendor proposal{'s' if len(vendor_file_map) != 1 else ''}.")
        await run_ingestion_agent(content=rfp_bytes, filename=rfp_filename,
                                  vendor_id="rfp", org_id=org_id, rfp_id=rfp_id,
                                  evaluation_setup=evaluation_setup)
        for vid, (vbytes, vfilename) in vendor_file_map.items():
            await run_ingestion_agent(content=vbytes, filename=vfilename,
                                      vendor_id=vid, org_id=org_id, rfp_id=rfp_id,
                                      evaluation_setup=evaluation_setup)
        _emit("ingestion", "done", f"RFP + {len(vendor_file_map)} vendor docs indexed",
              log_msg=f"All documents processed and indexed — {len(vendor_file_map)} vendor proposal{'s' if len(vendor_file_map) != 1 else ''} ready for analysis.")

        # ── 3. Retrieval ──────────────────────────────────────────────────────
        # Run one targeted query per scoring criterion + one per mandatory check,
        # then merge and deduplicate chunks so extraction sees full coverage.
        _emit("retrieval", "running", f"Retrieving chunks for {n_vendors} vendors",
              log_msg="Searching each vendor proposal for relevant sections on pricing, compliance, SLAs, and technical capability.")
        retrieval_outputs: dict = {}
        for vid in vendor_ids:
            # Build targeted queries from the confirmed criteria
            queries: list[str] = []
            for criterion in evaluation_setup.scoring_criteria:
                queries.append(criterion.name)
            for check in evaluation_setup.mandatory_checks:
                queries.append(check.name)
            # Fallback if setup has no criteria yet
            if not queries:
                queries = ["technical capability SLA pricing compliance certifications experience"]

            seen_chunk_ids: set[str] = set()
            merged_chunks: list = []

            for query in queries:
                ret_out, _ = await run_retrieval_agent(
                    query=query, vendor_id=vid, org_id=org_id, rfp_id=rfp_id,
                    use_hyde=False, use_rewriting=True, n_candidates=10, n_final=3,
                )
                for chunk in ret_out.chunks:
                    if chunk.chunk_id not in seen_chunk_ids:
                        seen_chunk_ids.add(chunk.chunk_id)
                        merged_chunks.append(chunk)

            # Build a synthetic RetrievalOutput from all merged chunks
            combined = RetrievalOutput(
                query_id=str(uuid.uuid4()),
                original_query="; ".join(queries[:3]) + ("..." if len(queries) > 3 else ""),
                rewritten_query="multi-query",
                hyde_query_used=False,
                retrieval_strategy="multi-query-merge",
                chunks=merged_chunks,
                total_candidates_before_rerank=len(merged_chunks),
                confidence=round(
                    sum(c.final_score for c in merged_chunks) / len(merged_chunks), 3
                ) if merged_chunks else 0.0,
                empty_retrieval=len(merged_chunks) == 0,
                warnings=[],
            )
            retrieval_outputs[vid] = combined
            print(f"[DEBUG retrieval] vendor={vid} queries={len(queries)} unique_chunks={len(merged_chunks)}")
        _emit("retrieval", "done", f"Retrieved chunks for {n_vendors} vendors",
              log_msg=f"Found the most relevant passages from all {n_vendors} vendor proposals.")

        # ── 4. Extraction ─────────────────────────────────────────────────────
        _emit("extraction", "running", "Extracting structured facts",
              log_msg="Pulling out specific facts from each proposal — certifications, insurance, SLA commitments, project history, and pricing.")
        extraction_outputs: dict = {}
        source_chunks: dict = {}
        for vid in vendor_ids:
            ext_out, critic_ext = await run_extraction_agent(
                retrieval_output=retrieval_outputs[vid], vendor_id=vid, org_id=org_id,
                doc_id=f"{rfp_id}-{vid}", setup_id=setup_id, evaluation_setup=evaluation_setup,
                run_id=run_id)
            extraction_outputs[vid] = ext_out
            source_chunks[vid] = "\n".join(
                c.text for c in retrieval_outputs[vid].chunks
            ) if hasattr(retrieval_outputs[vid], "chunks") else ""
            print(f"[DEBUG extraction] vendor={vid} slas={len(ext_out.slas)} pricing={len(ext_out.pricing)} facts={len(ext_out.extracted_facts)} completeness={ext_out.extraction_completeness:.2f} hal_risk={ext_out.hallucination_risk:.2f} critic={critic_ext.overall_verdict}")
        total_facts = sum(
            len(getattr(o, "certifications", []) or []) +
            len(getattr(o, "slas", []) or []) +
            len(getattr(o, "pricing", []) or [])
            for o in extraction_outputs.values()
        )
        _emit("extraction", "done", "Facts extracted and stored",
              log_msg=f"Extracted and saved {total_facts} verifiable facts across all vendor proposals.")

        # ── 5. Evaluation ─────────────────────────────────────────────────────
        _emit("evaluation", "running", "Scoring vendors against criteria",
              log_msg=f"Scoring each vendor against your {len(evaluation_setup.scoring_criteria)} criteria with their configured weights.")
        evaluation_outputs: dict = {}
        for vid in vendor_ids:
            ev_out, _ = await run_evaluation_agent(vendor_id=vid, org_id=org_id,
                                                    run_id=run_id,
                                                    evaluation_setup=evaluation_setup,
                                                    extraction_output=extraction_outputs.get(vid))
            evaluation_outputs[vid] = ev_out
        _emit("evaluation", "done", "All vendors scored",
              log_msg=f"All {n_vendors} vendors scored. Scores ready for comparison.")

        # ── 6. Comparator ─────────────────────────────────────────────────────
        _emit("comparator", "running", "Cross-vendor ranking and stability check",
              log_msg="Ranking vendors against each other and checking whether the ranking is stable across scoring variations.")
        comp_out, _ = await run_comparator_agent(vendor_ids=vendor_ids, org_id=org_id,
                                                  rfp_id=rfp_id, evaluation_setup=evaluation_setup,
                                                  evaluation_outputs=evaluation_outputs)
        _emit("comparator", "done", "Vendors ranked",
              log_msg="Final vendor ranking confirmed.")

        # ── 7. Decision ───────────────────────────────────────────────────────
        _emit("decision", "running", "Governance routing and approval tier selection",
              log_msg="Applying your organisation's governance rules to determine the approval tier and required approvers.")
        dec_out, _ = await run_decision_agent(evaluation_outputs=evaluation_outputs,
                                               comparator_output=comp_out,
                                               contract_value=contract_value)
        n_short = len(getattr(dec_out, "shortlisted_vendors", []) or [])
        n_rej   = len(getattr(dec_out, "rejected_vendors",    []) or [])
        _emit("decision", "done", "Decision and approval tier set",
              log_msg=f"{n_short} vendor{'s' if n_short != 1 else ''} shortlisted, {n_rej} rejected. Approval routing determined.")

        # ── 8. Explanation ────────────────────────────────────────────────────
        _emit("explanation", "running", "Generating grounded report",
              log_msg="Writing the evaluation report — every recommendation is backed by a direct quote from the vendor proposals.")
        exp_out, _ = await run_explanation_agent(decision_output=dec_out,
                                                  evaluation_outputs=evaluation_outputs,
                                                  extraction_outputs=extraction_outputs,
                                                  source_chunks=source_chunks)
        _emit("explanation", "done", "Report ready — every claim cited",
              log_msg="Evaluation complete. Full report ready with citations for every finding.")

        # ── 9. Critic ─────────────────────────────────────────────────────────
        _emit("critic", "done", "All agent outputs validated",
              log_msg="Independent quality check passed — all findings verified for accuracy and consistency.")

        # Persist decision to DB
        _db_save_decision(run_id, dec_out.model_dump(mode="json"))
        audit(org_id=org_id, run_id=run_id, event_type="run.completed",
              actor="system",
              detail={"shortlisted": n_short, "rejected": n_rej,
                      "approval_tier": getattr(getattr(dec_out, "approval_routing", None), "approval_tier", None)})

    except Exception as exc:
        import traceback
        _fail("pipeline", exc)
        print(f"[pipeline error] run={run_id}: {traceback.format_exc()}")


# ── SSE stream ─────────────────────────────────────────────────────────────────

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


@router.get("/{run_id}/status")
async def run_status_stream(run_id: str, user: TokenData = Depends(get_current_user)):
    _db_get_run(run_id, user.org_id)
    return StreamingResponse(
        _event_stream(run_id, user.org_id),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/{run_id}/stream")
async def run_stream_alias(run_id: str, token: str = ""):
    """SSE alias accepting ?token= query param (EventSource cannot set headers)."""
    if not token:
        raise HTTPException(status_code=401, detail="Missing token")
    try:
        user = decode_token(token)
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid token")
    _db_get_run(run_id, user.org_id)
    return StreamingResponse(
        _event_stream(run_id, user.org_id),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ── GET /{runId}/results ───────────────────────────────────────────────────────

@router.get("/{run_id}/results")
async def get_results(run_id: str, user: TokenData = Depends(get_current_user)):
    run = _db_get_run(run_id, user.org_id)
    decision = run.get("decision_output")
    return {
        "run_id":       run_id,
        "status":       run.get("status"),
        "rfp_title":    run.get("rfp_title", ""),
        "department":   run.get("department", ""),
        "decision":     decision,
        "agent_log":    run.get("agent_log") or [],
        "vendor_names": run.get("vendor_names") or {},
    }


# ── GET /{runId}/decision ──────────────────────────────────────────────────────

@router.get("/{run_id}/decision")
async def get_vendor_decision(run_id: str, vendor: str,
                               user: TokenData = Depends(get_current_user)):
    run = _db_get_run(run_id, user.org_id)
    decision = run.get("decision_output") or {}

    for v in decision.get("shortlisted_vendors", []):
        if v["vendor_id"] == vendor:
            return {"vendor_id": v["vendor_id"], "vendor_name": v["vendor_name"],
                    "decision_type": "shortlisted", "rank": v["rank"],
                    "total_score": v["total_score"], "evidence_citations": []}

    for v in decision.get("rejected_vendors", []):
        if v["vendor_id"] == vendor:
            return {"vendor_id": v["vendor_id"], "vendor_name": v["vendor_name"],
                    "decision_type": "rejected",
                    "rejection_reasons": v.get("rejection_reasons", []),
                    "evidence_citations": v.get("evidence_citations", [])}

    raise HTTPException(status_code=404, detail=f"Vendor {vendor} not found in run {run_id}")


# ── POST /{runId}/override ─────────────────────────────────────────────────────

class OverrideRequest(BaseModel):
    vendor_id: str
    reason: str


@router.post("/{run_id}/override")
async def submit_override(run_id: str, body: OverrideRequest,
                           user: TokenData = Depends(get_current_user)):
    run = _db_get_run(run_id, user.org_id)
    decision = run.get("decision_output") or {}

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

    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(
            sa.text("""
                INSERT INTO audit_overrides
                    (override_id, org_id, run_id, overridden_by,
                     original_decision, new_decision, reason, timestamp)
                VALUES
                    (:override_id, CAST(:org_id AS uuid), CAST(:run_id AS uuid), :overridden_by,
                     CAST(:original AS jsonb), CAST(:new_decision AS jsonb), :reason, :timestamp)
            """),
            {
                "override_id":  override.override_id,
                "org_id":       user.org_id,
                "run_id":       run_id,
                "overridden_by": override.overridden_by,
                "original":     json.dumps(override.original_decision),
                "new_decision": json.dumps(override.new_decision),
                "reason":       override.reason,
                "timestamp":    override.timestamp,
            },
        )

    audit(org_id=user.org_id, run_id=run_id, event_type="override.submitted",
          actor=user.email,
          detail={"vendor_id": body.vendor_id, "reason": body.reason,
                  "override_id": override.override_id})

    return {"override_id": override.override_id, "status": "recorded"}


# ── POST /{runId}/re-evaluate ─────────────────────────────────────────────────

@router.post("/{run_id}/re-evaluate")
async def re_evaluate(
    run_id: str,
    background_tasks: BackgroundTasks,
    user: TokenData = Depends(get_current_user),
):
    """Re-run the pipeline for a completed/failed run (e.g. all scores were 0)."""
    run = _db_get_run(run_id, user.org_id)
    if run["status"] in ("running",):
        raise HTTPException(status_code=409, detail="Pipeline is still running")

    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(
            sa.text("""
                UPDATE evaluation_runs
                SET status = 'running',
                    decision_output = NULL,
                    agent_events = '[]',
                    agent_log = '[]',
                    completed_at = NULL
                WHERE run_id = CAST(:rid AS uuid)
            """),
            {"rid": run_id},
        )

    audit(org_id=user.org_id, run_id=run_id, event_type="run.confirmed",
          actor=user.email, detail={"re_evaluate": True, "rfp_title": run.get("rfp_title")})
    background_tasks.add_task(_run_pipeline, run_id, user.org_id)
    return {"run_id": run_id, "status": "running"}


# ── GET /{runId}/audit ────────────────────────────────────────────────────────

@router.get("/{run_id}/audit")
async def get_audit_trail(run_id: str, user: TokenData = Depends(get_current_user)):
    """Return the full append-only audit trail for a run, ordered by time."""
    _db_get_run(run_id, user.org_id)   # 404/403 guard
    engine = get_engine()
    with engine.connect() as conn:
        rows = conn.execute(
            sa.text("""
                SELECT log_id::text, event_type, actor, agent, detail, created_at
                FROM audit_log
                WHERE run_id = CAST(:rid AS uuid)
                  AND org_id = CAST(:oid AS uuid)
                ORDER BY created_at ASC
            """),
            {"rid": run_id, "oid": user.org_id},
        ).fetchall()
    return {
        "run_id": run_id,
        "events": [
            {
                "log_id":     r[0],
                "event_type": r[1],
                "actor":      r[2],
                "agent":      r[3],
                "detail":     r[4] or {},
                "ts":         r[5].isoformat() if r[5] else "",
            }
            for r in rows
        ],
    }
