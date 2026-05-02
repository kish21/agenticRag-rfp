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
            warnings.append(f"PostgreSQL save failed: {e}")

    return output, critic
