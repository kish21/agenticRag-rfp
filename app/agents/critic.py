"""
The Critic Agent runs after every other agent.
It is the only agent whose job is to be skeptical.
It does NOT retrieve, generate, or fix — it only validates and flags.
"""
import re
import uuid
from app.schemas.output_models import (
    CriticOutput, CriticFlag, CriticSeverity, CriticVerdict,
    RetrievalOutput, ExtractionOutput, EvaluationOutput,
    ComparatorOutput, DecisionOutput, ExplanationOutput,
    IngestionOutput, PlannerOutput,
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


def critic_after_planner(
    output: PlannerOutput,
    validation_errors: list[str],
) -> CriticOutput:
    flags = []

    if not output.vendor_ids:
        flags.append(_make_flag(
            CriticSeverity.HARD, "planner_agent",
            "no_vendors",
            "Plan contains no vendor IDs — nothing to evaluate",
            "vendor_ids=[]",
            "Provide at least one vendor ID before running evaluation."
        ))

    if not output.tasks:
        flags.append(_make_flag(
            CriticSeverity.HARD, "planner_agent",
            "empty_plan",
            "Plan contains no tasks",
            f"plan_id={output.plan_id}",
            "Plan generation failed. Check evaluation_setup is complete."
        ))

    for error in validation_errors:
        flags.append(_make_flag(
            CriticSeverity.HARD, "planner_agent",
            "plan_validation_error",
            error,
            f"plan_id={output.plan_id}",
            "Fix evaluation_setup before proceeding — plan does not cover all requirements."
        ))

    return CriticOutput(
        critic_run_id=str(uuid.uuid4()),
        evaluated_agent="planner_agent",
        evaluated_output_id=output.plan_id,
        flags=flags,
        hard_flag_count=sum(1 for f in flags if f.severity == CriticSeverity.HARD),
        soft_flag_count=sum(1 for f in flags if f.severity == CriticSeverity.SOFT),
        overall_verdict=_verdict(flags),
        requires_human_review=any(f.severity == CriticSeverity.HARD for f in flags),
    )


def critic_after_ingestion(output: IngestionOutput) -> CriticOutput:
    flags = []

    # issue #133 — prompt-injection defence (fail-CLOSED). A malicious vendor
    # may embed instructions in their PDF to manipulate the downstream LLM. The
    # Ingestion Agent scanned every chunk; if matches reach the configured
    # block_threshold we HARD-block here so poisoned text never reaches the
    # Extraction/Explanation LLM. The threshold is config-driven (no hardcoding).
    if output.injection_findings:
        from app.config import settings
        threshold = settings.platform.injection_defence.block_threshold
        # Count DISTINCT poisoned chunks, not raw match count — one crafted
        # sentence can trip several patterns, which would otherwise inflate the
        # count and make block_threshold mean "matches" instead of "attacks".
        poisoned_chunks = {f.chunk_id for f in output.injection_findings}
        if len(poisoned_chunks) >= threshold:
            patterns_hit = sorted({f.pattern_name for f in output.injection_findings})
            sample = output.injection_findings[0]
            flags.append(_make_flag(
                CriticSeverity.HARD, "ingestion_agent",
                "prompt_injection_detected",
                f"Vendor document contains text engineered to manipulate the LLM "
                f"({len(poisoned_chunks)} chunk(s); patterns: {', '.join(patterns_hit)})",
                f"pattern='{sample.pattern_name}' chunk={sample.chunk_id} "
                f"page={sample.page_number} text='{sample.matched_text[:80]}'",
                # NB: wording must NOT contain 'escalate' — _verdict() upgrades a
                # HARD flag with 'escalate' in its recommendation to ESCALATED,
                # which _hard_block_if() lets through. We need a true BLOCKED here.
                "Quarantine this document and require human security review before "
                "any further processing. Do NOT evaluate — the proposal contains "
                "prompt-injection content. Confirm with the vendor before proceeding."
            ))

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

    if output.reranking_degraded:
        flags.append(_make_flag(
            CriticSeverity.SOFT, "retrieval_agent",
            "reranking_degraded",
            "Reranker was unavailable — retrieval fell back to vector-score order, "
            "which lowers result precision (common cause: air-gapped box with no "
            "model access). Results are usable but not reranked.",
            f"warnings={output.warnings}",
            "Check RERANKER_PROVIDER / model availability for this deployment. "
            "Set RERANKER_PROVIDER=modal (GPU, no local HF egress) or =none if "
            "reranking is intentionally disabled."
        ))

    # When reranking degraded, the confidence was deliberately penalised (#212)
    # and the reranking_degraded flag above already explains the low number — so
    # skip this flag to avoid misattributing the cause to "vendor doesn't address
    # the criterion".
    if not output.empty_retrieval and not output.reranking_degraded and output.confidence < 0.4:
        flags.append(_make_flag(
            CriticSeverity.SOFT, "retrieval_agent",
            "low_retrieval_confidence",
            f"Retrieval confidence {output.confidence:.2f} is below 0.4 — "
            "vendor document may not address this criterion",
            f"confidence={output.confidence}, chunks={len(output.chunks)}",
            "Review retrieved chunks manually. Consider broadening query or checking "
            "if vendor document covers this requirement."
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

    def _ws(text: str) -> str:
        return re.sub(r"\s+", " ", text).strip()

    grounding_failures = 0
    for item in all_items:
        source_text = source_chunks.get(item.source_chunk_id, "")
        if source_text and item.grounding_quote:
            if _ws(item.grounding_quote) not in _ws(source_text):
                grounding_failures += 1
                flags.append(_make_flag(
                    CriticSeverity.SOFT,
                    "extraction_agent",
                    "grounding_verification_failed",
                    "Grounding quote not found verbatim — possible paraphrase, review manually",
                    f"quote='{item.grounding_quote[:80]}' not in chunk {item.source_chunk_id}",
                    "Flag for human review. Facts are saved but auditability is reduced."
                ))

    # Hard-block when the MAJORITY of facts fail grounding — indicates fabrication,
    # not mere paraphrasing. Individual soft flags are raised above for minority failures.
    total = len(all_items)
    if total and grounding_failures > total // 2:
        flags.append(_make_flag(
            CriticSeverity.HARD, "extraction_agent",
            "high_hallucination_risk",
            f"Majority of facts unverifiable ({grounding_failures}/{total})",
            f"hallucination_risk={output.hallucination_risk}",
            "Do not use extracted facts. Re-run extraction."
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
            # E3.b.2 — a contradiction the evaluation has ALREADY resolved to
            # insufficient_evidence is handled correctly (#198 "report always
            # completes"): it must stay in the report flagged for human review,
            # NOT be HARD-blocked into a futile retry loop and dropped (a source
            # contradiction can never be re-prompted away). Downgrade to SOFT.
            # A contradiction co-existing with a PASS/FAIL is still unreliable —
            # keep that HARD (defends the Q07 regression).
            resolved = decision.decision.value == "insufficient_evidence"
            flags.append(_make_flag(
                CriticSeverity.SOFT if resolved else CriticSeverity.HARD,
                "evaluation_agent",
                "contradictions_in_evidence",
                f"Check {decision.check_id} has contradictory evidence",
                f"contradictions={decision.contradictions_found}",
                "Resolved to insufficient_evidence; flag for human review."
                if resolved else
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


def critic_after_comparator(output: ComparatorOutput) -> CriticOutput:
    flags = []

    if not output.overall_ranking:
        flags.append(_make_flag(
            CriticSeverity.HARD, "comparator_agent",
            "empty_ranking",
            "Comparator produced no overall ranking",
            f"vendor_ids={output.vendor_ids}",
            "Cannot proceed to Decision Agent without a ranking."
        ))

    missing = set(output.vendor_ids) - set(output.overall_ranking)
    if missing:
        flags.append(_make_flag(
            CriticSeverity.HARD, "comparator_agent",
            "vendors_missing_from_ranking",
            f"{len(missing)} vendor(s) requested but absent from overall ranking",
            f"missing_vendors={sorted(missing)}",
            "Evaluation likely failed for these vendors. "
            "Do not proceed to Decision Agent — ranking is incomplete. Escalate to human review."
        ))

    if output.ranking_confidence < 0.5:
        flags.append(_make_flag(
            CriticSeverity.SOFT, "comparator_agent",
            "low_ranking_confidence",
            f"Ranking confidence is low ({output.ranking_confidence:.2f})",
            f"confidence={output.ranking_confidence}",
            "Note in report — ranking may not be reliable."
        ))

    unstable = [cc for cc in output.criteria_comparisons if not cc.rank_stable]
    if unstable:
        flags.append(_make_flag(
            CriticSeverity.SOFT, "comparator_agent",
            "unstable_criterion_rankings",
            f"Rankings unstable for {len(unstable)} criteria due to narrow margins",
            f"unstable_criteria={[cc.criterion_id for cc in unstable]}",
            "Flag in report — score margins too close for reliable ranking."
        ))

    return CriticOutput(
        critic_run_id=str(uuid.uuid4()),
        evaluated_agent="comparator_agent",
        evaluated_output_id=output.comparison_id,
        flags=flags,
        hard_flag_count=sum(1 for f in flags if f.severity == CriticSeverity.HARD),
        soft_flag_count=sum(1 for f in flags if f.severity == CriticSeverity.SOFT),
        overall_verdict=_verdict(flags),
        requires_human_review=any(f.severity == CriticSeverity.HARD for f in flags),
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

    if output.requires_human_review and output.review_reasons:
        for reason in output.review_reasons:
            if "insufficient evidence" in reason.lower():
                flags.append(_make_flag(
                    CriticSeverity.SOFT, "decision_agent",
                    "shortlisted_vendor_unresolved_checks",
                    reason,
                    f"vendor has mandatory checks with insufficient_evidence status",
                    "Flag in report. Approver must confirm these checks before award."
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

    # P2.26 — a claim-free report (no narrative made any PDF claim) computes a
    # *vacuous* grounding_completeness of 1.0: there was nothing to ground, which
    # is NOT the same as "100% of claims verified". Such a report ships with zero
    # PDF-grounded content (e.g. every vendor rejected/conflicted, the story
    # carried entirely by trusted system_facts) yet sails through the numeric
    # honesty gate above. Surface it as a SOFT flag so a human still reviews it
    # rather than letting the vacuous 1.0 pass silently. (Deferred import:
    # explanation imports critic at module load.)
    from app.agents.explanation import compute_grounding
    _, _total_claims, _ = compute_grounding(output.vendor_narratives)
    if _total_claims == 0:
        flags.append(_make_flag(
            CriticSeverity.SOFT, "explanation_agent",
            "claim_free_report",
            "Report contains no PDF-grounded claims — grounding_completeness is "
            "vacuously 1.0 (nothing to ground, not 100% verified)",
            f"total_claims=0, grounding_completeness={output.grounding_completeness}",
            "Report content rests entirely on system determinations "
            "(rejections/conflicts). Human review recommended before sending."
        ))

    for narrative in output.vendor_narratives:
        _system_facts = getattr(narrative, "system_facts", []) or []
        if (len(narrative.grounded_claims) == 0 and narrative.ungrounded_claims_removed == 0
                and len(_system_facts) == 0):
            # Truly empty only if there are no PDF claims, none were removed, AND no
            # system_facts. A vendor whose story is a trusted system determination
            # (rejection reasons / conflicts carried as system_facts) is NOT empty —
            # that IS the report content the customer needs.
            flags.append(_make_flag(
                CriticSeverity.HARD, "explanation_agent",
                "empty_narrative",
                f"Vendor {narrative.vendor_id} has zero claims — LLM produced no narrative content",
                f"vendor={narrative.vendor_id}",
                "LLM failed to generate any claims. Check source chunks and retry."
            ))
        elif len(narrative.grounded_claims) == 0 and narrative.ungrounded_claims_removed > 0:
            flags.append(_make_flag(
                CriticSeverity.HARD, "explanation_agent",
                "all_claims_ungrounded",
                f"All {narrative.ungrounded_claims_removed} claims for {narrative.vendor_id} "
                "failed grounding verification — no verifiable content remains",
                f"vendor={narrative.vendor_id}, removed={narrative.ungrounded_claims_removed}",
                "LLM is hallucinating. Source chunks may be insufficient. Do not publish report."
            ))
        elif narrative.ungrounded_claims_removed > 3:
            flags.append(_make_flag(
                CriticSeverity.SOFT, "explanation_agent",
                "many_claims_removed",
                f"Explanation agent removed {narrative.ungrounded_claims_removed} "
                f"ungrounded claims for {narrative.vendor_id}",
                f"vendor={narrative.vendor_id}, "
                f"removed={narrative.ungrounded_claims_removed}",
                "High hallucination in explanation. Check source data quality."
            ))

    # P1.8 — second-pass prose verification. The structured grounded_claims are
    # already quote-verified above; this gate covers the FREE-TEXT narrative prose
    # that verify_narrative_claims() fact-checked. The verified-claim ratio is
    # gated exactly like grounding_completeness, thresholds from config. A vacuous
    # 1.0 (verification disabled, or no prose claim to check) carries no
    # prose_verification entries and never trips these bands.
    from app.config import settings as _settings
    _sv = _settings.platform.synthesis_verification
    if _sv.enabled:
        for narrative in output.vendor_narratives:
            verifications = getattr(narrative, "prose_verification", []) or []
            if not verifications:
                continue
            score = getattr(narrative, "prose_verification_score", 1.0)
            unsupported = [v.claim_text for v in verifications if not v.supported]
            if score < _sv.block_below:
                flags.append(_make_flag(
                    CriticSeverity.HARD, "explanation_agent",
                    "unsupported_prose_claims",
                    f"Only {score:.0%} of {narrative.vendor_id}'s narrative prose claims "
                    f"are supported by evidence — {len(unsupported)} unsupported",
                    f"vendor={narrative.vendor_id}, score={score}, "
                    f"unsupported={unsupported[:5]}",
                    "Narrative prose contains claims not backed by source evidence. "
                    "Do not send to customer — regenerate the narrative."
                ))
            elif score < _sv.warn_below:
                flags.append(_make_flag(
                    CriticSeverity.SOFT, "explanation_agent",
                    "weak_prose_support",
                    f"{narrative.vendor_id}'s narrative prose is {score:.0%} supported — "
                    f"{len(unsupported)} claim(s) lack evidence",
                    f"vendor={narrative.vendor_id}, score={score}, "
                    f"unsupported={unsupported[:5]}",
                    "Some narrative prose claims are unsupported. Review before sending."
                ))

    import re as _re
    for narrative in output.vendor_narratives:
        for claim in narrative.grounded_claims[:5]:
            source = source_chunks.get(claim.source_chunk_id, "")
            if source and claim.grounding_quote:
                norm_source = _re.sub(r'\s+', ' ', source).strip()
                norm_quote  = _re.sub(r'\s+', ' ', claim.grounding_quote).strip()
                if norm_quote not in norm_source:
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
