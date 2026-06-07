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

from app.providers.llm import call_llm
from app.prompts.registry import get_prompt
from app.schemas.output_models import (
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
from app.domain.few_shot import build_few_shot_block
from app.infra.cost_tracker import mark_agent


def _feedback_block(critic_feedback: str) -> str:
    """Phase 2c — render a prior attempt's critic feedback as a 'PREVIOUS ATTEMPT
    FAILED' preamble so the LLM corrects course (mirrors the Extraction/Explanation
    agents). Empty string on the first attempt is a no-op."""
    if not critic_feedback:
        return ""
    return (
        f"========================================\n"
        f"{critic_feedback}\n"
        f"========================================\n\n"
    )


async def _llm_verify_threshold(
    chunk_text: str,
    check_name: str,
    what_passes: str,
) -> dict:
    """Ask the LLM whether a single chunk satisfies the mandatory check threshold."""
    messages = [
        {"role": "system", "content": get_prompt("evaluation/verify_threshold")},
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
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {"satisfies": False, "evidence": "", "confidence": 0.0}


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
    from app.validators.retrieval import judge_retrieval, CriticVerdict
    from app.infra.audit import audit
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


def _parse_check_response(raw: str) -> dict:
    """Parse one evaluate_check LLM response; fail-safe to insufficient_evidence on bad
    JSON (mirrors the original single-call behaviour)."""
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {
            "decision": "insufficient_evidence", "confidence": 0.0,
            "reasoning": "LLM returned invalid JSON", "evidence_used": [],
            "contradictions_found": [], "decision_basis": "not_addressed",
        }


def _normalise_decision(parsed: dict) -> str:
    """Map a parsed.decision onto a valid ComplianceStatus value, defaulting to
    insufficient_evidence — so an out-of-vocab vote can never escape the tally."""
    try:
        return ComplianceStatus(parsed.get("decision", "insufficient_evidence")).value
    except ValueError:
        return ComplianceStatus.INSUFFICIENT_EVIDENCE.value


async def _decide_check_with_voting(messages: list[dict]) -> tuple[dict, dict]:
    """P1.7 — decide ONE mandatory check, applying self-consistency voting ONLY when the
    primary verdict is borderline.

    Returns (representative_parsed, votes):
      • representative_parsed — a single parsed dict carrying the winning decision and an
        agreement-ratio confidence, so ALL downstream logic in _evaluate_mandatory_check
        (E3.b contradiction override, chunk fallback, ComplianceDecision construction) is
        untouched and operates on the voted result.
      • votes — audit breakdown: {"samples": 1} for a single call, else
        {"samples": N, "tally": {decision: count}, "winner": decision}.

    The first call is identical to today's single call (temperature 0, no explicit seed →
    deterministic auto-derived seed) so clear-cut checks and the whole non-borderline path
    are byte-for-byte unchanged. When the primary confidence lands in the configured band
    we resample at cfg.temperature with distinct seeds (the LLM cache keys on
    temperature+seed, so the samples are genuinely different yet reproducible), tally the
    decisions, and take the STRICT majority. No strict majority → fail-safe
    insufficient_evidence (owner decision; matches E3.b "can't confirm → insufficient").
    """
    from app.config import settings as cfg
    sc = cfg.platform.self_consistency

    # Deterministic baseline — unchanged from the original single call.
    raw_0 = await call_llm(messages, temperature=0.0, response_format={"type": "json_object"})
    parsed_0 = _parse_check_response(raw_0)
    conf_0 = float(parsed_0.get("confidence", 0.5) or 0.0)

    borderline = sc.confidence_min <= conf_0 <= sc.confidence_max
    if not sc.enabled or sc.samples <= 1 or not borderline:
        return parsed_0, {"samples": 1}

    # Borderline → resample. Distinct non-zero seeds + non-zero temperature so the votes
    # actually diverge (at temperature 0 every sample is identical and voting is a no-op).
    samples = [parsed_0]
    for i in range(1, sc.samples):
        raw_i = await call_llm(
            messages, temperature=sc.temperature, seed=i,
            response_format={"type": "json_object"},
        )
        samples.append(_parse_check_response(raw_i))

    decisions = [_normalise_decision(p) for p in samples]
    tally: dict = {}
    for d in decisions:
        tally[d] = tally.get(d, 0) + 1

    winner, winning_votes = max(tally.items(), key=lambda kv: kv[1])
    if winning_votes * 2 <= len(samples):  # no STRICT majority (> half) → fail-safe
        winner = ComplianceStatus.INSUFFICIENT_EVIDENCE.value
        winning_votes = tally.get(winner, 0)

    # Representative = the highest-confidence sample whose decision == winner, so the
    # reasoning/evidence carried downstream belong to the winning verdict. If the winner
    # came from the tie rule and no sample voted it, synthesise a minimal record.
    matching = [p for p, d in zip(samples, decisions) if d == winner]
    if matching:
        representative = dict(max(
            matching, key=lambda p: float(p.get("confidence", 0.0) or 0.0)
        ))
    else:
        representative = {
            "decision": winner, "reasoning": (
                "No majority across self-consistency samples — fail-safe insufficient_evidence."
            ),
            "evidence_used": [], "contradictions_found": [], "decision_basis": "not_addressed",
        }
    representative["decision"] = winner
    representative["confidence"] = winning_votes / len(samples)  # agreement ratio

    return representative, {"samples": len(samples), "tally": tally, "winner": winner}


async def _evaluate_mandatory_check(
    check: MandatoryCheck,
    target: ExtractionTarget,
    relevant_facts: list[dict],
    vendor_id: str,
    org_id: str = "",
    org_settings=None,
    retried_fact_types: list[str] | None = None,
    run_id: str = "",
    critic_feedback: str = "",
) -> ComplianceDecision:
    facts_text = (
        json.dumps(relevant_facts, indent=2, default=str)
        if relevant_facts
        else "No facts extracted for this requirement."
    )
    # P1.9 — inject this org's past human corrections for THIS check as calibration
    # examples. Empty string when the bank is off/empty → prompt unchanged.
    few_shot = build_few_shot_block(org_id, "check", check.check_id, check.name)
    messages = [
        {"role": "system", "content": get_prompt("evaluation/evaluate_check")},
        {
            "role": "user",
            "content": (
                f"{_feedback_block(critic_feedback)}"
                f"Requirement: {check.name}\n"
                f"Description: {check.description}\n"
                f"What passes: {check.what_passes}\n"
                f"Extraction target: {target.name} — {target.description}\n\n"
                f"Extracted facts:\n{facts_text}\n\n"
                f"{few_shot}"
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
    # P1.7 — self-consistency voting (borderline checks only). Returns ONE representative
    # parsed dict (so the contradiction override + fallback + construction below are
    # untouched) plus a vote breakdown for audit.
    parsed, vote_breakdown = await _decide_check_with_voting(messages)

    try:
        decision = ComplianceStatus(parsed.get("decision", "insufficient_evidence"))
    except ValueError:
        decision = ComplianceStatus.INSUFFICIENT_EVIDENCE

    # E3.b — a flagged contradiction means compliance cannot be confirmed, whatever
    # the model proposed. Force insufficient_evidence and never let the optimistic
    # chunk-fallback below flip it to PASS by re-finding the value that happens to pass.
    contradictions = parsed.get("contradictions_found") or []
    if contradictions:
        decision = ComplianceStatus.INSUFFICIENT_EVIDENCE

    # Fallback: fire when (a) no facts + insufficient_evidence, OR
    # (b) facts exist but decision is FAIL and extraction was NOT already retried
    # by the extraction critic (which would mean the failure is genuine).
    # extraction_was_retried prevents looping between the two critics.
    extraction_was_retried = target.fact_type in (retried_fact_types or [])
    should_fallback = org_id and not contradictions and (
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

    evidence = chunk_evidence if chunk_evidence else (parsed.get("evidence_used") or [])

    return ComplianceDecision(
        check_id=check.check_id,
        vendor_id=vendor_id,
        decision=decision,
        confidence=float(parsed.get("confidence", 0.5)),
        reasoning=parsed.get("reasoning", ""),
        evidence_used=evidence,
        contradictions_found=parsed.get("contradictions_found", []),
        decision_basis=decision_basis,
        vote_breakdown=vote_breakdown,
    )


async def _score_criterion(
    criterion: ScoringCriterion,
    relevant_facts: list[dict],
    vendor_id: str,
    critic_feedback: str = "",
    org_id: str = "",
) -> CriterionScore:
    has_facts = bool(relevant_facts)
    # E3 — no forced scores: if NO evidence feeds this criterion, do not ask the
    # LLM to invent a 0. Declare insufficient evidence so the ranking/report/UI
    # can distinguish "we couldn't assess this" from a genuine 0/10.
    if not has_facts:
        return CriterionScore(
            criterion_id=criterion.criterion_id,
            vendor_id=vendor_id,
            raw_score=0,
            weighted_contribution=0.0,
            confidence=0.0,
            rubric_band_applied="insufficient_evidence",
            evidence_used=[],
            score_rationale=(
                "No evidence was extracted for this criterion; marked insufficient "
                "rather than scored. Requires human review."
            ),
            variance_estimate=0.0,
            insufficient_evidence=True,
        )
    facts_text = json.dumps(relevant_facts, indent=2, default=str)
    # P1.9 — inject this org's past human corrections for THIS criterion as calibration
    # examples. Empty string when the bank is off/empty → prompt unchanged.
    few_shot = build_few_shot_block(org_id, "criterion", criterion.criterion_id, criterion.name)
    messages = [
        {"role": "system", "content": get_prompt("evaluation/score_criterion")},
        {
            "role": "user",
            "content": (
                f"{_feedback_block(critic_feedback)}"
                f"Criterion: {criterion.name}\n\n"
                f"Rubric:\n"
                f"9-10: {criterion.rubric_9_10}\n"
                f"6-8:  {criterion.rubric_6_8}\n"
                f"3-5:  {criterion.rubric_3_5}\n"
                f"0-2:  {criterion.rubric_0_2}\n\n"
                f"Extracted facts:\n{facts_text}\n\n"
                f"{few_shot}"
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
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        parsed = {"raw_score": 0, "confidence": 0.0, "rubric_band_applied": "0-2", "evidence_used": [], "score_rationale": "LLM returned invalid JSON", "variance_estimate": 3.0}

    raw_score = max(0, min(10, int(float(parsed.get("raw_score") or 0))))

    return CriterionScore(
        criterion_id=criterion.criterion_id,
        vendor_id=vendor_id,
        raw_score=raw_score,
        weighted_contribution=round((raw_score / 10) * criterion.weight, 4),
        confidence=float(parsed.get("confidence", 0.5)),
        rubric_band_applied=parsed.get("rubric_band_applied", "0-2"),
        evidence_used=(parsed.get("evidence_used") or []),
        score_rationale=parsed.get("score_rationale", ""),
        variance_estimate=float(parsed.get("variance_estimate", 1.0)),
    )


async def run_evaluation_agent(
    vendor_id: str,
    org_id: str,
    evaluation_setup: EvaluationSetup,
    extraction_output: Optional[ExtractionOutput] = None,
    run_id: str = "",
    critic_feedback: str = "",
) -> tuple[EvaluationOutput, object]:
    """Phase 2c: optionally accepts `critic_feedback` from a previous attempt's
    critic verdict. When non-empty it is prepended (via `_feedback_block`) to the
    mandatory-check and criterion-scoring prompts so the LLM corrects course.
    Empty string on the first attempt is a no-op."""
    mark_agent("evaluation_agent")  # cost attribution for this task's LLM calls
    evaluation_id = str(uuid.uuid4())
    warnings: list[str] = []

    from app.domain.org_settings import get_org_settings
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
                critic_feedback=critic_feedback,
            )
            compliance_decisions.append(decision)
        except Exception as e:
            warnings.append(f"Check {check.check_id} failed: {e}")

    # P1.7 — surface how many checks were resampled by self-consistency voting this run
    # (cost visibility: extra LLM calls fire only inside the borderline band).
    voted_checks = sum(
        1 for d in compliance_decisions if d.vote_breakdown.get("samples", 1) > 1
    )
    if voted_checks:
        import logging
        logging.getLogger(__name__).info(
            "self_consistency: %d/%d mandatory checks resampled (vendor=%s)",
            voted_checks, len(compliance_decisions), vendor_id,
        )

    # Score every criterion
    criterion_scores: list[CriterionScore] = []
    for criterion in evaluation_setup.scoring_criteria:
        relevant: list[dict] = []
        for tid in criterion.extraction_target_ids:
            target = target_by_id.get(tid)
            if target:
                relevant.extend(_get_facts_for_target(facts, target))
        if not relevant:
            warnings.append(
                f"Criterion {criterion.criterion_id} ({criterion.name}): no targeted facts found — "
                "marked INSUFFICIENT EVIDENCE (not scored). Requires human review."
            )
        try:
            score = await _score_criterion(criterion, relevant, vendor_id,
                                           critic_feedback=critic_feedback,
                                           org_id=org_id)
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

    # total_weighted_score is on a 0–10 scale. Each criterion's weighted_contribution is
    # (raw/10)*weight and the weights sum to 1.0, so the bare sum is 0–1; multiply by 10 so
    # the total matches the 0–10 per-criterion raw scores AND the 0–10 recommendation_thresholds
    # in platform.yaml (decision._recommendation compares against this value).
    total_score = round(sum(s.weighted_contribution for s in criterion_scores) * 10, 2)
    # Confidence reflects only the criteria we could actually score — an
    # insufficient-evidence criterion carries no signal and must not drag it down.
    scored = [s for s in criterion_scores if not s.insufficient_evidence]
    avg_confidence = (
        round(sum(s.confidence for s in scored) / len(scored), 3) if scored else 0.0
    )
    insufficient_criteria = [s.criterion_id for s in criterion_scores if s.insufficient_evidence]

    # E3.d — coverage-normalised score. `coverage` is the fraction of total criterion
    # weight actually assessed; insufficient-evidence criteria contribute 0 to
    # total_weighted_score (an absolute view), so we also project the observed quality
    # over the assessed weight onto 0–10. Ranking/recommendation use the normalised score
    # so a partially-assessed vendor isn't treated as if it scored 0 on the gaps.
    weight_by_criterion = {
        c.criterion_id: c.weight for c in evaluation_setup.scoring_criteria
    }
    total_weight = sum(weight_by_criterion.values())
    assessed_weight = sum(
        weight_by_criterion.get(s.criterion_id, 0.0)
        for s in criterion_scores
        if not s.insufficient_evidence
    )
    coverage = round(assessed_weight / total_weight, 4) if total_weight else 0.0
    coverage_normalised_score = (
        round(total_score / coverage, 2) if coverage else 0.0
    )

    if insufficient_criteria:
        warnings.append(
            "Insufficient evidence to score: " + ", ".join(insufficient_criteria)
            + " — flagged for human review and excluded from the confidence average. "
            f"Coverage {coverage:.2f}; ranking uses the coverage-normalised score "
            f"{coverage_normalised_score:.2f} (vs absolute total {total_score:.2f}) so the "
            "un-assessed criteria don't count as genuine 0s (E3.d)."
        )

    output = EvaluationOutput(
        evaluation_id=evaluation_id,
        vendor_id=vendor_id,
        compliance_decisions=compliance_decisions,
        criterion_scores=criterion_scores,
        overall_compliance=overall_compliance,
        total_weighted_score=total_score,
        coverage=coverage,
        coverage_normalised_score=coverage_normalised_score,
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
