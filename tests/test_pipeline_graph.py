"""
tests/test_pipeline_graph.py
============================
Unit tests for the LangGraph pipeline graph routing.

Tests the StateGraph topology and conditional edge logic WITHOUT
calling real agents, LLMs, PostgreSQL, or Qdrant.

Key insight: LangGraph binds node function references at compile time
(inside build_graph → add_node). To mock nodes, patch the names inside
app.pipeline.graph (where add_node picks them up) and call build_graph()
INSIDE the patch context so the compiled graph holds the mocks.

Run:
    python -m pytest tests/test_pipeline_graph.py -v
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from unittest.mock import patch

from app.pipeline.graph import build_graph
from app.pipeline.state import PipelineState

# ── Minimal valid initial state ───────────────────────────────────────────────

_SETUP_DICT = {
    "setup_id":         "setup-001",
    "org_id":           "test-org-001",
    "department":       "IT",
    "rfp_id":           "test-rfp-001",
    "rfp_confirmed":    True,
    "mandatory_checks": [],
    "scoring_criteria": [],
    "extraction_targets": [],
    "total_weight":     1.0,
    "confirmed_by":     "test-user",
    "confirmed_at":     None,
    "source":           "csv",
}

def _base_state(**overrides) -> PipelineState:
    state: PipelineState = {
        "run_id":                "test-run-001",
        "org_id":                "test-org-001",
        "rfp_id":                "test-rfp-001",
        "rfp_title":             "Test RFP",
        "rfp_filename":          "rfp.pdf",
        "rfp_bytes":             b"",
        "vendor_ids":            ["vendor_a"],
        "contract_value":        100_000.0,
        "currency":              "GBP",
        "setup_id":              "setup-001",
        "n_vendors":             1,
        "evaluation_setup_dict": _SETUP_DICT,
        "vendor_file_map":       {"vendor_a": (b"", "vendor_a.pdf")},
        "org_settings":          None,
        "retrieval_output_objects":  {},
        "extraction_output_objects": {},
        "evaluation_output_objects": {},
        "comparator_output":         None,
        "decision_output":           None,
        "explanation_output":        None,
        "source_chunks":             {},
        "blocked":       False,
        "blocked_agent": "",
        "error_message": "",
    }
    state.update(overrides)
    return state


# ── Mock node helpers ─────────────────────────────────────────────────────────

def _ok(name: str, extra: dict | None = None):
    """Async node that succeeds, optionally adding fields to state."""
    async def node(state):
        return extra or {}
    node.__name__ = name
    return node


def _blocked(name: str):
    """Async node that simulates a HARD critic block."""
    async def node(state):
        return {"blocked": True, "blocked_agent": name,
                "error_message": f"[CRITIC BLOCK] {name}: test"}
    node.__name__ = name
    return node


# ── Patch helper: patches all 8 node names in app.pipeline.graph ─────────────

def _patch_all(overrides: dict):
    """
    Returns a context manager that patches node references inside graph.py.
    Any name not in overrides gets a passthrough _ok() mock.
    """
    node_names = [
        "planner_node", "ingestion_node", "retrieval_node", "extraction_node",
        "evaluation_node", "comparator_node", "decision_node", "explanation_node",
    ]
    patches = []
    for n in node_names:
        mock = overrides.get(n, _ok(n))
        patches.append(patch(f"app.pipeline.graph.{n}", mock))
    # stack them all
    from contextlib import ExitStack
    stack = ExitStack()
    for p in patches:
        stack.enter_context(p)
    return stack


# ── Topology tests (no mocking needed) ───────────────────────────────────────

class TestGraphTopology:
    def test_all_nodes_present(self):
        nodes = list(build_graph().get_graph().nodes.keys())
        for name in ["__start__", "planner", "ingestion", "retrieval",
                     "extraction", "evaluation", "comparator",
                     "decision", "explanation", "__end__"]:
            assert name in nodes, f"Node '{name}' missing"

    def test_every_non_terminal_node_has_blocked_edge_to_end(self):
        edges = build_graph().get_graph().edges
        terminal_sources = {"__start__", "explanation"}
        for edge in edges:
            if edge.source in terminal_sources:
                continue
            assert edge.conditional, (
                f"Edge {edge.source}→{edge.target} must be conditional "
                "(needs blocked→END path)"
            )

    def test_explanation_goes_directly_to_end(self):
        edges = [e for e in build_graph().get_graph().edges
                 if e.source == "explanation"]
        assert len(edges) == 1
        assert edges[0].target == "__end__"
        assert not edges[0].conditional


# ── Routing tests (mocked nodes, graph rebuilt inside patch context) ──────────

class TestGraphRouting:
    @pytest.mark.asyncio
    async def test_happy_path_all_nodes_run(self):
        with _patch_all({}):
            graph = build_graph()
            final = await graph.ainvoke(_base_state())
        assert final["blocked"] is False
        assert final["error_message"] == ""

    @pytest.mark.asyncio
    async def test_planner_block_skips_all_downstream(self):
        visited = []

        async def planner_node(state):
            visited.append("planner")
            return {"blocked": True, "blocked_agent": "planner",
                    "error_message": "hard block"}

        async def track(name):
            async def node(state):
                visited.append(name)
                return {}
            return node

        overrides = {
            "planner_node":     planner_node,
            "ingestion_node":   await track("ingestion"),
            "retrieval_node":   await track("retrieval"),
            "extraction_node":  await track("extraction"),
            "evaluation_node":  await track("evaluation"),
            "comparator_node":  await track("comparator"),
            "decision_node":    await track("decision"),
            "explanation_node": await track("explanation"),
        }
        with _patch_all(overrides):
            graph = build_graph()
            final = await graph.ainvoke(_base_state())

        assert "planner"    in visited
        assert "ingestion"  not in visited
        assert "retrieval"  not in visited
        assert final["blocked"] is True
        assert final["blocked_agent"] == "planner"

    @pytest.mark.asyncio
    async def test_mid_pipeline_block_stops_at_retrieval(self):
        visited = []

        def track(name):
            async def node(state):
                visited.append(name)
                return {}
            return node

        async def retrieval_node(state):
            visited.append("retrieval")
            return {"blocked": True, "blocked_agent": "retrieval",
                    "error_message": "low confidence"}

        overrides = {
            "planner_node":     track("planner"),
            "ingestion_node":   track("ingestion"),
            "retrieval_node":   retrieval_node,
            "extraction_node":  track("extraction"),
            "evaluation_node":  track("evaluation"),
            "comparator_node":  track("comparator"),
            "decision_node":    track("decision"),
            "explanation_node": track("explanation"),
        }
        with _patch_all(overrides):
            graph = build_graph()
            final = await graph.ainvoke(_base_state())

        assert visited == ["planner", "ingestion", "retrieval"]
        assert final["blocked"] is True
        assert final["blocked_agent"] == "retrieval"

    @pytest.mark.asyncio
    async def test_state_accumulates_across_nodes(self):
        """Verify retrieval output is visible to extraction node."""
        seen_by_extraction = {}

        async def retrieval_node(state):
            return {"retrieval_output_objects": {"vendor_a": "mock_ret"}}

        async def extraction_node(state):
            seen_by_extraction.update(state["retrieval_output_objects"])
            return {"extraction_output_objects": {"vendor_a": "mock_ext"}}

        overrides = {
            "retrieval_node":  retrieval_node,
            "extraction_node": extraction_node,
        }
        with _patch_all(overrides):
            graph = build_graph()
            final = await graph.ainvoke(_base_state())

        assert seen_by_extraction.get("vendor_a") == "mock_ret"
        assert final["extraction_output_objects"]["vendor_a"] == "mock_ext"
        assert final["blocked"] is False
