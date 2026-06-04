"""
Adapter between the live pipeline and the benchmark.

Two layers, deliberately separated:

  * state_to_actual(...)  — PURE: maps a finished pipeline `final_state` (plain
    dict of Pydantic models or dicts) into an `ActualScenario`. No DB/LLM/IO, so
    it is unit-tested in CI (tests/test_benchmark_metrics.py).
  * run_scenario(...)     — IMPURE: provisions a throw-away org, seeds the run +
    vendor docs + fixed setup, drives the graph, then calls state_to_actual.
    This is the only code that spends API budget.
"""
from __future__ import annotations

import hashlib
import uuid
from pathlib import Path
from typing import Optional

from benchmark.golden_schema import ScenarioGolden
from benchmark.metrics.actuals import (
    ActualComplianceDecision, ActualCriterionScore, ActualFact, ActualScenario, ActualVendor,
)

# Field subsets that the golden key_fields may reference, per fact type.
_TYPED_FIELDS = {
    "certifications": ("certification",
        ["standard_name", "version", "cert_number", "issuing_body", "scope", "valid_until", "status"]),
    "insurance": ("insurance", ["insurance_type", "amount", "amount_gbp", "provider"]),
    "slas": ("sla", ["priority_level", "response_minutes", "resolution_hours", "uptime_percentage"]),
    "projects": ("project", ["client_name", "client_sector", "user_count", "outcomes", "reference_available"]),
    "pricing": ("pricing", ["year", "amount", "total_amount", "description"]),
}


def _get(obj, attr, default=None):
    """Read attr whether obj is a Pydantic model or a dict."""
    if obj is None:
        return default
    if isinstance(obj, dict):
        return obj.get(attr, default)
    return getattr(obj, attr, default)


def _scalar(v):
    """Coerce enums/dates to comparable scalars."""
    if v is None:
        return None
    if hasattr(v, "value"):          # enum
        return v.value
    if hasattr(v, "isoformat"):      # date/datetime
        return v.isoformat()
    return v


def _facts_from_extraction(extraction) -> list[ActualFact]:
    facts: list[ActualFact] = []
    for list_attr, (fact_type, fields) in _TYPED_FIELDS.items():
        for item in (_get(extraction, list_attr, []) or []):
            facts.append(ActualFact(
                fact_type=fact_type,
                fields={f: _scalar(_get(item, f)) for f in fields if _get(item, f) is not None},
                grounding_quote=_get(item, "grounding_quote", "") or "",
                source_chunk_id=_get(item, "source_chunk_id", "") or "",
                confidence=float(_get(item, "confidence", 0.0) or 0.0),
            ))
    for f in (_get(extraction, "extracted_facts", []) or []):
        facts.append(ActualFact(
            fact_type=_get(f, "fact_type", "custom") or "custom",
            fields={_get(f, "fact_name", "value"): _scalar(
                _get(f, "numeric_value") if _get(f, "numeric_value") is not None
                else _get(f, "text_value"))},
            grounding_quote=_get(f, "grounding_quote", "") or "",
            source_chunk_id=_get(f, "source_chunk_id", "") or "",
            confidence=float(_get(f, "confidence", 0.0) or 0.0),
        ))
    return facts


def _retrieved_texts(retrieval_obj) -> list[str]:
    """Collect chunk texts from whatever shape retrieval output takes for a vendor."""
    texts: list[str] = []

    def walk(node):
        if node is None:
            return
        chunks = _get(node, "chunks", None)
        if chunks is not None:                       # a RetrievalOutput
            for c in chunks:
                t = _get(c, "text", "")
                if t:
                    texts.append(t)
            return
        if isinstance(node, dict):
            for v in node.values():
                walk(v)
        elif isinstance(node, (list, tuple)):
            for v in node:
                walk(v)

    walk(retrieval_obj)
    return texts


