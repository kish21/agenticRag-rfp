"""
The Critic Agent runs after every other agent.
It is the only agent whose job is to be skeptical.
It does NOT retrieve, generate, or fix — it only validates and flags.
"""
import uuid
from app.core.output_models import (
    CriticOutput, CriticFlag, CriticSeverity, CriticVerdict,
    RetrievalOutput, ExtractionOutput, EvaluationOutput,
    ComparatorOutput, DecisionOutput, ExplanationOutput,
    IngestionOutput
)


def _make_flag(
    severity: CriticSeverity,
    agent: str,
    check: str,
    description: str,
    evidence: str,
    recommendation: str,
    auto_resolvable: bool = False
) -> CriticFlag:
    return CriticFlag(
        flag_id=str(uuid.uuid4()),
        severity=severity,
        agent=agent,
        check_name=check,
        description=description,
        evidence=evidence,
        recommendation=recommendation,
        auto_resolvable=auto_resolvable
    )


def _verdict(flags: list[CriticFlag]) -> CriticVerdict:
    hard = any(f.severity == CriticSeverity.HARD for f in flags)
    escalated = any(
        "escalate" in f.recommendation.lower()
        for f in flags
        if f.severity == CriticSeverity.HARD
    )
    soft = any(f.severity == CriticSeverity.SOFT for f in flags)
    if escalated:
        return CriticVerdict.ESCALATED
    if hard:
        return CriticVerdict.BLOCKED
    if soft:
        return CriticVerdict.APPROVED_WITH_WARNINGS
    return CriticVerdict.APPROVED


def critic_after_ingestion(output: IngestionOutput) -> CriticOutput:
    flags = []

    if output.quality_score < 0.4:
        flags.append(_make_flag(
            CriticSeverity.HARD, "ingestion_agent",
            "quality_score_critical",
            "Document quality score below 0.4 — document may be unreadable",
            f"quality_score={output.quality_score}",
            "Reject document. Ask vendor to resubmit as a digital PDF."
        ))
    elif output.quality_score < 0.65:
        flags.append(_make_flag(
            CriticSeverity.SOFT, "ingestion_agent",
            "quality_score_low",
            "Document quality score below 0.65",
            f"quality_score={output.quality_score}",
            "Proceed with caution. Some sections may not be retrievable."
        ))

    req_resp = output.chunks_by_type.get("requirement_response", 0)
    if req_resp == 0:
        flags.append(_make_flag(
            CriticSeverity.HARD, "ingestion_agent",
            "no_requirement_sections",
            "Zero requirement_response sections found",
            f"chunks_by_type={output.chunks_by_type}",
            "Document does not address any RFP requirements. "
            "Do not evaluate. Contact vendor."
        ))

    if output.status == "duplicate":
        flags.append(_make_flag(
            CriticSeverity.SOFT, "ingestion_agent",
            "duplicate_document",
            "Document already ingested with identical content",
            f"content_hash={output.content_hash}",
            "Skip re-ingestion. Use existing data.",
            auto_resolvable=True
        ))

    return CriticOutput(
        critic_run_id=str(uuid.uuid4()),
        evaluated_agent="ingestion_agent",
        evaluated_output_id=output.doc_id,
        flags=flags,
        hard_flag_count=sum(1 for f in flags if f.severity == CriticSeverity.HARD),
        soft_flag_count=sum(1 for f in flags if f.severity == CriticSeverity.SOFT),
        overall_verdict=_verdict(flags),
        requires_human_review=any(f.severity == CriticSeverity.HARD for f in flags)
    )


