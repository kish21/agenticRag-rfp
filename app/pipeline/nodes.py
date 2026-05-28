"""
LangGraph node functions — one per agent in the 9-agent pipeline.

Each node:
  1. Calls the underlying agent function (unchanged).
  2. Passes the CriticOutput to _hard_block_if() — raises on HARD verdict.
  3. Returns a dict of state fields to update (LangGraph merges this).
  4. On any exception, returns the blocked sentinel via _block_update().

The agents themselves are NOT modified. All business logic stays in app/agents/.
"""
import traceback
import uuid
from datetime import datetime, timezone

from app.infra.audit import audit
from app.infra.logger import rfp_logger, DevLevel
from app.schemas.output_models import (
    EvaluationSetup,
    RetrievalOutput,
    CriticVerdict,
)
from app.agents.critic import (
    critic_after_retrieval,
    critic_after_comparator,
    critic_after_decision,
    critic_after_explanation,
)
from app.agents.planner import run_planner
from app.agents.ingestion import run_ingestion_agent
from app.agents.retrieval import run_retrieval_agent
from app.agents.extraction import run_extraction_agent
from app.agents.evaluation import run_evaluation_agent
from app.agents.comparator import run_comparator_agent
from app.agents.decision import run_decision_agent
from app.agents.explanation import run_explanation_agent
from app.api._evaluation.db import (
    _db_append_event,
    _db_append_log,
    _db_update_status,
)

from .state import PipelineState
from .concurrency import vendor_slot


# ── Shared helpers ────────────────────────────────────────────────────────────

def _emit(
    state: PipelineState,
    agent: str,
    status: str,
    message: str = "",
    log_msg: str = "",
) -> None:
    run_id = state["run_id"]
    org_id = state["org_id"]
    event = {"agent": agent, "status": status, "message": message,
             "log_msg": log_msg or message}
    try:
        _db_append_event(run_id, event)
        rfp_logger.dev(DevLevel.AGENT, agent, f"{status}: {message}",
                       data={"status": status}, run_id=run_id, org_id=org_id)
    except Exception as e:
        rfp_logger.dev(DevLevel.ERROR, agent, f"_emit DB write failed: {e}",
                       run_id=run_id, org_id=org_id)
    if log_msg:
        entry = {"ts": datetime.now(timezone.utc).isoformat(),
                 "agent": agent, "status": status, "message": log_msg}
        try:
            _db_append_log(run_id, entry)
        except Exception:
            pass
    event_type = (
        "agent.started"   if status == "running"  else
        "agent.completed" if status == "done"      else
        "agent.blocked"   if status == "blocked"   else None
    )
    if event_type:
        audit(org_id=org_id, run_id=run_id, event_type=event_type,
              actor="system", agent=agent, detail={"message": message})


def _hard_block_if(critic, context: str) -> None:
    if critic.overall_verdict == CriticVerdict.BLOCKED:
        hard_descs = [f.description for f in critic.flags
                      if f.severity.value == "hard"]
        raise RuntimeError(f"[CRITIC BLOCK] {context}: {'; '.join(hard_descs)}")


def _block_update(state: PipelineState, agent: str, exc: Exception) -> dict:
    run_id = state["run_id"]
    org_id = state["org_id"]
    msg = str(exc)
    rfp_logger.dev(DevLevel.ERROR, agent, f"Pipeline blocked: {exc}",
                   data={"traceback": traceback.format_exc()},
                   run_id=run_id, org_id=org_id)
    rfp_logger.end_run(run_id=run_id, org_id=org_id, status="blocked")
    _emit(state, agent, "blocked", msg,
          log_msg=f"Something went wrong in the {agent} step. "
                  "The evaluation could not continue.")
    try:
        _db_update_status(run_id, "blocked", completed=True)
    except Exception:
        pass
    audit(org_id=org_id, run_id=run_id, event_type="run.blocked",
          actor="system", detail={"agent": agent, "error": msg})
    return {"blocked": True, "blocked_agent": agent, "error_message": msg}


# ── Node 1 — Planner ──────────────────────────────────────────────────────────

async def planner_node(state: PipelineState) -> dict:
    agent = "planner"
    vendor_ids = state["vendor_ids"]
    n_vendors = state["n_vendors"]
    evaluation_setup = EvaluationSetup(**state["evaluation_setup_dict"])
    try:
        _emit(state, agent, "running",
              "Decomposing evaluation into task DAG",
              log_msg=f"Reading the RFP and planning how to evaluate "
                      f"{n_vendors} vendor{'s' if n_vendors != 1 else ''}.")
        planner_out, planner_critic = await run_planner(
            rfp_id=state["rfp_id"], org_id=state["org_id"],
            vendor_ids=vendor_ids, evaluation_setup=evaluation_setup)
        _hard_block_if(planner_critic, "planner")
        _emit(state, agent, "done", "Task DAG ready",
              log_msg=f"Evaluation plan created — "
                      f"{len(evaluation_setup.mandatory_checks)} compliance checks and "
                      f"{len(evaluation_setup.scoring_criteria)} scoring criteria defined.")
        return {}
    except Exception as exc:
        return _block_update(state, agent, exc)


