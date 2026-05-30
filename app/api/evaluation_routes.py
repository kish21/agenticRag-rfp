"""
Evaluation API routes — wires the 9-agent pipeline to HTTP + SSE.

All run state is persisted in PostgreSQL. No in-memory store.

Endpoints:
  POST /api/v1/evaluate/start             — upload RFP + vendor docs, returns run_id
  GET  /api/v1/evaluate/list              — dashboard: all runs for org
  GET  /api/v1/evaluate/{runId}/setup     — confirm page: EvaluationSetup details
  PUT  /api/v1/evaluate/{runId}/setup     — edit criteria before pipeline starts
  POST /api/v1/evaluate/{runId}/confirm   — start the pipeline
  GET  /api/v1/evaluate/{runId}/status    — SSE agent status stream
  GET  /api/v1/evaluate/{runId}/stream    — SSE alias with ?token= query param
  GET  /api/v1/evaluate/{runId}/results   — results page: decision output
  GET  /api/v1/evaluate/{runId}/decision  — override page: vendor decision
  POST /api/v1/evaluate/{runId}/override  — submit human override
  POST /api/v1/evaluate/{runId}/re-evaluate — re-run a completed/failed run
  GET  /api/v1/evaluate/{runId}/audit     — full audit trail
  GET  /api/v1/evaluate/{runId}/cost      — LLM cost and token usage
  POST /api/v1/evaluate/{runId}/cancel    — interrupt a running evaluation
  DELETE /api/v1/evaluate/{runId}         — permanently delete a run
"""
import hashlib
import json
import uuid
from datetime import datetime

import sqlalchemy as sa
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, UploadFile, File, Form
from fastapi.responses import StreamingResponse, HTMLResponse, Response
from pydantic import BaseModel

from app.auth.dependencies import get_current_user
from app.auth.jwt import TokenData, decode_token
from app.infra.audit import audit
from app.auth.rbac import require_run_access, require_admin_role, log_access
from app.schemas.output_models import (
    AuditOverride, EvaluationSetup, MandatoryCheck,
    ScoringCriterion, ExtractionTarget,
)
from app.db.fact_store import get_engine, save_evaluation_setup

from app.api._evaluation.db import (
    _db_get_run, _db_update_status, _db_get_setup,
)
from app.api._evaluation.pipeline import _run_pipeline
from app.api._evaluation.streaming import _event_stream
from app.api._evaluation.refinement import _refine_setup_with_llm

router = APIRouter(prefix="/api/v1/evaluate", tags=["evaluate"])


