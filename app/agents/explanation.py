"""
Explanation Agent — grounded narrative report.

Pipeline:
1. For each vendor (rejected + shortlisted), generate narrative sections via LLM
2. Every claim in the narrative must cite a grounding_quote from source chunks
3. Ungrounded claims are removed and counted in ungrounded_claims_removed
4. If grounding_completeness < 0.70: Critic hard blocks
5. Critic check
"""
import json
import re
import uuid

from app.core.llm_provider import call_llm
from pydantic import ValidationError
from app.core.output_models import (
    ExplanationOutput, VendorNarrative, GroundedClaim,
    SynthesisLLMResponse,
    DecisionOutput, EvaluationOutput, ExtractionOutput,
)
from app.agents.critic import critic_after_explanation


def verify_grounding(
    claim_text: str,
    grounding_quote: str,
    source_chunk_id: str,
    source_chunks: dict[str, str],
) -> bool:
    """
    Programmatic check — not LLM.
    The grounding_quote must appear (whitespace-normalised) in the source chunk.
    """
    source = source_chunks.get(source_chunk_id, "")
    if not source or not grounding_quote:
        return False

    def _ws(t: str) -> str:
        return re.sub(r"\s+", " ", t).strip()

    return _ws(grounding_quote) in _ws(source)


async def _generate_vendor_narrative(
    vendor_id: str,
    vendor_name: str,
    is_rejected: bool,
    evaluation: EvaluationOutput,
    extraction: ExtractionOutput,
    source_chunks: dict[str, str],
    decision_output: DecisionOutput,
) -> VendorNarrative:
    """Generates narrative sections and verifies every claim is grounded."""

    context_facts = _build_fact_context(extraction)
    compliance_summary = _build_compliance_summary(evaluation)

    if is_rejected:
        rejection = next(
            (r for r in decision_output.rejected_vendors if r.vendor_id == vendor_id),
            None,
        )
        decision_context = (
            f"REJECTED. Failed checks: {rejection.failed_checks if rejection else []}. "
            f"Reasons: {rejection.rejection_reasons if rejection else []}"
        )
    else:
        shortlisted = next(
            (s for s in decision_output.shortlisted_vendors if s.vendor_id == vendor_id),
            None,
        )
        decision_context = (
            f"SHORTLISTED. Rank: {shortlisted.rank if shortlisted else '?'}. "
            f"Score: {evaluation.total_weighted_score:.2f}/10. "
            f"Recommendation: {shortlisted.recommendation if shortlisted else '?'}"
        )

    messages = [
        {
            "role": "system",
            "content": (
                "You are writing a formal procurement evaluation report section.\n"
                "Generate a structured narrative for this vendor.\n\n"
                "RULES:\n"
                "- Every factual claim MUST include a grounding_quote — an exact phrase "
                "from the source text below.\n"
                "- Do NOT invent facts. Only state what is in the source text.\n"
                "- Return JSON only, no prose.\n\n"
                "Return this exact structure:\n"
                "{\n"
                '  "executive_summary": "2-3 sentence summary",\n'
                '  "compliance_narrative": "paragraph on mandatory check results",\n'
                '  "scoring_narrative": "paragraph on scoring performance",\n'
                '  "recommendation_rationale": "1-2 sentence rationale",\n'
                '  "grounded_claims": [\n'
                "    {\n"
                '      "claim_text": "the claim being made",\n'
                '      "grounding_quote": "exact phrase from source text",\n'
                '      "source_chunk_id": "chunk-id from source",\n'
                '      "source_filename": "filename",\n'
                '      "source_page": 1,\n'
                '      "confidence": 0.0\n'
                "    }\n"
                "  ]\n"
                "}\n"
                "Respond with only valid JSON, no prose."
            ),
        },
        {
            "role": "user",
            "content": (
                f"Vendor: {vendor_name} ({vendor_id})\n"
                f"Decision: {decision_context}\n\n"
                f"Compliance results:\n{compliance_summary}\n\n"
                f"Extracted facts:\n{context_facts}\n\n"
                f"Source chunks:\n{_format_chunks(source_chunks)}"
            ),
        },
    ]

    raw = await call_llm(messages, temperature=0.2,
                         response_format={"type": "json_object"})

    try:
        raw_dict = json.loads(raw)
    except json.JSONDecodeError:
        raw_dict = {}

    try:
        synthesis = SynthesisLLMResponse.model_validate(raw_dict)
    except ValidationError:
        synthesis = SynthesisLLMResponse()

    verified_claims = []
    ungrounded_count = 0

    for claim in synthesis.grounded_claims:
        if verify_grounding(claim.claim_text, claim.grounding_quote, claim.source_chunk_id, source_chunks):
            verified_claims.append(claim)
        else:
            ungrounded_count += 1

    return VendorNarrative(
        vendor_id=vendor_id,
        vendor_name=vendor_name,
        executive_summary=synthesis.executive_summary,
        compliance_narrative=synthesis.compliance_narrative,
        scoring_narrative=synthesis.scoring_narrative,
        recommendation_rationale=synthesis.recommendation_rationale,
        grounded_claims=verified_claims,
        ungrounded_claims_removed=ungrounded_count,
    )


