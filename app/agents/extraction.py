"""
Extraction Agent — reads retrieved chunks, extracts typed facts, stores in PostgreSQL.

Pipeline:
1. Build source context from RetrievalOutput chunks
2. Call LLM (temperature=0.0) to extract all six fact types
3. Parse JSON response into Pydantic models
4. Calculate extraction_completeness and hallucination_risk
5. Critic verifies every grounding_quote programmatically
6. Save to PostgreSQL only if Critic approves
"""
import json
import re
import uuid
from datetime import date
from typing import Optional

from app.config import settings
from app.core.llm_provider import call_llm
from app.core.output_models import (
    CriticVerdict,
    DocumentStatus,
    EvaluationSetup,
    ExtractionOutput,
    ExtractedCertification,
    ExtractedFact,
    ExtractedInsurance,
    ExtractedPricing,
    ExtractedProject,
    ExtractedSLA,
    RetrievalOutput,
)
from app.agents.critic import critic_after_extraction
from app.db.fact_store import save_extraction_output


def _schema_description(extraction_targets: list[dict]) -> str:
    custom_targets = [t for t in extraction_targets if t.get("fact_type") == "custom"]
    custom_block = ""
    if custom_targets:
        targets_text = "\n".join(
            f'  - target_id="{t["target_id"]}", name="{t["name"]}", description="{t["description"]}"'
            for t in custom_targets
        )
        custom_block = f"""
extracted_facts: array of custom facts per the ExtractionTarget list below.
  For each target, find the best matching evidence and return one object:
    fact_id (uuid string), target_id, fact_type, fact_name,
    text_value (string summary), numeric_value (number or null),
    boolean_value (true/false or null), confidence (0.0-1.0), grounding_quote, source_chunk_id

  ExtractionTargets to extract:
{targets_text}"""
    else:
        custom_block = "extracted_facts: [] (no custom targets defined)"

    return f"""Return a JSON object with this exact structure:

{{
  "certifications": [
    {{
      "standard_name": "name of the standard e.g. a security or quality standard",
      "version": "2022 or null",
      "cert_number": "string or null",
      "issuing_body": "string or null",
      "scope": "string or null",
      "valid_until": "YYYY-MM-DD or null",
      "status": "current|pending|expired|not_mentioned",
      "confidence": 0.0-1.0,
      "grounding_quote": "exact verbatim sentence from source",
      "source_chunk_id": "chunk_id from context header"
    }}
  ],
  "insurance": [
    {{
      "insurance_type": "Professional Indemnity etc",
      "amount_gbp": number or null,
      "provider": "string or null",
      "confidence": 0.0-1.0,
      "grounding_quote": "exact verbatim sentence",
      "source_chunk_id": "chunk_id"
    }}
  ],
  "slas": [
    {{
      "priority_level": "P1/P2/Critical etc or null",
      "response_minutes": integer or null,
      "resolution_hours": integer or null,
      "uptime_percentage": float or null,
      "confidence": 0.0-1.0,
      "grounding_quote": "exact verbatim text from source — see table rules below",
      "source_chunk_id": "chunk_id"
    }}
  ],
  "projects": [
    {{
      "client_name": "string or null",
      "client_sector": "string or null",
      "user_count": integer or null,
      "outcomes": "string or null",
      "reference_available": true/false/null,
      "confidence": 0.0-1.0,
      "grounding_quote": "exact verbatim sentence",
      "source_chunk_id": "chunk_id"
    }}
  ],
  "pricing": [
    {{
      "year": integer or null,
      "amount_gbp": number or null,
      "total_gbp": number or null,
      "includes": ["item1", "item2"],
      "confidence": 0.0-1.0,
      "grounding_quote": "exact verbatim sentence",
      "source_chunk_id": "chunk_id"
    }}
  ],
  {custom_block}
}}"""


def _parse_date(v: Optional[str]) -> Optional[date]:
    if not v:
        return None
    try:
        return date.fromisoformat(v)
    except (ValueError, TypeError):
        return None


