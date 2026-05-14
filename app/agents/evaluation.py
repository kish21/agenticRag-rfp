"""
Evaluation Agent — reads PostgreSQL facts, evaluates mandatory checks and scores criteria.

Key rule: reads from PostgreSQL (structured facts), NOT from Qdrant (raw chunks).
Same typed facts in → same evaluation out. Temperature 0.0 enforces determinism.

Mandatory check fallback: when PostgreSQL has no facts for a check, the evaluator
queries Qdrant directly (top-K=5) and runs _llm_verify_threshold per chunk.
This ensures checks with no extracted facts still get a verdict rather than defaulting
to insufficient_evidence.
"""
import json
import uuid
from typing import Optional

from app.core.llm_provider import call_llm
from app.core.output_models import (
    ComplianceDecision,
    ComplianceStatus,
    CriterionScore,
    DecisionBasis,
    EvaluationOutput,
    EvaluationSetup,
    ExtractionOutput,
    ExtractionTarget,
    MandatoryCheck,
    ScoringCriterion,
)
from app.agents.critic import critic_after_evaluation
from app.db.fact_store import get_vendor_facts


async def _llm_verify_threshold(
    chunk_text: str,
    check_name: str,
    what_passes: str,
) -> dict:
    """Ask the LLM whether a single chunk satisfies the mandatory check threshold."""
    messages = [
        {
            "role": "system",
            "content": (
                "You are a compliance verifier. "
                "Check whether the provided text passage satisfies ALL stated conditions. "
                "Only return satisfies=true if every condition in 'Passes when' is explicitly met. "
                "Return only valid JSON."
            ),
        },
        {
            "role": "user",
            "content": (
                f"Requirement: {check_name}\n"
                f"Passes when: {what_passes}\n\n"
                f"Text passage:\n{chunk_text}\n\n"
                "Does this passage satisfy ALL conditions?\n"
                'Return JSON: {"satisfies": true|false, "evidence": "verbatim quote or empty string", "confidence": 0.0}'
            ),
        },
    ]
    raw = await call_llm(messages, temperature=0.0, response_format={"type": "json_object"})
    return json.loads(raw)


# Stash most-recent critic verdict per (check_name, vendor_id) so callers
# can inspect adequacy reasoning without changing the return signature.
_last_retrieval_verdict: dict[tuple[str, str], object] = {}


def get_last_retrieval_verdict(check_name: str, vendor_id: str):
    """Return the CriticVerdict for the most recent retrieval attempt, or None."""
    return _last_retrieval_verdict.get((check_name, vendor_id))


def _chunks_from_output(output) -> list[dict]:
    return [
        {"text": c.text, "payload": {"chunk_id": c.chunk_id, "section_type": c.section_type}}
        for c in output.chunks
    ]


