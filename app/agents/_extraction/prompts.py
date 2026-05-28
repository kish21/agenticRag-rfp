def _schema_description(extraction_targets: list[dict]) -> str:
    """
    Build the extraction JSON schema from the customer's EvaluationSetup only.
    Only sections that have extraction targets defined are included.
    Nothing is hardcoded — the schema adapts to any department or domain.
    """
    active_types = {t.get("fact_type") for t in extraction_targets}
    custom_targets = [t for t in extraction_targets if t.get("fact_type") == "custom"]

    if not active_types:
        return 'Return a JSON object: {} (no extraction targets defined for this evaluation)'

    parts: list[str] = []

    if "certification" in active_types:
        parts.append('''"certifications": [
    {
      "standard_name": "name of the standard or accreditation",
      "version": "year or version string or null",
      "cert_number": "certificate number or null",
      "issuing_body": "certifying organisation or null",
      "scope": "scope of the certification or null",
      "valid_until": "YYYY-MM-DD or null",
      "status": "current|pending|expired|not_mentioned",
      "confidence": 0.0,
      "grounding_quote": "exact verbatim sentence from source",
      "source_chunk_id": "chunk_id from context header"
    }
  ]''')

    if "insurance" in active_types:
        parts.append('''"insurance": [
    {
      "insurance_type": "e.g. Professional Indemnity, Public Liability, Employers Liability",
      "amount_gbp": null,
      "provider": "insurer name or null",
      "confidence": 0.0,
      "grounding_quote": "exact verbatim sentence from source",
      "source_chunk_id": "chunk_id from context header"
    }
  ]''')

    if "sla" in active_types:
        parts.append('''"slas": [
    {
      "priority_level": "P1 / P2 / Critical / High / etc or null",
      "response_minutes": null,
      "resolution_hours": null,
      "uptime_percentage": null,
      "confidence": 0.0,
      "grounding_quote": "exact verbatim text — for tables join cells with single space",
      "source_chunk_id": "chunk_id from context header"
    }
  ]''')

    if "project" in active_types:
        parts.append('''"projects": [
    {
      "client_name": "string or null",
      "client_sector": "industry sector or null",
      "user_count": null,
      "outcomes": "key outcomes or deliverables or null",
      "reference_available": null,
      "confidence": 0.0,
      "grounding_quote": "exact verbatim sentence from source",
      "source_chunk_id": "chunk_id from context header"
    }
  ]''')

    if "pricing" in active_types:
        parts.append('''"pricing": [
    {
      "year": null,
      "amount_gbp": null,
      "total_gbp": null,
      "includes": [],
      "confidence": 0.0,
      "grounding_quote": "exact verbatim sentence from source",
      "source_chunk_id": "chunk_id from context header"
    }
  ]''')

    if custom_targets:
        targets_text = "\n".join(
            f'    - target_id="{t["target_id"]}", name="{t["name"]}", '
            f'description="{t["description"]}"'
            for t in custom_targets
        )
        parts.append(
            f'"extracted_facts": [\n'
            f'    {{\n'
            f'      "fact_id": "<uuid string>",\n'
            f'      "target_id": "<target_id from list below>",\n'
            f'      "fact_type": "custom",\n'
            f'      "fact_name": "<name of what was found>",\n'
            f'      "text_value": "<string summary of the finding>",\n'
            f'      "numeric_value": null,\n'
            f'      "boolean_value": null,\n'
            f'      "confidence": 0.0,\n'
            f'      "grounding_quote": "exact verbatim sentence from source",\n'
            f'      "source_chunk_id": "<chunk_id>"\n'
            f'    }}\n'
            f'  ]\n\n'
            f'  ExtractionTargets for extracted_facts (one entry per target found):\n'
            f'{targets_text}'
        )

    body = ",\n  ".join(parts)
    active_names = ", ".join(sorted(active_types))
    return (
        f"Return a JSON object with ONLY these sections (defined by the customer's "
        f"evaluation criteria for this run: {active_names}).\n"
        f"Do NOT add sections that are not listed here.\n\n"
        f"{{\n  {body}\n}}"
    )


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
