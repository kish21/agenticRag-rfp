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


# ── Node 3 — Retrieval ────────────────────────────────────────────────────────

async def retrieval_node(state: PipelineState) -> dict:
    agent = "retrieval"
    org_id = state["org_id"]
    rfp_id = state["rfp_id"]
    vendor_ids = state["vendor_ids"]
    n_vendors = state["n_vendors"]
    evaluation_setup = EvaluationSetup(**state["evaluation_setup_dict"])
    org_settings = state["org_settings"]
    try:
        _emit(state, agent, "running",
              f"Retrieving chunks for {n_vendors} vendors",
              log_msg="Searching each vendor proposal for relevant sections on "
                      "pricing, compliance, SLAs, and technical capability.")

        retrieval_output_objects: dict = {}
        source_chunks: dict = {}
        mandatory_names = {c.name for c in evaluation_setup.mandatory_checks}

        for vid in vendor_ids:
            queries = (
                [c.name for c in evaluation_setup.scoring_criteria] +
                [c.name for c in evaluation_setup.mandatory_checks]
            ) or ["technical capability SLA pricing compliance certifications experience"]

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
            combined_critic = critic_after_retrieval(combined, is_mandatory=False)
            _hard_block_if(combined_critic, f"retrieval/combined vendor={vid}")

            retrieval_output_objects[vid] = combined
            for chunk in merged_chunks:
                source_chunks[chunk.chunk_id] = chunk.text

            rfp_logger.dev(DevLevel.RAG, agent,
                           f"Vendor {vid}: {len(merged_chunks)} unique chunks "
                           f"from {len(queries)} queries",
                           data={"vendor_id": vid, "queries": len(queries),
                                 "unique_chunks": len(merged_chunks),
                                 "confidence": combined.confidence},
                           run_id=state["run_id"], org_id=org_id)

        _emit(state, agent, "done",
              f"Retrieved chunks for {n_vendors} vendors",
              log_msg=f"Found the most relevant passages from all {n_vendors} vendor proposals.")

        return {
            "retrieval_output_objects": retrieval_output_objects,
            "source_chunks": source_chunks,
        }
    except Exception as exc:
        return _block_update(state, agent, exc)


# ── Node 4 — Extraction ───────────────────────────────────────────────────────

async def extraction_node(state: PipelineState) -> dict:
    agent = "extraction"
    org_id = state["org_id"]
    rfp_id = state["rfp_id"]
    vendor_ids = state["vendor_ids"]
    evaluation_setup = EvaluationSetup(**state["evaluation_setup_dict"])
    retrieval_output_objects = state["retrieval_output_objects"]
    try:
        _emit(state, agent, "running",
              "Extracting structured facts",
              log_msg="Pulling out specific facts from each proposal — "
                      "certifications, insurance, SLA commitments, project history, and pricing.")

        extraction_output_objects: dict = {}

        for vid in vendor_ids:
            ret_out = retrieval_output_objects[vid]
            ext_out, critic_ext = await run_extraction_agent(
                retrieval_output=ret_out, vendor_id=vid, org_id=org_id,
                doc_id=f"{rfp_id}-{vid}", setup_id=state["setup_id"],
                evaluation_setup=evaluation_setup, run_id=state["run_id"])
            extraction_output_objects[vid] = ext_out
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

        total_facts = sum(
            len(getattr(o, "certifications", []) or []) +
            len(getattr(o, "slas", []) or []) +
            len(getattr(o, "pricing", []) or [])
            for o in extraction_output_objects.values()
        )
        _emit(state, agent, "done", "Facts extracted and stored",
              log_msg=f"Extracted and saved {total_facts} verifiable facts "
                      "across all vendor proposals.")

        return {"extraction_output_objects": extraction_output_objects}
    except Exception as exc:
        return _block_update(state, agent, exc)


# ── Node 5 — Evaluation ───────────────────────────────────────────────────────

async def evaluation_node(state: PipelineState) -> dict:
    agent = "evaluation"
    org_id = state["org_id"]
    vendor_ids = state["vendor_ids"]
    n_vendors = state["n_vendors"]
    evaluation_setup = EvaluationSetup(**state["evaluation_setup_dict"])
    extraction_output_objects = state["extraction_output_objects"]
    try:
        _emit(state, agent, "running",
              "Scoring vendors against criteria",
              log_msg=f"Scoring each vendor against your "
                      f"{len(evaluation_setup.scoring_criteria)} criteria "
                      "with their configured weights.")

        evaluation_output_objects: dict = {}

        for vid in vendor_ids:
            ev_out, ev_critic = await run_evaluation_agent(
                vendor_id=vid, org_id=org_id, run_id=state["run_id"],
                evaluation_setup=evaluation_setup,
                extraction_output=extraction_output_objects.get(vid))
            evaluation_output_objects[vid] = ev_out
            if ev_critic.overall_verdict.value != "approved":
                rfp_logger.dev(DevLevel.INFO, agent,
                               f"Vendor {vid} critic: {ev_critic.overall_verdict.value} "
                               f"— {len(ev_critic.flags)} flag(s)",
                               data={"vendor_id": vid,
                                     "verdict": ev_critic.overall_verdict.value,
                                     "flags": [f.check_name for f in ev_critic.flags]},
                               run_id=state["run_id"], org_id=org_id)
            _hard_block_if(ev_critic, f"evaluation/vendor={vid}")

        _emit(state, agent, "done", "All vendors scored",
              log_msg=f"All {n_vendors} vendors scored. Scores ready for comparison.")

        return {"evaluation_output_objects": evaluation_output_objects}
    except Exception as exc:
        return _block_update(state, agent, exc)


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
    agent = "explanation"
    evaluation_output_objects = state["evaluation_output_objects"]
    extraction_output_objects = state["extraction_output_objects"]
    dec_out = state["decision_output"]
    source_chunks = state["source_chunks"]
    exp_out = None  # captured before critic check so diagnostics survive a block
    try:
        _emit(state, agent, "running",
              "Generating grounded report",
              log_msg="Writing the evaluation report — every recommendation is "
                      "backed by a direct quote from the vendor proposals.")

        exp_out, exp_critic = await run_explanation_agent(
            decision_output=dec_out,
            evaluation_outputs=evaluation_output_objects,
            extraction_outputs=extraction_output_objects,
            source_chunks=source_chunks,
            currency=state["currency"])
        _hard_block_if(exp_critic, "explanation")

        _emit(state, agent, "done",
              "Report ready — every claim cited",
              log_msg="Evaluation complete. Full report ready with citations for every finding.")

        return {"explanation_output": exp_out}
    except Exception as exc:
        # Preserve the generated explanation (with grounding diagnostics) even
        # when the critic blocks — otherwise the ungrounded_examples are lost.
        update = _block_update(state, agent, exc)
        if exp_out is not None:
            update["explanation_output"] = exp_out
        return update