# ── POST /start ────────────────────────────────────────────────────────────────

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
    criteria_sheet: UploadFile = File(default=None),
    currency: str = Form(default="GBP"),
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

    rfp_bytes = await rfp_file.read()
    criteria_bytes: bytes | None = None
    criteria_filename: str | None = None
    if criteria_sheet and criteria_sheet.filename:
        criteria_bytes = await criteria_sheet.read()
        criteria_filename = criteria_sheet.filename

    vendor_file_map: dict[str, tuple[bytes, str]] = {}
    for vf in vendor_files:
        vbytes = await vf.read()
        vid = (vf.filename or "vendor").rsplit(".", 1)[0]
        vendor_file_map[vid] = (vbytes, vf.filename or vid)

    if vendor_file_map and not any(vendor_list):
        vendor_list = list(vendor_file_map.keys())

    from app.domain.criteria import (
        get_org_criteria, get_dept_criteria,
        extract_rfp_text, extract_criteria_from_user_sheet,
        merge_criteria,
    )

    rfp_text      = extract_rfp_text(rfp_bytes)
    org_criteria  = get_org_criteria(user.org_id)
    dept_criteria = get_dept_criteria(user.org_id, department)

    user_criteria: dict | None = None
    if criteria_bytes and criteria_filename:
        user_criteria = await extract_criteria_from_user_sheet(criteria_bytes, criteria_filename)

    from app.domain.criteria import extract_criteria_from_rfp, detect_and_fill_gaps
    rfp_criteria = await extract_criteria_from_rfp(rfp_text)

    merged = merge_criteria(
        org_criteria=org_criteria,
        dept_criteria=dept_criteria,
        rfp_criteria=rfp_criteria,
        department=department,
        rfp_id=rfp_id,
        org_id=user.org_id,
        user_criteria=user_criteria,
    )

    merged, gaps_report = await detect_and_fill_gaps(merged, department)

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

    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(
            sa.text("""
                INSERT INTO evaluation_runs
                    (run_id, org_id, rfp_id, setup_id, rfp_title, department,
                     rfp_filename, rfp_bytes, status, vendor_ids, contract_value,
                     vendor_names, created_by_email, creator_dept_id, currency)
                VALUES
                    (CAST(:run_id AS uuid), CAST(:org_id AS uuid), :rfp_id, :setup_id,
                     :rfp_title, :department, :rfp_filename, :rfp_bytes,
                     'pending_confirm', :vendor_ids, :contract_value,
                     CAST(:vendor_names AS jsonb), :created_by_email, :creator_dept_id, :currency)
            """),
            {
                "run_id":           run_id,
                "org_id":           user.org_id,
                "rfp_id":           rfp_id,
                "setup_id":         setup_id,
                "rfp_title":        rfp_title,
                "department":       department,
                "rfp_filename":     rfp_file.filename or "rfp.pdf",
                "rfp_bytes":        rfp_bytes,
                "vendor_ids":       vendor_list,
                "contract_value":   contract_value,
                "vendor_names":     vendor_names if vendor_names.strip() else "{}",
                "created_by_email": user.email,
                "creator_dept_id":  user.dept_id,
                "currency":         currency.upper().strip()[:3],
            },
        )
        for vid, (vbytes, vfilename) in vendor_file_map.items():
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

    if gaps_report.get("has_gaps"):
        with engine.begin() as conn:
            conn.execute(sa.text("""
                UPDATE evaluation_runs
                SET gaps_report = CAST(:gaps AS jsonb)
                WHERE run_id = CAST(:run_id AS uuid)
            """), {"gaps": json.dumps(gaps_report), "run_id": run_id})

    audit(org_id=user.org_id, run_id=run_id, event_type="run.created", actor=user.email,
          detail={"rfp_title": rfp_title, "department": department,
                  "rfp_filename": rfp_file.filename, "vendor_count": len(vendor_file_map),
                  "vendor_files": list(vendor_file_map.keys()),
                  "contract_value": contract_value})

    background_tasks.add_task(
        _refine_setup_with_llm,
        setup_id, rfp_text, org_criteria, dept_criteria,
        department, rfp_id, user.org_id, user_criteria,
    )

    return {"run_id": run_id, "setup_id": setup_id, "rfp_id": rfp_id}


# ── GET /list ──────────────────────────────────────────────────────────────────

