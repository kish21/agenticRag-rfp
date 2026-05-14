"""
Retrieval critic — judges whether a set of retrieved chunks collectively
contains evidence adequate for a criterion's threshold rule.

Generic across criterion types: the prompt asks "do these passages contain
the facts the rule demands" rather than checking criterion-specific patterns.
"""
import json
import logging
from pydantic import BaseModel, Field
from app.config import settings
from app.core.llm_provider import call_llm

log = logging.getLogger(__name__)


class CriticVerdict(BaseModel):
    adequate: bool
    confidence: float = Field(ge=0, le=1)
    missing: str = ""


async def judge_retrieval(
    criterion_name: str,
    what_passes: str,
    chunks: list[dict],
) -> CriticVerdict:
    """Single-call judgement of whether chunks are adequate for the criterion."""
    if not chunks:
        return CriticVerdict(
            adequate=False,
            confidence=1.0,
            missing="no chunks retrieved",
        )

    chunks_text = "\n\n".join(
        f"[Chunk {i + 1}]\n{c.get('text', '')[:600]}"
        for i, c in enumerate(chunks[:8])
    )

    prompt = settings.platform.retrieval_critic_prompt.format(
        criterion_name=criterion_name,
        what_passes=what_passes or criterion_name,
        chunks=chunks_text,
    )

    messages = [
        {"role": "system", "content": "You are a strict retrieval quality judge. Return only valid JSON."},
        {"role": "user", "content": prompt},
    ]

    raw = None
    try:
        raw = await call_llm(messages, temperature=0.0, response_format={"type": "json_object"})
        data = json.loads(raw) if isinstance(raw, str) else raw
        return CriticVerdict.model_validate(data)
    except Exception as exc:
        log.warning(
            "retrieval_critic: LLM call failed (%s) raw_response=%r — defaulting adequate=False",
            type(exc).__name__, (raw or "")[:500],
        )
        return CriticVerdict(adequate=False, confidence=0.0, missing=f"critic error: {type(exc).__name__}: {exc}")
