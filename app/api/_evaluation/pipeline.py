"""
9-agent pipeline — orchestrates all agents via LangGraph StateGraph.

Replaces the old sequential-await approach with evaluation_graph.astream(),
which yields a state diff after each node completes. This gives us:
  • Live streaming progress (each node diff → DB event → SSE to frontend)
  • LangSmith DAG visualisation of every run
  • Clean HARD-critic routing to END without a try/except waterfall
  • State snapshot at each node for future replay / checkpointing
"""
import traceback

import sqlalchemy as sa

from app.infra.audit import audit
from app.infra.logger import rfp_logger, DevLevel
from app.infra.cost_tracker import set_run_context, get_run_cost, clear_run_cost
from app.schemas.output_models import EvaluationSetup
from app.domain.org_settings import get_org_settings
from app.db.fact_store import get_engine
from app.pipeline.graph import evaluation_graph
from app.pipeline.state import PipelineState

from .db import (
    _db_get_setup,
    _db_load_vendor_files,
    _db_update_status,
    _db_append_event,
    _db_save_decision,
)


async def _run_pipeline(run_id: str, org_id: str) -> None:
    """
    Entry point called by the FastAPI background task.
    Loads run data from PostgreSQL, builds the initial LangGraph state,
    streams the graph, then persists the final decision.
    """
    rfp_logger.start_run(run_id=run_id, org_id=org_id, rfp_id="", vendor_count=0)
    cost_ctx = set_run_context(run_id=run_id, agent="pipeline")
    cost_ctx.__enter__()

    try:
        # ── 1. Load run data from PostgreSQL ──────────────────────────────────
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
        org_settings     = get_org_settings(org_id)
        vendor_file_map  = _db_load_vendor_files(run_id)
        n_vendors        = len(vendor_ids)

        rfp_logger.dev(DevLevel.AGENT, "Pipeline",
                       f"Starting graph: {n_vendors} vendor(s), RFP '{rfp_title}'",
                       data={"rfp_id": rfp_id, "vendors": n_vendors,
                             "criteria": len(evaluation_setup.scoring_criteria),
                             "mandatory_checks": len(evaluation_setup.mandatory_checks)},
                       run_id=run_id, org_id=org_id)

        # ── 2. Build initial state ────────────────────────────────────────────
        initial_state: PipelineState = {
            # Fixed inputs
            "run_id":                run_id,
            "org_id":                org_id,
            "rfp_id":                rfp_id,
            "rfp_title":             rfp_title,
            "rfp_filename":          rfp_filename,
            "rfp_bytes":             rfp_bytes,
            "vendor_ids":            vendor_ids,
            "contract_value":        contract_value,
            "currency":              currency,
            "setup_id":              setup_id,
            "n_vendors":             n_vendors,
            "evaluation_setup_dict": evaluation_setup.model_dump(mode="json"),
            "vendor_file_map":       vendor_file_map,
            "org_settings":          org_settings,
            # Outputs (empty — each node fills its section)
            "retrieval_output_objects":  {},
            "extraction_output_objects": {},
            "evaluation_output_objects": {},
            "comparator_output":         None,
            "decision_output":           None,
            "explanation_output":        None,
            "source_chunks":             {},
            # Control flow
            "blocked":       False,
            "blocked_agent": "",
            "error_message": "",
        }

        # ── 3. Stream the graph ───────────────────────────────────────────────
        # astream() yields {node_name: state_diff} after each node completes.
        # We iterate to drive execution; nodes write progress to the DB themselves.
        final_state: PipelineState = initial_state
        async for state_diff in evaluation_graph.astream(initial_state):
            # state_diff is {node_name: updated_fields_dict}
            node_name = next(iter(state_diff))
            updated   = state_diff[node_name]
            # Merge diff into our local view of final_state for post-run access
            final_state = {**final_state, **updated}
            rfp_logger.dev(DevLevel.AGENT, "Graph",
                           f"Node '{node_name}' completed",
                           data={"node": node_name,
                                 "blocked": final_state.get("blocked", False)},
                           run_id=run_id, org_id=org_id)

        # ── 4. Handle final state ─────────────────────────────────────────────
        if final_state.get("blocked"):
            # Nodes already called _db_update_status("blocked") and audit().
            # Nothing more to do — run is marked blocked in DB.
            rfp_logger.dev(DevLevel.ERROR, "Pipeline",
                           f"Graph ended blocked at '{final_state.get('blocked_agent')}': "
                           f"{final_state.get('error_message')}",
                           run_id=run_id, org_id=org_id)
            return

        # Success path — persist decision and close the run
        dec_out = final_state.get("decision_output")
        if dec_out:
            _db_save_decision(run_id, dec_out.model_dump(mode="json"))

        n_short = len(getattr(dec_out, "shortlisted_vendors", []) or [])
        n_rej   = len(getattr(dec_out, "rejected_vendors",    []) or [])

        # Emit final critic summary (soft warnings accumulated across all nodes)
        _db_append_event(run_id, {
            "agent": "critic",
            "status": "done",
            "message": "All agent outputs validated by Critic",
            "log_msg": "Independent quality check complete.",
        })

        _db_update_status(run_id, "complete", completed=True)
        rfp_logger.end_run(run_id=run_id, org_id=org_id, status="complete",
                           recommended_vendor=(
                               getattr(dec_out, "shortlisted_vendors", None) or [None]
                           )[0])
        rfp_logger.dev(DevLevel.SUCCESS, "Pipeline",
                       f"Graph complete — {n_short} shortlisted, {n_rej} rejected",
                       data={"shortlisted": n_short, "rejected": n_rej},
                       run_id=run_id, org_id=org_id)
        audit(org_id=org_id, run_id=run_id, event_type="run.completed",
              actor="system",
              detail={
                  "shortlisted": n_short, "rejected": n_rej,
                  "approval_tier": getattr(
                      getattr(dec_out, "approval_routing", None),
                      "approval_tier", None),
              })

    except Exception as exc:
        rfp_logger.dev(DevLevel.ERROR, "Pipeline",
                       f"Unhandled error outside graph: {exc}",
                       data={"traceback": traceback.format_exc()},
                       run_id=run_id, org_id=org_id)
        rfp_logger.end_run(run_id=run_id, org_id=org_id, status="blocked")
        try:
            _db_update_status(run_id, "blocked", completed=True)
        except Exception:
            pass
        audit(org_id=org_id, run_id=run_id, event_type="run.blocked",
              actor="system", detail={"agent": "pipeline", "error": str(exc)})

    finally:
        cost_ctx.__exit__(None, None, None)
        acc = get_run_cost(run_id)
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
                        {"cost": acc.total_cost_usd,
                         "tokens": acc.total_tokens,
                         "rid": run_id},
                    )
            except Exception:
                pass
            clear_run_cost(run_id)
