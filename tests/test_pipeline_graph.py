"""
tests/test_pipeline_graph.py
============================
Unit tests for the LangGraph pipeline topology + routing.

Updated for Phase 4 (parallel vendor execution via LangGraph Send):
  - Each vendor-iterating stage is now THREE nodes:
        {stage}_start  → fan-out → {stage}_per_vendor (×N) → {stage}_done
  - Per-vendor nodes do NOT route to END on `blocked` — they isolate failures
    via the `failed_vendors` state field instead.
  - Only the *_start nodes have a conditional edge to END (when pre-stage
    state is already blocked); the per-vendor and *_done nodes do not.

These tests verify topology + routing WITHOUT touching real agents / LLMs.

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

# Stages that are split into start/per_vendor/done (or finalise for explanation).
# Each contributes 3 nodes to the graph.
_FAN_OUT_STAGES = ["retrieval", "extraction", "evaluation"]
_EXPLANATION_NODES = ["explanation_start", "explanation_per_vendor", "explanation_finalise"]

# Non-per-vendor nodes that follow the original blocked→END pattern.
_LINEAR_NODES = ["planner", "ingestion", "comparator", "decision"]

# Node names that exist in the compiled graph.
_ALL_GRAPH_NODES = (
    ["__start__"]
    + _LINEAR_NODES
    + [f"{s}_{suffix}" for s in _FAN_OUT_STAGES for suffix in ("start", "per_vendor", "done")]
    + _EXPLANATION_NODES
    + ["__end__"]
)

# Patch target -> mock kind. _ok() is the default; tests can override.
_NODE_PATCH_NAMES = [
    "planner_node", "ingestion_node",
    "retrieval_start", "retrieval_per_vendor", "retrieval_done",
    "extraction_start", "extraction_per_vendor", "extraction_done",
    "evaluation_start", "evaluation_per_vendor", "evaluation_done",
    "comparator_node", "decision_node",
    "explanation_start", "explanation_per_vendor", "explanation_finalise",
]


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


def _base_state(**overrides) -> dict:
    state: dict = {
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
        "vendor_id":             "",
        "retrieval_output_objects":  {},
        "extraction_output_objects": {},
        "evaluation_output_objects": {},
        "source_chunks":             {},
        "vendor_narratives_accum":   {},
        "failed_vendors":            [],
        "comparator_output":         None,
        "decision_output":           None,
        "explanation_output":        None,
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


def _patch_all(overrides: dict):
    """Returns a context manager that patches node references inside graph.py.
    Any name not in overrides gets a passthrough _ok() mock."""
    from contextlib import ExitStack
    stack = ExitStack()
    for n in _NODE_PATCH_NAMES:
        mock = overrides.get(n, _ok(n))
        stack.enter_context(patch(f"app.pipeline.graph.{n}", mock))
    return stack


# ── Topology tests ────────────────────────────────────────────────────────────

class TestGraphTopology:
    def test_all_nodes_present(self):
        nodes = list(build_graph().get_graph().nodes.keys())
        for name in _ALL_GRAPH_NODES:
            assert name in nodes, f"Node '{name}' missing from compiled graph"

    def test_linear_nodes_have_blocked_edge_to_end(self):
        """planner, ingestion, comparator, decision must have a conditional
        edge that routes to END when state.blocked is True. This preserves
        the Phase 1 hard-block behaviour for non-per-vendor stages."""
        edges = build_graph().get_graph().edges
        for linear in _LINEAR_NODES:
            outgoing = [e for e in edges if e.source == linear]
            ends = [e for e in outgoing if e.target == "__end__"]
            assert ends, f"{linear} has no edge to __end__ (blocked path missing)"
            assert any(e.conditional for e in ends), \
                f"{linear} -> __end__ must be conditional"

    def test_fan_out_stages_route_through_three_nodes(self):
        """For each fan-out stage, *_start → *_per_vendor → *_done exists
        as a connected path."""
        edges = build_graph().get_graph().edges
        edge_pairs = {(e.source, e.target) for e in edges}
        for stage in _FAN_OUT_STAGES:
            start = f"{stage}_start"
            per   = f"{stage}_per_vendor"
            done  = f"{stage}_done"
            # start → per_vendor (conditional Send) AND start → END (blocked)
            assert any(s == start and t == per for s, t in edge_pairs), \
                f"Missing edge {start} -> {per}"
            # per_vendor → done (plain)
            assert (per, done) in edge_pairs, \
                f"Missing edge {per} -> {done}"

    def test_explanation_finalise_is_terminal(self):
        edges = [e for e in build_graph().get_graph().edges
                 if e.source == "explanation_finalise"]
        assert len(edges) == 1, "explanation_finalise must have exactly one outgoing edge"
        assert edges[0].target == "__end__"

    def test_comparator_is_sync_barrier_after_evaluation(self):
        """evaluation_done → comparator is the sync point where all per-vendor
        results converge for cross-vendor ranking."""
        edges = build_graph().get_graph().edges
        assert any(e.source == "evaluation_done" and e.target == "comparator"
                   for e in edges), \
            "Missing the sync-barrier edge: evaluation_done -> comparator"


# ── Routing tests ─────────────────────────────────────────────────────────────

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

        def track(name):
            async def node(state):
                visited.append(name)
                return {}
            return node

        overrides = {"planner_node": planner_node}
        for n in _NODE_PATCH_NAMES:
            if n not in overrides:
                overrides[n] = track(n)

        with _patch_all(overrides):
            graph = build_graph()
            final = await graph.ainvoke(_base_state())

        assert "planner" in visited
        # No downstream node should have run
        for n in [
            "ingestion_node",
            "retrieval_start", "retrieval_per_vendor", "retrieval_done",
            "extraction_start", "extraction_per_vendor", "extraction_done",
            "evaluation_start", "evaluation_per_vendor", "evaluation_done",
            "comparator_node", "decision_node",
            "explanation_start", "explanation_per_vendor", "explanation_finalise",
        ]:
            assert n not in visited, f"{n} should not run after planner block"
        assert final["blocked"] is True
        assert final["blocked_agent"] == "planner"

    @pytest.mark.asyncio
    async def test_ingestion_block_skips_all_fan_out_stages(self):
        visited = []

        def track(name):
            async def node(state):
                visited.append(name)
                return {}
            return node

        async def ingestion_block(state):
            visited.append("ingestion")
            return {"blocked": True, "blocked_agent": "ingestion",
                    "error_message": "low quality"}

        overrides = {"ingestion_node": ingestion_block}
        for n in _NODE_PATCH_NAMES:
            if n not in overrides:
                overrides[n] = track(n)

        with _patch_all(overrides):
            graph = build_graph()
            final = await graph.ainvoke(_base_state())

        assert "ingestion" in visited
        for n in [
            "retrieval_start", "retrieval_per_vendor",
            "extraction_start", "evaluation_start",
            "comparator_node", "decision_node",
        ]:
            assert n not in visited, f"{n} should not run after ingestion block"
        assert final["blocked"] is True
        assert final["blocked_agent"] == "ingestion"

    @pytest.mark.asyncio
    async def test_per_vendor_node_fires_once_per_vendor(self):
        """With 3 vendors in state, retrieval_per_vendor should be invoked
        exactly 3 times (LangGraph Send fan-out)."""
        call_count = 0
        seen_vendor_ids: list[str] = []

        async def counting_retrieval(state):
            nonlocal call_count
            call_count += 1
            seen_vendor_ids.append(state.get("vendor_id", "?"))
            return {"retrieval_output_objects": {state["vendor_id"]: "ok"}}

        overrides = {"retrieval_per_vendor": counting_retrieval}
        with _patch_all(overrides):
            graph = build_graph()
            await graph.ainvoke(_base_state(
                vendor_ids=["v1", "v2", "v3"], n_vendors=3,
                vendor_file_map={"v1": (b"", "1.pdf"), "v2": (b"", "2.pdf"), "v3": (b"", "3.pdf")},
            ))

        assert call_count == 3, \
            f"Expected 3 retrieval_per_vendor calls, got {call_count}"
        assert sorted(seen_vendor_ids) == ["v1", "v2", "v3"]

    @pytest.mark.asyncio
    async def test_state_dict_reducer_merges_parallel_writes(self):
        """Each per-vendor node returns {retrieval_output_objects: {vid: ...}}.
        The Annotated[dict, _merge_dicts] reducer must merge all N parallel
        returns into a single dict (no last-writer-wins clobbering)."""
        async def writing_retrieval(state):
            return {"retrieval_output_objects": {state["vendor_id"]: f"out-{state['vendor_id']}"}}

        overrides = {"retrieval_per_vendor": writing_retrieval}
        with _patch_all(overrides):
            graph = build_graph()
            final = await graph.ainvoke(_base_state(
                vendor_ids=["va", "vb", "vc"], n_vendors=3,
                vendor_file_map={"va": (b"", "a.pdf"), "vb": (b"", "b.pdf"), "vc": (b"", "c.pdf")},
            ))

        merged = final.get("retrieval_output_objects") or {}
        assert set(merged.keys()) == {"va", "vb", "vc"}, \
            f"Reducer dropped vendors: got {list(merged.keys())}"

    @pytest.mark.asyncio
    async def test_failed_vendor_appends_without_blocking_pipeline(self):
        """A per-vendor node that hits an error appends to failed_vendors
        but does NOT set state.blocked. Other vendors keep running."""
        async def failing_retrieval(state):
            vid = state["vendor_id"]
            if vid == "v2":
                return {"failed_vendors": [{
                    "vendor_id": vid, "stage": "retrieval",
                    "error": "simulated", "ts": "now",
                }]}
            return {"retrieval_output_objects": {vid: "ok"}}

        overrides = {"retrieval_per_vendor": failing_retrieval}
        with _patch_all(overrides):
            graph = build_graph()
            final = await graph.ainvoke(_base_state(
                vendor_ids=["v1", "v2", "v3"], n_vendors=3,
                vendor_file_map={"v1": (b"", "1.pdf"), "v2": (b"", "2.pdf"), "v3": (b"", "3.pdf")},
            ))

        # Pipeline did NOT block on one bad vendor
        assert final["blocked"] is False
        # The two healthy vendors made it through
        assert set((final.get("retrieval_output_objects") or {}).keys()) == {"v1", "v3"}
        # The failed vendor is recorded for downstream stages to skip
        failed = final.get("failed_vendors") or []
        assert any(f["vendor_id"] == "v2" and f["stage"] == "retrieval"
                   for f in failed)
