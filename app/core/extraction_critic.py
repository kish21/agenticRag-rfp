"""
Extraction critic — judges whether an extracted fact correctly
answers a procurement criterion based on its grounding quote.

Generic: works for any criterion type. The prompt asks
"does this fact answer the criterion based on this quote"
rather than checking criterion-specific patterns.
"""
import json
import logging
from pydantic import BaseModel, Field
from app.config import settings
from app.core.llm_provider import call_llm

log = logging.getLogger(__name__)


class ExtractionVerdict(BaseModel):
    adequate: bool
    confidence: float = Field(ge=0, le=1)
    missing: str = ""
    should_retry: bool = False


async def judge_extraction(
    criterion_name: str,
    what_passes: str,
    fact_type: str,
    fact_value: str,
    provider_or_issuer: str = "",
    key_identifier: str = "",
    grounding_quote: str = "",
) -> ExtractionVerdict:
    """
    Single-call judgement on whether an extracted fact correctly
    answers a criterion, based on its grounding quote.
    """
    if not grounding_quote:
        return ExtractionVerdict(
            adequate=False,
            confidence=1.0,
            missing="no grounding quote provided",
            should_retry=False,
        )

    prompt = settings.platform.extraction_critic_prompt.format(
        criterion_name=criterion_name,
        what_passes=what_passes or criterion_name,
        fact_type=fact_type,
        fact_value=fact_value,
        provider_or_issuer=provider_or_issuer,
        key_identifier=key_identifier,
        grounding_quote=grounding_quote[:1500],
    )

    messages = [
        {
            "role": "system",
            "content": "You are a strict extraction quality judge. Return only valid JSON.",
        },
        {"role": "user", "content": prompt},
    ]

    raw = None
    try:
        raw = await call_llm(messages, temperature=0.0, response_format={"type": "json_object"})
        data = json.loads(raw) if isinstance(raw, str) else raw
        return ExtractionVerdict.model_validate(data)
    except Exception as exc:
        log.warning(
            "extraction_critic: LLM call failed (%s) raw_response=%r — defaulting adequate=True",
            type(exc).__name__, (raw or "")[:500],
        )
        # Safe default: don't block extraction on critic errors
        return ExtractionVerdict(
            adequate=True,
            confidence=0.0,
            missing=f"critic error: {type(exc).__name__}: {exc}",
            should_retry=False,
        )