def _parse_certifications(raw: list, warnings: list[str]) -> list[ExtractedCertification]:
    results = []
    for item in raw:
        try:
            status_val = item.get("status", "not_mentioned")
            try:
                status = DocumentStatus(status_val)
            except ValueError:
                status = DocumentStatus.NOT_MENTIONED
            results.append(ExtractedCertification(
                standard_name=item["standard_name"],
                version=item.get("version"),
                cert_number=item.get("cert_number"),
                issuing_body=item.get("issuing_body"),
                scope=item.get("scope"),
                valid_until=_parse_date(item.get("valid_until")),
                status=status,
                confidence=float(item.get("confidence", 0.5)),
                grounding_quote=item.get("grounding_quote", ""),
                source_chunk_id=item.get("source_chunk_id", ""),
            ))
        except Exception as e:
            warnings.append(f"Skipped malformed certification: {e}")
    return results


def _parse_insurance(raw: list, warnings: list[str]) -> list[ExtractedInsurance]:
    results = []
    for item in raw:
        try:
            results.append(ExtractedInsurance(
                insurance_type=item.get("insurance_type"),
                amount_gbp=item.get("amount_gbp"),
                provider=item.get("provider"),
                confidence=float(item.get("confidence", 0.5)),
                grounding_quote=item.get("grounding_quote", ""),
                source_chunk_id=item.get("source_chunk_id", ""),
            ))
        except Exception as e:
            warnings.append(f"Skipped malformed insurance: {e}")
    return results


def _parse_slas(raw: list, warnings: list[str]) -> list[ExtractedSLA]:
    results = []
    for item in raw:
        try:
            results.append(ExtractedSLA(
                priority_level=item.get("priority_level"),
                response_minutes=item.get("response_minutes"),
                resolution_hours=item.get("resolution_hours"),
                uptime_percentage=item.get("uptime_percentage"),
                confidence=float(item.get("confidence", 0.5)),
                grounding_quote=item.get("grounding_quote", ""),
                source_chunk_id=item.get("source_chunk_id", ""),
            ))
        except Exception as e:
            warnings.append(f"Skipped malformed SLA: {e}")
    return results


def _parse_projects(raw: list, warnings: list[str]) -> list[ExtractedProject]:
    results = []
    for item in raw:
        try:
            results.append(ExtractedProject(
                client_name=item.get("client_name"),
                client_sector=item.get("client_sector"),
                user_count=item.get("user_count"),
                outcomes=item.get("outcomes"),
                reference_available=item.get("reference_available"),
                confidence=float(item.get("confidence", 0.5)),
                grounding_quote=item.get("grounding_quote", ""),
                source_chunk_id=item.get("source_chunk_id", ""),
            ))
        except Exception as e:
            warnings.append(f"Skipped malformed project: {e}")
    return results


def _parse_pricing(raw: list, warnings: list[str]) -> list[ExtractedPricing]:
    results = []
    for item in raw:
        try:
            results.append(ExtractedPricing(
                year=item.get("year"),
                amount_gbp=item.get("amount_gbp"),
                total_gbp=item.get("total_gbp"),
                includes=item.get("includes", []),
                confidence=float(item.get("confidence", 0.5)),
                grounding_quote=item.get("grounding_quote", ""),
                source_chunk_id=item.get("source_chunk_id", ""),
            ))
        except Exception as e:
            warnings.append(f"Skipped malformed pricing: {e}")
    return results


def _parse_extracted_facts(raw: list, warnings: list[str]) -> list[ExtractedFact]:
    results = []
    for item in raw:
        try:
            results.append(ExtractedFact(
                fact_id=item.get("fact_id", str(uuid.uuid4())),
                target_id=item["target_id"],
                fact_type=item.get("fact_type", "custom"),
                fact_name=item.get("fact_name", item.get("target_id", "")),
                text_value=item.get("text_value", ""),
                numeric_value=item.get("numeric_value"),
                boolean_value=item.get("boolean_value"),
                confidence=float(item.get("confidence", 0.5)),
                grounding_quote=item.get("grounding_quote", ""),
                source_chunk_id=item.get("source_chunk_id", ""),
            ))
        except Exception as e:
            warnings.append(f"Skipped malformed extracted_fact: {e}")
    return results


