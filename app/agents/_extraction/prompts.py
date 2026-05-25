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