# ── Node 2 — Ingestion ────────────────────────────────────────────────────────

async def ingestion_node(state: PipelineState) -> dict:
    agent = "ingestion"
    org_id = state["org_id"]
    rfp_id = state["rfp_id"]
    vendor_file_map = state["vendor_file_map"]
    evaluation_setup = EvaluationSetup(**state["evaluation_setup_dict"])
    try:
        _emit(state, agent, "running",
              f"Ingesting RFP + {len(vendor_file_map)} vendor docs",
              log_msg=f"Reading and indexing the RFP document plus "
                      f"{len(vendor_file_map)} vendor "
                      f"proposal{'s' if len(vendor_file_map) != 1 else ''}.")

        _, rfp_critics = await run_ingestion_agent(
            content=state["rfp_bytes"], filename=state["rfp_filename"],
            vendor_id="rfp", org_id=org_id, rfp_id=rfp_id,
            evaluation_setup=evaluation_setup)
        for c in rfp_critics:
            _hard_block_if(c, f"ingestion/{state['rfp_filename']}")

        for vid, (vbytes, vfilename) in vendor_file_map.items():
            _, ving_critics = await run_ingestion_agent(
                content=vbytes, filename=vfilename,
                vendor_id=vid, org_id=org_id, rfp_id=rfp_id,
                evaluation_setup=evaluation_setup)
            for c in ving_critics:
                if c.overall_verdict.value in ("approved_with_warnings", "blocked"):
                    rfp_logger.dev(DevLevel.INFO, agent,
                                   f"Vendor {vid} critic: {c.overall_verdict.value} "
                                   f"— {len(c.flags)} flag(s)",
                                   data={"vendor_id": vid,
                                         "verdict": c.overall_verdict.value,
                                         "flags": [f.check_name for f in c.flags]},
                                   run_id=state["run_id"], org_id=org_id)
                _hard_block_if(c, f"ingestion/{vfilename} (vendor={vid})")

        _emit(state, agent, "done",
              f"RFP + {len(vendor_file_map)} vendor docs indexed",
              log_msg=f"All documents processed and indexed — "
                      f"{len(vendor_file_map)} vendor "
                      f"proposal{'s' if len(vendor_file_map) != 1 else ''} "
                      "ready for analysis.")
        return {}
    except Exception as exc:
        return _block_update(state, agent, exc)


# ── Node 3 — Retrieval (Phase 4: fan-out across vendors) ──────────────────────
# Stage is split into three nodes:
#   retrieval_start       — tiny, emits "running" event (preserves SSE UX)
#   retrieval_per_vendor  — does the work for ONE vendor; runs in parallel
#                           via LangGraph Send. Bounded by vendor_slot semaphore.
#   retrieval_done        — tiny, emits "done" after all parallel branches join

async def retrieval_start(state: PipelineState) -> dict:
    agent = "retrieval"
    n_vendors = state["n_vendors"]
    _emit(state, agent, "running",
          f"Retrieving chunks for {n_vendors} vendors",
          log_msg="Searching each vendor proposal for relevant sections on "
                  "pricing, compliance, SLAs, and technical capability.")
    return {}