@router.get("/list")
async def list_runs(
    user: TokenData = Depends(get_current_user),
    scope: str = "auto",
):
    """Dashboard: returns evaluation runs the caller is allowed to see.

    Phase 9 — accepts an optional `?scope=` query parameter:
      - `auto` (default)  → legacy behaviour (wide role sees org; dept_user sees own)
      - `mine`            → runs the user personally created
      - `department`      → runs in any department the user belongs to
      - `approvals`       → runs the user has a pending approval on
      - `shared`          → runs the user was explicitly invited to
      - `all`             → entire visible set (the union of mine/department/
                            approvals/shared); wide-role users get whole org

    Default-deny: a user who doesn't match any predicate sees an empty list,
    even within the same org.
    """
    engine = get_engine()

    # Legacy path — preserved exactly so existing frontend clients don't break.
    if scope == "auto":
        if user.role == "department_user":
            query = sa.text("""
                SELECT
                    r.run_id::text, r.rfp_id, r.status, r.created_at,
                    r.approval_tier, r.contract_value, r.currency,
                    r.rfp_title, r.department,
                    array_length(r.vendor_ids, 1) AS vendor_count,
                    r.decision_output,
                    r.llm_cost_usd, r.llm_tokens_total
                FROM evaluation_runs r
                WHERE r.org_id = CAST(:oid AS uuid)
                  AND r.created_by_email = :email
                ORDER BY r.created_at DESC
                LIMIT 100
            """)
            params = {"oid": user.org_id, "email": user.email}
        else:
            query = sa.text("""
                SELECT
                    r.run_id::text, r.rfp_id, r.status, r.created_at,
                    r.approval_tier, r.contract_value, r.currency,
                    r.rfp_title, r.department,
                    array_length(r.vendor_ids, 1) AS vendor_count,
                    r.decision_output,
                    r.llm_cost_usd, r.llm_tokens_total
                FROM evaluation_runs r
                WHERE r.org_id = CAST(:oid AS uuid)
                ORDER BY r.created_at DESC
                LIMIT 100
            """)
            params = {"oid": user.org_id}

        with engine.connect() as conn:
            rows = conn.execute(query, params).fetchall()
    else:
        # Phase 9 scoped path — delegate to the visibility wrapper.
        if scope not in ("mine", "department", "approvals", "shared", "all"):
            raise HTTPException(status_code=400, detail=f"Unknown scope: {scope}")
        if scope == "all" and user.role not in ("platform_admin", "company_admin"):
            raise HTTPException(status_code=403, detail="scope=all requires a wide-role account")
        from app.domain.visibility import visible_runs as _visible_runs
        visible = _visible_runs(user, scope=scope, limit=100)
        # Re-query the full row data for each visible run_id, then sort by created_at desc.
        if not visible:
            rows = []
        else:
            run_ids = [str(v["run_id"]) for v in visible]
            with engine.connect() as conn:
                rows = conn.execute(
                    sa.text("""
                        SELECT
                            r.run_id::text, r.rfp_id, r.status, r.created_at,
                            r.approval_tier, r.contract_value, r.currency,
                            r.rfp_title, r.department,
                            array_length(r.vendor_ids, 1) AS vendor_count,
                            r.decision_output,
                            r.llm_cost_usd, r.llm_tokens_total
                        FROM evaluation_runs r
                        WHERE r.run_id::text = ANY(:ids)
                        ORDER BY r.created_at DESC
                        LIMIT 100
                    """),
                    {"ids": run_ids},
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
            "currency":          r.get("currency") or "GBP",
            "contract_value":    float(r["contract_value"]) if r.get("contract_value") is not None else None,
            "total_cost_usd":    float(r["llm_cost_usd"]) if r.get("llm_cost_usd") is not None else None,
        })

    return {"runs": runs}


# ── GET /{runId}/setup ─────────────────────────────────────────────────────────

@router.get("/{run_id}/setup")
async def get_setup(run_id: str, user: TokenData = Depends(get_current_user)):
    """Confirm page: returns the EvaluationSetup for this run."""
    run = _db_get_run(run_id, user.org_id)
    require_run_access(user, run)
    log_access(run_id, user.org_id, user.email, "view_setup")
    setup = _db_get_setup(run["setup_id"])
    if not setup:
        raise HTTPException(status_code=404, detail="Setup not found")
    setup["currency"] = run.get("currency") or "GBP"
    setup["contract_value"] = float(run["contract_value"]) if run.get("contract_value") is not None else None
    setup["vendor_count"] = len(run.get("vendor_ids") or [])
    setup["rfp_title"] = run.get("rfp_title") or ""
    setup["department"] = run.get("department") or ""
    gaps = run.get("gaps_report")
    setup["gaps_report"] = gaps if isinstance(gaps, dict) else (json.loads(gaps) if gaps else {
        "has_gaps": False,
        "score_guides_generated": [],
        "mandatory_checks_suggested": [],
    })
    return setup


# ── PUT /{runId}/setup ─────────────────────────────────────────────────────────

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
    require_run_access(user, run)
    if run["status"] not in ("pending", "pending_confirm"):
        raise HTTPException(409, "Cannot edit setup after pipeline has started")

    existing = _db_get_setup(run["setup_id"])

    extraction_targets: list[dict] = list(
        body.extraction_targets if body.extraction_targets
        else existing.get("extraction_targets") or []
    )
    existing_target_ids = {t["target_id"] for t in extraction_targets}

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


# ── POST /{runId}/confirm ──────────────────────────────────────────────────────

@router.post("/{run_id}/confirm")
async def confirm_run(
    run_id: str,
    background_tasks: BackgroundTasks,
    user: TokenData = Depends(get_current_user),
):
    """Confirm page: user approved. Updates status and starts the pipeline."""
    run = _db_get_run(run_id, user.org_id)
    require_run_access(user, run)
    if run["status"] not in ("pending_confirm",):
        raise HTTPException(status_code=409, detail=f"Run already in status: {run['status']}")

    _db_update_status(run_id, "running")
    audit(org_id=user.org_id, run_id=run_id, event_type="run.confirmed", actor=user.email,
          detail={"rfp_title": run.get("rfp_title"), "department": run.get("department")})
    background_tasks.add_task(_run_pipeline, run_id, user.org_id)
    return {"run_id": run_id, "status": "running"}


