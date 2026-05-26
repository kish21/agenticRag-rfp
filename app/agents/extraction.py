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
import uuid

from app.config import settings
from app.providers.llm import call_llm
from app.schemas.output_models import (
    CriticVerdict,
    EvaluationSetup,
    ExtractionOutput,
    RetrievalOutput,
)
from app.agents.critic import critic_after_extraction
from app.db.fact_store import save_extraction_output

from app.agents._extraction.prompts import _schema_description
from app.agents._extraction.parsing import (
    _parse_certifications,
    _parse_extracted_facts,
    _parse_insurance,
    _parse_pricing,
    _parse_projects,
    _parse_slas,
)
from app.agents._extraction.scoring import _extraction_completeness, _hallucination_risk
from app.agents._extraction.retry_loop import FactsState, run_extraction_critic_retries


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
    parse_warnings: list[str] = []
    try:
        raw = json.loads(raw_text)
    except json.JSONDecodeError as e:
        parse_warnings.append(f"LLM returned invalid JSON: {e}")
        raw = {}

    state = FactsState(
        certifications=_parse_certifications(raw.get("certifications", []), parse_warnings),
        insurance=_parse_insurance(raw.get("insurance", []), parse_warnings),
        slas=_parse_slas(raw.get("slas", []), parse_warnings),
        projects=_parse_projects(raw.get("projects", []), parse_warnings),
        pricing=_parse_pricing(raw.get("pricing", []), parse_warnings),
        extracted_facts=_parse_extracted_facts(raw.get("extracted_facts", []), parse_warnings),
        warnings=parse_warnings,
    )

    # Step 4.5: Extraction critic retries
    if org_id:
        state = await run_extraction_critic_retries(
            state=state,
            org_id=org_id,
            vendor_id=vendor_id,
            run_id=run_id,
            context=context,
            evaluation_setup=evaluation_setup,
        )

    # Step 5: Score completeness and hallucination risk
    all_facts_list = (
        state.certifications + state.insurance + state.slas
        + state.projects + state.pricing + state.extracted_facts
    )
    completeness = _extraction_completeness(
        state.certifications, state.insurance, state.slas,
        state.projects, state.pricing, state.extracted_facts,
        extraction_targets,
    )
    hal_risk = _hallucination_risk(all_facts_list, source_chunks)

    # Step 6: Build ExtractionOutput
    output = ExtractionOutput(
        extraction_id=extraction_id,
        vendor_id=vendor_id,
        org_id=org_id,
        source_chunk_ids=list(source_chunks.keys()),
        certifications=state.certifications,
        insurance=state.insurance,
        slas=state.slas,
        projects=state.projects,
        pricing=state.pricing,
        extracted_facts=state.extracted_facts,
        extraction_completeness=completeness,
        hallucination_risk=hal_risk,
        warnings=state.warnings,
        retried_fact_types=list(state.retried_fact_types),
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