async def _retrieve_top_k_for_check(
    check_name: str,
    vendor_id: str,
    org_id: str,
    k: int = 5,  # audit:allow — default when org_settings not available
    what_passes: str = "",
    org_settings=None,
    run_id: str = "",
) -> list[dict]:
    """Retrieve evidence for a mandatory check via run_retrieval_agent (HyDE-aware).

    Runs the retrieval critic after the first pass. If the critic judges the
    chunks inadequate, retries once with escalated settings (hybrid+HyDE,
    doubled K). Returns whichever chunks came from the final pass.
    query priority: what_passes > check_name.
    """
    import logging
    from app.agents.retrieval import run_retrieval_agent
    from app.core.retrieval_critic import judge_retrieval, CriticVerdict
    from app.core.audit import audit
    from app.config import settings as cfg

    log = logging.getLogger(__name__)
    query = what_passes or check_name
    max_retries = cfg.platform.infrastructure.retrieval_critic_max_retries
    confidence_floor = cfg.platform.infrastructure.retrieval_critic_confidence_floor

    chunks: list[dict] = []
    verdict: CriticVerdict | None = None
    retry_count = 0

    # --- First pass ---
    try:
        output, _ = await run_retrieval_agent(
            query=query,
            vendor_id=vendor_id,
            org_id=org_id,
            rfp_id="",
            is_mandatory_check=True,
            org_settings=org_settings,
            run_id=run_id or None,
            criterion_id=check_name,
        )
        chunks = _chunks_from_output(output)
    except Exception as exc:
        log.warning("_retrieve_top_k_for_check: first pass failed: %s", exc)
        chunks = []

    verdict = await judge_retrieval(check_name, what_passes, chunks)
    log.info(
        "retrieval_critic first pass: check=%r adequate=%s confidence=%.2f missing=%r",
        check_name, verdict.adequate, verdict.confidence, verdict.missing,
    )

    # --- Retry if inadequate and budget allows ---
    if not (verdict.adequate and verdict.confidence >= confidence_floor) and max_retries > 0:
        retry_count = 1

        # Build escalated settings: force hybrid+HyDE, double K (cap 20)
        escalated_top_k = min(20, (org_settings.retrieval_top_k if org_settings else k) * 2)  # audit:allow

        class _EscalatedSettings:
            use_hyde = True
            use_hybrid_search = True
            use_query_rewriting = True
            retrieval_top_k = escalated_top_k
            rerank_top_n = (org_settings.rerank_top_n if org_settings else 5)  # audit:allow
            reranker_provider = (org_settings.reranker_provider if org_settings else None)  # audit:allow

        try:
            output2, _ = await run_retrieval_agent(
                query=query,
                vendor_id=vendor_id,
                org_id=org_id,
                rfp_id="",
                is_mandatory_check=True,
                org_settings=_EscalatedSettings(),
                run_id=run_id or None,
                criterion_id=f"{check_name}:retry",
            )
            chunks = _chunks_from_output(output2)
        except Exception as exc:
            log.warning("_retrieve_top_k_for_check: retry pass failed: %s", exc)

        verdict = await judge_retrieval(check_name, what_passes, chunks)
        log.info(
            "retrieval_critic retry pass: check=%r adequate=%s confidence=%.2f missing=%r",
            check_name, verdict.adequate, verdict.confidence, verdict.missing,
        )

    # --- Stash verdict + emit audit row ---
    _last_retrieval_verdict[(check_name, vendor_id)] = verdict
    audit(
        org_id=org_id,
        run_id=run_id or None,
        event_type="retrieval_critic.verdict",
        actor="retrieval_critic",
        detail={
            "check_name": check_name,
            "vendor_id": vendor_id,
            "adequate": verdict.adequate,
            "confidence": verdict.confidence,
            "missing": verdict.missing,
            "retry_count": retry_count,
        },
    )

    return chunks


def _get_facts_for_target(facts: dict, target: ExtractionTarget) -> list[dict]:
    type_map = {
        "certification": facts.get("certifications", []),
        "insurance": facts.get("insurance", []),
        "sla": facts.get("slas", []),
        "project": facts.get("projects", []),
        "pricing": facts.get("pricing", []),
        "custom": [
            f for f in facts.get("extracted_facts", [])
            if f.get("target_id") == target.target_id
        ],
    }
    return type_map.get(target.fact_type, [])