# ── Phase 3 PR-B — bypass-cache rerun (3.14 + 3.16) ──────────────────


@router.post("/{run_id}/rerun")
async def rerun_evaluation(
    run_id: str,
    background_tasks: BackgroundTasks,
    bypass_cache: bool = False,
    user: TokenData = Depends(get_current_user),
):
    """
    3.14 — Re-execute a completed evaluation_run. The original run row stays
    as audit record. A new evaluation_runs row is created, points at the
    same RFP + vendor inputs, and is processed by _run_pipeline.

    bypass_cache=true:
      - Disables the LLM response cache for THIS rerun only (via a
        ContextVar that propagates through the background task).
      - 3.16: when the rerun completes, the divergence between the cached
        and fresh decision_output is computed and recorded on the new run
        for the report to surface.
    """
    import sqlalchemy as sa

    from app.db.fact_store import get_engine
    from app.providers import llm_cache

    original = _db_get_run(run_id, user.org_id)
    require_run_access(user, original)
    if original["status"] not in ("complete", "blocked"):
        raise HTTPException(
            status_code=409,
            detail=f"Cannot rerun while original status is '{original['status']}'.",
        )

    new_run_id = str(uuid.uuid4())
    engine = get_engine()
    with engine.begin() as conn:
        result = conn.execute(
            sa.text(
                """
                INSERT INTO evaluation_runs (
                    run_id, org_id, setup_id, rfp_id, rfp_title, department,
                    rfp_filename, rfp_bytes, agent_id, status, vendor_ids,
                    contract_value, currency, approval_tier, vendor_names,
                    created_by_email, creator_dept_id
                )
                SELECT
                    CAST(:new_id AS uuid), org_id, setup_id, rfp_id, rfp_title,
                    department, rfp_filename, rfp_bytes, agent_id, 'running',
                    vendor_ids, contract_value, currency, approval_tier,
                    vendor_names, :email, creator_dept_id
                FROM evaluation_runs WHERE run_id = CAST(:orig_id AS uuid)
                """
            ),
            {"new_id": new_run_id, "orig_id": run_id, "email": user.email},
        )
        # Code-review fix #2: SELECT can match 0 rows if the original was
        # deleted between _db_get_run() and the INSERT (TOCTOU race).
        # Without this guard the endpoint would return a new_run_id for a
        # row that never existed, then the BackgroundTask would crash on
        # its own _db_get_run lookup with a confusing 404.
        if result.rowcount == 0:
            raise HTTPException(
                status_code=409,
                detail="Original run was deleted before the rerun could be cloned.",
            )

    audit(
        org_id=user.org_id, run_id=new_run_id,
        event_type="run.rerun_started", actor=user.email,
        detail={
            "original_run_id": run_id, "bypass_cache": bypass_cache,
        },
    )

    async def _rerun_with_bypass():
        # ContextVar is set INSIDE the new task so it survives the
        # BackgroundTask scheduling boundary without needing
        # contextvars.copy_context(). FastAPI awaits this coroutine
        # directly — no fire-and-forget asyncio.create_task involved.
        if bypass_cache:
            llm_cache.disable_for_current_context()
        await _run_pipeline(new_run_id, user.org_id)
        if bypass_cache:
            await _compute_divergence(
                original_run_id=run_id,
                new_run_id=new_run_id,
                org_id=user.org_id,
            )

    background_tasks.add_task(_rerun_with_bypass)

    return {
        "new_run_id": new_run_id,
        "original_run_id": run_id,
        "bypass_cache": bypass_cache,
        "status": "running",
    }


