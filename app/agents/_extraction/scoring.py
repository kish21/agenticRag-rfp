import re


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


def _extraction_completeness(
    certifications: list,
    insurance: list,
    slas: list,
    projects: list,
    pricing: list,
    extracted_facts: list,
    extraction_targets: list[dict],
) -> float:
    """
    Score based only on fact types the customer's evaluation actually requires.
    Standard types not in extraction_targets are ignored — an HR evaluation
    with no SLA requirements is not penalised for having zero SLA facts.
    """
    active_standard = {
        t.get("fact_type") for t in extraction_targets
        if t.get("fact_type") in ("certification", "insurance", "sla", "project", "pricing")
    }

    score = 0
    total = 0

    if "certification" in active_standard:
        total += 1
        if certifications:
            score += 1
    if "insurance" in active_standard:
        total += 1
        if insurance:
            score += 1
    if "sla" in active_standard:
        total += 1
        if slas:
            score += 1
    if "project" in active_standard:
        total += 1
        if projects:
            score += 1
    if "pricing" in active_standard:
        total += 1
        if pricing:
            score += 1

    custom_targets = [t for t in extraction_targets if t.get("fact_type") == "custom"]
    found_target_ids = {f.target_id for f in extracted_facts}
    for t in custom_targets:
        total += 1
        if t["target_id"] in found_target_ids:
            score += 1

    return round(score / total, 3) if total > 0 else 1.0


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
