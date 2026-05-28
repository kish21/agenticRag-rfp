"""
LangGraph StateGraph — wires the 9-agent pipeline with conditional edges.

Topology (Phase 4 — parallel vendor execution):

  planner → ingestion
                ↓
            retrieval_start ─→ [fan-out via Send] ─→ retrieval_per_vendor  (×N parallel)
                                                          ↓
                                                  retrieval_done
                                                          ↓
                                              [fan-out] → extraction_per_vendor (×N parallel)
                                                          ↓
                                                  extraction_done
                                                          ↓
                                              [fan-out] → evaluation_per_vendor (×N parallel)
                                                          ↓
                                                  evaluation_done
                                                          ↓
                                                    comparator        (sync barrier — reads merged dicts)
                                                          ↓
                                                    decision
                                                          ↓
                                              explanation_start
                                                          ↓
                                              [fan-out] → explanation_per_vendor (×N parallel)
                                                          ↓
                                              explanation_finalise   (stitches + critic + emits done)
                                                          ↓
                                                         END

Behaviour:
  • Per-vendor failures append to state.failed_vendors and DO NOT block the
    pipeline — Phase 4 isolation. Other vendors keep going. Comparator /
    Decision treat missing vendors as "no submission".
  • CRITIC HARD BLOCK from any non-per-vendor node still routes to END via
    _route_after() — preserves Phase 1's blocking-on-pipeline-fatal behaviour.
  • Vendor-iterating "start" / "done" nodes run exactly once per stage and
    just emit SSE events so the frontend UX stays compatible.
"""
from langgraph.graph import StateGraph, END
from langgraph.graph.state import CompiledStateGraph
from langgraph.types import Send

from .state import PipelineState
from .nodes import (
    planner_node,
    ingestion_node,
    # Retrieval (3 nodes — fan-out pattern)
    retrieval_start, retrieval_per_vendor, retrieval_done,
    # Extraction (3 nodes)
    extraction_start, extraction_per_vendor, extraction_done,
    # Evaluation (3 nodes)
    evaluation_start, evaluation_per_vendor, evaluation_done,
    # Cross-vendor stages
    comparator_node,
    decision_node,
    # Explanation (Phase 2: 4 nodes — fan-out + finalise + critic-controller)
    explanation_start, explanation_per_vendor, explanation_finalise, explanation_critic,
)

# Node name constants
_PLANNER    = "planner"
_INGESTION  = "ingestion"

_RETRIEVAL_START      = "retrieval_start"
_RETRIEVAL_PER_VENDOR = "retrieval_per_vendor"
_RETRIEVAL_DONE       = "retrieval_done"

_EXTRACTION_START      = "extraction_start"
_EXTRACTION_PER_VENDOR = "extraction_per_vendor"
_EXTRACTION_DONE       = "extraction_done"

_EVALUATION_START      = "evaluation_start"
_EVALUATION_PER_VENDOR = "evaluation_per_vendor"
_EVALUATION_DONE       = "evaluation_done"

_COMPARATOR = "comparator"
_DECISION   = "decision"

_EXPLANATION_START      = "explanation_start"
_EXPLANATION_PER_VENDOR = "explanation_per_vendor"
_EXPLANATION_FINALISE   = "explanation_finalise"
_EXPLANATION_CRITIC     = "explanation_critic"   # Phase 2 — controller node


# ── Routing helpers ──────────────────────────────────────────────────────────

def _route_after(state: PipelineState) -> str:
    """For non-per-vendor nodes: any HARD critic block routes straight to END.
    Per-vendor nodes don't use this — they isolate failures via failed_vendors."""
    return END if state.get("blocked") else "continue"


def _fan_out(target_node: str):
    """Build a conditional-edge function that fans out one Send per vendor_id.
    The Send payload carries the full state plus a `vendor_id` field that the
    per-vendor node reads to know which vendor it's processing."""
    def _edge(state: PipelineState):
        # If the prior stage marked the pipeline blocked (rare — only via the
        # non-per-vendor nodes upstream), short-circuit to END.
        if state.get("blocked"):
            return END
        vendor_ids = state.get("vendor_ids") or []
        if not vendor_ids:
            return END
        return [Send(target_node, {**state, "vendor_id": v}) for v in vendor_ids]
    return _edge