async def _compute_divergence(
    *, original_run_id: str, new_run_id: str, org_id: str,
) -> None:
    """3.16 — After a bypass_cache rerun finishes, compare decision_output
    headline numbers against the cached run. Persists a `divergence_flag`
    on the new run's decision_output JSON if they differ.

    Uses the shared `extract_decision_summary` helper so Phase 7 (PDF
    report), Phase 8 (delivery channels), and any future decision-diff
    feature can rely on the same comparison shape. Code-review fix #1
    (None-safe sort) lives inside that helper.
    """
    import json as _json
    import sqlalchemy as sa

    from app.db.fact_store import get_engine
    from app.domain.decision_summary import extract_decision_summary

    engine = get_engine()
    with engine.connect() as conn:
        rows = conn.execute(
            sa.text(
                """
                SELECT run_id::text AS rid, decision_output
                FROM evaluation_runs
                WHERE run_id IN (CAST(:a AS uuid), CAST(:b AS uuid))
                """
            ),
            {"a": original_run_id, "b": new_run_id},
        ).fetchall()
    by_id = {r.rid: r.decision_output for r in rows}
    a = by_id.get(original_run_id) or {}
    b = by_id.get(new_run_id) or {}

    sig_a = extract_decision_summary(a)
    sig_b = extract_decision_summary(b)
    if sig_a == sig_b:
        return

    if not isinstance(b, dict):
        # New run never wrote a decision_output (e.g., pipeline blocked).
        # Nothing to attach the flag to; skip silently.
        return

    b_with_flag = dict(b)
    b_with_flag["divergence_flag"] = {
        "diverges_from": original_run_id,
        "cached_signature": sig_a,
        "fresh_signature":  sig_b,
        "message": "Re-run with bypass_cache produced a different shortlist "
                   "than the cached run — model is non-deterministic on "
                   "this RFP. Review both runs.",
    }
    with engine.begin() as conn:
        conn.execute(
            sa.text(
                """
                UPDATE evaluation_runs
                SET decision_output = CAST(:dec AS JSONB)
                WHERE run_id = CAST(:rid AS uuid)
                """
            ),
            {"dec": _json.dumps(b_with_flag), "rid": new_run_id},
        )
    audit(
        org_id=org_id, run_id=new_run_id,
        event_type="run.divergence_flagged", actor="system",
        detail={"original_run_id": original_run_id, "fresh_signature": sig_b,
                "cached_signature": sig_a},
    )


# ── SSE streams ────────────────────────────────────────────────────────────────

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


# ── GET /{runId}/report.html | report.pdf  (Phase 7) ───────────────────────────

def _run_report_or_404(run_id: str, user: TokenData, action: str) -> dict:
    """Shared loader: org-scoped fetch + access check + 'run complete' gate."""
    run = _db_get_run(run_id, user.org_id)
    require_run_access(user, run)
    log_access(run_id, user.org_id, user.email, action)
    if not run.get("decision_output"):
        raise HTTPException(
            status_code=409,
            detail="Report not available — this run has not completed.",
        )
    return run


@router.get("/{run_id}/report.html", response_class=HTMLResponse)
async def get_report_html(run_id: str, user: TokenData = Depends(get_current_user)):
    """In-app report view: the customer logs in and reads the report as HTML."""
    from app.output.pdf_report import build_report_html_for_run
    run = _run_report_or_404(run_id, user, "view_report_html")
    return HTMLResponse(content=build_report_html_for_run(run))


@router.get("/{run_id}/report.pdf")
async def get_report_pdf(run_id: str, user: TokenData = Depends(get_current_user)):
    """Download the report as a PDF (same template as the HTML view)."""
    from app.output.pdf_report import render_report_pdf_for_run
    run = _run_report_or_404(run_id, user, "download_report_pdf")
    try:
        pdf = render_report_pdf_for_run(run)
    except RuntimeError as exc:
        # weasyprint / native libs unavailable in this deployment.
        raise HTTPException(status_code=503, detail=str(exc))
    filename = f"evaluation-report-{run_id[:8]}.pdf"
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ── GET /{runId}/results ───────────────────────────────────────────────────────