def _criterion_scores(evaluation) -> list[ActualCriterionScore]:
    out = []
    for cs in (_get(evaluation, "criterion_scores", []) or []):
        out.append(ActualCriterionScore(
            criterion_id=_get(cs, "criterion_id", ""),
            raw_score=_get(cs, "raw_score"),
            confidence=float(_get(cs, "confidence", 0.0) or 0.0),
            # E3 no-forced-score flag (Stage 4 sets this on the schema). Until then
            # it is absent → False, which is exactly what the baseline should show.
            insufficient=bool(_get(cs, "insufficient_evidence", False)),
        ))
    return out


def _compliance(evaluation) -> list[ActualComplianceDecision]:
    out = []
    for d in (_get(evaluation, "compliance_decisions", []) or []):
        out.append(ActualComplianceDecision(
            check_id=_get(d, "check_id", ""),
            decision=str(_scalar(_get(d, "decision", ""))),
            confidence=float(_get(d, "confidence", 0.0) or 0.0),
        ))
    return out


def state_to_actual(
    golden: ScenarioGolden,
    final_state: dict,
    vendor_source_texts: dict[str, str],
    node_timings_s: Optional[dict] = None,
    cost: Optional[dict] = None,
) -> ActualScenario:
    """PURE: map a finished pipeline state to an ActualScenario for the metrics."""
    extraction = final_state.get("extraction_output_objects", {}) or {}
    evaluation = final_state.get("evaluation_output_objects", {}) or {}
    retrieval = final_state.get("retrieval_output_objects", {}) or {}
    decision = final_state.get("decision_output")
    rejected_ids = {_get(r, "vendor_id") for r in (_get(decision, "rejected_vendors", []) or [])}

    # E3.b.2 — a vendor whose stage was critic-blocked / failed lands here (NOT in the
    # *_output_objects), keyed by vendor_id. First entry per vendor = originating failure.
    blocked: dict[str, dict] = {}
    for f in (final_state.get("failed_vendors", []) or []):
        vid = _get(f, "vendor_id")
        if vid and vid not in blocked:
            blocked[vid] = {"stage": _get(f, "stage", "") or "", "error": _get(f, "error", "") or ""}

    vendors: list[ActualVendor] = []
    for ev in golden.vendors:
        vid = ev.vendor_id
        b = blocked.get(vid)
        vendors.append(ActualVendor(
            vendor_id=vid,
            source_text=vendor_source_texts.get(vid, ""),
            retrieved_texts=_retrieved_texts(retrieval.get(vid)),
            facts=_facts_from_extraction(extraction.get(vid)),
            criterion_scores=_criterion_scores(evaluation.get(vid)),
            compliance_decisions=_compliance(evaluation.get(vid)),
            rejected=vid in rejected_ids,
            blocked_stage=(b["stage"] or "unknown") if b else None,
            blocked_error=b["error"] if b else "",
        ))

    return ActualScenario(
        scenario_id=golden.scenario_id,
        vendors=vendors,
        node_timings_s=node_timings_s or {},
        cost=cost or {},
        blocked=bool(final_state.get("blocked")),
        blocked_agent=final_state.get("blocked_agent", "") or "",
        error=final_state.get("error_message", "") or "",
    )


def _seed_org_settings(org_id: str, reranker_provider: str) -> None:
    """Write an org_settings row for the throw-away benchmark org so retrieval
    honours the configured reranker (E3.e).

    Reuses the one org_settings write path (`upsert_org_settings`) with
    `apply_preset=False` to write exactly this field. Scoped to the benchmark org
    only. (Since #212 a defaulted org already resolves reranker_provider from
    .env via `_defaults_for`, so this explicit seed is now belt-and-braces — it
    pins the value on a real row regardless of default-resolution changes.)
    """
    from app.domain.org_settings import upsert_org_settings
    upsert_org_settings(org_id, updated_by="benchmark", apply_preset=False,
                        reranker_provider=reranker_provider)


# ── Impure: run one scenario through the real pipeline ────────────────────────

