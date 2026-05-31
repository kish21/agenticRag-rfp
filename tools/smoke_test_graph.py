#!/usr/bin/env python3
"""
smoke_test_graph.py — End-to-end smoke test of the LangGraph pipeline
=====================================================================
Drives the FULL LangGraph (`evaluation_graph.astream`) against real PDFs,
real PostgreSQL, real Qdrant, real LLM calls. Mirrors the production code
path: POST /api/v1/evaluate/start → POST /{run_id}/confirm → astream.

Unlike tools/smoke_test.py (which invokes each agent function directly),
this test confirms that:
  • the LangGraph StateGraph compiles
  • astream() actually drives all 8 nodes
  • per-node state diffs flow through the graph
  • conditional blocked→END routing reaches a terminal state
  • decision_output is persisted and status='complete' on success

VERBOSE OUTPUT
--------------
Prints the compiled graph (ASCII + Mermaid) BEFORE the run, then for every
node logs: ▶ ENTER, state field count, elapsed time, ▲ EXIT diff keys, and
routing decision (→ next | → END).

ARTIFACTS
---------
Everything is saved under  tests/smoke_results/<UTC-timestamp>_<run_id>/ :
    graph_topology.txt   — ASCII diagram
    graph_topology.mmd   — Mermaid source
    transcript.log       — full stdout copy
    node_diffs/          — per-node JSON diff files (01_planner.json …)
    final_state.json     — merged state at END (non-serialisable fields stripped)
    decision_output.json — persisted decision
    agent_events.json    — SSE events written to evaluation_runs.agent_events
    summary.json         — pass/fail + per-node timing + which nodes ran

Usage:
    python tools/smoke_test_graph.py \\
        --rfp data/documents/RFP_IT_Managed_Services_MFS_2026.pdf \\
        --criteria data/documents/Vendor_Selection_Criteria_MFS.csv \\
        --vendor-pdf data/documents/Acme_ClearPath_Proposal.pdf \\
        --vendor-pdf data/documents/nightbuilb_Apex_Technology_Proposal.pdf

Exit codes:
    0 — graph completed and produced a decision
    1 — graph blocked / setup failed / no decision persisted
"""
import argparse
import asyncio
import json
import os
import sys
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path

# Force UTF-8 on Windows
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if sys.stderr.encoding and sys.stderr.encoding.lower() != "utf-8":
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# Force local YAML prompts so Phase 1 prompt changes take effect without
# requiring a LangSmith Hub re-push. Production deploys can opt back in by
# unsetting this. Smoke test = ground truth of the in-repo prompt files.
os.environ.setdefault("PROMPTS_FORCE_LOCAL", "true")

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

# Updated for Phase 4 — each vendor-iterating stage is split into start/per_vendor/done.
# These are the LangGraph node names that should fire during a healthy run.
EXPECTED_NODES = [
    "planner", "ingestion",
    "retrieval_start", "retrieval_per_vendor", "retrieval_done",
    "extraction_start", "extraction_per_vendor", "extraction_done",
    "evaluation_start", "evaluation_per_vendor", "evaluation_done",
    "comparator", "decision",
    "explanation_start", "explanation_per_vendor", "explanation_finalise",
]

# Logical "agent" stage names that appear in the agent_events SSE stream
# (one emit per stage regardless of how many per-vendor branches ran).
# Used for the DB-event verification at the end of a run.
EXPECTED_AGENT_EVENTS = [
    "planner", "ingestion", "retrieval", "extraction",
    "evaluation", "comparator", "decision", "explanation",
]


# ── Output helpers (tee-able) ─────────────────────────────────────────────────

class Tee:
    """Mirror stdout to a file so the transcript is captured verbatim.

    Unknown attribute access falls through to the wrapped stream — this keeps
    callers that rely on `sys.stdout.encoding`, `sys.stdout.reconfigure(...)`,
    `sys.stdout.isatty()`, etc. happy.
    """
    def __init__(self, path: Path):
        self._f = open(path, "w", encoding="utf-8", buffering=1)
        self._orig = sys.stdout
        sys.stdout = self

    def write(self, s):
        self._orig.write(s)
        try:
            self._f.write(s)
        except Exception:
            pass

    def flush(self):
        self._orig.flush()
        try:
            self._f.flush()
        except Exception:
            pass

    def close(self):
        sys.stdout = self._orig
        try:
            self._f.close()
        except Exception:
            pass

    # Forward anything we don't explicitly handle (encoding, reconfigure,
    # isatty, fileno, buffer, …) to the real stdout so consumers that probe
    # stdout's metadata (e.g. tools/smoke_test.py's UTF-8 reconfigure) work.
    def __getattr__(self, name):
        return getattr(self._orig, name)


