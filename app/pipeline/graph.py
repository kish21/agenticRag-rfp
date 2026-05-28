"""
LangGraph StateGraph — wires the 9-agent pipeline with conditional edges.

Topology:
  planner → ingestion → retrieval → extraction → evaluation
          → comparator → decision → explanation → END

After every node:
  • CriticVerdict.BLOCKED  →  _route_after() returns END immediately
  • Otherwise              →  proceeds to the next node

Benefits over the old sequential-await approach:
  • astream() yields a state diff after each node — frontend can show live progress
  • LangSmith renders the full DAG in its trace view
  • A BLOCKED critic routes to END cleanly without a try/except waterfall
  • State is snapshotted at each node — replay is trivial
"""
from langgraph.graph import StateGraph, END
from langgraph.graph.state import CompiledStateGraph

from .state import PipelineState
from .nodes import (
    planner_node,
    ingestion_node,
    retrieval_node,
    extraction_node,
    evaluation_node,
    comparator_node,
    decision_node,
    explanation_node,
)

# Node name constants — avoids magic strings in edge definitions
_PLANNER    = "planner"
_INGESTION  = "ingestion"
_RETRIEVAL  = "retrieval"
_EXTRACTION = "extraction"
_EVALUATION = "evaluation"
_COMPARATOR = "comparator"
_DECISION   = "decision"
_EXPLANATION = "explanation"


def _route_after(state: PipelineState) -> str:
    """Shared conditional router: any HARD critic block routes straight to END."""
    return END if state.get("blocked") else "continue"


def build_graph() -> CompiledStateGraph:
    """
    Construct and compile the evaluation pipeline StateGraph.

    No checkpointer is attached — state lives in-memory for the duration of
    one evaluation run. Add a SqliteSaver / AsyncPostgresSaver here later if
    you need durable mid-run snapshots.
    """
    g: StateGraph = StateGraph(PipelineState)

    # Register nodes
    g.add_node(_PLANNER,     planner_node)
    g.add_node(_INGESTION,   ingestion_node)
    g.add_node(_RETRIEVAL,   retrieval_node)
    g.add_node(_EXTRACTION,  extraction_node)
    g.add_node(_EVALUATION,  evaluation_node)
    g.add_node(_COMPARATOR,  comparator_node)
    g.add_node(_DECISION,    decision_node)
    g.add_node(_EXPLANATION, explanation_node)

    # Entry point
    g.set_entry_point(_PLANNER)

    # Conditional edges after each node:
    #   blocked=True  → END
    #   blocked=False → next node
    g.add_conditional_edges(_PLANNER,     _route_after,
                            {END: END, "continue": _INGESTION})
    g.add_conditional_edges(_INGESTION,   _route_after,
                            {END: END, "continue": _RETRIEVAL})
    g.add_conditional_edges(_RETRIEVAL,   _route_after,
                            {END: END, "continue": _EXTRACTION})
    g.add_conditional_edges(_EXTRACTION,  _route_after,
                            {END: END, "continue": _EVALUATION})
    g.add_conditional_edges(_EVALUATION,  _route_after,
                            {END: END, "continue": _COMPARATOR})
    g.add_conditional_edges(_COMPARATOR,  _route_after,
                            {END: END, "continue": _DECISION})
    g.add_conditional_edges(_DECISION,    _route_after,
                            {END: END, "continue": _EXPLANATION})

    # Explanation always goes to END (it is the terminal node)
    g.add_edge(_EXPLANATION, END)

    return g.compile()


# Module-level singleton — built once on first import, reused across requests.
# Thread-safe: CompiledStateGraph is stateless between invocations.
evaluation_graph: CompiledStateGraph = build_graph()