@router.get("/{run_id}/results")
async def get_results(run_id: str, user: TokenData = Depends(get_current_user)):
    run = _db_get_run(run_id, user.org_id)
    require_run_access(user, run)
    log_access(run_id, user.org_id, user.email, "view_results")
    decision = run.get("decision_output") or {}

    vendors = []
    for v in decision.get("shortlisted_vendors", []):
        vendors.append({
            "vendor_name":      v.get("vendor_name", v.get("vendor_id", "Unknown")),
            "decision":         "shortlisted",
            "total_score":      v.get("total_score", 0),
            "score_confidence": v.get("score_confidence"),
            "recommendation":   v.get("recommendation"),
            "summary":          v.get("recommendation", ""),
        })
    for v in decision.get("rejected_vendors", []):
        vendors.append({
            "vendor_name":      v.get("vendor_name", v.get("vendor_id", "Unknown")),
            "decision":         "rejected",
            "total_score":      0,
            "score_confidence": None,
            "recommendation":   None,
            "summary":          "; ".join(v.get("rejection_reasons", [])),
        })

    approval_routing = decision.get("approval_routing") or {}

    return {
        "run_id":        run_id,
        "status":        run.get("status"),
        "rfp_title":     run.get("rfp_title", ""),
        "department":    run.get("department", ""),
        "vendors":       vendors,
        "recommendation": (
            decision.get("shortlisted_vendors", [{}])[0].get("recommendation", "")
            if decision.get("shortlisted_vendors") else ""
        ),
        "approval_tier":        approval_routing.get("approval_tier"),
        "decision_confidence":  decision.get("decision_confidence"),
        "requires_human_review": decision.get("requires_human_review", False),
        "review_reasons":       decision.get("review_reasons", []),
        "decision":             decision,
        "agent_log":            run.get("agent_log") or [],
        "vendor_names":         run.get("vendor_names") or {},
    }


# ── GET /{runId}/decision ──────────────────────────────────────────────────────

@router.get("/{run_id}/decision")
async def get_vendor_decision(run_id: str, vendor: str,
                               user: TokenData = Depends(get_current_user)):
    run = _db_get_run(run_id, user.org_id)
    require_run_access(user, run)
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
    require_admin_role(user)
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
                "override_id":   override.override_id,
                "org_id":        user.org_id,
                "run_id":        run_id,
                "overridden_by": override.overridden_by,
                "original":      json.dumps(override.original_decision),
                "new_decision":  json.dumps(override.new_decision),
                "reason":        override.reason,
                "timestamp":     override.timestamp,
            },
        )

    audit(org_id=user.org_id, run_id=run_id, event_type="override.submitted",
          actor=user.email,
          detail={"vendor_id": body.vendor_id, "reason": body.reason,
                  "override_id": override.override_id})

    return {"override_id": override.override_id, "status": "recorded"}


# ── POST /{runId}/re-evaluate ──────────────────────────────────────────────────

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


# ── GET /{runId}/audit ─────────────────────────────────────────────────────────

@router.get("/{run_id}/audit")
async def get_audit_trail(run_id: str, user: TokenData = Depends(get_current_user)):
    """Return the full append-only audit trail for a run, ordered by time."""
    run = _db_get_run(run_id, user.org_id)
    require_run_access(user, run)
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


# ── GET /{runId}/export ────────────────────────────────────────────────────────

@router.get("/{run_id}/export")
async def export_run_csv(run_id: str, user: TokenData = Depends(get_current_user)):
    """Download evaluation results as CSV with criterion-level scores and grounding quotes."""
    import csv
    import io
    from fastapi.responses import StreamingResponse

    run = _db_get_run(run_id, user.org_id)
    require_run_access(user, run)

    decision = run.get("decision_output") or {}
    rfp_title  = run.get("rfp_title", run_id)
    department = run.get("department", "")
    started_at = run.get("created_at", "")
    if hasattr(started_at, "isoformat"):
        started_at = started_at.isoformat()

    buf = io.StringIO()
    writer = csv.writer(buf)

    # Header
    writer.writerow([
        "run_id", "rfp_title", "department", "started_at",
        "vendor_name", "decision", "total_score", "score_confidence",
        "recommendation",
        "criterion_id", "raw_score", "weighted_contribution",
        "criterion_confidence", "rubric_band", "rationale",
        "evidence_1", "evidence_2",
    ])

    for v in decision.get("shortlisted_vendors", []):
        vendor_name = v.get("vendor_name", v.get("vendor_id", ""))
        breakdown   = v.get("criterion_breakdown", [])
        base = [
            run_id, rfp_title, department, started_at,
            vendor_name, "shortlisted",
            v.get("total_score", ""), v.get("score_confidence", ""),
            v.get("recommendation", ""),
        ]
        if breakdown:
            for c in breakdown:
                evidence = c.get("evidence_used", [])
                writer.writerow(base + [
                    c.get("criterion_id", ""),
                    c.get("raw_score", ""),
                    c.get("weighted_contribution", ""),
                    c.get("confidence", ""),
                    c.get("rubric_band_applied", ""),
                    c.get("score_rationale", ""),
                    evidence[0] if len(evidence) > 0 else "",
                    evidence[1] if len(evidence) > 1 else "",
                ])
        else:
            writer.writerow(base + [""] * 8)

    for v in decision.get("rejected_vendors", []):
        vendor_name = v.get("vendor_name", v.get("vendor_id", ""))
        reasons = "; ".join(v.get("rejection_reasons", []))
        writer.writerow([
            run_id, rfp_title, department, started_at,
            vendor_name, "rejected", "", "", "",
            "", "", "", "", "",
            reasons, "", "",
        ])

    buf.seek(0)
    filename = f"evaluation_{run_id[:8]}.csv"
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=\"{filename}\""},
    )