def section(title: str) -> None:
    bar = "═" * 78
    print(f"\n{bar}\n  {title}\n{bar}")


def kv(k: str, v) -> None:
    print(f"  {k:<32} {v}")


# ── DB helpers ────────────────────────────────────────────────────────────────

def _confirm_run(run_id: str, org_id: str) -> None:
    """Flip rfp_confirmed=True and status='running' — mirrors confirm_run."""
    import sqlalchemy as sa
    from app.db.fact_store import get_engine

    engine = get_engine()
    with engine.begin() as conn:
        row = conn.execute(sa.text("""
            SELECT setup_id FROM evaluation_runs
            WHERE run_id = CAST(:rid AS uuid)
        """), {"rid": run_id}).fetchone()
        if not row:
            raise RuntimeError(f"Run {run_id} not found in evaluation_runs")
        setup_id = row[0]
        conn.execute(sa.text("""
            UPDATE evaluation_setups
            SET setup_json = jsonb_set(setup_json, '{rfp_confirmed}', 'true'::jsonb)
            WHERE setup_id = :sid AND org_id = CAST(:oid AS uuid)
        """), {"sid": setup_id, "oid": org_id})
        conn.execute(sa.text("""
            UPDATE evaluation_runs SET status = 'running'
            WHERE run_id = CAST(:rid AS uuid)
        """), {"rid": run_id})


def _read_run(run_id: str, org_id: str) -> dict:
    import sqlalchemy as sa
    from app.db.fact_store import get_engine

    engine = get_engine()
    with engine.connect() as conn:
        row = conn.execute(sa.text("""
            SELECT status, agent_events, decision_output, completed_at
            FROM evaluation_runs
            WHERE run_id = CAST(:rid AS uuid) AND org_id = CAST(:oid AS uuid)
        """), {"rid": run_id, "oid": org_id}).fetchone()
    if not row:
        raise RuntimeError(f"Run {run_id} not found post-execution")
    events = row[1] or []
    if isinstance(events, str):
        events = json.loads(events)
    decision = row[2]
    if isinstance(decision, str):
        decision = json.loads(decision)
    return {
        "status": row[0],
        "agent_events": events,
        "decision_output": decision,
        "completed_at": row[3].isoformat() if row[3] else None,
    }


# ── Serialisation: strip non-JSON-safe fields from PipelineState ──────────────

_DROP_KEYS = {"rfp_bytes", "vendor_file_map", "org_settings"}


def _safe_dump(obj):
    """Best-effort JSON-safe rendering of state diffs / final state."""
    if obj is None or isinstance(obj, (bool, int, float, str)):
        return obj
    if isinstance(obj, bytes):
        return f"<bytes len={len(obj)}>"
    if isinstance(obj, dict):
        return {k: _safe_dump(v) for k, v in obj.items() if k not in _DROP_KEYS}
    if isinstance(obj, (list, tuple)):
        return [_safe_dump(v) for v in obj]
    # Pydantic v2
    if hasattr(obj, "model_dump"):
        try:
            return obj.model_dump(mode="json")
        except Exception:
            pass
    # Fallback
    try:
        return repr(obj)
    except Exception:
        return "<unrepr>"


# ── Graph rendering ───────────────────────────────────────────────────────────