async def retrieval_per_vendor(state: PipelineState) -> dict:
    """One-vendor retrieval. LangGraph spawns this once per vendor via Send.

    Failure isolation: per-vendor exceptions append to `failed_vendors` instead
    of aborting the whole pipeline. The other vendors keep going.
    """
    agent = "retrieval"
    vid = state["vendor_id"]
    org_id = state["org_id"]
    rfp_id = state["rfp_id"]
    evaluation_setup = EvaluationSetup(**state["evaluation_setup_dict"])
    org_settings = state["org_settings"]
    mandatory_names = {c.name for c in evaluation_setup.mandatory_checks}

    queries = (
        [c.name for c in evaluation_setup.scoring_criteria] +
        [c.name for c in evaluation_setup.mandatory_checks]
    ) or ["technical capability SLA pricing compliance certifications experience"]

    try:
        async with vendor_slot():
            seen: set = set()
            merged_chunks = []
            for query in queries:
                ret_out, ret_critic = await run_retrieval_agent(
                    query=query, vendor_id=vid, org_id=org_id, rfp_id=rfp_id,
                    is_mandatory_check=(query in mandatory_names),
                    org_settings=org_settings)
                if ret_critic.overall_verdict.value != "approved":
                    rfp_logger.dev(DevLevel.INFO, agent,
                                   f"Vendor {vid} query '{query[:60]}' "
                                   f"critic: {ret_critic.overall_verdict.value}",
                                   data={"vendor_id": vid,
                                         "verdict": ret_critic.overall_verdict.value,
                                         "flags": [f.check_name for f in ret_critic.flags]},
                                   run_id=state["run_id"], org_id=org_id)
                for chunk in ret_out.chunks:
                    if chunk.chunk_id not in seen:
                        seen.add(chunk.chunk_id)
                        merged_chunks.append(chunk)

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
                empty_retrieval=(len(merged_chunks) == 0),
                warnings=[],
            )

            # Per-vendor critic — restored after Phase 4 regression review.
            # HARD verdicts mark THIS vendor as failed (other vendors continue
            # under per-vendor isolation); soft warnings are logged only.
            # Pre-Phase-4 behaviour was "HARD → abort the whole pipeline";
            # Phase 4 isolation upgrades this to "HARD → fail this vendor".
            combined_critic = critic_after_retrieval(combined, is_mandatory=False)
            if combined_critic.overall_verdict == CriticVerdict.BLOCKED:
                hard_descs = "; ".join(f.description for f in combined_critic.flags
                                       if f.severity.value == "hard")[:240]
                rfp_logger.dev(DevLevel.ERROR, agent,
                               f"Vendor {vid} retrieval HARD-blocked by critic: {hard_descs}",
                               data={"vendor_id": vid,
                                     "verdict": combined_critic.overall_verdict.value,
                                     "flags": [f.check_name for f in combined_critic.flags]},
                               run_id=state["run_id"], org_id=org_id)
                return {
                    "failed_vendors": [{
                        "vendor_id": vid, "stage": "retrieval",
                        "error": f"critic_hard_block: {hard_descs}",
                        "ts": datetime.now(timezone.utc).isoformat(),
                    }],
                }

            rfp_logger.dev(DevLevel.RAG, agent,
                           f"Vendor {vid}: {len(merged_chunks)} unique chunks "
                           f"from {len(queries)} queries",
                           data={"vendor_id": vid, "queries": len(queries),
                                 "unique_chunks": len(merged_chunks),
                                 "confidence": combined.confidence},
                           run_id=state["run_id"], org_id=org_id)

            return {
                "retrieval_output_objects": {vid: combined},
                "source_chunks": {c.chunk_id: c.text for c in merged_chunks},
            }
    except Exception as exc:
        rfp_logger.dev(DevLevel.ERROR, agent,
                       f"Vendor {vid} retrieval failed: {exc}",
                       data={"vendor_id": vid, "error": str(exc),
                             "traceback": traceback.format_exc()},
                       run_id=state["run_id"], org_id=org_id)
        return {
            "failed_vendors": [{
                "vendor_id": vid, "stage": "retrieval",
                "error": str(exc),
                "ts": datetime.now(timezone.utc).isoformat(),
            }],
        }


async def retrieval_done(state: PipelineState) -> dict:
    agent = "retrieval"
    n_vendors = state["n_vendors"]
    n_failed = len([f for f in (state.get("failed_vendors") or [])
                    if f.get("stage") == "retrieval"])
    n_ok = n_vendors - n_failed
    _emit(state, agent, "done",
          f"Retrieved chunks for {n_ok} of {n_vendors} vendors"
          + (f" ({n_failed} failed)" if n_failed else ""),
          log_msg=f"Found relevant passages from {n_ok} of {n_vendors} vendor proposals.")
    return {}


# ── Node 4 — Extraction (Phase 4: fan-out across vendors) ─────────────────────

async def extraction_start(state: PipelineState) -> dict:
    agent = "extraction"
    evaluation_setup = EvaluationSetup(**state["evaluation_setup_dict"])
    _emit(state, agent, "running",
          "Extracting structured facts",
          log_msg=f"Pulling specific facts from each proposal against "
                  f"{len(evaluation_setup.extraction_targets)} extraction targets.")
    return {}