def _fact_fields_for_critic(fact) -> dict:
    """Extract the fields needed by judge_extraction from any standard fact object."""
    name = type(fact).__name__
    if name == "ExtractedInsurance":
        return {
            "fact_type": fact.insurance_type or "unknown",
            "fact_value": str(fact.amount_gbp) if fact.amount_gbp is not None else "",
            "provider_or_issuer": fact.provider or "",
            "key_identifier": "",
        }
    if name == "ExtractedCertification":
        return {
            "fact_type": fact.standard_name or "certification",
            "fact_value": fact.cert_number or "",
            "provider_or_issuer": fact.issuing_body or "",
            "key_identifier": str(fact.valid_until) if fact.valid_until else "",
        }
    if name == "ExtractedSLA":
        return {
            "fact_type": fact.priority_level or "SLA",
            "fact_value": str(fact.uptime_percentage or fact.response_minutes or ""),
            "provider_or_issuer": "",
            "key_identifier": str(fact.resolution_hours or ""),
        }
    if name == "ExtractedProject":
        return {
            "fact_type": "project",
            "fact_value": (fact.outcomes or "")[:200],
            "provider_or_issuer": fact.client_name or "",
            "key_identifier": str(fact.user_count or ""),
        }
    if name == "ExtractedPricing":
        return {
            "fact_type": "pricing",
            "fact_value": str(fact.total_gbp or fact.amount_gbp or ""),
            "provider_or_issuer": "",
            "key_identifier": str(fact.year or ""),
        }
    return {"fact_type": "unknown", "fact_value": "", "provider_or_issuer": "", "key_identifier": ""}


def _focused_schema(fact_type: str, target_id: str = "") -> str:
    """Return a minimal inline JSON schema for a single fact type (used in retry prompts)."""
    if fact_type == "custom":
        return (
            f'{{"extracted_facts": [{{"fact_id": "<uuid>", "target_id": "{target_id}", '
            '"fact_type": "custom", "fact_name": "...", "text_value": "...", '
            '"numeric_value": <number or null>, "boolean_value": <bool or null>, '
            '"confidence": <0.0-1.0>, "grounding_quote": "<exact verbatim sentence>", '
            '"source_chunk_id": "<chunk_id>"}}]}}'
        )
    schemas = {
        "insurance": (
            '{"insurance": [{"insurance_type": "...", "amount_gbp": <number or null>, '
            '"provider": "...", "confidence": <0.0-1.0>, '
            '"grounding_quote": "<exact verbatim sentence>", "source_chunk_id": "..."}]}'
        ),
        "certification": (
            '{"certifications": [{"standard_name": "...", "version": "...", "cert_number": "...", '
            '"issuing_body": "...", "scope": "...", "valid_until": "<YYYY-MM-DD or null>", '
            '"status": "<current|pending|expired|not_mentioned>", "confidence": <0.0-1.0>, '
            '"grounding_quote": "<exact verbatim sentence>", "source_chunk_id": "..."}]}'
        ),
        "sla": (
            '{"slas": [{"priority_level": "...", "response_minutes": <int or null>, '
            '"resolution_hours": <int or null>, "uptime_percentage": <float or null>, '
            '"confidence": <0.0-1.0>, "grounding_quote": "<exact verbatim text>", '
            '"source_chunk_id": "..."}]}'
        ),
        "project": (
            '{"projects": [{"client_name": "...", "client_sector": "...", '
            '"user_count": <int or null>, "outcomes": "...", "reference_available": <bool or null>, '
            '"confidence": <0.0-1.0>, "grounding_quote": "<exact verbatim sentence>", '
            '"source_chunk_id": "..."}]}'
        ),
        "pricing": (
            '{"pricing": [{"year": <int or null>, "amount_gbp": <number or null>, '
            '"total_gbp": <number or null>, "includes": [], "confidence": <0.0-1.0>, '
            '"grounding_quote": "<exact verbatim sentence>", "source_chunk_id": "..."}]}'
        ),
    }
    return schemas.get(fact_type, "{}")


def _extraction_completeness(
    certifications: list,
    insurance: list,
    slas: list,
    projects: list,
    pricing: list,
    extracted_facts: list,
    extraction_targets: list[dict],
) -> float:
    standard_populated = sum([
        bool(certifications),
        bool(insurance),
        bool(slas),
        bool(projects),
        bool(pricing),
    ])
    custom_targets = [t for t in extraction_targets if t.get("fact_type") == "custom"]
    found_target_ids = {f.target_id for f in extracted_facts}
    custom_found = sum(1 for t in custom_targets if t["target_id"] in found_target_ids)
    total = 5 + len(custom_targets)
    achieved = standard_populated + custom_found
    return round(achieved / total, 3) if total > 0 else 1.0


