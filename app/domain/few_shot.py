"""
Few-shot example bank for the Evaluation Agent (P1.9 / #60).

When a human reviewer corrects an AI decision, the correction is stored
org-scoped in `evaluation_corrections`. This module reads those corrections back
and renders them as a calibration block that the Evaluation Agent injects into
its evaluate-check / score-criterion prompt for the SAME criterion/check. The
platform learns from its own reviewers.

Design guarantees:
  • Config-driven — every knob lives in `platform.yaml` (`few_shot`). Disabled, or
    an org with no corrections, yields an EMPTY string → the prompt is byte-for-byte
    unchanged (this is why the benchmark org is unaffected).
  • Org-isolated — corrections are fetched with the org_id filter under RLS; a
    tenant only ever sees its OWN corrections.
  • Defence-in-depth (OWASP LLM01) — a correction's text lands inside an LLM prompt,
    so each one is re-scanned with the injection scanner; any that trip a pattern are
    skipped (a compromised reviewer cannot smuggle instructions into the evaluator).
  • Fail-safe — any error reading/rendering the bank logs and returns "" so the
    evaluation continues without examples; it never blocks a run. The Critic still
    runs after the agent regardless.
"""
import json
import logging

from app.config import settings
from app.db.fact_store import get_evaluation_corrections
from app.prompts.registry import get_prompt
from app.validators.injection import scan_text

logger = logging.getLogger(__name__)


def _format_value(target_type: str, value: dict) -> str:
    """Render a stored correction value for the prompt in human-readable form.

    criterion → a 0-10 score; check → a pass/fail decision. Falls back to compact
    JSON for any other shape so the example is never silently dropped."""
    value = value or {}
    if not value:
        return "(not recorded)"
    if target_type == "criterion" and "raw_score" in value:
        return f"score {value['raw_score']}/10"
    if target_type == "check" and "decision" in value:
        return str(value["decision"])
    return json.dumps(value, default=str, sort_keys=True)


def _render_examples(corrections: list[dict], fs) -> str:
    """Turn raw correction rows into the numbered example text, applying the
    min-reason-length filter and the injection re-scan. Returns "" if nothing
    survives the filters."""
    patterns = settings.platform.injection_defence.patterns
    lines: list[str] = []
    n = 0
    for c in corrections:
        reason = (c.get("reason") or "").strip()
        if len(reason) < fs.min_reason_len:
            continue
        original = c.get("original_value") or {}
        corrected = c.get("corrected_value") or {}
        # Re-scan everything that will reach the prompt — the reviewer's free text
        # plus the stored values — and skip the whole example on any hit.
        scan_target = " ".join(
            [reason, json.dumps(original, default=str), json.dumps(corrected, default=str)]
        )
        if patterns and scan_text(scan_target, patterns):
            logger.warning(
                "few-shot: skipping correction %s — injection pattern matched",
                c.get("correction_id"),
            )
            continue
        n += 1
        target_type = c.get("target_type", "")
        lines.append(
            f"Example {n}:\n"
            f"  AI judged: {_format_value(target_type, original)}\n"
            f"  Human corrected to: {_format_value(target_type, corrected)}\n"
            f"  Reason: {reason}"
        )
    return "\n\n".join(lines)


def build_few_shot_block(
    org_id: str,
    target_type: str,
    target_id: str,
    target_name: str = "",
) -> str:
    """Return the calibration block to inject for one criterion/check, or "".

    target_type is "criterion" or "check". Returns "" (a no-op) when the feature
    is off, the relevant injection point is gated off, there is no org context, or
    no usable corrections exist.
    """
    fs = settings.platform.few_shot
    if not fs.enabled or not org_id:
        return ""
    if target_type == "check" and not fs.apply_to_checks:
        return ""
    if target_type == "criterion" and not fs.apply_to_scores:
        return ""

    try:
        corrections = get_evaluation_corrections(
            org_id=org_id,
            target_type=target_type,
            target_id=target_id,
            limit=fs.max_examples,
        )
        if not corrections:
            return ""
        rendered = _render_examples(corrections, fs)
        if not rendered:
            return ""
        return get_prompt("evaluation/few_shot_examples", examples=rendered)
    except Exception:
        # Fail-safe: the few-shot bank is an enhancement, never a dependency. A DB
        # hiccup or render error must not break an evaluation run.
        logger.warning(
            "few-shot: bank unavailable for %s/%s — continuing without examples",
            target_type, target_id, exc_info=True,
        )
        return ""