async def extraction_per_vendor(state: PipelineState) -> dict:
    """One-vendor extraction. Failure isolation via failed_vendors."""
    agent = "extraction"
    vid = state["vendor_id"]
    org_id = state["org_id"]
    rfp_id = state["rfp_id"]
    evaluation_setup = EvaluationSetup(**state["evaluation_setup_dict"])
    retrieval_output_objects = state.get("retrieval_output_objects") or {}

    # Skip if this vendor failed retrieval — nothing to extract from.
    if vid not in retrieval_output_objects:
        return {
            "failed_vendors": [{
                "vendor_id": vid, "stage": "extraction",
                "error": "no retrieval output available (vendor failed upstream)",
                "ts": datetime.now(timezone.utc).isoformat(),
            }],
        }

    ret_out = retrieval_output_objects[vid]
    try:
        async with vendor_slot():
            ext_out, critic_ext = await run_extraction_agent(
                retrieval_output=ret_out, vendor_id=vid, org_id=org_id,
                doc_id=f"{rfp_id}-{vid}", setup_id=state["setup_id"],
                evaluation_setup=evaluation_setup, run_id=state["run_id"])
            rfp_logger.dev(DevLevel.INFO, agent,
                           f"Vendor {vid}: {len(ext_out.slas)} SLAs, "
                           f"{len(ext_out.pricing)} pricing, "
                           f"{len(ext_out.extracted_facts)} facts",
                           data={"vendor_id": vid,
                                 "slas": len(ext_out.slas),
                                 "pricing": len(ext_out.pricing),
                                 "facts": len(ext_out.extracted_facts),
                                 "completeness": round(ext_out.extraction_completeness, 2),
                                 "hallucination_risk": round(ext_out.hallucination_risk, 2),
                                 "critic": critic_ext.overall_verdict},
                           run_id=state["run_id"], org_id=org_id)
            return {"extraction_output_objects": {vid: ext_out}}
    except Exception as exc:
        rfp_logger.dev(DevLevel.ERROR, agent,
                       f"Vendor {vid} extraction failed: {exc}",
                       data={"vendor_id": vid, "error": str(exc),
                             "traceback": traceback.format_exc()},
                       run_id=state["run_id"], org_id=org_id)
        return {
            "failed_vendors": [{
                "vendor_id": vid, "stage": "extraction",
                "error": str(exc),
                "ts": datetime.now(timezone.utc).isoformat(),
            }],
        }


async def extraction_done(state: PipelineState) -> dict:
    agent = "extraction"
    extraction_output_objects = state.get("extraction_output_objects") or {}
    total_facts = sum(
        len(getattr(o, "certifications", []) or []) +
        len(getattr(o, "slas", []) or []) +
        len(getattr(o, "pricing", []) or [])
        for o in extraction_output_objects.values()
    )
    n_ok = len(extraction_output_objects)
    n_vendors = state["n_vendors"]
    _emit(state, agent, "done", "Facts extracted and stored",
          log_msg=f"Extracted {total_facts} verifiable facts from {n_ok} of {n_vendors} vendors.")
    return {}


# ── Node 5 — Evaluation ───────────────────────────────────────────────────────

async def evaluation_node(state: PipelineState) -> dict:
    agent = "evaluation"
    # ── (Original evaluation_node body replaced by Phase 4 fan-out below) ──
    raise NotImplementedError(
        "evaluation_node has been split into evaluation_start + evaluation_per_vendor + evaluation_done. "
        "Use the Phase 4 fan-out pattern in graph.py."
    )


# ── Node 5 — Evaluation (Phase 4: fan-out across vendors) ─────────────────────

async def evaluation_start(state: PipelineState) -> dict:
    agent = "evaluation"
    evaluation_setup = EvaluationSetup(**state["evaluation_setup_dict"])
    _emit(state, agent, "running",
          "Scoring vendors against criteria",
          log_msg=f"Scoring each vendor against your "
                  f"{len(evaluation_setup.scoring_criteria)} criteria "
                  "with their configured weights.")
    return {}


async def evaluation_per_vendor(state: PipelineState) -> dict:
    """One-vendor evaluation. Per-vendor critic flags are logged but do NOT
    block the pipeline in Phase 4. (Phase 2 will hook retry-with-feedback here.)"""
    agent = "evaluation"
    vid = state["vendor_id"]
    org_id = state["org_id"]
    evaluation_setup = EvaluationSetup(**state["evaluation_setup_dict"])
    extraction_output_objects = state.get("extraction_output_objects") or {}

    if vid not in extraction_output_objects:
        return {
            "failed_vendors": [{
                "vendor_id": vid, "stage": "evaluation",
                "error": "no extraction output available (vendor failed upstream)",
                "ts": datetime.now(timezone.utc).isoformat(),
            }],
        }

    try:
        async with vendor_slot():
            ev_out, ev_critic = await run_evaluation_agent(
                vendor_id=vid, org_id=org_id, run_id=state["run_id"],
                evaluation_setup=evaluation_setup,
                extraction_output=extraction_output_objects.get(vid))

            # HARD-block guard restored after Phase 4 regression review.
            # Pre-Phase-4: HARD critic on evaluation aborted the whole run.
            # Phase 4 isolation: HARD critic on ONE vendor's evaluation marks
            # that vendor failed (others continue). Soft/warning logged.
            if ev_critic.overall_verdict == CriticVerdict.BLOCKED:
                hard_descs = "; ".join(f.description for f in ev_critic.flags
                                       if f.severity.value == "hard")[:240]
                rfp_logger.dev(DevLevel.ERROR, agent,
                               f"Vendor {vid} evaluation HARD-blocked by critic: {hard_descs}",
                               data={"vendor_id": vid,
                                     "verdict": ev_critic.overall_verdict.value,
                                     "flags": [f.check_name for f in ev_critic.flags]},
                               run_id=state["run_id"], org_id=org_id)
                return {
                    "failed_vendors": [{
                        "vendor_id": vid, "stage": "evaluation",
                        "error": f"critic_hard_block: {hard_descs}",
                        "ts": datetime.now(timezone.utc).isoformat(),
                    }],
                }
            if ev_critic.overall_verdict.value != "approved":
                rfp_logger.dev(DevLevel.INFO, agent,
                               f"Vendor {vid} critic: {ev_critic.overall_verdict.value} "
                               f"— {len(ev_critic.flags)} flag(s)",
                               data={"vendor_id": vid,
                                     "verdict": ev_critic.overall_verdict.value,
                                     "flags": [f.check_name for f in ev_critic.flags]},
                               run_id=state["run_id"], org_id=org_id)
            return {"evaluation_output_objects": {vid: ev_out}}
    except Exception as exc:
        rfp_logger.dev(DevLevel.ERROR, agent,
                       f"Vendor {vid} evaluation failed: {exc}",
                       data={"vendor_id": vid, "error": str(exc),
                             "traceback": traceback.format_exc()},
                       run_id=state["run_id"], org_id=org_id)
        return {
            "failed_vendors": [{
                "vendor_id": vid, "stage": "evaluation",
                "error": str(exc),
                "ts": datetime.now(timezone.utc).isoformat(),
            }],
        }