def run_scenario(scenario_dir: Path, golden: ScenarioGolden, *, repeats: int = 1) -> ActualScenario:
    """Provision a throw-away org, run the pipeline, and return an ActualScenario.

    Spends API budget. Cleans up its org (DB cascade + Qdrant collection) afterwards.
    `repeats` (>1) re-runs scoring to populate score-consistency samples.
    """
    import sqlalchemy as sa

    from app.config import settings
    from app.db.fact_store import get_admin_engine, get_engine, save_evaluation_setup
    from app.db.session import org_context
    from app.domain.criteria import extract_rfp_text
    from app.domain.org_settings import get_org_settings
    from app.infra.cost_tracker import set_run_context, get_run_cost, clear_run_cost
    from app.pipeline.graph import evaluation_graph
    from app.schemas.output_models import EvaluationSetup

    org_id = str(uuid.uuid4())
    run_id = str(uuid.uuid4())
    rfp_id = f"rfp-{run_id[:8]}"
    setup_id = f"setup-{run_id[:8]}"

    setup = EvaluationSetup.model_validate_json((scenario_dir / golden.setup_json).read_text(encoding="utf-8"))
    setup = setup.model_copy(update={"org_id": org_id, "rfp_id": rfp_id, "setup_id": setup_id})

    rfp_bytes = (scenario_dir / golden.rfp_pdf).read_bytes()
    vendor_source_texts: dict[str, str] = {}
    vendor_rows = []
    for v in golden.vendors:
        vb = (scenario_dir / v.vendor_pdf).read_bytes()
        vendor_source_texts[v.vendor_id] = extract_rfp_text(vb)
        vendor_rows.append((v.vendor_id, v.vendor_pdf, vb))

    admin = get_admin_engine()
    with admin.begin() as c:
        c.execute(sa.text(
            "INSERT INTO organisations (org_id, org_name, industry, subscription_tier, is_active) "
            "VALUES (CAST(:o AS uuid), :n, 'Benchmark', 'trial', TRUE) ON CONFLICT DO NOTHING"),
            {"o": org_id, "n": f"bench-{org_id[:8]}"})
        c.execute(sa.text(
            "INSERT INTO tenant_modules (org_id, module_key, enabled, activated_at) "
            "VALUES (CAST(:o AS uuid), 'rfp_evaluation', TRUE, now()) ON CONFLICT DO NOTHING"),
            {"o": org_id})

    try:
        with org_context(org_id):
            save_evaluation_setup(setup.model_dump(mode="json"), org_id=org_id)
            # E3.e — make the benchmark honour RERANKER_PROVIDER from .env. The
            # throw-away org otherwise has no org_settings row, so retrieval reads
            # the product default (`bge`) and the explicit provider= argument wins
            # over the global setting — silently measuring un-reranked retrieval on
            # a no-HF-egress box. Seed this org's setting from settings.reranker_provider.
            _seed_org_settings(org_id, settings.reranker_provider)
            engine = get_engine()
            with engine.begin() as conn:
                conn.execute(sa.text("""
                    INSERT INTO evaluation_runs
                        (run_id, org_id, rfp_id, setup_id, rfp_title, department, rfp_filename,
                         rfp_bytes, status, vendor_ids, contract_value, vendor_names,
                         created_by_email, creator_dept_id, currency)
                    VALUES (CAST(:run_id AS uuid), CAST(:org_id AS uuid), :rfp_id, :setup_id,
                            :title, :dept, :fname, :rfp_bytes, 'running', :vids, :cval,
                            CAST('{}' AS jsonb), :email, NULL, 'GBP')
                """), {"run_id": run_id, "org_id": org_id, "rfp_id": rfp_id, "setup_id": setup_id,
                       "title": golden.title, "dept": "Procurement", "fname": golden.rfp_pdf,
                       "rfp_bytes": rfp_bytes, "vids": [v[0] for v in vendor_rows],
                       "cval": 1000000.0, "email": "benchmark@local"})
                for vid, vfname, vb in vendor_rows:
                    conn.execute(sa.text("""
                        INSERT INTO vendor_documents
                            (org_id, vendor_id, rfp_id, setup_id, filename, file_name,
                             file_bytes, content_hash)
                        VALUES (CAST(:o AS uuid), :vid, :rfp_id, :setup_id, :fn, :fn,
                                :fb, :h) ON CONFLICT (org_id, vendor_id, rfp_id, content_hash) DO NOTHING
                    """), {"o": org_id, "vid": vid, "rfp_id": rfp_id, "setup_id": setup_id,
                           "fn": vfname, "fb": vb, "h": hashlib.sha256(vb).hexdigest()})

            from app.api._evaluation.db import _db_load_vendor_files
            initial_state = {
                "run_id": run_id, "org_id": org_id, "rfp_id": rfp_id,
                "rfp_title": golden.title, "rfp_filename": golden.rfp_pdf, "rfp_bytes": rfp_bytes,
                "vendor_ids": [v[0] for v in vendor_rows], "contract_value": 1000000.0,
                "currency": "GBP", "setup_id": setup_id, "n_vendors": len(vendor_rows),
                "evaluation_setup_dict": setup.model_dump(mode="json"),
                "vendor_file_map": _db_load_vendor_files(run_id),
                "org_settings": get_org_settings(org_id),
                "retrieval_output_objects": {}, "extraction_output_objects": {},
                "evaluation_output_objects": {}, "comparator_output": None,
                "decision_output": None, "explanation_output": None,
                "source_chunks": {}, "blocked": False, "blocked_agent": "", "error_message": "",
            }

            import asyncio
            timings: dict = {}
            cost_ctx = set_run_context(run_id=run_id, agent="pipeline")
            cost_ctx.__enter__()
            try:
                final_state = asyncio.run(_timed_run(evaluation_graph, initial_state, timings))
                cost = get_run_cost(run_id).summary() if get_run_cost(run_id) else {}
            finally:
                cost_ctx.__exit__(None, None, None)
                clear_run_cost(run_id)

            actual = state_to_actual(golden, final_state, vendor_source_texts, timings, cost)

            # Optional repeat runs to populate scoring-consistency samples.
            if repeats > 1:
                _add_repeat_scores(actual, golden, initial_state, evaluation_graph, repeats - 1)
            return actual
    finally:
        _cleanup(org_id, settings)


