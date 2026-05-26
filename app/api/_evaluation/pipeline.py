"""9-agent pipeline — orchestrates all agents for a single evaluation run."""
import traceback
import uuid
from datetime import datetime, timezone

import sqlalchemy as sa

from app.infra.audit import audit
from app.infra.logger import rfp_logger, DevLevel
from app.schemas.output_models import EvaluationSetup, RetrievalOutput, CriticVerdict
from app.domain.org_settings import get_org_settings
from app.agents.critic import (
    critic_after_ingestion,
    critic_after_retrieval,
    critic_after_evaluation,
    critic_after_comparator,
    critic_after_decision,
    critic_after_explanation,
)
from app.db.fact_store import get_engine
from app.agents.planner import run_planner
from app.agents.ingestion import run_ingestion_agent
from app.agents.retrieval import run_retrieval_agent
from app.agents.extraction import run_extraction_agent
from app.agents.evaluation import run_evaluation_agent
from app.agents.comparator import run_comparator_agent
from app.agents.decision import run_decision_agent
from app.agents.explanation import run_explanation_agent

from .db import (
    _db_get_setup,
    _db_load_vendor_files,
    _db_update_status,
    _db_append_event,
    _db_append_log,
    _db_save_decision,
)


async def _run_pipeline(run_id: str, org_id: str) -> None:
    """9-agent pipeline. All state read from and written to PostgreSQL."""

    def _emit(agent: str, status: str, message: str = "", log_msg: str = "") -> None:
        event = {"agent": agent, "status": status, "message": message, "log_msg": log_msg or message}
        try:
            _db_append_event(run_id, event)
            rfp_logger.dev(DevLevel.AGENT, agent, f"{status}: {message}",
                           data={"status": status}, run_id=run_id, org_id=org_id)
        except Exception as _e:
            rfp_logger.dev(DevLevel.ERROR, agent, f"_emit DB write failed: {_e}",
                           run_id=run_id, org_id=org_id)
        if log_msg:
            entry = {"ts": datetime.now(timezone.utc).isoformat(),
                     "agent": agent, "status": status, "message": log_msg}
            try:
                _db_append_log(run_id, entry)
            except Exception:
                pass
        event_type = "agent.started" if status == "running" else \
                     "agent.completed" if status == "done" else \
                     "agent.blocked" if status == "blocked" else None
        if event_type:
            audit(org_id=org_id, run_id=run_id, event_type=event_type,
                  actor="system", agent=agent, detail={"message": message})

    def _block_if_hard(critic, context: str) -> None:
        """Raise RuntimeError if critic returned a HARD block so the outer except catches it."""
        if critic.overall_verdict == CriticVerdict.BLOCKED:
            hard_descs = [f.description for f in critic.flags if f.severity.value == "hard"]
            raise RuntimeError(f"[CRITIC BLOCK] {context}: {'; '.join(hard_descs)}")

    def _fail(agent: str, err: Exception) -> None:
        rfp_logger.dev(DevLevel.ERROR, agent, f"Pipeline blocked: {err}",
                       data={"traceback": traceback.format_exc()},
                       run_id=run_id, org_id=org_id)
        rfp_logger.end_run(run_id=run_id, org_id=org_id, status="blocked")
        _emit(agent, "blocked", str(err),
              log_msg=f"Something went wrong in the {agent} step. The evaluation could not continue.")
        try:
            _db_update_status(run_id, "blocked", completed=True)
        except Exception:
            pass
        audit(org_id=org_id, run_id=run_id, event_type="run.blocked",
              actor="system", detail={"agent": agent, "error": str(err)})

    rfp_logger.start_run(run_id=run_id, org_id=org_id, rfp_id="", vendor_count=0)

    from app.infra.cost_tracker import set_run_context, get_run_cost as _get_cost, clear_run_cost
    _cost_ctx = set_run_context(run_id=run_id, agent="pipeline")
    _cost_ctx.__enter__()
    try:
        engine = get_engine()
        with engine.connect() as conn:
            row = conn.execute(
                sa.text("""
                    SELECT rfp_id, rfp_title, department, rfp_filename,
                           rfp_bytes, vendor_ids, contract_value, setup_id,
                           currency
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
        currency       = row[8] if len(row) > 8 and row[8] else "GBP"

        setup_json = _db_get_setup(setup_id)
        if not setup_json:
            raise RuntimeError("EvaluationSetup not found")
        evaluation_setup = EvaluationSetup(**setup_json)

        vendor_file_map = _db_load_vendor_files(run_id)
        n_vendors = len(vendor_ids)
        org_settings = get_org_settings(org_id)

        rfp_logger.dev(DevLevel.AGENT, "Pipeline",
                       f"Starting pipeline: {n_vendors} vendor(s), RFP '{rfp_title}'",
                       data={"rfp_id": rfp_id, "vendors": n_vendors,
                             "criteria": len(evaluation_setup.scoring_criteria),
                             "mandatory_checks": len(evaluation_setup.mandatory_checks)},
                       run_id=run_id, org_id=org_id)

        # ── 1. Planner ─────────────────────────────────────────────────────────
        _emit("planner", "running", "Decomposing evaluation into task DAG",
              log_msg=f"Reading the RFP and planning how to evaluate {n_vendors} vendor{'s' if n_vendors != 1 else ''}.")
        await run_planner(rfp_id=rfp_id, org_id=org_id, vendor_ids=vendor_ids,
                          evaluation_setup=evaluation_setup)
        _emit("planner", "done", "Task DAG ready",
              log_msg=f"Evaluation plan created — {len(evaluation_setup.mandatory_checks)} compliance checks and {len(evaluation_setup.scoring_criteria)} scoring criteria defined.")

        # ── 2. Ingestion ───────────────────────────────────────────────────────
        _emit("ingestion", "running", f"Ingesting RFP + {len(vendor_file_map)} vendor docs",
              log_msg=f"Reading and indexing the RFP document plus {len(vendor_file_map)} vendor proposal{'s' if len(vendor_file_map) != 1 else ''}.")
        _, rfp_ing_critics = await run_ingestion_agent(
            content=rfp_bytes, filename=rfp_filename,
            vendor_id="rfp", org_id=org_id, rfp_id=rfp_id,
            evaluation_setup=evaluation_setup)
        for c in rfp_ing_critics:
            _block_if_hard(c, f"ingestion/{rfp_filename}")

        for vid, (vbytes, vfilename) in vendor_file_map.items():
            _, ving_critics = await run_ingestion_agent(
                content=vbytes, filename=vfilename,
                vendor_id=vid, org_id=org_id, rfp_id=rfp_id,
                evaluation_setup=evaluation_setup)
            for c in ving_critics:
                if c.overall_verdict.value in ("approved_with_warnings", "blocked"):
                    rfp_logger.dev(DevLevel.INFO, "ingestion",
                                   f"Vendor {vid} critic: {c.overall_verdict.value} "
                                   f"— {len(c.flags)} flag(s)",
                                   data={"vendor_id": vid,
                                         "verdict": c.overall_verdict.value,
                                         "flags": [f.check_name for f in c.flags]},
                                   run_id=run_id, org_id=org_id)
                _block_if_hard(c, f"ingestion/{vfilename} (vendor={vid})")
        _emit("ingestion", "done", f"RFP + {len(vendor_file_map)} vendor docs indexed",
              log_msg=f"All documents processed and indexed — {len(vendor_file_map)} vendor proposal{'s' if len(vendor_file_map) != 1 else ''} ready for analysis.")

        # ── 3. Retrieval ───────────────────────────────────────────────────────
        _emit("retrieval", "running", f"Retrieving chunks for {n_vendors} vendors",
              log_msg="Searching each vendor proposal for relevant sections on pricing, compliance, SLAs, and technical capability.")
        retrieval_outputs: dict = {}
        for vid in vendor_ids:
            queries: list[str] = []
            for criterion in evaluation_setup.scoring_criteria:
                queries.append(criterion.name)
            for check in evaluation_setup.mandatory_checks:
                queries.append(check.name)
            if not queries:
                queries = ["technical capability SLA pricing compliance certifications experience"]

            seen_chunk_ids: set[str] = set()
            merged_chunks: list = []

            mandatory_names = {c.name for c in evaluation_setup.mandatory_checks}
            for query in queries:
                ret_out, ret_critic = await run_retrieval_agent(
                    query=query, vendor_id=vid, org_id=org_id, rfp_id=rfp_id,
                    is_mandatory_check=(query in mandatory_names),
                    org_settings=org_settings,
                )
                if ret_critic.overall_verdict.value != "approved":
                    rfp_logger.dev(DevLevel.INFO, "retrieval",
                                   f"Vendor {vid} query '{query[:60]}' critic: "
                                   f"{ret_critic.overall_verdict.value}",
                                   data={"vendor_id": vid,
                                         "verdict": ret_critic.overall_verdict.value,
                                         "flags": [f.check_name for f in ret_critic.flags]},
                                   run_id=run_id, org_id=org_id)
                for chunk in ret_out.chunks:
                    if chunk.chunk_id not in seen_chunk_ids:
                        seen_chunk_ids.add(chunk.chunk_id)
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
                empty_retrieval=len(merged_chunks) == 0,
                warnings=[],
            )
            combined_critic = critic_after_retrieval(combined, is_mandatory=False)
            _block_if_hard(combined_critic, f"retrieval/combined vendor={vid}")
            retrieval_outputs[vid] = combined
            rfp_logger.dev(DevLevel.RAG, "retrieval",
                           f"Vendor {vid}: {len(merged_chunks)} unique chunks from {len(queries)} queries",
                           data={"vendor_id": vid, "queries": len(queries),
                                 "unique_chunks": len(merged_chunks),
                                 "confidence": combined.confidence},
                           run_id=run_id, org_id=org_id)
        _emit("retrieval", "done", f"Retrieved chunks for {n_vendors} vendors",
              log_msg=f"Found the most relevant passages from all {n_vendors} vendor proposals.")

        # ── 4. Extraction ──────────────────────────────────────────────────────
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
            rfp_logger.dev(DevLevel.INFO, "extraction",
                           f"Vendor {vid}: {len(ext_out.slas)} SLAs, {len(ext_out.pricing)} pricing, {len(ext_out.extracted_facts)} facts",
                           data={"vendor_id": vid,
                                 "slas": len(ext_out.slas),
                                 "pricing": len(ext_out.pricing),
                                 "facts": len(ext_out.extracted_facts),
                                 "completeness": round(ext_out.extraction_completeness, 2),
                                 "hallucination_risk": round(ext_out.hallucination_risk, 2),
                                 "critic": critic_ext.overall_verdict},
                           run_id=run_id, org_id=org_id)
        total_facts = sum(
            len(getattr(o, "certifications", []) or []) +
            len(getattr(o, "slas", []) or []) +
            len(getattr(o, "pricing", []) or [])
            for o in extraction_outputs.values()
        )
        _emit("extraction", "done", "Facts extracted and stored",
              log_msg=f"Extracted and saved {total_facts} verifiable facts across all vendor proposals.")

        # ── 5. Evaluation ──────────────────────────────────────────────────────
        _emit("evaluation", "running", "Scoring vendors against criteria",
              log_msg=f"Scoring each vendor against your {len(evaluation_setup.scoring_criteria)} criteria with their configured weights.")
        evaluation_outputs: dict = {}
        for vid in vendor_ids:
            ev_out, ev_critic = await run_evaluation_agent(
                vendor_id=vid, org_id=org_id, run_id=run_id,
                evaluation_setup=evaluation_setup,
                extraction_output=extraction_outputs.get(vid))
            evaluation_outputs[vid] = ev_out
            if ev_critic.overall_verdict.value != "approved":
                rfp_logger.dev(DevLevel.INFO, "evaluation",
                               f"Vendor {vid} critic: {ev_critic.overall_verdict.value} "
                               f"— {len(ev_critic.flags)} flag(s)",
                               data={"vendor_id": vid,
                                     "verdict": ev_critic.overall_verdict.value,
                                     "flags": [f.check_name for f in ev_critic.flags]},
                               run_id=run_id, org_id=org_id)
            _block_if_hard(ev_critic, f"evaluation/vendor={vid}")
        _emit("evaluation", "done", "All vendors scored",
              log_msg=f"All {n_vendors} vendors scored. Scores ready for comparison.")

        # ── 6. Comparator ──────────────────────────────────────────────────────
        _emit("comparator", "running", "Cross-vendor ranking and stability check",
              log_msg="Ranking vendors against each other and checking whether the ranking is stable across scoring variations.")
        comp_out, comp_critic = await run_comparator_agent(
            vendor_ids=vendor_ids, org_id=org_id, rfp_id=rfp_id,
            evaluation_setup=evaluation_setup, evaluation_outputs=evaluation_outputs)
        _block_if_hard(comp_critic, "comparator")
        if comp_critic.overall_verdict.value != "approved":
            rfp_logger.dev(DevLevel.INFO, "comparator",
                           f"Comparator critic: {comp_critic.overall_verdict.value} "
                           f"— {len(comp_critic.flags)} flag(s)",
                           data={"verdict": comp_critic.overall_verdict.value,
                                 "flags": [f.check_name for f in comp_critic.flags]},
                           run_id=run_id, org_id=org_id)
        _emit("comparator", "done", "Vendors ranked",
              log_msg="Final vendor ranking confirmed.")

        # ── 7. Decision ────────────────────────────────────────────────────────
        _emit("decision", "running", "Governance routing and approval tier selection",
              log_msg="Applying your organisation's governance rules to determine the approval tier and required approvers.")
        dec_out, dec_critic = await run_decision_agent(
            evaluation_outputs=evaluation_outputs,
            comparator_output=comp_out,
            contract_value=contract_value)
        _block_if_hard(dec_critic, "decision")
        if dec_critic.overall_verdict.value != "approved":
            rfp_logger.dev(DevLevel.INFO, "decision",
                           f"Decision critic: {dec_critic.overall_verdict.value} "
                           f"— {len(dec_critic.flags)} flag(s)",
                           data={"verdict": dec_critic.overall_verdict.value,
                                 "flags": [f.check_name for f in dec_critic.flags]},
                           run_id=run_id, org_id=org_id)
        n_short = len(getattr(dec_out, "shortlisted_vendors", []) or [])
        n_rej   = len(getattr(dec_out, "rejected_vendors",    []) or [])
        _emit("decision", "done", "Decision and approval tier set",
              log_msg=f"{n_short} vendor{'s' if n_short != 1 else ''} shortlisted, {n_rej} rejected. Approval routing determined.")

        # ── 8. Explanation ─────────────────────────────────────────────────────
        _emit("explanation", "running", "Generating grounded report",
              log_msg="Writing the evaluation report — every recommendation is backed by a direct quote from the vendor proposals.")
        exp_out, exp_critic = await run_explanation_agent(
            decision_output=dec_out,
            evaluation_outputs=evaluation_outputs,
            extraction_outputs=extraction_outputs,
            source_chunks=source_chunks,
            currency=currency)
        _block_if_hard(exp_critic, "explanation")
        _emit("explanation", "done", "Report ready — every claim cited",
              log_msg="Evaluation complete. Full report ready with citations for every finding.")

        # ── 9. Critic — final summary across all agents ────────────────────────
        # Individual critics ran inline after each agent above and blocked on hard flags.
        # Here we collect soft warnings and emit a final summary for the audit log.
        all_critics = [comp_critic, dec_critic, exp_critic]
        all_critics += [ev_critic for ev_critic in
                        [evaluation_outputs.get(vid) for vid in vendor_ids]
                        if ev_critic is not None and hasattr(ev_critic, "flags")]
        total_soft = sum(c.soft_flag_count for c in all_critics if hasattr(c, "soft_flag_count"))
        critic_summary_msg = (
            f"All agents passed — {total_soft} soft warning(s) noted in logs"
            if total_soft == 0 or total_soft > 0
            else "All agent outputs validated"
        )
        _emit("critic", "done", critic_summary_msg,
              log_msg=f"Independent quality check complete — {total_soft} soft flag(s) logged. "
                      f"No hard blocks reached this step.")

        _db_save_decision(run_id, dec_out.model_dump(mode="json"))
        rfp_logger.end_run(run_id=run_id, org_id=org_id, status="complete",
                           recommended_vendor=(getattr(dec_out, "shortlisted_vendors", None) or [None])[0])
        rfp_logger.dev(DevLevel.SUCCESS, "Pipeline",
                       f"Evaluation complete — {n_short} shortlisted, {n_rej} rejected",
                       data={"shortlisted": n_short, "rejected": n_rej},
                       run_id=run_id, org_id=org_id)
        audit(org_id=org_id, run_id=run_id, event_type="run.completed",
              actor="system",
              detail={"shortlisted": n_short, "rejected": n_rej,
                      "approval_tier": getattr(getattr(dec_out, "approval_routing", None), "approval_tier", None)})

    except Exception as exc:
        _fail("pipeline", exc)
        print(f"[pipeline error] run={run_id}: {traceback.format_exc()}")
    finally:
        _cost_ctx.__exit__(None, None, None)
        acc = _get_cost(run_id)
        if acc is not None:
            try:
                _eng = get_engine()
                with _eng.begin() as _conn:
                    _conn.execute(
                        sa.text("""
                            UPDATE evaluation_runs
                            SET llm_cost_usd = :cost, llm_tokens_total = :tokens
                            WHERE run_id = CAST(:rid AS uuid)
                        """),
                        {"cost": acc.total_cost_usd, "tokens": acc.total_tokens, "rid": run_id},
                    )
            except Exception:
                pass
            clear_run_cost(run_id)