async def evaluation_done(state: PipelineState) -> dict:
    agent = "evaluation"
    n_ok = len(state.get("evaluation_output_objects") or {})
    n_vendors = state["n_vendors"]
    _emit(state, agent, "done", f"Scored {n_ok} of {n_vendors} vendors",
          log_msg=f"{n_ok} vendor(s) scored. Scores ready for comparison.")
    return {}


# ── Node 6 — Comparator ───────────────────────────────────────────────────────

async def comparator_node(state: PipelineState) -> dict:
    agent = "comparator"
    org_id = state["org_id"]
    vendor_ids = state["vendor_ids"]
    evaluation_setup = EvaluationSetup(**state["evaluation_setup_dict"])
    evaluation_output_objects = state["evaluation_output_objects"]
    try:
        _emit(state, agent, "running",
              "Cross-vendor ranking and stability check",
              log_msg="Ranking vendors against each other and checking whether "
                      "the ranking is stable across scoring variations.")

        comp_out, comp_critic = await run_comparator_agent(
            vendor_ids=vendor_ids, org_id=org_id, rfp_id=state["rfp_id"],
            evaluation_setup=evaluation_setup,
            evaluation_outputs=evaluation_output_objects)
        _hard_block_if(comp_critic, "comparator")
        if comp_critic.overall_verdict.value != "approved":
            rfp_logger.dev(DevLevel.INFO, agent,
                           f"Comparator critic: {comp_critic.overall_verdict.value} "
                           f"— {len(comp_critic.flags)} flag(s)",
                           data={"verdict": comp_critic.overall_verdict.value,
                                 "flags": [f.check_name for f in comp_critic.flags]},
                           run_id=state["run_id"], org_id=org_id)

        _emit(state, agent, "done", "Vendors ranked",
              log_msg="Final vendor ranking confirmed.")

        return {"comparator_output": comp_out}
    except Exception as exc:
        return _block_update(state, agent, exc)


# ── Node 7 — Decision ─────────────────────────────────────────────────────────

async def decision_node(state: PipelineState) -> dict:
    agent = "decision"
    org_id = state["org_id"]
    evaluation_output_objects = state["evaluation_output_objects"]
    comp_out = state["comparator_output"]
    try:
        _emit(state, agent, "running",
              "Governance routing and approval tier selection",
              log_msg="Applying your organisation's governance rules to determine "
                      "the approval tier and required approvers.")

        dec_out, dec_critic = await run_decision_agent(
            evaluation_outputs=evaluation_output_objects,
            comparator_output=comp_out,
            contract_value=state["contract_value"])
        _hard_block_if(dec_critic, "decision")
        if dec_critic.overall_verdict.value != "approved":
            rfp_logger.dev(DevLevel.INFO, agent,
                           f"Decision critic: {dec_critic.overall_verdict.value} "
                           f"— {len(dec_critic.flags)} flag(s)",
                           data={"verdict": dec_critic.overall_verdict.value,
                                 "flags": [f.check_name for f in dec_critic.flags]},
                           run_id=state["run_id"], org_id=org_id)

        n_short = len(getattr(dec_out, "shortlisted_vendors", []) or [])
        n_rej   = len(getattr(dec_out, "rejected_vendors",    []) or [])
        _emit(state, agent, "done",
              "Decision and approval tier set",
              log_msg=f"{n_short} vendor{'s' if n_short != 1 else ''} shortlisted, "
                      f"{n_rej} rejected. Approval routing determined.")

        return {"decision_output": dec_out}
    except Exception as exc:
        return _block_update(state, agent, exc)


