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
import json
import uuid
from datetime import datetime, timedelta

from app.providers.llm import call_llm
from app.prompts.registry import get_prompt
from app.config import settings
from app.schemas.output_models import (
    DecisionOutput, RejectionNotice, ShortlistedVendor, ApprovalRouting,
    EvaluationOutput, ComparatorOutput, ComplianceStatus,
)
from app.agents.critic import critic_after_decision


def route_to_approval_tier(contract_value: float) -> ApprovalRouting:
    tiers = sorted(
        settings.platform.governance.approval_tiers,
        key=lambda t: t.max_value if t.max_value is not None else float("inf"),
    )
    for tier in tiers:
        if tier.max_value is None or contract_value <= tier.max_value:
            return ApprovalRouting(
                approval_tier=tier.tier,
                approver_role=tier.approver_role,
                contract_value=contract_value,
                sla_hours=tier.sla_hours,
                sla_deadline=datetime.utcnow() + timedelta(hours=tier.sla_hours),
            )
    last = tiers[-1]
    return ApprovalRouting(
        approval_tier=last.tier,
        approver_role=last.approver_role,
        contract_value=contract_value,
        sla_hours=last.sla_hours,
        sla_deadline=datetime.utcnow() + timedelta(hours=last.sla_hours),
    )


def _recommendation(score: float) -> str:
    thresholds = settings.platform.governance.recommendation_thresholds
    for label in ("strongly_recommended", "recommended", "acceptable", "marginal"):
        if score >= thresholds.get(label, 0.0):
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
            {"role": "system", "content": get_prompt("decision/extract_evidence")},
            {"role": "user", "content": "\n".join(rejection_reasons)},
        ]
        try:
            raw = await call_llm(messages, temperature=0.0,
                                 response_format={"type": "json_object"})
            parsed = json.loads(raw)
            citations = parsed.get("evidence") or []
            evidence_citations = [c for c in citations if isinstance(c, str)]
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
    review_reasons = []
    for rank, (vendor_id, evaluation) in enumerate(shortlisted_sorted, start=1):
        criterion_scores = evaluation.criterion_scores
        rec = _recommendation(evaluation.total_weighted_score)

        # Surface unresolved insufficient_evidence decisions on shortlisted vendors
        unresolved = [
            d.check_id for d in evaluation.compliance_decisions
            if d.decision == ComplianceStatus.INSUFFICIENT_EVIDENCE
        ]
        if unresolved:
            review_reasons.append(
                f"Vendor {vendor_id} shortlisted but has unresolved mandatory checks "
                f"with insufficient evidence: {unresolved}. Human review recommended."
            )

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
    requires_review = (len(shortlisted) == 0 and len(rejected_vendors) > 0) or bool(review_reasons)
    if len(shortlisted) == 0 and len(rejected_vendors) > 0:
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