# ── GET /{runId}/cost ──────────────────────────────────────────────────────────

@router.get("/{run_id}/cost")
async def get_run_cost_endpoint(run_id: str, user: TokenData = Depends(get_current_user)):
    """Return LLM cost and token usage for a run (live if in-progress, persisted if completed)."""
    run = _db_get_run(run_id, user.org_id)
    require_run_access(user, run)

    from app.infra.cost_tracker import get_run_cost as _get_cost
    acc = _get_cost(run_id)
    if acc is not None:
        return {**acc.summary(), "source": "live"}

    engine = get_engine()
    with engine.connect() as conn:
        row = conn.execute(
            sa.text("""
                SELECT llm_cost_usd, llm_tokens_total
                FROM evaluation_runs
                WHERE run_id = CAST(:rid AS uuid)
                  AND org_id = CAST(:oid AS uuid)
            """),
            {"rid": run_id, "oid": user.org_id},
        ).fetchone()
    return {
        "run_id": run_id,
        "total_cost_usd": float(row[0]) if row[0] is not None else None,
        "total_tokens": row[1],
        "by_agent": {},
        "source": "persisted",
    }


# ── GET /{runId}/cost-estimate ─────────────────────────────────────────────────

@router.get("/{run_id}/cost-estimate")
async def get_cost_estimate(run_id: str, user: TokenData = Depends(get_current_user)):
    """Pre-run cost estimate based on vendor count and configured LLM model."""
    run = _db_get_run(run_id, user.org_id)
    require_run_access(user, run)

    from app.infra.cost_tracker import estimate_cost
    from app.config import settings

    vendor_ids = run.get("vendor_ids") or []
    vendor_count = len(vendor_ids) if isinstance(vendor_ids, list) else 0
    if vendor_count == 0:
        vendor_count = 1

    model = settings.openai_model or "gpt-4o"
    # 9-agent pipeline: ~3 000 prompt + 800 output tokens per agent per vendor
    low_cost  = estimate_cost(model, vendor_count * 9 * 2_000, vendor_count * 9 * 500)
    high_cost = estimate_cost(model, vendor_count * 9 * 5_000, vendor_count * 9 * 1_500)

    return {
        "run_id": run_id,
        "vendor_count": vendor_count,
        "model": model,
        "estimated_cost_low_usd":  round(low_cost,  4),
        "estimated_cost_high_usd": round(high_cost, 4),
        "currency": run.get("currency") or "GBP",
    }


# ── POST /{runId}/cancel ───────────────────────────────────────────────────────

@router.post("/{run_id}/cancel")
async def cancel_run(run_id: str, user: TokenData = Depends(get_current_user)):
    """Mark a running evaluation as interrupted so the SSE stream terminates."""
    run = _db_get_run(run_id, user.org_id)
    require_run_access(user, run)

    if run["status"] not in ("running", "pending"):
        raise HTTPException(
            status_code=409,
            detail=f"Cannot cancel a run with status '{run['status']}'.",
        )

    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(
            sa.text("""
                UPDATE evaluation_runs
                SET status = 'interrupted', completed_at = NOW()
                WHERE run_id = CAST(:rid AS uuid)
                  AND org_id = CAST(:oid AS uuid)
            """),
            {"rid": run_id, "oid": user.org_id},
        )

    return {"run_id": run_id, "status": "interrupted"}


# ── DELETE /{runId} ────────────────────────────────────────────────────────────

