"""
LLM-fallback attribution for files that landed without a clear vendor folder.

Called by the ingestion_watcher when a file is dropped into
`{drops_root}/{rfp_id}/` directly (no vendor subfolder) AND no other heuristic
identified the vendor. The LLM reads the first ~2 pages of the file and
returns a vendor_id + confidence.

Confidence ≥ settings.platform.ingestion.llm_attribution_confidence_floor →
auto-attribute. Below → return None and let the caller route to the
needs_attribution queue.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from app.providers.llm import call_llm

logger = logging.getLogger(__name__)


@dataclass
class AttributionGuess:
    vendor_id: Optional[str]
    confidence: float
    reasoning: str


async def attribute_via_llm(
    *,
    file_text: str,
    invited_vendor_ids: list[str],
    invited_vendor_names: dict[str, str],
) -> AttributionGuess:
    """
    Asks the LLM which invited vendor this file most likely belongs to.
    The LLM can only return one of the invited_vendor_ids OR None.

    `file_text` is expected to be ~first 2 pages of the file (PDF text or raw).
    Caller is responsible for extraction; this function only reasons over text.
    """
    if not invited_vendor_ids:
        return AttributionGuess(
            vendor_id=None,
            confidence=0.0,
            reasoning="No invited vendors on this RFP.",
        )

    options = [
        f"  - {vid}" + (f"  ({invited_vendor_names[vid]})" if vid in invited_vendor_names else "")
        for vid in invited_vendor_ids
    ]
    options_block = "\n".join(options)

    system = (
        "You are attributing a vendor proposal file to one of the invited vendors. "
        "Read the first two pages of the file. Return ONLY one of the allowed "
        "vendor_id values, or null if you cannot tell with high confidence. "
        "Do NOT invent vendor ids. Respond as JSON: "
        '{"vendor_id": "<id>" | null, "confidence": 0.0..1.0, "reasoning": "<one sentence>"}.'
    )
    user = (
        f"Allowed vendor ids:\n{options_block}\n\n"
        f"--- FILE TEXT (first ~2 pages) ---\n{file_text[:6000]}\n--- END ---\n\n"
        "Which vendor wrote this?"
    )

    try:
        raw = await call_llm(
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            temperature=0.0,
            response_format={"type": "json_object"},
        )
        parsed = json.loads(raw)
    except (json.JSONDecodeError, Exception) as exc:  # pragma: no cover — provider error
        logger.warning("LLM attribution failed: %s", exc)
        return AttributionGuess(
            vendor_id=None,
            confidence=0.0,
            reasoning=f"LLM call failed: {exc}",
        )

    vendor_id = parsed.get("vendor_id")
    confidence = float(parsed.get("confidence", 0.0))
    reasoning = str(parsed.get("reasoning", ""))[:500]

    # Guard against hallucinated vendor ids.
    if vendor_id is not None and vendor_id not in set(invited_vendor_ids):
        return AttributionGuess(
            vendor_id=None,
            confidence=0.0,
            reasoning=f"LLM returned id '{vendor_id}' not in invited list; treating as unknown.",
        )

    return AttributionGuess(
        vendor_id=vendor_id, confidence=confidence, reasoning=reasoning
    )


def read_first_pages_text(path: Path, max_pages: int = 2) -> str:
    """
    Extracts the first `max_pages` of text from a file. Supports .pdf via
    pypdf and falls back to raw read for .txt / unknown. Returns empty
    string on failure — caller decides how to handle.
    """
    suffix = path.suffix.lower()
    try:
        if suffix == ".pdf":
            from pypdf import PdfReader  # local import keeps watcher startup light

            reader = PdfReader(str(path))
            pages = reader.pages[:max_pages]
            return "\n".join((p.extract_text() or "") for p in pages)
        return path.read_text(encoding="utf-8", errors="ignore")[:6000]
    except Exception as exc:  # pragma: no cover — corrupt file
        logger.warning("Could not extract text from %s: %s", path, exc)
        return ""