def critic_after_retrieval(
    output: RetrievalOutput,
    is_mandatory: bool = False
) -> CriticOutput:
    flags = []

    if output.empty_retrieval:
        severity = CriticSeverity.HARD if is_mandatory else CriticSeverity.SOFT
        flags.append(_make_flag(
            severity, "retrieval_agent",
            "empty_retrieval",
            "Retrieval returned zero chunks" + (
                " for mandatory requirement" if is_mandatory else ""
            ),
            f"query='{output.original_query}'",
            "Widen search query and retry. If still empty, "
            "mark as insufficient_evidence."
        ))

    if not output.empty_retrieval:
        answer_bearing = [c for c in output.chunks if c.is_answer_bearing]
        if not answer_bearing:
            flags.append(_make_flag(
                CriticSeverity.SOFT, "retrieval_agent",
                "no_answer_bearing_chunks",
                "Retrieved chunks do not appear to contain answer-bearing content",
                f"top_score={output.chunks[0].final_score if output.chunks else 0}",
                "Try HyDE retrieval or broaden query."
            ))

        all_background = all(c.section_type == "background" for c in output.chunks)
        if all_background and is_mandatory:
            flags.append(_make_flag(
                CriticSeverity.SOFT, "retrieval_agent",
                "wrong_section_type",
                "All retrieved chunks are from 'background' sections",
                f"section_types={[c.section_type for c in output.chunks]}",
                "Add section_type filter for requirement_response."
            ))

    return CriticOutput(
        critic_run_id=str(uuid.uuid4()),
        evaluated_agent="retrieval_agent",
        evaluated_output_id=output.query_id,
        flags=flags,
        hard_flag_count=sum(1 for f in flags if f.severity == CriticSeverity.HARD),
        soft_flag_count=sum(1 for f in flags if f.severity == CriticSeverity.SOFT),
        overall_verdict=_verdict(flags),
        requires_human_review=any(f.severity == CriticSeverity.HARD for f in flags)
    )


def critic_after_extraction(
    output: ExtractionOutput,
    source_chunks: dict[str, str]
) -> CriticOutput:
    """
    source_chunks: {chunk_id: chunk_text} — used for grounding verification.
    Grounding verification is PROGRAMMATIC, not LLM.
    """
    flags = []

    all_items = (
        output.certifications
        + output.insurance
        + output.slas
        + output.projects
        + output.pricing
        + output.extracted_facts
    )

    for item in all_items:
        source_text = source_chunks.get(item.source_chunk_id, "")
        if source_text and item.grounding_quote:
            if item.grounding_quote.strip() not in source_text:
                flags.append(_make_flag(
                    CriticSeverity.HARD,
                    "extraction_agent",
                    "grounding_verification_failed",
                    "Extracted grounding_quote not found in source chunk",
                    f"quote='{item.grounding_quote[:80]}' "
                    f"not in chunk {item.source_chunk_id}",
                    "HALLUCINATION DETECTED. Discard this extraction result."
                ))

    if output.hallucination_risk > 0.5:
        flags.append(_make_flag(
            CriticSeverity.HARD, "extraction_agent",
            "high_hallucination_risk",
            "Extraction agent reported high hallucination risk",
            f"hallucination_risk={output.hallucination_risk}",
            "Do not use extracted facts. Re-run extraction with stricter prompt."
        ))

    if output.extraction_completeness < 0.5:
        flags.append(_make_flag(
            CriticSeverity.SOFT, "extraction_agent",
            "low_extraction_completeness",
            f"Only {output.extraction_completeness:.0%} of required fields extracted",
            f"completeness={output.extraction_completeness}",
            "Vendor may not have addressed all requirements."
        ))

    return CriticOutput(
        critic_run_id=str(uuid.uuid4()),
        evaluated_agent="extraction_agent",
        evaluated_output_id=output.extraction_id,
        flags=flags,
        hard_flag_count=sum(1 for f in flags if f.severity == CriticSeverity.HARD),
        soft_flag_count=sum(1 for f in flags if f.severity == CriticSeverity.SOFT),
        overall_verdict=_verdict(flags),
        requires_human_review=any(f.severity == CriticSeverity.HARD for f in flags)
    )


def critic_after_evaluation(
    output: EvaluationOutput,
    extraction_output: ExtractionOutput
) -> CriticOutput:
    flags = []

    for decision in output.compliance_decisions:
        if (
            decision.decision.value == "pass"
            and decision.decision_basis.value == "implicit_confirmation"
        ):
            flags.append(_make_flag(
                CriticSeverity.SOFT, "evaluation_agent",
                "implicit_confirmation_on_mandatory",
                f"Check {decision.check_id} passed on implicit confirmation only",
                f"basis={decision.decision_basis}",
                "Mandatory requirements need explicit confirmation."
            ))

        if decision.contradictions_found:
            flags.append(_make_flag(
                CriticSeverity.HARD, "evaluation_agent",
                "contradictions_in_evidence",
                f"Check {decision.check_id} has contradictory evidence",
                f"contradictions={decision.contradictions_found}",
                "Cannot make reliable decision. Human review required."
            ))

    for score in output.criterion_scores:
        if score.variance_estimate >= 2.0:
            flags.append(_make_flag(
                CriticSeverity.SOFT, "evaluation_agent",
                "high_score_variance",
                f"Score for {score.criterion_id} has high variance "
                f"(+/-{score.variance_estimate})",
                f"score={score.raw_score}+/-{score.variance_estimate}",
                "Score may not be reliable. Note in report."
            ))

    return CriticOutput(
        critic_run_id=str(uuid.uuid4()),
        evaluated_agent="evaluation_agent",
        evaluated_output_id=output.evaluation_id,
        flags=flags,
        hard_flag_count=sum(1 for f in flags if f.severity == CriticSeverity.HARD),
        soft_flag_count=sum(1 for f in flags if f.severity == CriticSeverity.SOFT),
        overall_verdict=_verdict(flags),
        requires_human_review=any(f.severity == CriticSeverity.HARD for f in flags)
    )