# ── Node 8 — Explanation ──────────────────────────────────────────────────────

async def explanation_node(state: PipelineState) -> dict:
    """DEPRECATED in Phase 4 — split into explanation_start / explanation_per_vendor
    / explanation_finalise below. Kept so accidental references fail loudly."""
    raise NotImplementedError(
        "explanation_node has been split into explanation_start + explanation_per_vendor "
        "+ explanation_finalise. Use the Phase 4 fan-out pattern in graph.py."
    )


# ── Node 8 — Explanation (Phase 4: fan-out across vendors + final stitching) ──

async def explanation_start(state: PipelineState) -> dict:
    agent = "explanation"
    _emit(state, agent, "running",
          "Generating grounded report",
          log_msg="Writing the evaluation report — every recommendation is "
                  "backed by a direct quote from the vendor proposals.")
    return {}


async def explanation_per_vendor(state: PipelineState) -> dict:
    """One-vendor narrative generation. Calls _generate_vendor_narrative
    directly so we can parallelise across vendors. The final ExplanationOutput
    is stitched together by explanation_finalise after all branches converge.
    """
    from app.agents.explanation import _generate_vendor_narrative
    from app.schemas.schema_extraction import ExtractionOutput

    agent = "explanation"
    vid = state["vendor_id"]
    evaluation_output_objects = state.get("evaluation_output_objects") or {}
    extraction_output_objects = state.get("extraction_output_objects") or {}
    source_chunks = state.get("source_chunks") or {}
    decision_output = state["decision_output"]

    if vid not in evaluation_output_objects:
        return {
            "failed_vendors": [{
                "vendor_id": vid, "stage": "explanation",
                "error": "no evaluation output available (vendor failed upstream)",
                "ts": datetime.now(timezone.utc).isoformat(),
            }],
        }

    evaluation = evaluation_output_objects[vid]
    extraction = extraction_output_objects.get(vid) or ExtractionOutput(
        extraction_id="empty", vendor_id=vid, org_id=state["org_id"],
        source_chunk_ids=[], extraction_completeness=0.0, hallucination_risk=0.0,
    )
    # Filter chunks to this vendor's own chunks — prevents cross-vendor
    # contamination in the grounding check.
    vendor_chunks = {
        cid: source_chunks[cid]
        for cid in getattr(extraction, "source_chunk_ids", []) or []
        if cid in source_chunks
    } or source_chunks  # fallback when extraction has no chunk IDs

    is_rejected = any(r.vendor_id == vid for r in decision_output.rejected_vendors)

    # Phase 2 — pass through any critic feedback from a prior attempt so the
    # LLM corrects course. Empty string on the first attempt (no-op).
    critic_feedback = state.get("explanation_critic_feedback") or ""
    # Phase 2 (fix) — tag accumulator key with current attempt number so
    # stale narratives from a previous attempt don't leak into a retry.
    # explanation_finalise filters to the LATEST attempt per vendor.
    attempt = (state.get("explanation_retry_count") or 0) + 1
    accum_key = f"{vid}@attempt{attempt}"

    try:
        async with vendor_slot():
            narrative = await _generate_vendor_narrative(
                vendor_id=vid,
                vendor_name=vid,
                is_rejected=is_rejected,
                evaluation=evaluation,
                extraction=extraction,
                source_chunks=vendor_chunks,
                decision_output=decision_output,
                currency=state["currency"],
                critic_feedback=critic_feedback,
            )
            return {"vendor_narratives_accum": {accum_key: narrative}}
    except Exception as exc:
        rfp_logger.dev(DevLevel.ERROR, agent,
                       f"Vendor {vid} explanation failed: {exc}",
                       data={"vendor_id": vid, "error": str(exc),
                             "traceback": traceback.format_exc()},
                       run_id=state["run_id"], org_id=state["org_id"])
        return {
            "failed_vendors": [{
                "vendor_id": vid, "stage": "explanation",
                "error": str(exc),
                "ts": datetime.now(timezone.utc).isoformat(),
            }],
        }