def render_graph(graph, out_dir: Path) -> None:
    """Print ASCII diagram + save ASCII and Mermaid sources to disk."""
    gv = graph.get_graph()

    section("LANGGRAPH TOPOLOGY (compiled StateGraph)")
    ascii_txt = ""
    try:
        ascii_txt = gv.draw_ascii()
        print(ascii_txt)
    except Exception as e:
        print(f"  [draw_ascii unavailable: {e}]")
        # Hand-drawn fallback
        ascii_txt = (
            "  __start__\n"
            "      │\n"
            "      ▼\n"
            "   planner ──blocked──▶ END\n"
            "      │ continue\n"
            "      ▼\n"
            "   ingestion ──blocked──▶ END\n"
            "      │\n"
            "      ▼\n"
            "   retrieval ──blocked──▶ END\n"
            "      │\n"
            "      ▼\n"
            "   extraction ──blocked──▶ END\n"
            "      │\n"
            "      ▼\n"
            "   evaluation ──blocked──▶ END\n"
            "      │\n"
            "      ▼\n"
            "   comparator ──blocked──▶ END\n"
            "      │\n"
            "      ▼\n"
            "   decision ──blocked──▶ END\n"
            "      │\n"
            "      ▼\n"
            "   explanation\n"
            "      │\n"
            "      ▼\n"
            "    __end__\n"
        )
        print(ascii_txt)

    (out_dir / "graph_topology.txt").write_text(ascii_txt, encoding="utf-8")

    try:
        mermaid = gv.draw_mermaid()
    except Exception:
        mermaid = "graph TD\n  planner --> ingestion --> retrieval --> extraction --> evaluation --> comparator --> decision --> explanation\n"
    (out_dir / "graph_topology.mmd").write_text(mermaid, encoding="utf-8")

    # Hand-built clean Mermaid — LangGraph's output uses &nbsp; / <p>... / YAML
    # frontmatter that some renderers reject. This version pastes cleanly into
    # mermaid.live, GitHub READMEs, and the VS Code Mermaid Preview extension.
    clean_mermaid = (
        "flowchart TD\n"
        "    START([__start__]) --> planner\n"
        "    planner --> ingestion\n"
        "    planner -.blocked.-> END\n"
        "    ingestion --> retrieval\n"
        "    ingestion -.blocked.-> END\n"
        "    retrieval --> extraction\n"
        "    retrieval -.blocked.-> END\n"
        "    extraction --> evaluation\n"
        "    extraction -.blocked.-> END\n"
        "    evaluation --> comparator\n"
        "    evaluation -.blocked.-> END\n"
        "    comparator --> decision\n"
        "    comparator -.blocked.-> END\n"
        "    decision --> explanation\n"
        "    decision -.blocked.-> END\n"
        "    explanation --> END([__end__])\n"
        "\n"
        "    classDef ok fill:#d4f4dd,stroke:#2d7a4f,color:#000\n"
        "    classDef terminal fill:#ffe5e5,stroke:#aa3333,color:#000\n"
        "    class planner,ingestion,retrieval,extraction,evaluation,"
        "comparator,decision,explanation ok\n"
        "    class START,END terminal\n"
    )
    (out_dir / "graph_topology_clean.mmd").write_text(clean_mermaid, encoding="utf-8")

    # Critic-annotated view — the Critic is NOT a LangGraph node (it runs
    # inline inside each node via _hard_block_if). This diagram makes that
    # behaviour visible: every agent → critic check → {approved | BLOCKED}.
    critic_mermaid = (
        "flowchart TD\n"
        "    START([__start__]) --> planner\n"
    )
    nodes_in_order = [
        ("planner",     "p_crit",  "ingestion"),
        ("ingestion",   "i_crit",  "retrieval"),
        ("retrieval",   "r_crit",  "extraction"),
        ("extraction",  "x_crit",  "evaluation"),
        ("evaluation",  "e_crit",  "comparator"),
        ("comparator",  "c_crit",  "decision"),
        ("decision",    "d_crit",  "explanation"),
        ("explanation", "ex_crit", "END"),
    ]
    for agent, crit, nxt in nodes_in_order:
        critic_mermaid += (
            f"    subgraph {agent}_box [{agent} node]\n"
            f"        {agent}[{agent.title()} Agent] --> {crit}{{{{Critic check}}}}\n"
            f"    end\n"
        )
        if nxt == "END":
            critic_mermaid += f"    {crit} -- approved --> END([__end__])\n"
        else:
            critic_mermaid += f"    {crit} -- approved --> {nxt}\n"
        critic_mermaid += f"    {crit} -- BLOCKED --> END\n"
    critic_mermaid += (
        "\n"
        "    classDef agent fill:#d4f4dd,stroke:#2d7a4f,color:#000\n"
        "    classDef critic fill:#fff4cc,stroke:#aa7700,color:#000\n"
        "    classDef terminal fill:#ffe5e5,stroke:#aa3333,color:#000\n"
        "    class " + ",".join(a for a, _, _ in nodes_in_order) + " agent\n"
        "    class " + ",".join(c for _, c, _ in nodes_in_order) + " critic\n"
        "    class START,END terminal\n"
    )
    (out_dir / "graph_topology_with_critic.mmd").write_text(critic_mermaid, encoding="utf-8")

    print("\n  Nodes:")
    for n in gv.nodes:
        print(f"    • {n}")
    print("\n  Edges (source → target, conditional?):")
    for e in gv.edges:
        cond = " [conditional]" if getattr(e, "conditional", False) else ""
        print(f"    {e.source}  →  {e.target}{cond}")