def _normalise(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _quote_found(quote: str, source: str) -> bool:
    """Check verbatim match with whitespace normalisation (handles PDF table cell-per-line)."""
    if not quote or not source:
        return False
    return _normalise(quote) in _normalise(source)


def _hallucination_risk(
    all_facts: list,
    source_chunks: dict[str, str],
) -> float:
    if not all_facts:
        return 0.0
    risky = 0
    for fact in all_facts:
        gq = getattr(fact, "grounding_quote", "")
        chunk_id = getattr(fact, "source_chunk_id", "")
        source = source_chunks.get(chunk_id, "")
        if not _quote_found(gq, source):
            risky += 1
    return round(risky / len(all_facts), 3)


async def run_extraction_agent(
    retrieval_output: RetrievalOutput,
    vendor_id: str,
    org_id: str,
    doc_id: str,
    setup_id: str,
    evaluation_setup: EvaluationSetup,
    run_id: str = "",
) -> tuple[ExtractionOutput, object]:
    extraction_id = str(uuid.uuid4())
    warnings: list[str] = []

    # Step 1: Build source context
    source_chunks: dict[str, str] = {
        chunk.chunk_id: chunk.text
        for chunk in retrieval_output.chunks
    }
    context = "\n\n---\n\n".join(
        f"[{chunk.chunk_id}]\n{chunk.text}"
        for chunk in retrieval_output.chunks
    )

    if not context.strip():
        output = ExtractionOutput(
            extraction_id=extraction_id,
            vendor_id=vendor_id,
            org_id=org_id,
            source_chunk_ids=[],
            extraction_completeness=0.0,
            hallucination_risk=0.0,
            warnings=["No chunks in retrieval output — nothing to extract"],
        )
        critic = critic_after_extraction(output, source_chunks)
        return output, critic

    # Step 2: Prepare extraction targets from EvaluationSetup
    extraction_targets: list[dict] = [
        t.model_dump() for t in (evaluation_setup.extraction_targets or [])
    ]

    # Step 3: Call LLM for structured extraction
    schema_desc = _schema_description(extraction_targets)
    system_prompt = (
        "You are a structured fact extraction engine for enterprise vendor documents.\n"
        "Extract facts from the provided document chunks.\n\n"
        "Rules:\n"
        "1. For EVERY fact, provide grounding_quote — the EXACT verbatim text from the source.\n"
        "2. If you cannot find a verbatim quote, omit the fact entirely. Never invent quotes.\n"
        "3. source_chunk_id must match the chunk ID shown in [brackets] in the context.\n"
        "4. Only extract what is explicitly stated. Do not infer or assume.\n"
        "5. confidence reflects how clearly the fact is stated (0.9+ = explicit, 0.5-0.8 = implied).\n\n"
        "SLA table rules — grounding_quote for table data:\n"
        "- PDF tables are often parsed with each cell on its own line.\n"
        "- The grounding_quote must use the exact text as it appears in the chunk, including whitespace.\n"
        "- Copy the entire row content as a single string joining cells with a single space.\n"
        "- Example: if source has 'P1 Critical' then '15 minutes' then '4 hours' on separate lines,\n"
        "  grounding_quote must be exactly 'P1 Critical 15 minutes 4 hours'.\n"
        "- Do not add colons, dashes, or any punctuation not present in the source.\n"
        "- Do not quote only the header row (Priority, Response Time, Resolution Time).\n"
        "- For uptime guarantees, quote the full sentence verbatim.\n\n"
        + schema_desc
    )

    raw_text = await call_llm(
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"Extract from the following vendor document chunks:\n\n{context}"},
        ],
        temperature=0.0,
        response_format={"type": "json_object"},
    )

    # Step 4: Parse JSON response
    try:
        raw = json.loads(raw_text)
    except json.JSONDecodeError as e:
        warnings.append(f"LLM returned invalid JSON: {e}")
        raw = {}

    certifications = _parse_certifications(raw.get("certifications", []), warnings)
    insurance = _parse_insurance(raw.get("insurance", []), warnings)
    slas = _parse_slas(raw.get("slas", []), warnings)
    projects = _parse_projects(raw.get("projects", []), warnings)
    pricing = _parse_pricing(raw.get("pricing", []), warnings)
    extracted_facts = _parse_extracted_facts(raw.get("extracted_facts", []), warnings)

    # Step 4.5: Extraction critic — judge each fact type against its mandatory criterion.
    # For each type that has a mandatory check, run judge_extraction on every fact.
    # If all high-confidence verdicts are inadequate, retry that type with a focused prompt.
    # Caps at extraction_critic_max_retries per type. Emits one audit event per fact.
    retried_fact_types: set[str] = set()
    if org_id:
        from app.core.extraction_critic import judge_extraction
        from app.core.audit import audit as _audit

        # Build: fact_type → [(criterion_name, what_passes)] from mandatory checks
        target_by_id = {t.target_id: t for t in (evaluation_setup.extraction_targets or [])}
        check_by_fact_type: dict[str, list[tuple[str, str]]] = {}
        for chk in (evaluation_setup.mandatory_checks or []):
            tgt = target_by_id.get(chk.extraction_target_id)
            if tgt and tgt.fact_type in ("insurance", "certification", "sla", "project", "pricing"):
                check_by_fact_type.setdefault(tgt.fact_type, []).append(
                    (chk.name, chk.what_passes)
                )

        _max_retries = settings.platform.infrastructure.extraction_critic_max_retries
        _conf_floor = settings.platform.infrastructure.extraction_critic_confidence_floor

        # (fact_type, list_var, parse_fn, response_key)
        _type_configs = [
            ("insurance",     insurance,      _parse_insurance,      "insurance"),
            ("certification", certifications, _parse_certifications, "certifications"),
            ("sla",           slas,           _parse_slas,           "slas"),
            ("project",       projects,       _parse_projects,       "projects"),
            ("pricing",       pricing,        _parse_pricing,        "pricing"),
        ]

        for fact_type, fact_list, parse_fn, response_key in _type_configs:
            criteria = check_by_fact_type.get(fact_type)
            if not criteria:
                continue  # no mandatory check for this type

            criterion_name, what_passes = criteria[0]
            high_conf_fails: list[str] = []
            high_conf_passes: int = 0
            wrong_value_parts: list[str] = []

            if not fact_list:
                # Bulk extraction returned nothing — treat as immediate retry candidate
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

            # Retry when all high-confidence verdicts failed, or when bulk returned nothing
            should_retry = (
                len(high_conf_fails) > 0
                and high_conf_passes == 0
                and _max_retries > 0
                and fact_type not in retried_fact_types
            )
            if not should_retry:
                continue

            retried_fact_types.add(fact_type)
            wrong_summary = "; ".join(wrong_value_parts[:3])
            missing_summary = high_conf_fails[0]

            retry_system = (
                "You are a structured fact extraction engine for enterprise vendor documents.\n"
                "CRITICAL: The previous extraction FAILED for this criterion:\n"
                f"  Criterion: {criterion_name}\n"
                f"  Requires: {what_passes}\n"
                f"  Previous extraction returned: {wrong_summary}\n"
                f"  What was wrong: {missing_summary}\n\n"
                f"Find the PRIMARY statement of '{criterion_name}' in the passages. "
                "Do NOT extract adjacent or referenced facts — only the primary statement "
                "that directly satisfies the criterion.\n\n"
                "Rules:\n"
                "1. grounding_quote must be the EXACT verbatim sentence that is the primary statement.\n"
                "2. source_chunk_id must match the [chunk_id] shown in context headers.\n"
                "3. Only extract what is explicitly stated. Do not infer.\n\n"
                f"Return ONLY a JSON object with a '{response_key}' array:\n"
                + _focused_schema(fact_type)
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
                retry_facts = parse_fn(retry_raw.get(response_key, []), warnings)

                # Re-judge retry facts and emit audit events
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

                # Replace original facts with retry results regardless of adequacy
                if fact_type == "insurance":
                    insurance = retry_facts
                elif fact_type == "certification":
                    certifications = retry_facts
                elif fact_type == "sla":
                    slas = retry_facts
                elif fact_type == "project":
                    projects = retry_facts
                elif fact_type == "pricing":
                    pricing = retry_facts

                if not retry_adequate:
                    warnings.append(
                        f"extraction_critic: retry for {fact_type}/{criterion_name} still inadequate"
                    )

            except Exception as exc:
                warnings.append(f"extraction_critic retry failed for {fact_type}: {exc}")

        # Custom targets — judge extracted_facts rows per mandatory check target
        for chk in (evaluation_setup.mandatory_checks or []):
            tgt = target_by_id.get(chk.extraction_target_id)
            if not tgt or tgt.fact_type != "custom":
                continue
            target_id = tgt.target_id
            criterion_name = chk.name
            what_passes = chk.what_passes
            custom_key = f"custom:{target_id}"
            if custom_key in retried_fact_types:
                continue  # already retried this target

            fact_list = [f for f in extracted_facts if f.target_id == target_id]
            if not fact_list:
                continue

            high_conf_fails: list[str] = []
            high_conf_passes: int = 0
            wrong_value_parts: list[str] = []

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
                        high_conf_passes += 1
                    else:
                        high_conf_fails.append(verdict.missing)
                        wrong_value_parts.append((fact.text_value or "")[:80])

            should_retry = (
                len(high_conf_fails) > 0
                and high_conf_passes == 0
                and _max_retries > 0
            )
            if not should_retry:
                continue

            retried_fact_types.add(custom_key)
            wrong_summary = "; ".join(wrong_value_parts[:3])
            missing_summary = high_conf_fails[0]

            retry_system = (
                "You are a structured fact extraction engine for enterprise vendor documents.\n"
                "CRITICAL: The previous extraction FAILED for this criterion:\n"
                f"  Criterion: {criterion_name}\n"
                f"  Target: {tgt.name} — {tgt.description}\n"
                f"  Requires: {what_passes}\n"
                f"  Previous extraction returned: {wrong_summary}\n"
                f"  What was wrong: {missing_summary}\n\n"
                f"Find the PRIMARY statement satisfying '{criterion_name}' in the passages. "
                "Do NOT extract adjacent or referenced facts.\n\n"
                "Rules:\n"
                "1. grounding_quote must be the EXACT verbatim sentence from the source.\n"
                "2. source_chunk_id must match the [chunk_id] shown in context headers.\n"
                "3. Only extract what is explicitly stated.\n\n"
                f"Return ONLY a JSON object using this schema:\n"
                + _focused_schema("custom", target_id=target_id)
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
                retry_custom = _parse_extracted_facts(
                    [f for f in retry_raw.get("extracted_facts", []) if f.get("target_id") == target_id],
                    warnings,
                )

                retry_adequate = True
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
                        retry_adequate = False

                # Replace this target's facts with retry results
                extracted_facts = [f for f in extracted_facts if f.target_id != target_id] + retry_custom

                if not retry_adequate:
                    warnings.append(
                        f"extraction_critic: retry for custom/{criterion_name} still inadequate"
                    )

            except Exception as exc:
                warnings.append(f"extraction_critic retry failed for custom/{criterion_name}: {exc}")

        # Scoring criteria — judge extracted facts for each scoring criterion's targets.
        # Uses rubric_9_10 as the quality benchmark (what excellent evidence looks like).
        _type_to_list_map = {
            "insurance": lambda: insurance,
            "certification": lambda: certifications,
            "sla": lambda: slas,
            "project": lambda: projects,
            "pricing": lambda: pricing,
        }
        _type_parse_map = {
            "insurance": ("insurance", _parse_insurance),
            "certification": ("certifications", _parse_certifications),
            "sla": ("slas", _parse_slas),
            "project": ("projects", _parse_projects),
            "pricing": ("pricing", _parse_pricing),
        }

        for crit in (evaluation_setup.scoring_criteria or []):
            for target_id in (crit.extraction_target_ids or []):
                tgt = target_by_id.get(target_id)
                if not tgt:
                    continue
                scoring_key = f"scoring:{crit.criterion_id}:{target_id}"
                if scoring_key in retried_fact_types:
                    continue

                is_custom = tgt.fact_type == "custom"
                if is_custom:
                    fact_list = [f for f in extracted_facts if f.target_id == target_id]
                else:
                    getter = _type_to_list_map.get(tgt.fact_type)
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

                retried_fact_types.add(scoring_key)
                wrong_summary_sc = "; ".join(wrong_value_parts_sc[:3])
                missing_summary_sc = high_conf_fails_sc[0]

                if is_custom:
                    retry_schema_sc = _focused_schema("custom", target_id=target_id)
                    response_key_sc = "extracted_facts"
                    parse_fn_sc = None
                    target_desc_sc = f"  Target: {tgt.name} — {tgt.description}\n"
                else:
                    response_key_sc, parse_fn_sc = _type_parse_map.get(tgt.fact_type, ("", None))
                    if not response_key_sc:
                        continue
                    retry_schema_sc = _focused_schema(tgt.fact_type)
                    target_desc_sc = ""

                retry_system_sc = (
                    "You are a structured fact extraction engine for enterprise vendor documents.\n"
                    "CRITICAL: The previous extraction FAILED for this scoring criterion:\n"
                    f"  Criterion: {sc_criterion_name}\n"
                    f"{target_desc_sc}"
                    f"  Excellent evidence looks like: {sc_what_passes}\n"
                    f"  Previous extraction returned: {wrong_summary_sc}\n"
                    f"  What was wrong: {missing_summary_sc}\n\n"
                    f"Find the PRIMARY statement satisfying '{sc_criterion_name}' in the passages. "
                    "Do NOT extract adjacent or referenced facts.\n\n"
                    "Rules:\n"
                    "1. grounding_quote must be the EXACT verbatim sentence from the source.\n"
                    "2. source_chunk_id must match the [chunk_id] shown in context headers.\n"
                    "3. Only extract what is explicitly stated.\n\n"
                    f"Return ONLY a JSON object using this schema:\n"
                    + retry_schema_sc
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
                            warnings,
                        )
                    else:
                        retry_facts_sc = parse_fn_sc(retry_raw_sc.get(response_key_sc, []), warnings)

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

                    # Replace original facts with retry results
                    if is_custom:
                        extracted_facts = [f for f in extracted_facts if f.target_id != target_id] + retry_facts_sc
                    elif tgt.fact_type == "insurance":
                        insurance = retry_facts_sc
                    elif tgt.fact_type == "certification":
                        certifications = retry_facts_sc
                    elif tgt.fact_type == "sla":
                        slas = retry_facts_sc
                    elif tgt.fact_type == "project":
                        projects = retry_facts_sc
                    elif tgt.fact_type == "pricing":
                        pricing = retry_facts_sc

                    if not retry_adequate_sc:
                        warnings.append(
                            f"extraction_critic: retry for scoring/{sc_criterion_name}/{tgt.fact_type} still inadequate"
                        )

                except Exception as exc:
                    warnings.append(f"extraction_critic retry failed for scoring/{sc_criterion_name}: {exc}")

    # Step 5: Score completeness and hallucination risk
    all_facts_list = certifications + insurance + slas + projects + pricing + extracted_facts
    completeness = _extraction_completeness(
        certifications, insurance, slas, projects, pricing,
        extracted_facts, extraction_targets,
    )
    hal_risk = _hallucination_risk(all_facts_list, source_chunks)

    # Step 6: Build ExtractionOutput
    output = ExtractionOutput(
        extraction_id=extraction_id,
        vendor_id=vendor_id,
        org_id=org_id,
        source_chunk_ids=list(source_chunks.keys()),
        certifications=certifications,
        insurance=insurance,
        slas=slas,
        projects=projects,
        pricing=pricing,
        extracted_facts=extracted_facts,
        extraction_completeness=completeness,
        hallucination_risk=hal_risk,
        warnings=warnings,
        retried_fact_types=list(retried_fact_types),
    )

    # Step 7: Critic — programmatic grounding check
    critic = critic_after_extraction(output, source_chunks)

    # Step 8: Save to PostgreSQL only if not blocked
    if critic.overall_verdict != CriticVerdict.BLOCKED:
        # Attach setup_id so fact_store can link extracted_facts rows to EvaluationSetup
        object.__setattr__(output, "setup_id", setup_id)
        try:
            save_extraction_output(output, doc_id)
        except Exception as e:
            # Print here because Pydantic copies warnings list at model construction
            # time, so appending after won't update output.warnings.
            print(f"[ERROR extraction] PostgreSQL save failed vendor={vendor_id}: {e}")

    return output, critic
