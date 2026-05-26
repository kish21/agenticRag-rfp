"""
Extraction critic retry loop.

Runs judge_extraction on every extracted fact against each mandatory check and
scoring criterion. Fires focused LLM retries when all high-confidence verdicts
fail. Emits one audit event per fact judgment.
"""
import json
from dataclasses import dataclass, field

from app.config import settings
from app.providers.llm import call_llm
from app.prompts.registry import get_prompt
from app.schemas.output_models import EvaluationSetup

from .parsing import (
    _parse_certifications,
    _parse_extracted_facts,
    _parse_insurance,
    _parse_pricing,
    _parse_projects,
    _parse_slas,
)
from .prompts import _focused_schema
from .scoring import _fact_fields_for_critic


@dataclass
class FactsState:
    certifications: list = field(default_factory=list)
    insurance: list = field(default_factory=list)
    slas: list = field(default_factory=list)
    projects: list = field(default_factory=list)
    pricing: list = field(default_factory=list)
    extracted_facts: list = field(default_factory=list)
    retried_fact_types: set = field(default_factory=set)
    warnings: list = field(default_factory=list)


async def run_extraction_critic_retries(
    state: FactsState,
    org_id: str,
    vendor_id: str,
    run_id: str,
    context: str,
    evaluation_setup: EvaluationSetup,
) -> FactsState:
    """Mutates and returns state with retried facts and updated warnings/retried_fact_types."""
    from app.validators.extraction import judge_extraction
    from app.infra.audit import audit as _audit

    target_by_id = {t.target_id: t for t in (evaluation_setup.extraction_targets or [])}
    _max_retries = settings.platform.infrastructure.extraction_critic_max_retries
    _conf_floor = settings.platform.infrastructure.extraction_critic_confidence_floor

    # Build: fact_type → [(criterion_name, what_passes)] from mandatory checks
    check_by_fact_type: dict[str, list[tuple[str, str]]] = {}
    for chk in (evaluation_setup.mandatory_checks or []):
        tgt = target_by_id.get(chk.extraction_target_id)
        if tgt and tgt.fact_type in ("insurance", "certification", "sla", "project", "pricing"):
            check_by_fact_type.setdefault(tgt.fact_type, []).append(
                (chk.name, chk.what_passes)
            )

    # ── Standard fact types vs mandatory checks ────────────────────────────────
    _type_configs = [
        ("insurance",     state.insurance,      _parse_insurance,      "insurance"),
        ("certification", state.certifications, _parse_certifications, "certifications"),
        ("sla",           state.slas,           _parse_slas,           "slas"),
        ("project",       state.projects,       _parse_projects,       "projects"),
        ("pricing",       state.pricing,        _parse_pricing,        "pricing"),
    ]

    for fact_type, fact_list, parse_fn, response_key in _type_configs:
        criteria = check_by_fact_type.get(fact_type)
        if not criteria:
            continue

        criterion_name, what_passes = criteria[0]
        high_conf_fails: list[str] = []
        high_conf_passes: int = 0
        wrong_value_parts: list[str] = []

        if not fact_list:
            high_conf_fails = [f"No {fact_type} facts found in initial extraction"]
            wrong_value_parts = ["(empty)"]
        else:
            for fact in fact_list:
                fields = _fact_fields_for_critic(fact)
                verdict = await judge_extraction(
                    criterion_name=criterion_name,
                    what_passes=what_passes,
                    grounding_quote=fact.grounding_quote,
                    **fields,
                )
                _audit(
                    org_id=org_id,
                    run_id=run_id or None,
                    event_type="extraction_critic.verdict",
                    actor="extraction_critic",
                    detail={
                        "vendor_id": vendor_id,
                        "fact_type": fact_type,
                        "criterion_name": criterion_name,
                        "adequate": verdict.adequate,
                        "confidence": verdict.confidence,
                        "missing": verdict.missing,
                        "should_retry": verdict.should_retry,
                        "retry_count": 0,
                    },
                )
                if verdict.confidence >= _conf_floor:
                    if verdict.adequate:
                        high_conf_passes += 1
                    else:
                        high_conf_fails.append(verdict.missing)
                        wrong_value_parts.append(
                            f"{fields['fact_type']} {fields['fact_value']}".strip()
                        )

        should_retry = (
            len(high_conf_fails) > 0
            and high_conf_passes == 0
            and _max_retries > 0
            and fact_type not in state.retried_fact_types
        )
        if not should_retry:
            continue

        state.retried_fact_types.add(fact_type)
        wrong_summary = "; ".join(wrong_value_parts[:3])
        missing_summary = high_conf_fails[0]

        retry_system = get_prompt(
            "extraction/retry_extract",
            criterion_name=criterion_name,
            what_passes=what_passes,
            wrong_summary=wrong_summary,
            missing_summary=missing_summary,
            target_desc="",
            response_key=response_key,
            schema=_focused_schema(fact_type),
        )

        try:
            retry_raw_text = await call_llm(
                messages=[
                    {"role": "system", "content": retry_system},
                    {"role": "user", "content": f"Extract from the following vendor document chunks:\n\n{context}"},
                ],
                temperature=0.0,
                response_format={"type": "json_object"},
            )
            retry_raw = json.loads(retry_raw_text)
            retry_facts = parse_fn(retry_raw.get(response_key, []), state.warnings)

            retry_adequate = True
            for fact in retry_facts:
                fields = _fact_fields_for_critic(fact)
                v2 = await judge_extraction(
                    criterion_name=criterion_name,
                    what_passes=what_passes,
                    grounding_quote=fact.grounding_quote,
                    **fields,
                )
                _audit(
                    org_id=org_id,
                    run_id=run_id or None,
                    event_type="extraction_critic.verdict",
                    actor="extraction_critic",
                    detail={
                        "vendor_id": vendor_id,
                        "fact_type": fact_type,
                        "criterion_name": criterion_name,
                        "adequate": v2.adequate,
                        "confidence": v2.confidence,
                        "missing": v2.missing,
                        "should_retry": v2.should_retry,
                        "retry_count": 1,
                    },
                )
                if not v2.adequate and v2.confidence >= _conf_floor:
                    retry_adequate = False

            if fact_type == "insurance":
                state.insurance = retry_facts
            elif fact_type == "certification":
                state.certifications = retry_facts
            elif fact_type == "sla":
                state.slas = retry_facts
            elif fact_type == "project":
                state.projects = retry_facts
            elif fact_type == "pricing":
                state.pricing = retry_facts

            if not retry_adequate:
                state.warnings.append(
                    f"extraction_critic: retry for {fact_type}/{criterion_name} still inadequate"
                )

        except Exception as exc:
            state.warnings.append(f"extraction_critic retry failed for {fact_type}: {exc}")

    # ── Custom targets vs mandatory checks ─────────────────────────────────────
    for chk in (evaluation_setup.mandatory_checks or []):
        tgt = target_by_id.get(chk.extraction_target_id)
        if not tgt or tgt.fact_type != "custom":
            continue
        target_id = tgt.target_id
        criterion_name = chk.name
        what_passes = chk.what_passes
        custom_key = f"custom:{target_id}"
        if custom_key in state.retried_fact_types:
            continue

        fact_list = [f for f in state.extracted_facts if f.target_id == target_id]
        if not fact_list:
            continue

        high_conf_fails_c: list[str] = []
        high_conf_passes_c: int = 0
        wrong_value_parts_c: list[str] = []

        for fact in fact_list:
            verdict = await judge_extraction(
                criterion_name=criterion_name,
                what_passes=what_passes,
                fact_type=fact.fact_type,
                fact_value=(fact.text_value or "")[:300],
                provider_or_issuer="",
                key_identifier=(
                    str(fact.numeric_value) if fact.numeric_value is not None
                    else str(fact.boolean_value) if fact.boolean_value is not None
                    else ""
                ),
                grounding_quote=fact.grounding_quote,
            )
            _audit(
                org_id=org_id,
                run_id=run_id or None,
                event_type="extraction_critic.verdict",
                actor="extraction_critic",
                detail={
                    "vendor_id": vendor_id,
                    "fact_type": "custom",
                    "target_id": target_id,
                    "criterion_name": criterion_name,
                    "adequate": verdict.adequate,
                    "confidence": verdict.confidence,
                    "missing": verdict.missing,
                    "should_retry": verdict.should_retry,
                    "retry_count": 0,
                },
            )
            if verdict.confidence >= _conf_floor:
                if verdict.adequate:
                    high_conf_passes_c += 1
                else:
                    high_conf_fails_c.append(verdict.missing)
                    wrong_value_parts_c.append((fact.text_value or "")[:80])

        should_retry_c = (
            len(high_conf_fails_c) > 0
            and high_conf_passes_c == 0
            and _max_retries > 0
        )
        if not should_retry_c:
            continue

        state.retried_fact_types.add(custom_key)
        wrong_summary_c = "; ".join(wrong_value_parts_c[:3])
        missing_summary_c = high_conf_fails_c[0]

        retry_system_c = get_prompt(
            "extraction/retry_extract",
            criterion_name=criterion_name,
            what_passes=what_passes,
            wrong_summary=wrong_summary_c,
            missing_summary=missing_summary_c,
            target_desc=f"  Target: {tgt.name} - {tgt.description}\n",
            response_key="extracted_facts",
            schema=_focused_schema("custom", target_id=target_id),
        )

        try:
            retry_raw_text_c = await call_llm(
                messages=[
                    {"role": "system", "content": retry_system_c},
                    {"role": "user", "content": f"Extract from the following vendor document chunks:\n\n{context}"},
                ],
                temperature=0.0,
                response_format={"type": "json_object"},
            )
            retry_raw_c = json.loads(retry_raw_text_c)
            retry_custom = _parse_extracted_facts(
                [f for f in retry_raw_c.get("extracted_facts", []) if f.get("target_id") == target_id],
                state.warnings,
            )

            retry_adequate_c = True
            for fact in retry_custom:
                v2 = await judge_extraction(
                    criterion_name=criterion_name,
                    what_passes=what_passes,
                    fact_type=fact.fact_type,
                    fact_value=(fact.text_value or "")[:300],
                    provider_or_issuer="",
                    key_identifier=(
                        str(fact.numeric_value) if fact.numeric_value is not None
                        else str(fact.boolean_value) if fact.boolean_value is not None
                        else ""
                    ),
                    grounding_quote=fact.grounding_quote,
                )
                _audit(
                    org_id=org_id,
                    run_id=run_id or None,
                    event_type="extraction_critic.verdict",
                    actor="extraction_critic",
                    detail={
                        "vendor_id": vendor_id,
                        "fact_type": "custom",
                        "target_id": target_id,
                        "criterion_name": criterion_name,
                        "adequate": v2.adequate,
                        "confidence": v2.confidence,
                        "missing": v2.missing,
                        "should_retry": v2.should_retry,
                        "retry_count": 1,
                    },
                )
                if not v2.adequate and v2.confidence >= _conf_floor:
                    retry_adequate_c = False

            state.extracted_facts = (
                [f for f in state.extracted_facts if f.target_id != target_id] + retry_custom
            )

            if not retry_adequate_c:
                state.warnings.append(
                    f"extraction_critic: retry for custom/{criterion_name} still inadequate"
                )

        except Exception as exc:
            state.warnings.append(f"extraction_critic retry failed for custom/{criterion_name}: {exc}")

    # ── Scoring criteria — judge facts for each criterion's extraction targets ──
    _type_to_list = {
        "insurance":     lambda: state.insurance,
        "certification": lambda: state.certifications,
        "sla":           lambda: state.slas,
        "project":       lambda: state.projects,
        "pricing":       lambda: state.pricing,
    }
    _type_parse = {
        "insurance":     ("insurance",      _parse_insurance),
        "certification": ("certifications", _parse_certifications),
        "sla":           ("slas",           _parse_slas),
        "project":       ("projects",       _parse_projects),
        "pricing":       ("pricing",        _parse_pricing),
    }

    for crit in (evaluation_setup.scoring_criteria or []):
        for target_id in (crit.extraction_target_ids or []):
            tgt = target_by_id.get(target_id)
            if not tgt:
                continue
            scoring_key = f"scoring:{crit.criterion_id}:{target_id}"
            if scoring_key in state.retried_fact_types:
                continue

            is_custom = tgt.fact_type == "custom"
            if is_custom:
                fact_list = [f for f in state.extracted_facts if f.target_id == target_id]
            else:
                getter = _type_to_list.get(tgt.fact_type)
                fact_list = getter() if getter else []

            if not fact_list:
                continue

            sc_criterion_name = crit.name
            sc_what_passes = crit.rubric_9_10
            high_conf_fails_sc: list[str] = []
            high_conf_passes_sc: int = 0
            wrong_value_parts_sc: list[str] = []

            for fact in fact_list:
                if is_custom:
                    verdict = await judge_extraction(
                        criterion_name=sc_criterion_name,
                        what_passes=sc_what_passes,
                        fact_type=fact.fact_type,
                        fact_value=(fact.text_value or "")[:300],
                        provider_or_issuer="",
                        key_identifier=(
                            str(fact.numeric_value) if fact.numeric_value is not None
                            else str(fact.boolean_value) if fact.boolean_value is not None
                            else ""
                        ),
                        grounding_quote=fact.grounding_quote,
                    )
                    wrong_val = (fact.text_value or "")[:80]
                else:
                    fields = _fact_fields_for_critic(fact)
                    verdict = await judge_extraction(
                        criterion_name=sc_criterion_name,
                        what_passes=sc_what_passes,
                        grounding_quote=fact.grounding_quote,
                        **fields,
                    )
                    wrong_val = f"{fields['fact_type']} {fields['fact_value']}".strip()

                _audit(
                    org_id=org_id,
                    run_id=run_id or None,
                    event_type="extraction_critic.verdict",
                    actor="extraction_critic",
                    detail={
                        "vendor_id": vendor_id,
                        "fact_type": tgt.fact_type,
                        "target_id": target_id,
                        "criterion_id": crit.criterion_id,
                        "criterion_name": sc_criterion_name,
                        "scope": "scoring",
                        "adequate": verdict.adequate,
                        "confidence": verdict.confidence,
                        "missing": verdict.missing,
                        "should_retry": verdict.should_retry,
                        "retry_count": 0,
                    },
                )
                if verdict.confidence >= _conf_floor:
                    if verdict.adequate:
                        high_conf_passes_sc += 1
                    else:
                        high_conf_fails_sc.append(verdict.missing)
                        wrong_value_parts_sc.append(wrong_val)

            should_retry_sc = (
                len(high_conf_fails_sc) > 0
                and high_conf_passes_sc == 0
                and _max_retries > 0
            )
            if not should_retry_sc:
                continue

            state.retried_fact_types.add(scoring_key)
            wrong_summary_sc = "; ".join(wrong_value_parts_sc[:3])
            missing_summary_sc = high_conf_fails_sc[0]

            if is_custom:
                retry_schema_sc = _focused_schema("custom", target_id=target_id)
                response_key_sc = "extracted_facts"
                parse_fn_sc = None
                target_desc_sc = f"  Target: {tgt.name} — {tgt.description}\n"
            else:
                response_key_sc, parse_fn_sc = _type_parse.get(tgt.fact_type, ("", None))
                if not response_key_sc:
                    continue
                retry_schema_sc = _focused_schema(tgt.fact_type)
                target_desc_sc = ""

            retry_system_sc = get_prompt(
                "extraction/retry_extract",
                criterion_name=sc_criterion_name,
                what_passes=sc_what_passes,
                wrong_summary=wrong_summary_sc,
                missing_summary=missing_summary_sc,
                target_desc=target_desc_sc,
                response_key=response_key_sc,
                schema=retry_schema_sc,
            )

            try:
                retry_raw_text_sc = await call_llm(
                    messages=[
                        {"role": "system", "content": retry_system_sc},
                        {"role": "user", "content": f"Extract from the following vendor document chunks:\n\n{context}"},
                    ],
                    temperature=0.0,
                    response_format={"type": "json_object"},
                )
                retry_raw_sc = json.loads(retry_raw_text_sc)

                if is_custom:
                    retry_facts_sc = _parse_extracted_facts(
                        [f for f in retry_raw_sc.get("extracted_facts", []) if f.get("target_id") == target_id],
                        state.warnings,
                    )
                else:
                    retry_facts_sc = parse_fn_sc(retry_raw_sc.get(response_key_sc, []), state.warnings)

                retry_adequate_sc = True
                for fact in retry_facts_sc:
                    if is_custom:
                        v2 = await judge_extraction(
                            criterion_name=sc_criterion_name,
                            what_passes=sc_what_passes,
                            fact_type=fact.fact_type,
                            fact_value=(fact.text_value or "")[:300],
                            provider_or_issuer="",
                            key_identifier=(
                                str(fact.numeric_value) if fact.numeric_value is not None
                                else str(fact.boolean_value) if fact.boolean_value is not None
                                else ""
                            ),
                            grounding_quote=fact.grounding_quote,
                        )
                    else:
                        fields2 = _fact_fields_for_critic(fact)
                        v2 = await judge_extraction(
                            criterion_name=sc_criterion_name,
                            what_passes=sc_what_passes,
                            grounding_quote=fact.grounding_quote,
                            **fields2,
                        )
                    _audit(
                        org_id=org_id,
                        run_id=run_id or None,
                        event_type="extraction_critic.verdict",
                        actor="extraction_critic",
                        detail={
                            "vendor_id": vendor_id,
                            "fact_type": tgt.fact_type,
                            "target_id": target_id,
                            "criterion_id": crit.criterion_id,
                            "criterion_name": sc_criterion_name,
                            "scope": "scoring",
                            "adequate": v2.adequate,
                            "confidence": v2.confidence,
                            "missing": v2.missing,
                            "should_retry": v2.should_retry,
                            "retry_count": 1,
                        },
                    )
                    if not v2.adequate and v2.confidence >= _conf_floor:
                        retry_adequate_sc = False

                if is_custom:
                    state.extracted_facts = (
                        [f for f in state.extracted_facts if f.target_id != target_id] + retry_facts_sc
                    )
                elif tgt.fact_type == "insurance":
                    state.insurance = retry_facts_sc
                elif tgt.fact_type == "certification":
                    state.certifications = retry_facts_sc
                elif tgt.fact_type == "sla":
                    state.slas = retry_facts_sc
                elif tgt.fact_type == "project":
                    state.projects = retry_facts_sc
                elif tgt.fact_type == "pricing":
                    state.pricing = retry_facts_sc

                if not retry_adequate_sc:
                    state.warnings.append(
                        f"extraction_critic: retry for scoring/{sc_criterion_name}/{tgt.fact_type} still inadequate"
                    )

            except Exception as exc:
                state.warnings.append(f"extraction_critic retry failed for scoring/{sc_criterion_name}: {exc}")

    return state