def critic_after_decision(output: DecisionOutput) -> CriticOutput:
    flags = []

    for rej in output.rejected_vendors:
        if not rej.evidence_citations:
            flags.append(_make_flag(
                CriticSeverity.HARD, "decision_agent",
                "rejection_without_evidence",
                f"Vendor {rej.vendor_id} rejected without evidence",
                "evidence_citations=[]",
                "CANNOT REJECT WITHOUT EVIDENCE. Legal exposure. "
                "Find evidence or change decision."
            ))

    if not output.shortlisted_vendors and output.rejected_vendors:
        flags.append(_make_flag(
            CriticSeverity.HARD, "decision_agent",
            "all_vendors_rejected",
            "All vendors were rejected",
            f"rejected={len(output.rejected_vendors)}, shortlisted=0",
            "ESCALATE. Requirements may be too restrictive. "
            "Review mandatory requirements with procurement team."
        ))

    return CriticOutput(
        critic_run_id=str(uuid.uuid4()),
        evaluated_agent="decision_agent",
        evaluated_output_id=output.decision_id,
        flags=flags,
        hard_flag_count=sum(1 for f in flags if f.severity == CriticSeverity.HARD),
        soft_flag_count=sum(1 for f in flags if f.severity == CriticSeverity.SOFT),
        overall_verdict=_verdict(flags),
        requires_human_review=any(f.severity == CriticSeverity.HARD for f in flags)
    )


def critic_after_explanation(
    output: ExplanationOutput,
    source_chunks: dict[str, str]
) -> CriticOutput:
    flags = []

    if output.grounding_completeness < 0.70:
        flags.append(_make_flag(
            CriticSeverity.HARD, "explanation_agent",
            "low_grounding_completeness",
            f"Only {output.grounding_completeness:.0%} of claims are grounded",
            f"grounding_completeness={output.grounding_completeness}",
            "Report contains too many unverified claims. Do not send to customer."
        ))
    elif output.grounding_completeness < 0.90:
        flags.append(_make_flag(
            CriticSeverity.SOFT, "explanation_agent",
            "moderate_grounding",
            f"Grounding completeness {output.grounding_completeness:.0%}",
            f"grounding_completeness={output.grounding_completeness}",
            "Report contains some unverified claims. Review before sending."
        ))

    for narrative in output.vendor_narratives:
        if narrative.ungrounded_claims_removed > 3:
            flags.append(_make_flag(
                CriticSeverity.SOFT, "explanation_agent",
                "many_claims_removed",
                f"Explanation agent removed {narrative.ungrounded_claims_removed} "
                f"ungrounded claims for {narrative.vendor_id}",
                f"vendor={narrative.vendor_id}, "
                f"removed={narrative.ungrounded_claims_removed}",
                "High hallucination in explanation. Check source data quality."
            ))

    for narrative in output.vendor_narratives:
        for claim in narrative.grounded_claims[:5]:
            source = source_chunks.get(claim.source_chunk_id, "")
            if source and claim.grounding_quote:
                if claim.grounding_quote not in source:
                    flags.append(_make_flag(
                        CriticSeverity.HARD, "explanation_agent",
                        "grounding_verification_failed",
                        "Claim grounding quote not found in source",
                        f"quote='{claim.grounding_quote[:60]}'",
                        "HALLUCINATION. Remove claim from report."
                    ))
                    break

    return CriticOutput(
        critic_run_id=str(uuid.uuid4()),
        evaluated_agent="explanation_agent",
        evaluated_output_id=output.explanation_id,
        flags=flags,
        hard_flag_count=sum(1 for f in flags if f.severity == CriticSeverity.HARD),
        soft_flag_count=sum(1 for f in flags if f.severity == CriticSeverity.SOFT),
        overall_verdict=_verdict(flags),
        requires_human_review=any(f.severity == CriticSeverity.HARD for f in flags)
    )
