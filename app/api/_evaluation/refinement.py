"""Background LLM task: refine EvaluationSetup after /start returns."""
import json
import logging

import sqlalchemy as sa

from app.db.fact_store import save_evaluation_setup, get_engine

_log = logging.getLogger(__name__)


async def _refine_setup_with_llm(
    setup_id: str,
    rfp_text: str,
    org_criteria: dict,
    dept_criteria: dict,
    department: str,
    rfp_id: str,
    org_id: str,
    user_criteria: dict | None = None,
) -> None:
    """
    Runs after /start returns. Calls the LLM to extract RFP-specific criteria
    and overwrites the default setup in the DB. The confirm page shows defaults
    until this completes, then refreshes with LLM-extracted criteria.
    """
    # Lazy import: app.domain.criteria imports app.providers.llm which triggers
    # model loading — deferred to avoid slowing down the initial server startup.
    from app.domain.criteria import extract_criteria_from_rfp, merge_criteria

    try:
        rfp_criteria = await extract_criteria_from_rfp(rfp_text)
        merged = merge_criteria(
            org_criteria=org_criteria,
            dept_criteria=dept_criteria,
            rfp_criteria=rfp_criteria,
            department=department,
            rfp_id=rfp_id,
            org_id=org_id,
            user_criteria=user_criteria,
        )
        if not merged["mandatory_checks"] and not merged["scoring_criteria"]:
            return  # nothing better than defaults — leave as-is

        engine = get_engine()
        with engine.connect() as conn:
            row = conn.execute(
                sa.text("SELECT setup_json FROM evaluation_setups WHERE setup_id = :sid"),
                {"sid": setup_id},
            ).fetchone()
        if not row:
            return

        existing = json.loads(row[0]) if isinstance(row[0], str) else row[0]
        if merged["mandatory_checks"]:
            existing["mandatory_checks"] = [
                m if isinstance(m, dict) else m.model_dump() for m in merged["mandatory_checks"]
            ]
        if merged["scoring_criteria"]:
            existing["scoring_criteria"] = [
                c if isinstance(c, dict) else c.model_dump() for c in merged["scoring_criteria"]
            ]
        if merged.get("extraction_targets"):
            existing["extraction_targets"] = [
                t if isinstance(t, dict) else t.model_dump() for t in merged["extraction_targets"]
            ]
        else:
            # Auto-create a minimal ExtractionTarget for every mandatory check
            # whose extraction_target_id has no matching entry in extraction_targets
            existing_target_ids = {t["target_id"] for t in existing.get("extraction_targets", [])}
            for mc in existing.get("mandatory_checks", []):
                mc = mc if isinstance(mc, dict) else mc.model_dump()
                et_id = mc.get("extraction_target_id")
                if et_id and et_id not in existing_target_ids:
                    existing.setdefault("extraction_targets", []).append({
                        "target_id": et_id,
                        "name": mc.get("name", et_id),
                        "description": mc.get("description", ""),
                        "fact_type": "certification",
                        "is_mandatory": True,
                        "feeds_check_id": mc.get("check_id", ""),
                    })
                    existing_target_ids.add(et_id)
        existing["source"] = merged.get("source", "llm_refined")
        save_evaluation_setup(existing, org_id=org_id)
    except Exception as e:
        _log.warning(f"LLM criteria refinement failed for {setup_id}: {e}")