# ── Verbose graph driver ──────────────────────────────────────────────────────

async def drive_graph_verbose(graph, initial_state: dict, out_dir: Path) -> tuple[dict, list[dict]]:
    """
    Stream the graph and print ENTER/EXIT lines + diff summaries for each node.
    Returns (final_state, node_trace).

    node_trace[i] = {
        "order": i+1, "node": "planner", "elapsed_s": 1.23,
        "diff_keys": [...], "blocked": False, "diff": <safe_dump>
    }
    """
    from app.pipeline.state import _merge_critic_metrics

    section("DRIVING LANGGRAPH — verbose per-node trace")
    print("  Streaming evaluation_graph.astream(initial_state)…\n")

    diffs_dir = out_dir / "node_diffs"
    diffs_dir.mkdir(parents=True, exist_ok=True)

    final_state = dict(initial_state)
    node_trace: list[dict] = []
    order = 0
    last_tick = time.perf_counter()

    # Snapshot of which keys exist in initial state (for ENTER printout)
    initial_keys = {k for k, v in initial_state.items()
                    if k not in _DROP_KEYS and v not in (None, {}, [], "", False)}

    # recursion_limit=50 to accommodate Phase 2 critic-retry cycles
    async for state_diff in graph.astream(initial_state, {"recursion_limit": 50}):
        elapsed = time.perf_counter() - last_tick
        # astream yields {node_name: updated_fields_dict}
        node_name = next(iter(state_diff))
        diff = state_diff[node_name] or {}
        order += 1

        print(f"  ▶ ENTER  {node_name}")
        # We can't observe the pre-state inside astream, but we can show what
        # the merged state held going in (= final_state from previous iter).
        pre_filled = sorted(k for k, v in final_state.items()
                            if k not in _DROP_KEYS and v not in (None, {}, [], "", False))
        print(f"           state-in keys ({len(pre_filled)}): "
              f"{', '.join(pre_filled) if pre_filled else '(empty)'}")

        # Merge the diff (shallow). In astream "updates" mode each diff is a
        # node's RAW return, NOT the reducer-applied channel — so critic
        # telemetry (a deep-merge reducer field) must be accumulated explicitly
        # or a later stage's emission overwrites the earlier one.
        _prev_critic = final_state.get("critic_metrics_accum") or {}
        final_state = {**final_state, **diff}
        if "critic_metrics_accum" in diff:
            final_state["critic_metrics_accum"] = _merge_critic_metrics(
                _prev_critic, diff["critic_metrics_accum"])
        blocked = bool(final_state.get("blocked"))
        next_route = "END" if blocked else (
            EXPECTED_NODES[EXPECTED_NODES.index(node_name) + 1]
            if node_name in EXPECTED_NODES
               and EXPECTED_NODES.index(node_name) < len(EXPECTED_NODES) - 1
            else "END"
        )

        diff_keys = sorted(diff.keys())
        print(f"  ▲ EXIT   {node_name}  ({elapsed:6.2f}s)")
        print(f"           diff keys: {diff_keys or '(none)'}")
        if blocked:
            print(f"           ✗ blocked={blocked}  agent={final_state.get('blocked_agent')!r}")
            print(f"           error: {final_state.get('error_message','')[:200]}")
        # Tiny per-key summary for non-trivial diffs
        for k, v in diff.items():
            if isinstance(v, dict):
                print(f"           · {k}: dict with {len(v)} keys")
            elif isinstance(v, list):
                print(f"           · {k}: list with {len(v)} items")
            elif isinstance(v, (str, int, float, bool)) or v is None:
                preview = str(v)[:80]
                print(f"           · {k}: {preview}")
            else:
                print(f"           · {k}: {type(v).__name__}")
        print(f"  ▼ ROUTE  → {next_route}\n")

        # Save the diff to disk
        safe = _safe_dump(diff)
        (diffs_dir / f"{order:02d}_{node_name}.json").write_text(
            json.dumps(safe, indent=2, default=str), encoding="utf-8")

        node_trace.append({
            "order": order,
            "node": node_name,
            "elapsed_s": round(elapsed, 3),
            "diff_keys": diff_keys,
            "blocked": blocked,
        })
        last_tick = time.perf_counter()

    return final_state, node_trace