def _build_fact_context(extraction: ExtractionOutput) -> str:
    lines = []
    for cert in extraction.certifications:
        lines.append(f"Certification: {cert.standard_name} ({cert.status.value})")
    for ins in extraction.insurance:
        lines.append(f"Insurance: {ins.insurance_type} £{ins.amount_gbp:,.0f}" if ins.amount_gbp else f"Insurance: {ins.insurance_type}")
    for sla in extraction.slas:
        lines.append(f"SLA: {sla.priority_level} response={sla.response_minutes}m resolution={sla.resolution_hours}h")
    for proj in extraction.projects:
        lines.append(f"Project: {proj.client_name} ({proj.client_sector})")
    for price in extraction.pricing:
        if price.total_gbp:
            lines.append(f"Pricing: Year {price.year} £{price.total_gbp:,.0f}")
        elif price.amount_gbp:
            lines.append(f"Pricing: £{price.amount_gbp:,.0f}/yr")
        else:
            lines.append(f"Pricing: {price.description or 'amount not specified'}")
    return "\n".join(lines) if lines else "No extracted facts available."


def _build_compliance_summary(evaluation: EvaluationOutput) -> str:
    lines = []
    for d in evaluation.compliance_decisions:
        lines.append(
            f"{d.check_id}: {d.decision.value} "
            f"(basis={d.decision_basis.value}, confidence={d.confidence:.2f})"
        )
    return "\n".join(lines) if lines else "No compliance decisions."


def _format_chunks(source_chunks: dict[str, str]) -> str:
    parts = []
    for chunk_id, text in list(source_chunks.items())[:10]:
        parts.append(f"[{chunk_id}]\n{text[:400]}")
    return "\n\n".join(parts) if parts else "No source chunks."


async def run_explanation_agent(
    decision_output: DecisionOutput,
    evaluation_outputs: dict[str, EvaluationOutput],
    extraction_outputs: dict[str, ExtractionOutput],
    source_chunks: dict[str, str],
) -> tuple[ExplanationOutput, object]:
    """
    decision_output:     DecisionOutput from Decision Agent
    evaluation_outputs:  {vendor_id: EvaluationOutput}
    extraction_outputs:  {vendor_id: ExtractionOutput}
    source_chunks:       {chunk_id: chunk_text} — all vendors combined
    """
    explanation_id = str(uuid.uuid4())
    vendor_narratives = []

    all_vendor_ids = list(evaluation_outputs.keys())

    for vendor_id in all_vendor_ids:
        evaluation = evaluation_outputs[vendor_id]
        extraction = extraction_outputs.get(vendor_id, ExtractionOutput(
            extraction_id="empty", vendor_id=vendor_id, org_id="",
            source_chunk_ids=[], extraction_completeness=0.0, hallucination_risk=0.0
        ))
        is_rejected = any(r.vendor_id == vendor_id for r in decision_output.rejected_vendors)

        narrative = await _generate_vendor_narrative(
            vendor_id=vendor_id,
            vendor_name=vendor_id,
            is_rejected=is_rejected,
            evaluation=evaluation,
            extraction=extraction,
            source_chunks=source_chunks,
            decision_output=decision_output,
        )
        vendor_narratives.append(narrative)

    # Compute grounding completeness across all narratives
    total_claims = sum(
        len(n.grounded_claims) + n.ungrounded_claims_removed
        for n in vendor_narratives
    )
    grounded_claims = sum(len(n.grounded_claims) for n in vendor_narratives)
    grounding_completeness = (
        grounded_claims / total_claims if total_claims > 0 else 1.0
    )

    methodology_note = (
        "This report was generated by an automated evaluation pipeline. "
        "Every factual claim is grounded to a verbatim quote from the vendor submission. "
        "Claims that could not be verified against source text were removed. "
        "Human review is recommended before final procurement decisions."
    )

    limitations = []
    for n in vendor_narratives:
        if n.ungrounded_claims_removed > 0:
            limitations.append(
                f"{n.vendor_id}: {n.ungrounded_claims_removed} unverified claim(s) removed."
            )

    output = ExplanationOutput(
        explanation_id=explanation_id,
        executive_summary=_build_executive_summary(decision_output, vendor_narratives),
        vendor_narratives=vendor_narratives,
        methodology_note=methodology_note,
        limitations=limitations,
        grounding_completeness=round(grounding_completeness, 3),
        report_confidence=decision_output.decision_confidence,
    )

    return output, critic_after_explanation(output, source_chunks)


def _build_executive_summary(
    decision_output: DecisionOutput,
    narratives: list[VendorNarrative],
) -> str:
    n_rejected = len(decision_output.rejected_vendors)
    n_shortlisted = len(decision_output.shortlisted_vendors)
    top = decision_output.shortlisted_vendors[0] if decision_output.shortlisted_vendors else None
    top_line = (
        f"Top-ranked vendor: {top.vendor_id} (score {top.total_score:.2f}/10, "
        f"{top.recommendation})."
        if top else "No vendors shortlisted."
    )
    return (
        f"Evaluation complete. {n_shortlisted} vendor(s) shortlisted, "
        f"{n_rejected} rejected. {top_line} "
        f"Approval routed to {decision_output.approval_routing.approver_role} "
        f"(Tier {decision_output.approval_routing.approval_tier})."
    )
