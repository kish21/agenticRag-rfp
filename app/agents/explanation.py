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

from app.providers.llm import call_llm
from app.prompts.registry import get_prompt
from pydantic import ValidationError
from app.schemas.output_models import (
    ExplanationOutput, VendorNarrative, GroundedClaim,
    SynthesisLLMResponse, SystemFact,
    DecisionOutput, EvaluationOutput, ExtractionOutput,
)
from app.agents.critic import critic_after_explanation
from app.infra.cost_tracker import mark_agent


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
    currency: str = "GBP",
    critic_feedback: str = "",
) -> VendorNarrative:
    """Generates narrative sections and verifies every claim is grounded.

    Phase 2: optionally accepts `critic_feedback` from a previous attempt's
    critic verdict. When non-empty, it is prepended to the user message as
    a 'PREVIOUS ATTEMPT FAILED' preamble so the LLM corrects course."""

    mark_agent("explanation_agent")  # cost attribution for this task's LLM calls
    context_facts = _build_fact_context(extraction, currency=currency)
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

    # Phase 2 retry feedback prepended to user message (if any)
    feedback_block = (
        f"========================================\n"
        f"{critic_feedback}\n"
        f"========================================\n\n"
        if critic_feedback else ""
    )

    messages = [
        {"role": "system", "content": get_prompt("explanation/generate_narrative")},
        {
            "role": "user",
            "content": (
                f"{feedback_block}"
                f"Vendor: {vendor_name} ({vendor_id})\n"
                f"Decision: {decision_context}\n\n"
                f"Compliance results:\n{compliance_summary}\n\n"
                f"Extracted facts:\n{context_facts}\n\n"
                f"Source chunks:\n{_format_chunks(source_chunks)}"
            ),
        },
    ]

    raw = await call_llm(messages, temperature=0.0,
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
    ungrounded_examples: list[dict] = []

    for claim in synthesis.grounded_claims:
        if verify_grounding(claim.claim_text, claim.grounding_quote, claim.source_chunk_id, source_chunks):
            verified_claims.append(claim)
        else:
            ungrounded_count += 1
            src_text = source_chunks.get(claim.source_chunk_id, "")
            ungrounded_examples.append({
                "claim_text":        claim.claim_text,
                "llm_grounding_quote": claim.grounding_quote,
                "cited_chunk_id":    claim.source_chunk_id,
                "chunk_exists":      bool(src_text),
                "source_excerpt":    src_text[:600] if src_text else "(no chunk under this id)",
                "diagnosis_hint":    (
                    "wrong_chunk_id" if not src_text else
                    "quote_not_in_source"
                ),
            })

    # Deterministically record WHY a vendor was rejected and WHAT conflicts were
    # found, as system_facts (trusted upstream determinations — no PDF grounding
    # needed). This guarantees the report always carries the rejection/conflict
    # explanation the customer needs to follow up, regardless of what the LLM
    # chose to write — and means a legitimately rejected/conflicted vendor is
    # NOT an empty narrative.
    system_facts: list[SystemFact] = list(synthesis.system_facts)
    for d in evaluation.compliance_decisions:
        if d.contradictions_found:
            vals = "; ".join(str(c) for c in d.contradictions_found)
            system_facts.append(SystemFact(
                fact_text=(
                    f"Conflicting evidence for '{d.check_id}': {vals}. Cannot confirm "
                    "the requirement — recommend the customer follow up with the vendor."
                ),
                origin="evaluation", origin_id=d.check_id,
            ))
    if is_rejected and rejection is not None:
        reasons = "; ".join(rejection.rejection_reasons) or "mandatory requirement not met"
        failed = "; ".join(rejection.failed_checks)
        system_facts.append(SystemFact(
            fact_text=(
                f"Rejected — failed mandatory checks: {failed}. {reasons}."
            ),
            origin="decision", origin_id=vendor_id,
        ))

    return VendorNarrative(
        vendor_id=vendor_id,
        vendor_name=vendor_name,
        executive_summary=synthesis.executive_summary,
        compliance_narrative=synthesis.compliance_narrative,
        scoring_narrative=synthesis.scoring_narrative,
        recommendation_rationale=synthesis.recommendation_rationale,
        grounded_claims=verified_claims,
        ungrounded_claims_removed=ungrounded_count,
        # System-computed facts (rank, score, check pass/fail, rejection reasons,
        # conflicts) bypass grounding — their truth comes from upstream agents.
        system_facts=system_facts,
        ungrounded_examples=ungrounded_examples,
    )


def _fmt_currency(value: float | None, currency: str) -> str:
    if value is None:
        return ""
    return f"{currency} {value:,.0f}"


def _build_fact_context(extraction: ExtractionOutput, currency: str = "GBP") -> str:
    lines = []
    for cert in extraction.certifications:
        lines.append(f"Certification: {cert.standard_name} ({cert.status.value})")
    for ins in extraction.insurance:
        amt = ins.amount if ins.amount is not None else ins.amount_gbp
        if amt:
            lines.append(f"Insurance: {ins.insurance_type} {_fmt_currency(amt, currency)}")
        else:
            lines.append(f"Insurance: {ins.insurance_type}")
    for sla in extraction.slas:
        lines.append(f"SLA: {sla.priority_level} response={sla.response_minutes}m resolution={sla.resolution_hours}h")
    for proj in extraction.projects:
        lines.append(f"Project: {proj.client_name} ({proj.client_sector})")
    for price in extraction.pricing:
        total = price.total_amount if price.total_amount is not None else price.total_gbp
        amt = price.amount if price.amount is not None else price.amount_gbp
        if total:
            lines.append(f"Pricing: Year {price.year} {_fmt_currency(total, currency)}")
        elif amt:
            lines.append(f"Pricing: {_fmt_currency(amt, currency)}/yr")
        else:
            lines.append(f"Pricing: {price.description or 'amount not specified'}")
    for fact in extraction.extracted_facts:
        lines.append(f"Custom fact [{fact.target_id}]: {fact.text_value}")
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
    parts = [f"[{chunk_id}]\n{text}" for chunk_id, text in source_chunks.items()]
    return "\n\n".join(parts) if parts else "No source chunks."


# Single source of truth for the report's grounding methodology statement.
METHODOLOGY_NOTE = (
    "This report was generated by an automated evaluation pipeline. "
    "Every factual claim is grounded to a verbatim quote from the vendor submission. "
    "Claims that could not be verified against source text were removed. "
    "Human review is recommended before final procurement decisions."
)


def compute_grounding(vendor_narratives) -> tuple[float, int, list[str]]:
    """Single source of truth for grounding completeness + base limitations.

    Grounding completeness = fraction of PDF claims that grounded, measured ONLY
    over narratives that actually made PDF claims. A narrative whose content is
    entirely system_facts (e.g. a vendor rejected for a conflict — its story is a
    trusted system determination, not a PDF quote) has nothing that needed
    grounding and must not be scored 0%. The honesty rule stays fully strict on
    the PDF claims that ARE made (a narrative that made claims which all failed
    grounding still scores 0 and is blocked).

    If no narrative made any PDF claim, ``total_claims == 0`` and completeness is
    *vacuously* 1.0 — there was nothing to ground. That is NOT the same as "100%
    of claims verified"; callers and the critic must treat ``total_claims == 0``
    distinctly (a claim-free report still warrants human eyes — see
    ``critic_after_explanation``'s ``claim_free_report`` SOFT flag).

    Returns ``(grounding_completeness, total_claims, base_limitations)``. Callers
    append any stage-specific limitations (e.g. failed-vendor or
    insufficient-evidence notices) after the base ones to preserve ordering.
    """
    claim_bearing = [
        n for n in vendor_narratives
        if (len(n.grounded_claims) + n.ungrounded_claims_removed) > 0
    ]
    total_claims = sum(len(n.grounded_claims) + n.ungrounded_claims_removed for n in claim_bearing)
    grounded_claims = sum(len(n.grounded_claims) for n in claim_bearing)
    grounding_completeness = (grounded_claims / total_claims) if total_claims > 0 else 1.0

    limitations: list[str] = []
    if total_claims == 0:
        limitations.append(
            "No grounded claims were produced for any vendor — "
            "narratives may be empty. Check source chunks and re-run."
        )
    for n in vendor_narratives:
        if n.ungrounded_claims_removed > 0:
            limitations.append(
                f"{n.vendor_id}: {n.ungrounded_claims_removed} unverified claim(s) removed."
            )
        if len(n.grounded_claims) == 0:
            limitations.append(
                f"{n.vendor_id}: zero grounded claims — narrative has no verifiable content."
            )
    return round(grounding_completeness, 3), total_claims, limitations


async def run_explanation_agent(
    decision_output: DecisionOutput,
    evaluation_outputs: dict[str, EvaluationOutput],
    extraction_outputs: dict[str, ExtractionOutput],
    source_chunks: dict[str, str],
    currency: str = "GBP",
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

        # Filter source chunks to only this vendor's chunks — prevents cross-vendor
        # contamination in the LLM context and grounding checks
        vendor_chunks = {
            cid: source_chunks[cid]
            for cid in extraction.source_chunk_ids
            if cid in source_chunks
        }
        if not vendor_chunks:
            vendor_chunks = source_chunks  # fallback if extraction has no chunk IDs

        is_rejected = any(r.vendor_id == vendor_id for r in decision_output.rejected_vendors)

        narrative = await _generate_vendor_narrative(
            vendor_id=vendor_id,
            vendor_name=vendor_id,
            is_rejected=is_rejected,
            evaluation=evaluation,
            extraction=extraction,
            source_chunks=vendor_chunks,
            decision_output=decision_output,
            currency=currency,
        )
        vendor_narratives.append(narrative)

    # Grounding completeness + base limitations via the shared helper (single
    # source of truth — see compute_grounding). Stage-specific notices are
    # appended below.
    grounding_completeness, _, limitations = compute_grounding(vendor_narratives)
    methodology_note = METHODOLOGY_NOTE

    # E3 — surface criteria that could not be scored for lack of evidence so the
    # report never presents them as a genuine 0/10.
    for sv in decision_output.shortlisted_vendors:
        insufficient = [c.criterion_id for c in sv.criterion_breakdown
                        if getattr(c, "insufficient_evidence", False)]
        if insufficient:
            limitations.append(
                f"{sv.vendor_id}: insufficient evidence to score {insufficient} — "
                "these criteria were NOT scored (not counted as 0); human review needed."
            )

    output = ExplanationOutput(
        explanation_id=explanation_id,
        executive_summary=_build_executive_summary(decision_output, vendor_narratives),
        vendor_narratives=vendor_narratives,
        methodology_note=methodology_note,
        limitations=limitations,
        grounding_completeness=grounding_completeness,  # already rounded by compute_grounding
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
    # E3.d — headline the coverage-normalised score (the rank basis), not the absolute
    # total, so the #1 vendor's quoted score is consistent with why it ranked first.
    top_line = (
        f"Top-ranked vendor: {top.vendor_id} (score {top.coverage_normalised_score:.2f}/10, "
        f"{top.recommendation})."
        if top else "No vendors shortlisted."
    )
    return (
        f"Evaluation complete. {n_shortlisted} vendor(s) shortlisted, "
        f"{n_rejected} rejected. {top_line} "
        f"Approval routed to {decision_output.approval_routing.approver_role} "
        f"(Tier {decision_output.approval_routing.approval_tier})."
    )
