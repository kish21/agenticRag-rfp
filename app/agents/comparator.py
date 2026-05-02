"""
Comparator Agent — SQL-join cross-vendor ranking from PostgreSQL facts.

Key rule: this is a structured data operation, not a retrieval operation.
Vendors are ranked from PostgreSQL facts and typed EvaluationOutputs, not from Qdrant chunks.
"""
import json
import uuid

from app.core.llm_provider import call_llm
from app.core.output_models import (
    ComparatorOutput,
    CriterionComparison,
    EvaluationOutput,
    EvaluationSetup,
    VendorCriterionComparison,
)
from app.agents.critic import critic_after_comparator
from app.db.fact_store import get_vendor_facts


def _relative_position(rank: int, total: int) -> str:
    if total == 1:
        return "best"
    if rank == 1:
        return "best"
    if rank == total:
        return "weakest"
    mid = total / 2
    if rank < mid:
        return "above_average"
    if rank > mid:
        return "below_average"
    return "average"


def _rank_is_stable(scores: list[tuple[str, float]], margin_threshold: float = 0.05) -> bool:
    """Returns False if any two adjacent-ranked vendors have scores within margin_threshold."""
    if len(scores) <= 1:
        return True
    sorted_scores = sorted(scores, key=lambda x: x[1], reverse=True)
    for i in range(len(sorted_scores) - 1):
        margin = sorted_scores[i][1] - sorted_scores[i + 1][1]
        if margin < margin_threshold:
            return False
    return True


async def _compare_criterion(
    criterion_id: str,
    criterion_name: str,
    weight: float,
    rubric: str,
    vendor_scores: dict[str, int],
    vendor_evidences: dict[str, list[str]],
) -> CriterionComparison:
    scores_text = "\n".join(
        f"  {vid}: {score}/10 — evidence: {vendor_evidences.get(vid, [])}"
        for vid, score in vendor_scores.items()
    )
    messages = [
        {
            "role": "system",
            "content": (
                "You are a procurement comparator. Compare vendors on this criterion "
                "based only on the scores and evidence provided. Identify what differentiates them.\n"
                "Return only valid JSON."
            ),
        },
        {
            "role": "user",
            "content": (
                f"Criterion: {criterion_name} (weight: {weight:.0%})\n"
                f"Rubric summary: {rubric}\n\n"
                f"Vendor scores:\n{scores_text}\n\n"
                "For each vendor provide a key_differentiator (one phrase).\n"
                "Return JSON:\n"
                '{"vendor_differentiators": {"vendor_id": "key differentiator phrase"}, '
                '"distinguishing_factors": "one sentence on what separates top from bottom", '
                '"comparison_confidence": 0.0}'
            ),
        },
    ]
    raw = await call_llm(messages, temperature=0.0, response_format={"type": "json_object"})
    parsed = json.loads(raw)

    differentiators: dict[str, str] = parsed.get("vendor_differentiators", {})
    score_pairs = list(vendor_scores.items())
    sorted_vendors = sorted(score_pairs, key=lambda x: x[1], reverse=True)
    rank_map = {vid: rank + 1 for rank, (vid, _) in enumerate(sorted_vendors)}

    vendor_comparisons = [
        VendorCriterionComparison(
            criterion_id=criterion_id,
            vendor_id=vid,
            score=score,
            key_differentiator=differentiators.get(vid, ""),
            relative_position=_relative_position(rank_map[vid], len(vendor_scores)),
            evidence_summary="; ".join(vendor_evidences.get(vid, [])[:2]),
        )
        for vid, score in vendor_scores.items()
    ]

    stable = _rank_is_stable(score_pairs)

    return CriterionComparison(
        criterion_id=criterion_id,
        criterion_name=criterion_name,
        weight=weight,
        vendors=vendor_comparisons,
        comparison_confidence=float(parsed.get("comparison_confidence", 0.7)),
        rank_stable=stable,
        distinguishing_factors=parsed.get("distinguishing_factors", ""),
    )


async def run_comparator_agent(
    vendor_ids: list[str],
    org_id: str,
    rfp_id: str,
    evaluation_setup: EvaluationSetup,
    evaluation_outputs: dict[str, EvaluationOutput],
) -> tuple[ComparatorOutput, object]:
    comparison_id = str(uuid.uuid4())
    warnings: list[str] = []

    # Get all vendors' facts from PostgreSQL in one pass
    all_facts = {
        vid: get_vendor_facts(org_id, vid, setup_id=evaluation_setup.setup_id)
        for vid in vendor_ids
    }

    # Build score lookup: {vendor_id: {criterion_id: CriterionScore}}
    score_lookup: dict[str, dict[str, object]] = {
        vid: {s.criterion_id: s for s in ev.criterion_scores}
        for vid, ev in evaluation_outputs.items()
    }

    # Compare criterion by criterion
    criteria_comparisons: list[CriterionComparison] = []
    for criterion in evaluation_setup.scoring_criteria:
        vendor_scores: dict[str, int] = {}
        vendor_evidences: dict[str, list[str]] = {}

        for vid in vendor_ids:
            cs = score_lookup.get(vid, {}).get(criterion.criterion_id)
            if cs:
                vendor_scores[vid] = cs.raw_score
                vendor_evidences[vid] = cs.evidence_used
            else:
                vendor_scores[vid] = 0
                vendor_evidences[vid] = []
                warnings.append(f"No score for vendor {vid} on criterion {criterion.criterion_id}")

        rubric_summary = criterion.rubric_9_10[:80]
        try:
            comparison = await _compare_criterion(
                criterion.criterion_id,
                criterion.name,
                criterion.weight,
                rubric_summary,
                vendor_scores,
                vendor_evidences,
            )
            criteria_comparisons.append(comparison)
        except Exception as e:
            warnings.append(f"Criterion {criterion.criterion_id} comparison failed: {e}")

    # Overall ranking by total_weighted_score (deterministic SQL-style sort)
    vendor_totals = {
        vid: ev.total_weighted_score
        for vid, ev in evaluation_outputs.items()
        if vid in vendor_ids
    }
    overall_ranking = [
        vid for vid, _ in sorted(vendor_totals.items(), key=lambda x: x[1], reverse=True)
    ]

    # Rank margins: score gap between each vendor and the one ranked above it
    rank_margins: dict[str, float] = {}
    for i, vid in enumerate(overall_ranking):
        if i == 0:
            rank_margins[vid] = 0.0
        else:
            rank_margins[vid] = round(
                vendor_totals[overall_ranking[i - 1]] - vendor_totals[vid], 4
            )

    avg_comparison_confidence = (
        round(
            sum(cc.comparison_confidence for cc in criteria_comparisons)
            / len(criteria_comparisons),
            3,
        )
        if criteria_comparisons else 0.0
    )

    output = ComparatorOutput(
        comparison_id=comparison_id,
        rfp_id=rfp_id,
        vendor_ids=vendor_ids,
        criteria_comparisons=criteria_comparisons,
        overall_ranking=overall_ranking,
        ranking_confidence=avg_comparison_confidence,
        rank_margins=rank_margins,
        comparison_warnings=warnings,
    )

    critic = critic_after_comparator(output)
    return output, critic