# ── Verification ──────────────────────────────────────────────────────────────

def _verify_graph_executed(run: dict, node_trace: list[dict]) -> list[str]:
    failures: list[str] = []
    if run["status"] != "complete":
        failures.append(f"final status is '{run['status']}', expected 'complete'")
    nodes_ran = {t["node"] for t in node_trace}
    # Phase 4 fan-out: missing non-per-vendor nodes is a hard fail. Missing
    # `*_per_vendor` nodes is OK when vendor_ids is empty (no vendors -> no
    # parallel branches were ever spawned).
    n_vendors = (run.get("n_vendors") or 0)
    has_vendors = (n_vendors > 0)
    for node_name in EXPECTED_NODES:
        if node_name in nodes_ran:
            continue
        if node_name.endswith("_per_vendor") and not has_vendors:
            continue   # legitimately not spawned when no vendors submitted
        failures.append(f"node never invoked: {node_name}")
    # Cross-check the SSE event stream — at least one 'done' event per agent.
    events = run.get("agent_events") or []
    done_agents = {e.get("agent") for e in events if e.get("status") == "done"}
    missing_agents = [a for a in EXPECTED_AGENT_EVENTS if a not in done_agents]
    if missing_agents:
        failures.append(f"agents that never emitted 'done': {missing_agents}")
    if not run["decision_output"]:
        failures.append("decision_output is empty/null")
    if not run["completed_at"]:
        failures.append("completed_at is null")
    return failures


def _summarise_critic_metrics(accum: dict) -> dict:
    """Roll up the per-vendor critic-controller telemetry (Phase 2c).

    `accum` is {vendor_id: {agent: {blocks, retries, retry_success, exhausted}}}.
    Returns per-agent totals plus a flat per-vendor view, so a smoke run shows
    how often the self-correcting retry fired, recovered, or exhausted.
    """
    per_agent: dict[str, dict] = {}
    for _vid, agents in (accum or {}).items():
        for agent, m in (agents or {}).items():
            a = per_agent.setdefault(
                agent, {"vendors": 0, "blocks": 0, "retries": 0,
                        "retry_success": 0, "exhausted": 0})
            a["vendors"] += 1
            a["blocks"] += int(m.get("blocks", 0))
            a["retries"] += int(m.get("retries", 0))
            a["retry_success"] += 1 if m.get("retry_success") else 0
            a["exhausted"] += 1 if m.get("exhausted") else 0
    return {"by_agent": per_agent, "by_vendor": accum or {}}


# ── Main ──────────────────────────────────────────────────────────────────────