async def _timed_run(graph, initial_state, timings: dict) -> dict:
    import time
    merged = dict(initial_state)
    last = time.time()
    async for diff in graph.astream(initial_state, {"recursion_limit": 50}):
        now = time.time()
        for node, payload in diff.items():
            timings[node] = round(timings.get(node, 0.0) + (now - last), 4)
            if isinstance(payload, dict):
                merged.update(payload)
        last = now
    return merged


def _add_repeat_scores(actual: ActualScenario, golden, initial_state, graph, extra: int) -> None:
    """Re-run the graph `extra` times and collect per-criterion score samples
    (plus the first run already in actual) so variance has ≥2 samples."""
    import asyncio

    # Seed with the first (already-completed) run's scores.
    for av in actual.vendors:
        for cs in av.criterion_scores:
            if cs.raw_score is not None:
                av.repeat_scores.setdefault(cs.criterion_id, []).append(cs.raw_score)

    for _ in range(extra):
        fs = asyncio.run(_timed_run(graph, dict(initial_state), {}))
        ev = fs.get("evaluation_output_objects", {}) or {}
        for av in actual.vendors:
            for cs in _criterion_scores(ev.get(av.vendor_id)):
                if cs.raw_score is not None:
                    av.repeat_scores.setdefault(cs.criterion_id, []).append(cs.raw_score)


def _cleanup(org_id: str, settings) -> None:
    import sqlalchemy as sa
    from app.db.fact_store import get_admin_engine
    try:
        with get_admin_engine().begin() as c:
            c.execute(sa.text("DELETE FROM organisations WHERE org_id = CAST(:o AS uuid)"), {"o": org_id})
    except Exception:
        pass
    try:
        from qdrant_client import QdrantClient
        QdrantClient(host=settings.qdrant_host, port=settings.qdrant_port).delete_collection(
            f"{settings.qdrant_collection_prefix}_{org_id}")
    except Exception:
        pass