async def _evaluate_mandatory_check(
    check: MandatoryCheck,
    target: ExtractionTarget,
    relevant_facts: list[dict],
    vendor_id: str,
    org_id: str = "",
    org_settings=None,
    retried_fact_types: list[str] | None = None,
    run_id: str = "",
) -> ComplianceDecision:
    facts_text = (
        json.dumps(relevant_facts, indent=2, default=str)
        if relevant_facts
        else "No facts extracted for this requirement."
    )
    messages = [
        {
            "role": "system",
            "content": (
                "You are a compliance evaluation engine. "
                "Evaluate strictly based on the extracted facts provided. "
                "Do not assume or infer beyond what is explicitly stated.\n"
                "Return only valid JSON."
            ),
        },
        {
            "role": "user",
            "content": (
                f"Requirement: {check.name}\n"
                f"Description: {check.description}\n"
                f"What passes: {check.what_passes}\n"
                f"Extraction target: {target.name} — {target.description}\n\n"
                f"Extracted facts:\n{facts_text}\n\n"
                "Return JSON:\n"
                '{"decision": "pass|fail|insufficient_evidence", '
                '"confidence": 0.0, '
                '"reasoning": "one sentence", '
                '"evidence_used": ["verbatim quote"], '
                '"contradictions_found": [], '
                '"decision_basis": "explicit_confirmation|implicit_confirmation|partial_compliance|explicit_denial|not_addressed"}'
            ),
        },
    ]
    raw = await call_llm(messages, temperature=0.0, response_format={"type": "json_object"})
    parsed = json.loads(raw)

    try:
        decision = ComplianceStatus(parsed.get("decision", "insufficient_evidence"))
    except ValueError:
        decision = ComplianceStatus.INSUFFICIENT_EVIDENCE

    # Fallback: fire when (a) no facts + insufficient_evidence, OR
    # (b) facts exist but decision is FAIL and extraction was NOT already retried
    # by the extraction critic (which would mean the failure is genuine).
    # extraction_was_retried prevents looping between the two critics.
    extraction_was_retried = target.fact_type in (retried_fact_types or [])
    should_fallback = org_id and (
        (not relevant_facts and decision == ComplianceStatus.INSUFFICIENT_EVIDENCE)
        or (relevant_facts and decision == ComplianceStatus.FAIL and not extraction_was_retried)
    )
    chunk_evidence: list[str] = []
    if should_fallback:
        top_k = org_settings.retrieval_top_k if org_settings is not None else 5  # audit:allow
        chunks = await _retrieve_top_k_for_check(
            check.name, vendor_id, org_id, k=top_k,
            what_passes=check.what_passes, org_settings=org_settings,
            run_id=run_id,
        )
        for chunk in chunks:
            result = await _llm_verify_threshold(
                chunk.get("text", ""), check.name, check.what_passes
            )
            if result.get("satisfies"):
                ev = result.get("evidence", "")
                if ev:
                    chunk_evidence.append(ev)
        if chunk_evidence:
            decision = ComplianceStatus.PASS
            parsed["confidence"] = 0.75  # audit:allow — result confidence score, not a threshold
            parsed["reasoning"] = (
                f"Verified in source document: {chunk_evidence[0][:120]}"
            )
            parsed["decision_basis"] = "explicit_confirmation"

    try:
        decision_basis = DecisionBasis(parsed.get("decision_basis", "not_addressed"))
    except ValueError:
        decision_basis = DecisionBasis.NOT_ADDRESSED

    evidence = chunk_evidence if chunk_evidence else parsed.get("evidence_used", [])

    return ComplianceDecision(
        check_id=check.check_id,
        vendor_id=vendor_id,
        decision=decision,
        confidence=float(parsed.get("confidence", 0.5)),
        reasoning=parsed.get("reasoning", ""),
        evidence_used=evidence,
        contradictions_found=parsed.get("contradictions_found", []),
        decision_basis=decision_basis,
    )


async def _score_criterion(
    criterion: ScoringCriterion,
    relevant_facts: list[dict],
    vendor_id: str,
) -> CriterionScore:
    has_facts = bool(relevant_facts)
    facts_text = (
        json.dumps(relevant_facts, indent=2, default=str)
        if has_facts
        else "No specific facts extracted for this criterion — score based on the broader evidence below if present, otherwise score 0."
    )
    messages = [
        {
            "role": "system",
            "content": (
                "You are a scoring engine. Score based only on the extracted facts. "
                "Apply the rubric strictly. Do not award credit for facts not present.\n"
                "Return only valid JSON with numeric values (not null) for all fields."
            ),
        },
        {
            "role": "user",
            "content": (
                f"Criterion: {criterion.name}\n\n"
                f"Rubric:\n"
                f"9-10: {criterion.rubric_9_10}\n"
                f"6-8:  {criterion.rubric_6_8}\n"
                f"3-5:  {criterion.rubric_3_5}\n"
                f"0-2:  {criterion.rubric_0_2}\n\n"
                f"Extracted facts:\n{facts_text}\n\n"
                "Score this vendor 0-10. "
                "Set confidence to how certain you are of the score (0.0=uncertain, 1.0=certain). "
                "Even a score of 0 should have high confidence if evidence is clearly absent.\n"
                "Return JSON with these exact keys and numeric (not null) values:\n"
                '{"raw_score": <integer 0-10>, '
                '"confidence": <float 0.0-1.0>, '
                '"rubric_band_applied": "<one of: 9-10, 6-8, 3-5, 0-2>", '
                '"evidence_used": ["<verbatim quote or empty string>"], '
                '"score_rationale": "<one sentence>", '
                '"variance_estimate": <float 0.0-3.0>}'
            ),
        },
    ]
    raw = await call_llm(messages, temperature=0.0, response_format={"type": "json_object"})
    parsed = json.loads(raw)

    raw_score = max(0, min(10, int(parsed.get("raw_score") or 0)))

    return CriterionScore(
        criterion_id=criterion.criterion_id,
        vendor_id=vendor_id,
        raw_score=raw_score,
        weighted_contribution=round((raw_score / 10) * criterion.weight, 4),
        confidence=float(parsed.get("confidence", 0.5)),
        rubric_band_applied=parsed.get("rubric_band_applied", "0-2"),
        evidence_used=parsed.get("evidence_used", []),
        score_rationale=parsed.get("score_rationale", ""),
        variance_estimate=float(parsed.get("variance_estimate", 1.0)),
    )