@router.delete("/{run_id}")
async def delete_run(run_id: str, user: TokenData = Depends(get_current_user)):
    """
    Permanently delete an evaluation run.
    Blocked if the run status is 'completed' — those are audit records.
    Blocked if the run is currently 'running' — would orphan the pipeline.
    """
    run = _db_get_run(run_id, user.org_id)
    require_run_access(user, run)

    if run["status"] == "completed":
        raise HTTPException(
            status_code=409,
            detail="Completed runs cannot be deleted — they are audit records.",
        )
    if run["status"] == "running":
        raise HTTPException(
            status_code=409,
            detail="Cannot delete a run that is currently in progress.",
        )

    engine = get_engine()
    with engine.begin() as conn:
        rid = {"rid": run_id}
        conn.execute(sa.text("DELETE FROM approvals       WHERE run_id = CAST(:rid AS uuid)"), rid)
        conn.execute(sa.text("DELETE FROM decisions        WHERE run_id = CAST(:rid AS uuid)"), rid)
        conn.execute(sa.text("DELETE FROM retrieval_log    WHERE run_id = CAST(:rid AS uuid)"), rid)
        conn.execute(sa.text("UPDATE audit_log SET run_id = NULL WHERE run_id = CAST(:rid AS uuid)"), rid)
        conn.execute(
            sa.text("DELETE FROM vendor_documents WHERE rfp_id = :rfp_id AND org_id = CAST(:oid AS uuid)"),
            {"rfp_id": run["rfp_id"], "oid": user.org_id},
        )
        if run.get("setup_id"):
            conn.execute(sa.text("DELETE FROM extracted_facts WHERE setup_id = :sid"), {"sid": run["setup_id"]})
        conn.execute(
            sa.text("DELETE FROM evaluation_runs WHERE run_id = CAST(:rid AS uuid) AND org_id = CAST(:oid AS uuid)"),
            {"rid": run_id, "oid": user.org_id},
        )
        if run.get("setup_id"):
            conn.execute(sa.text("DELETE FROM evaluation_setups WHERE setup_id = :sid"), {"sid": run["setup_id"]})

    audit(org_id=user.org_id, run_id=run_id, event_type="run.deleted",
          actor=user.email, detail={"status_at_deletion": run["status"]})

    return {"run_id": run_id, "deleted": True}


# ═══════════════════════════════════════════════════════════════════════════
# Phase 9 — Collaborator management on a specific evaluation run
# ═══════════════════════════════════════════════════════════════════════════

class CollaboratorRequest(BaseModel):
    user_id: str
    role: str = "viewer"  # 'viewer' | 'reviewer' | 'editor'


@router.post("/{run_id}/collaborators")
async def add_run_collaborator(
    run_id: str,
    body: CollaboratorRequest,
    user: TokenData = Depends(get_current_user),
):
    """Invite a user to collaborate on this evaluation run. The caller must
    already have view access to the run (creator, dept member, admin, or
    existing collaborator with editor role)."""
    run = _db_get_run(run_id, user.org_id)
    require_run_access(user, run)

    # Look up adder's user_id (we need it for added_by FK).
    import sqlalchemy as _sa
    from app.db.fact_store import get_engine as _ge
    with _ge().connect() as _conn:
        row = _conn.execute(
            _sa.text("SELECT user_id::text FROM users WHERE email = :email AND org_id = CAST(:oid AS uuid)"),
            {"email": user.email, "oid": user.org_id},
        ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Caller user record not found")
    adder_user_id = row[0]

    from app.domain.visibility import add_collaborator as _add
    try:
        _add(run_id, body.user_id, body.role, adder_user_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    audit(org_id=user.org_id, run_id=run_id, event_type="collaborator.added",
          actor=user.email, detail={"invited_user_id": body.user_id, "role": body.role})
    return {"status": "ok", "run_id": run_id, "user_id": body.user_id, "role": body.role}


@router.delete("/{run_id}/collaborators/{user_id}")
async def remove_run_collaborator(
    run_id: str,
    user_id: str,
    user: TokenData = Depends(get_current_user),
):
    """Remove a collaborator. Same access requirement as adding."""
    run = _db_get_run(run_id, user.org_id)
    require_run_access(user, run)

    from app.domain.visibility import remove_collaborator as _rm
    _rm(run_id, user_id)

    audit(org_id=user.org_id, run_id=run_id, event_type="collaborator.removed",
          actor=user.email, detail={"removed_user_id": user_id})
    return {"status": "ok", "run_id": run_id, "removed_user_id": user_id}
