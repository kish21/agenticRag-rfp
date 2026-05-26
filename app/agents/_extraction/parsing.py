import uuid
from datetime import date
from typing import Optional

from app.schemas.output_models import (
    DocumentStatus,
    ExtractedCertification,
    ExtractedFact,
    ExtractedInsurance,
    ExtractedPricing,
    ExtractedProject,
    ExtractedSLA,
)


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