async def explanation_finalise(state: PipelineState) -> dict:
    """Aggregates per-vendor narratives into the final ExplanationOutput.

    Phase 2: this node NO LONGER runs the critic — that decision moved to
    the new `explanation_critic` node which can route to retry-with-feedback
    instead of just blocking. finalise's job is now purely "build the
    aggregate output." It never raises a hard block; the critic does.
    Exception handling preserves the in-progress output for diagnostics
    if aggregation itself crashes (very rare — pure aggregation code)."""
    from app.agents.explanation import _build_executive_summary
    from app.schemas.schema_decision import ExplanationOutput

    agent = "explanation"
    vendor_narratives_accum = state.get("vendor_narratives_accum") or {}
    decision_output = state["decision_output"]

    # Phase 2 (fix #1) — accumulator keys are "{vid}@attempt{N}". Pick the
    # HIGHEST attempt per vendor. This drops stale narratives from previous
    # attempts. If a vendor had a SUCCESSFUL attempt 1 but a CRASHED attempt 2
    # (no new key written), the attempt-1 narrative is preserved (best-effort).
    # If a vendor succeeded on attempt 2, the attempt-1 narrative is dropped.
    latest_per_vendor: dict[str, tuple[int, object]] = {}  # vid -> (attempt, narrative)
    for accum_key, narrative in vendor_narratives_accum.items():
        # Defensive: accept untagged legacy keys (treat as attempt 0).
        if "@attempt" in accum_key:
            vid, attempt_marker = accum_key.split("@attempt", 1)
            try:
                attempt = int(attempt_marker)
            except ValueError:
                attempt = 0
        else:
            vid, attempt = accum_key, 0
        prior_attempt, _ = latest_per_vendor.get(vid, (-1, None))
        if attempt > prior_attempt:
            latest_per_vendor[vid] = (attempt, narrative)

    exp_out = None
    try:
        # Sort by vendor_id for deterministic output across runs.
        vendor_narratives = [latest_per_vendor[v][1]
                             for v in sorted(latest_per_vendor.keys())]

        total_claims = sum(
            len(n.grounded_claims) + n.ungrounded_claims_removed
            for n in vendor_narratives
        )
        grounded_claims = sum(len(n.grounded_claims) for n in vendor_narratives)
        grounding_completeness = (
            grounded_claims / total_claims if total_claims > 0 else 0.0
        )

        methodology_note = (
            "This report was generated by an automated evaluation pipeline. "
            "Every factual claim is grounded to a verbatim quote from the vendor submission. "
            "Claims that could not be verified against source text were removed. "
            "Human review is recommended before final procurement decisions."
        )

        limitations: list[str] = []
        if total_claims == 0:
            limitations.append(
                "No grounded claims were produced for any vendor — "
                "narratives may be empty. Check source chunks and re-run."
            )
        for n in vendor_narratives:
            if n.ungrounded_claims_removed > 0:
                limitations.append(
                    f"{n.vendor_id}: {n.ungrounded_claims_removed} unverified claim(s) removed."
                )
            if len(n.grounded_claims) == 0:
                limitations.append(
                    f"{n.vendor_id}: zero grounded claims — narrative has no verifiable content."
                )
        for fv in state.get("failed_vendors") or []:
            if fv.get("stage") == "explanation":
                limitations.append(
                    f"{fv.get('vendor_id')}: narrative generation failed ({fv.get('error', 'unknown error')[:80]})."
                )

        exp_out = ExplanationOutput(
            explanation_id=str(uuid.uuid4()),
            executive_summary=_build_executive_summary(decision_output, vendor_narratives),
            vendor_narratives=vendor_narratives,
            methodology_note=methodology_note,
            limitations=limitations,
            grounding_completeness=round(grounding_completeness, 3),
            report_confidence=decision_output.decision_confidence,
        )

        # No "done" emit here — the critic node decides when the stage is truly
        # done (might be retried). The critic emits the final "done" event.
        return {"explanation_output": exp_out}

    except Exception as exc:
        # Pure aggregation crashed (e.g. bad shape in narratives_accum) —
        # genuinely fatal; route to END with whatever output we have.
        update = _block_update(state, agent, exc)
        if exp_out is not None:
            update["explanation_output"] = exp_out
        return update


# ── Phase 2 — Explanation critic node (retry-with-feedback controller) ────────

_EXPLANATION_MAX_RETRIES = 2  # 2 retries = 3 total attempts


def _build_critic_feedback(exp_out, exp_critic) -> str:
    """Construct structured retry guidance from the previous attempt's
    diagnostic fields. The Explanation LLM sees this on the next attempt
    as a 'PREVIOUS ATTEMPT FAILED' preamble. The more specific the feedback,
    the better the retry succeeds — generic 'do better' wastes a budget slot."""
    parts: list[str] = []

    # Headline metric
    gc = getattr(exp_out, "grounding_completeness", 0.0) if exp_out else 0.0
    parts.append(
        f"PREVIOUS ATTEMPT FAILED: grounding_completeness={gc:.0%} "
        "(threshold is 70%). Fix per the guidance below — do NOT repeat the same mistakes."
    )

    # Diagnostic samples from ungrounded_examples (Phase 1's instrumentation)
    if exp_out:
        samples = []
        for narrative in (exp_out.vendor_narratives or [])[:3]:
            for ex in (getattr(narrative, "ungrounded_examples", []) or [])[:2]:
                hint = ex.get("diagnosis_hint", "unknown")
                claim = ex.get("claim_text", "")[:100]
                quote = ex.get("llm_grounding_quote", "")[:120]
                samples.append(f"  - vendor={narrative.vendor_id} ({hint}): "
                               f"claim={claim!r}, quote you cited={quote!r}")
        if samples:
            parts.append("Examples of claims that were rejected:")
            parts.extend(samples)

    # General rule reminder — most failures are metadata-as-grounded-claim
    parts.append(
        "RULES:\n"
        "  • PDF-content claims (vendor proposal text)  → grounded_claims, with verbatim quote.\n"
        "  • System metadata (decision rank, scores, MC-* check IDs)  → system_facts, NO quote, NO chunk_id.\n"
        "  • The grounding_quote MUST be a copy-paste verbatim substring of one source chunk.\n"
    )
    return "\n".join(parts)


