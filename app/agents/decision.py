"""
Decision Agent — governance routing + vendor accept/reject.

Pipeline:
1. Identify rejected vendors (any FAIL compliance decision)
2. Shortlist remaining vendors ranked by total_weighted_score
3. Route to approval tier by contract value
4. Hard block if any rejection lacks evidence_citations
5. Hard block (escalate) if all vendors rejected
6. Critic check
"""
import uuid
from datetime import datetime, timedelta

from app.core.llm_provider import call_llm
from app.core.output_models import (
    DecisionOutput, RejectionNotice, ShortlistedVendor, ApprovalRouting,
    EvaluationOutput, ComparatorOutput, ComplianceStatus,
)
from app.agents.critic import critic_after_decision

# Default approval tiers — override via EvaluationSetup governance config if present.
# tier: int, approver_role: str, max_value: float|None, sla_hours: int
_DEFAULT_TIERS = [
    {"tier": 1, "approver_role": "department_head",  "max_value": 100_000,  "sla_hours": 24},
    {"tier": 2, "approver_role": "procurement_lead",  "max_value": 500_000,  "sla_hours": 48},
    {"tier": 3, "approver_role": "cfo",               "max_value": 1_000_000, "sla_hours": 72},
    {"tier": 4, "approver_role": "board",             "max_value": None,      "sla_hours": 120},
]

_RECOMMENDATION_MAP = [
    (8.0, "strongly_recommended"),
    (6.0, "recommended"),
    (4.0, "acceptable"),
    (0.0, "marginal"),
]


def route_to_approval_tier(contract_value: float) -> ApprovalRouting:
    tiers = sorted(_DEFAULT_TIERS, key=lambda t: t["max_value"] or float("inf"))
    for tier in tiers:
        max_val = tier["max_value"]
        if max_val is None or contract_value <= max_val:
            return ApprovalRouting(
                approval_tier=tier["tier"],
                approver_role=tier["approver_role"],
                contract_value=contract_value,
                sla_hours=tier["sla_hours"],
                sla_deadline=datetime.utcnow() + timedelta(hours=tier["sla_hours"]),
            )
    # Fallback — should never reach here given tier with max_value=None
    last = tiers[-1]
    return ApprovalRouting(
        approval_tier=last["tier"],
        approver_role=last["approver_role"],
        contract_value=contract_value,
        sla_hours=last["sla_hours"],
        sla_deadline=datetime.utcnow() + timedelta(hours=last["sla_hours"]),
    )


def _recommendation(score: float) -> str:
    for threshold, label in _RECOMMENDATION_MAP:
        if score >= threshold:
            return label
    return "marginal"


async def _build_rejection_notice(
    vendor_id: str,
    evaluation: EvaluationOutput,
) -> RejectionNotice:
    """
    Builds a RejectionNotice with evidence_citations populated from
    the compliance decisions that FAIL.
    """
    failed = [
        d for d in evaluation.compliance_decisions
        if d.decision == ComplianceStatus.FAIL
    ]

    failed_checks = [d.check_id for d in failed]
    rejection_reasons = [d.reasoning for d in failed]
    evidence_citations = [e for d in failed for e in d.evidence_used]
    clause_refs = [d.check_id for d in failed]

    # If evidence_citations is empty, ask LLM to derive from reasoning
    # (Critic will hard-block this if citations remain empty after this step)
    if not evidence_citations and failed:
        messages = [
            {
                "role": "system",
                "content": (
                    "Extract verbatim evidence phrases from these rejection reasons. "
                    "Return a JSON array of strings — exact quotes from the source. "
                    "Each string must be a verbatim phrase, not a summary.\n"
                    "Respond with only valid JSON, no prose."
                ),
            },
            {
                "role": "user",
                "content": "\n".join(rejection_reasons),
            },
        ]
        import json
        try:
            raw = await call_llm(messages, temperature=0.0,
                                 response_format={"type": "json_object"})
            parsed = json.loads(raw)
            if isinstance(parsed, list):
                evidence_citations = parsed
            elif isinstance(parsed, dict):
                evidence_citations = list(parsed.values())
        except Exception:
            evidence_citations = rejection_reasons[:3]

    return RejectionNotice(
        vendor_id=vendor_id,
        vendor_name=vendor_id,  # name not carried in EvaluationOutput — use id
        failed_checks=failed_checks,
        rejection_reasons=rejection_reasons,
        evidence_citations=evidence_citations,
        clause_references=clause_refs,
    )


async def run_decision_agent(
    evaluation_outputs: dict[str, EvaluationOutput],
    comparator_output: ComparatorOutput,
    contract_value: float = 500_000.0,
) -> tuple[DecisionOutput, object]:
    """
    evaluation_outputs: {vendor_id: EvaluationOutput}
    comparator_output:  ComparatorOutput from the Comparator Agent
    contract_value:     used for approval tier routing (GBP)
    """
    decision_id = str(uuid.uuid4())

    rejected_vendors = []
    shortlisted_vendors = []

    for vendor_id, evaluation in evaluation_outputs.items():
        has_fail = any(
            d.decision == ComplianceStatus.FAIL
            for d in evaluation.compliance_decisions
        )

        if has_fail:
            notice = await _build_rejection_notice(vendor_id, evaluation)
            rejected_vendors.append(notice)
        else:
            shortlisted_vendors.append((vendor_id, evaluation))

    # Rank shortlisted vendors using comparator overall_ranking order
    ranked_order = comparator_output.overall_ranking
    shortlisted_sorted = sorted(
        shortlisted_vendors,
        key=lambda x: ranked_order.index(x[0]) if x[0] in ranked_order else 999,
    )

    shortlisted = []
    for rank, (vendor_id, evaluation) in enumerate(shortlisted_sorted, start=1):
        # Look up per-criterion scores from comparator for breakdown
        criterion_scores = evaluation.criterion_scores
        rec = _recommendation(evaluation.total_weighted_score)

        shortlisted.append(
            ShortlistedVendor(
                vendor_id=vendor_id,
                vendor_name=vendor_id,
                rank=rank,
                total_score=evaluation.total_weighted_score,
                score_confidence=evaluation.score_confidence,
                criterion_breakdown=criterion_scores,
                recommendation=rec,
            )
        )

    approval_routing = route_to_approval_tier(contract_value)

    # All-vendors-rejected: escalate
    requires_review = len(shortlisted) == 0 and len(rejected_vendors) > 0
    review_reasons = []
    if requires_review:
        review_reasons.append(
            "All vendors rejected — mandatory requirements may be too restrictive. "
            "Escalate to procurement team for review."
        )
        approval_routing.escalation_reason = review_reasons[0]

    output = DecisionOutput(
        decision_id=decision_id,
        rfp_id=comparator_output.rfp_id,
        rejected_vendors=rejected_vendors,
        shortlisted_vendors=shortlisted,
        approval_routing=approval_routing,
        decision_confidence=comparator_output.ranking_confidence,
        requires_human_review=requires_review,
        review_reasons=review_reasons,
    )

    return output, critic_after_decision(output)