def build_graph() -> CompiledStateGraph:
    """Construct and compile the evaluation pipeline StateGraph with Phase 4
    parallel per-vendor fan-out."""
    g: StateGraph = StateGraph(PipelineState)

    # ── Register all nodes ──────────────────────────────────────────────────
    g.add_node(_PLANNER,     planner_node)
    g.add_node(_INGESTION,   ingestion_node)

    g.add_node(_RETRIEVAL_START,      retrieval_start)
    g.add_node(_RETRIEVAL_PER_VENDOR, retrieval_per_vendor)
    g.add_node(_RETRIEVAL_DONE,       retrieval_done)

    g.add_node(_EXTRACTION_START,      extraction_start)
    g.add_node(_EXTRACTION_PER_VENDOR, extraction_per_vendor)
    g.add_node(_EXTRACTION_DONE,       extraction_done)

    g.add_node(_EVALUATION_START,      evaluation_start)
    g.add_node(_EVALUATION_PER_VENDOR, evaluation_per_vendor)
    g.add_node(_EVALUATION_DONE,       evaluation_done)

    g.add_node(_COMPARATOR, comparator_node)
    g.add_node(_DECISION,   decision_node)

    g.add_node(_EXPLANATION_START,      explanation_start)
    g.add_node(_EXPLANATION_PER_VENDOR, explanation_per_vendor)
    g.add_node(_EXPLANATION_FINALISE,   explanation_finalise)
    g.add_node(_EXPLANATION_CRITIC,     explanation_critic)

    # ── Entry point ─────────────────────────────────────────────────────────
    g.set_entry_point(_PLANNER)

    # ── Non-per-vendor stages: planner → ingestion (with blocked→END) ──────
    g.add_conditional_edges(_PLANNER,   _route_after,
                            {END: END, "continue": _INGESTION})
    g.add_conditional_edges(_INGESTION, _route_after,
                            {END: END, "continue": _RETRIEVAL_START})

    # ── Retrieval stage: start → fan-out → per_vendor (×N) → done ──────────
    g.add_conditional_edges(_RETRIEVAL_START, _fan_out(_RETRIEVAL_PER_VENDOR),
                            [_RETRIEVAL_PER_VENDOR, END])
    g.add_edge(_RETRIEVAL_PER_VENDOR, _RETRIEVAL_DONE)
    g.add_edge(_RETRIEVAL_DONE, _EXTRACTION_START)

    # ── Extraction stage ───────────────────────────────────────────────────
    g.add_conditional_edges(_EXTRACTION_START, _fan_out(_EXTRACTION_PER_VENDOR),
                            [_EXTRACTION_PER_VENDOR, END])
    g.add_edge(_EXTRACTION_PER_VENDOR, _EXTRACTION_DONE)
    g.add_edge(_EXTRACTION_DONE, _EVALUATION_START)

    # ── Evaluation stage ───────────────────────────────────────────────────
    g.add_conditional_edges(_EVALUATION_START, _fan_out(_EVALUATION_PER_VENDOR),
                            [_EVALUATION_PER_VENDOR, END])
    g.add_edge(_EVALUATION_PER_VENDOR, _EVALUATION_DONE)
    g.add_edge(_EVALUATION_DONE, _COMPARATOR)

    # ── Cross-vendor sync barrier and downstream ───────────────────────────
    g.add_conditional_edges(_COMPARATOR, _route_after,
                            {END: END, "continue": _DECISION})
    g.add_conditional_edges(_DECISION,   _route_after,
                            {END: END, "continue": _EXPLANATION_START})

    # ── Explanation stage (fan-out + finalise + Phase 2 critic-controller) ──
    #
    # Topology:
    #     explanation_start → [fan-out] → explanation_per_vendor (×N)
    #                                          ↓
    #                                  explanation_finalise
    #                                          ↓
    #                                 explanation_critic ─→ approved → END
    #                                          │
    #                                          ├──→ retry → explanation_start
    #                                          │
    #                                          └──→ exhausted (blocked) → END
    #
    g.add_conditional_edges(_EXPLANATION_START, _fan_out(_EXPLANATION_PER_VENDOR),
                            [_EXPLANATION_PER_VENDOR, END])
    g.add_edge(_EXPLANATION_PER_VENDOR, _EXPLANATION_FINALISE)
    g.add_edge(_EXPLANATION_FINALISE, _EXPLANATION_CRITIC)
    g.add_conditional_edges(_EXPLANATION_CRITIC, _route_after_explanation_critic,
                            {"retry": _EXPLANATION_START, END: END})

    return g.compile()


def _route_after_explanation_critic(state: PipelineState) -> str:
    """Phase 2 routing decision for the explanation_critic node.

    The critic node sets an explicit `explanation_retry_requested: bool` flag
    so this router has an unambiguous signal — no inferring from the absence
    of other fields."""
    if state.get("blocked"):
        return END
    if state.get("explanation_retry_requested"):
        return "retry"
    return END


# Module-level singleton — built once on first import, reused across requests.
evaluation_graph: CompiledStateGraph = build_graph()