async def explanation_critic(state: PipelineState) -> dict:
    """Phase 2 — Critic-as-controller for the Explanation stage.

    Reads state['explanation_output'], runs the critic, and decides routing.
    Three outcomes (read by _route_after_explanation_critic):
      APPROVED   → emits 'done' and routes to END
      RETRY      → bumps retry_count, writes feedback into state, signals
                   loop-back to explanation_start
      EXHAUSTED  → 3rd consecutive block; emits 'blocked' and routes to END

    The critic itself is unchanged (`critic_after_explanation`). What's new
    is the routing logic that converts BLOCKED into a retry instead of a
    pipeline-fatal exception."""
    agent = "explanation"
    exp_out = state.get("explanation_output")
    source_chunks = state.get("source_chunks") or {}
    retry_count = state.get("explanation_retry_count") or 0

    if exp_out is None:
        # finalise didn't produce an output (genuine aggregation failure).
        # Treat as exhausted — nothing useful to retry from.
        _emit(state, agent, "blocked",
              "No explanation output to evaluate",
              log_msg="The report aggregation failed; cannot retry.")
        return {"blocked": True, "blocked_agent": agent,
                "error_message": "explanation_finalise produced no output"}

    exp_critic = critic_after_explanation(exp_out, source_chunks)

    if exp_critic.overall_verdict != CriticVerdict.BLOCKED:
        # APPROVED or APPROVED_WITH_WARNINGS — done.
        _emit(state, agent, "done",
              f"Report ready — every claim cited (attempt {retry_count + 1})",
              log_msg=("Evaluation complete. Report ready with citations for every finding."
                       if retry_count == 0
                       else f"Report ready on retry attempt {retry_count + 1}."))
        return {"explanation_retry_requested": False}

    # BLOCKED — decide retry vs exhausted.
    hard_descs = "; ".join(f.description for f in exp_critic.flags
                           if f.severity.value == "hard")[:240]

    if retry_count >= _EXPLANATION_MAX_RETRIES:
        # Exhausted budget. Emit blocked event, preserve explanation_output
        # (already in state from finalise) for the user to see why.
        _emit(state, agent, "blocked",
              f"[CRITIC BLOCK after {retry_count + 1} attempts] {hard_descs}",
              log_msg=f"Report could not pass the quality gate after "
                      f"{retry_count + 1} attempts. See explanation diagnostics for why.")
        rfp_logger.dev(DevLevel.ERROR, agent,
                       f"Critic exhausted after {retry_count + 1} attempts: {hard_descs}",
                       data={"retry_count": retry_count,
                             "flags": [f.check_name for f in exp_critic.flags]},
                       run_id=state["run_id"], org_id=state["org_id"])
        return {
            "blocked": True,
            "blocked_agent": agent,
            "error_message": f"[CRITIC BLOCK after {retry_count + 1} attempts] {hard_descs}",
            "explanation_retry_requested": False,
        }

    # Retry: build feedback, bump counter, signal loop-back.
    feedback = _build_critic_feedback(exp_out, exp_critic)
    next_attempt = retry_count + 1
    _emit(state, agent, "retrying",
          f"Critic blocked (attempt {retry_count + 1}); retrying with feedback",
          log_msg=f"The report quality check failed (attempt {retry_count + 1}). "
                  f"Retrying with structured feedback. {hard_descs[:120]}")
    rfp_logger.dev(DevLevel.INFO, agent,
                   f"Critic block → retry {next_attempt} of {_EXPLANATION_MAX_RETRIES}: {hard_descs[:200]}",
                   data={"attempt": retry_count + 1,
                         "next_attempt": next_attempt + 1,
                         "feedback_chars": len(feedback)},
                   run_id=state["run_id"], org_id=state["org_id"])
    return {
        "explanation_retry_count": next_attempt,
        "explanation_critic_feedback": feedback,
        # Clear the previous explanation_output so finalise re-aggregates fresh.
        # The retried explanation_per_vendor branches write with a NEW key
        # ("{vid}@attempt{N+1}"); finalise picks the highest attempt per vendor.
        # Old attempt-N keys are not overwritten in the accumulator but are
        # ignored during aggregation. This is the fix for /code-review finding #1.
        "explanation_output": None,
        # Explicit routing signal — read by _route_after_explanation_critic
        "explanation_retry_requested": True,
    }