async def main_async(args) -> int:
    # Prepare results folder up front (so transcript captures everything).
    # We use the timestamp as the folder name and write run_id.txt inside —
    # this avoids a Windows rename-while-open problem on the transcript file.
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    results_root = ROOT / "tests" / "smoke_results"
    results_root.mkdir(parents=True, exist_ok=True)
    out_dir = results_root / ts
    out_dir.mkdir(parents=True, exist_ok=True)
    tee = Tee(out_dir / "transcript.log")

    # RLS (post-#190): the app engine connects as the non-superuser platform_app
    # role. This dev smoke harness verifies the PIPELINE (not tenant isolation —
    # that's proven in tests/test_tenant_isolation_rls.py), and it seeds/reads many
    # rows for one org outside any request context. Mirror tests/conftest.py: route
    # the app engine to the RLS-exempt owner role for the run. Without this, the
    # evaluation_runs insert is rejected by row-level security.
    import app.db.fact_store as _fs
    from app.db.session import admin_engine_url as _admin_url
    _fs.app_engine_url = _admin_url
    _fs._engine = None

    overall_ok = False
    try:
        section("LANGGRAPH SMOKE TEST")
        kv("started (UTC)", ts)
        kv("results dir",   str(out_dir))
        kv("rfp",           args.rfp)
        kv("vendor PDFs",   ", ".join(args.vendor_pdf))
        kv("criteria",      args.criteria or "(none)")

        # ── 1. Render graph BEFORE driving it ─────────────────────────────────
        from app.pipeline.graph import evaluation_graph
        render_graph(evaluation_graph, out_dir)

        # ── 2. Reuse run_rfp from existing smoke_test for DB setup ────────────
        from smoke_test import run_rfp  # type: ignore

        section("STEP 1 — SETUP  (mirrors POST /api/v1/evaluate/start)")
        state: dict = {}
        await run_rfp(
            rfp_path=args.rfp,
            vendor_pdfs=args.vendor_pdf,
            criteria_path=args.criteria,
            state=state,
        )
        run_id = state["run_id"]
        org_id = state["org_id"]
        kv("run_id", run_id)
        kv("org_id", org_id)
        (out_dir / "run_id.txt").write_text(
            f"run_id={run_id}\norg_id={org_id}\n", encoding="utf-8")

        section("STEP 2 — CONFIRM  (mirrors POST /{run_id}/confirm)")
        _confirm_run(run_id, org_id)
        kv("rfp_confirmed", "True")
        kv("status",        "running")

        # ── 3. Build initial state (same shape as _run_pipeline) ──────────────
        section("STEP 3 — BUILDING INITIAL PIPELINE STATE")
        import sqlalchemy as sa
        from app.db.fact_store import get_engine
        from app.schemas.output_models import EvaluationSetup
        from app.domain.org_settings import get_org_settings
        from app.api._evaluation.db import _db_get_setup, _db_load_vendor_files
        from app.infra.cost_tracker import set_run_context, get_run_cost, clear_run_cost
        from app.infra.logger import rfp_logger
        from app.infra.audit import audit
        from app.api._evaluation.db import (
            _db_update_status, _db_append_event, _db_save_decision,
        )

        engine = get_engine()
        with engine.connect() as conn:
            row = conn.execute(sa.text("""
                SELECT rfp_id, rfp_title, department, rfp_filename,
                       rfp_bytes, vendor_ids, contract_value, setup_id,
                       currency
                FROM evaluation_runs WHERE run_id = CAST(:rid AS uuid)
            """), {"rid": run_id}).fetchone()
        if not row:
            raise RuntimeError("Run not found in DB after setup")

        setup_json = _db_get_setup(row[7])
        evaluation_setup = EvaluationSetup(**setup_json)
        org_settings = get_org_settings(org_id)
        vendor_file_map = _db_load_vendor_files(run_id)
        rfp_logger.start_run(run_id=run_id, org_id=org_id,
                             rfp_id=row[0], vendor_count=len(row[5] or []))
        cost_ctx = set_run_context(run_id=run_id, agent="pipeline")
        cost_ctx.__enter__()

        initial_state = {
            "run_id": run_id, "org_id": org_id, "rfp_id": row[0],
            "rfp_title": row[1], "rfp_filename": row[3] or "rfp.pdf",
            "rfp_bytes": bytes(row[4]) if row[4] else b"",
            "vendor_ids": list(row[5] or []),
            "contract_value": float(row[6] or 0),
            "currency": row[8] or "GBP",
            "setup_id": row[7],
            "n_vendors": len(row[5] or []),
            "evaluation_setup_dict": evaluation_setup.model_dump(mode="json"),
            "vendor_file_map": vendor_file_map,
            "org_settings": org_settings,
            "retrieval_output_objects": {}, "extraction_output_objects": {},
            "evaluation_output_objects": {}, "comparator_output": None,
            "decision_output": None, "explanation_output": None,
            "source_chunks": {}, "blocked": False, "blocked_agent": "",
            "error_message": "",
        }
        kv("vendor count",    initial_state["n_vendors"])
        kv("criteria count",  len(evaluation_setup.scoring_criteria))
        kv("mandatory checks",len(evaluation_setup.mandatory_checks))

        # ── 4. Drive the graph with verbose tracing ───────────────────────────
        final_state, node_trace = await drive_graph_verbose(
            evaluation_graph, initial_state, out_dir)

        # ── 5. Persist final outcome (mirror _run_pipeline tail) ──────────────
        if final_state.get("blocked"):
            try:
                _db_update_status(run_id, "blocked", completed=True)
            except Exception:
                pass
            audit(org_id=org_id, run_id=run_id, event_type="run.blocked",
                  actor="system", detail={"agent": final_state.get("blocked_agent"),
                                          "error": final_state.get("error_message")})
        else:
            dec_out = final_state.get("decision_output")
            if dec_out:
                _db_save_decision(run_id, dec_out.model_dump(mode="json"))
            _db_append_event(run_id, {
                "agent": "critic", "status": "done",
                "message": "All agent outputs validated by Critic",
                "log_msg": "Independent quality check complete.",
            })
            _db_update_status(run_id, "complete", completed=True)
            audit(org_id=org_id, run_id=run_id, event_type="run.completed",
                  actor="system", detail={})

        cost_ctx.__exit__(None, None, None)
        clear_run_cost(run_id)

        # ── 6. Save artifacts ─────────────────────────────────────────────────
        section("STEP 4 — SAVING ARTIFACTS")
        (out_dir / "final_state.json").write_text(
            json.dumps(_safe_dump(final_state), indent=2, default=str),
            encoding="utf-8")
        run = _read_run(run_id, org_id)
        (out_dir / "decision_output.json").write_text(
            json.dumps(run["decision_output"], indent=2, default=str),
            encoding="utf-8")
        (out_dir / "agent_events.json").write_text(
            json.dumps(run["agent_events"], indent=2, default=str),
            encoding="utf-8")
        kv("final_state.json",     "saved")
        kv("decision_output.json", "saved")
        kv("agent_events.json",    "saved")
        kv("node_diffs/",          f"{len(node_trace)} files saved")

        # ── 7. Verify ─────────────────────────────────────────────────────────
        section("STEP 5 — VERIFICATION")
        kv("final status",   run["status"])
        kv("completed_at",   run["completed_at"])
        kv("event count",    len(run["agent_events"]))
        kv("nodes executed", len(node_trace))

        print("\n  Node 'done' events from DB:")
        for ev in run["agent_events"]:
            if ev.get("status") == "done":
                print(f"    ✓ {ev.get('agent'):<12} — {ev.get('message','')[:60]}")
            elif ev.get("status") == "blocked":
                print(f"    ✗ {ev.get('agent'):<12} — BLOCKED: {ev.get('message','')[:60]}")

        failures = _verify_graph_executed(run, node_trace)

        section("RESULT")
        summary = {
            "started":      ts,
            "run_id":       run_id,
            "org_id":       org_id,
            "status":       run["status"],
            "completed_at": run["completed_at"],
            "nodes_executed":  [t["node"] for t in node_trace],
            "node_timings_s":  {t["node"]: t["elapsed_s"] for t in node_trace},
            "expected_nodes":  EXPECTED_NODES,
            "failures":     failures,
            "passed":       not failures,
        }
        # Phase 3 — cache observability
        cost_acc = get_run_cost(run_id)
        if cost_acc is not None:
            cs = cost_acc.summary()
            summary["cache"] = {
                "enabled":   os.getenv("LLM_CACHE_ENABLED", "true").lower() != "false",
                "hits":      cs["cache_hits"],
                "misses":    cs["cache_misses"],
                "hit_rate":  cs["cache_hit_rate"],
                "savings_usd": cs["cache_savings_usd"],
                "total_calls": cs["total_calls"],
                "total_cost_usd": cs["total_cost_usd"],
            }
        # Phase 2c — Critic-as-controller telemetry. final_state carries the
        # per-vendor {agent: {blocks, retries, retry_success, exhausted}} map
        # merged across the parallel branches. Roll it up so a smoke run shows
        # how often the self-correcting retry fired and recovered.
        summary["critic"] = _summarise_critic_metrics(
            final_state.get("critic_metrics_accum") or {})

        (out_dir / "summary.json").write_text(
            json.dumps(summary, indent=2, default=str), encoding="utf-8")

        # Phase 3 — byte-identity compare against a prior run dir, if requested.
        if getattr(args, "compare_with_prior", None):
            ok, msg = _compare_decision_outputs(out_dir, Path(args.compare_with_prior))
            (out_dir / "compare_with_prior.txt").write_text(msg, encoding="utf-8")
            if not ok:
                print(f"  [BYTE-IDENTITY FAIL] {msg}")
                failures.append(f"byte-identity vs prior: {msg}")
                summary["passed"] = False
                (out_dir / "summary.json").write_text(
                    json.dumps(summary, indent=2, default=str), encoding="utf-8")
            else:
                print(f"  [BYTE-IDENTITY PASS] {msg}")

        if failures:
            print("  [FAIL] LangGraph end-to-end smoke test failed:")
            for f in failures:
                print(f"    • {f}")
            print(f"\n  Artifacts: {out_dir}")
            return 1

        dec = run["decision_output"] or {}
        n_short = len(dec.get("shortlisted_vendors") or [])
        n_rej   = len(dec.get("rejected_vendors")    or [])
        print("  [OK] LangGraph end-to-end smoke test PASSED")
        print(f"       Shortlisted: {n_short}   Rejected: {n_rej}")
        print(f"       All {len(EXPECTED_NODES)} nodes ran via the StateGraph.")
        print(f"\n  Artifacts: {out_dir}")
        overall_ok = True
        return 0

    except Exception as exc:
        print(f"\n[ABORT] Unhandled error: {exc}")
        print(traceback.format_exc())
        (out_dir / "error.txt").write_text(
            f"{exc}\n\n{traceback.format_exc()}", encoding="utf-8")
        return 1
    finally:
        tee.close()
        if not overall_ok:
            print(f"\n  Partial artifacts saved to: {out_dir}", file=sys.stderr)