async def run_evaluation_agent(
    vendor_id: str,
    org_id: str,
    evaluation_setup: EvaluationSetup,
    extraction_output: Optional[ExtractionOutput] = None,
    run_id: str = "",
) -> tuple[EvaluationOutput, object]:
    evaluation_id = str(uuid.uuid4())
    warnings: list[str] = []

    from app.core.org_settings import get_org_settings
    org_settings = get_org_settings(org_id) if org_id else None

    # Reads from PostgreSQL — NOT Qdrant
    facts = get_vendor_facts(org_id, vendor_id, setup_id=evaluation_setup.setup_id)
    target_by_id = {t.target_id: t for t in evaluation_setup.extraction_targets}

    # Evaluate every mandatory check
    _retried_fact_types = list(getattr(extraction_output, "retried_fact_types", []) or [])
    compliance_decisions: list[ComplianceDecision] = []
    for check in evaluation_setup.mandatory_checks:
        target = target_by_id.get(check.extraction_target_id)
        if not target:
            warnings.append(f"No extraction target for check {check.check_id}")
            continue
        try:
            decision = await _evaluate_mandatory_check(
                check, target, _get_facts_for_target(facts, target), vendor_id, org_id,
                org_settings=org_settings,
                retried_fact_types=_retried_fact_types,
                run_id=run_id,
            )
            compliance_decisions.append(decision)
        except Exception as e:
            warnings.append(f"Check {check.check_id} failed: {e}")

    # All standard facts as fallback context when custom targets return nothing
    all_standard_facts = (
        facts.get("certifications", []) +
        facts.get("insurance", []) +
        facts.get("slas", []) +
        facts.get("projects", []) +
        facts.get("pricing", []) +
        facts.get("extracted_facts", [])
    )

    # Score every criterion
    criterion_scores: list[CriterionScore] = []
    for criterion in evaluation_setup.scoring_criteria:
        relevant: list[dict] = []
        for tid in criterion.extraction_target_ids:
            target = target_by_id.get(tid)
            if target:
                relevant.extend(_get_facts_for_target(facts, target))
        # Fall back to all extracted facts so the LLM always has context to score from
        if not relevant:
            relevant = all_standard_facts
        try:
            score = await _score_criterion(criterion, relevant, vendor_id)
            criterion_scores.append(score)
        except Exception as e:
            warnings.append(f"Criterion {criterion.criterion_id} failed: {e}")

    # Overall compliance — fail beats review_required beats pass
    decisions = [d.decision for d in compliance_decisions]
    if any(d == ComplianceStatus.FAIL for d in decisions):
        overall_compliance = "fail"
    elif any(d == ComplianceStatus.INSUFFICIENT_EVIDENCE for d in decisions):
        overall_compliance = "review_required"
    else:
        overall_compliance = "pass"

    total_score = round(sum(s.weighted_contribution for s in criterion_scores), 4)
    avg_confidence = (
        round(sum(s.confidence for s in criterion_scores) / len(criterion_scores), 3)
        if criterion_scores else 0.0
    )

    output = EvaluationOutput(
        evaluation_id=evaluation_id,
        vendor_id=vendor_id,
        compliance_decisions=compliance_decisions,
        criterion_scores=criterion_scores,
        overall_compliance=overall_compliance,
        total_weighted_score=total_score,
        score_confidence=avg_confidence,
        evaluation_warnings=warnings,
    )

    # critic_after_evaluation requires ExtractionOutput — use stub if not provided
    _extraction = extraction_output or ExtractionOutput(
        extraction_id="stub",
        vendor_id=vendor_id,
        org_id=org_id,
        source_chunk_ids=[],
        extraction_completeness=0.0,
        hallucination_risk=0.0,
    )
    critic = critic_after_evaluation(output, _extraction)
    return output, critic