# ── Phase 3 — byte-identity comparison helper ────────────────────────

_VOLATILE_KEYS = {
    "run_id", "decision_id", "setup_id", "rfp_id",
    "explanation_id", "query_id",
    "created_at", "completed_at", "started_at", "ts", "timestamp",
    "decision_timestamp",
}


def _normalize_for_compare(obj):
    """Recursively masks volatile fields so SHA256 reflects decision content
    only — not run-specific identifiers or timestamps."""
    if isinstance(obj, dict):
        return {
            k: ("<masked>" if k in _VOLATILE_KEYS else _normalize_for_compare(v))
            for k, v in obj.items()
        }
    if isinstance(obj, list):
        return [_normalize_for_compare(x) for x in obj]
    return obj


def _compare_decision_outputs(this_dir, prior_dir) -> tuple[bool, str]:
    import hashlib
    this_path = this_dir / "decision_output.json"
    prior_path = prior_dir / "decision_output.json"
    if not prior_path.exists():
        return False, f"prior decision_output.json not found at {prior_path}"
    a = json.loads(this_path.read_text(encoding="utf-8"))
    b = json.loads(prior_path.read_text(encoding="utf-8"))
    a_norm = json.dumps(_normalize_for_compare(a), sort_keys=True)
    b_norm = json.dumps(_normalize_for_compare(b), sort_keys=True)
    a_sha = hashlib.sha256(a_norm.encode("utf-8")).hexdigest()
    b_sha = hashlib.sha256(b_norm.encode("utf-8")).hexdigest()
    if a_sha == b_sha:
        return True, f"SHA256 match (after masking): {a_sha[:16]}..."
    return False, f"SHA256 mismatch — this={a_sha[:16]}... prior={b_sha[:16]}..."


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--rfp",       required=True, help="Path to the RFP PDF")
    ap.add_argument("--vendor-pdf", action="append", required=True,
                    help="Path to a vendor proposal PDF (repeatable)")
    ap.add_argument("--criteria",  default=None,
                    help="Optional path to a criteria CSV/XLSX")
    # Phase 3 — cache controls
    ap.add_argument("--no-cache", action="store_true",
                    help="Disable the LLM response cache for this run "
                         "(sets LLM_CACHE_ENABLED=false in the process env).")
    ap.add_argument("--compare-with-prior", default=None, metavar="PRIOR_RUN_DIR",
                    help="After the smoke completes, normalize decision_output.json "
                         "and compare SHA256 against the prior run directory. "
                         "Fails if they differ (Phase 3 byte-identity check).")
    args = ap.parse_args()
    if args.no_cache:
        os.environ["LLM_CACHE_ENABLED"] = "false"
        print("[phase3] LLM cache DISABLED for this run (--no-cache)")
    sys.exit(asyncio.run(main_async(args)))


if __name__ == "__main__":
    main()
