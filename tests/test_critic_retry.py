"""
Phase 2c — shared critic-retry helper tests (offline, no LLM, no Postgres).

Verifies the first-class self-correcting controller behaviour against the exit
criteria: retry-with-feedback (T1), per-vendor isolation (T2), HARD-block guard
on exhaustion (T3), telemetry (P2), and that the common path is untouched (P3).
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.pipeline.critic_retry import run_with_critic_retry  # noqa: E402
from app.schemas.schema_enums import CriticVerdict  # noqa: E402

_OK = next(v for v in CriticVerdict if v != CriticVerdict.BLOCKED)


class _Sev:
    def __init__(self, value): self.value = value


class _Flag:
    def __init__(self, description, severity="hard"):
        self.description = description
        self.severity = _Sev(severity)


class _Critic:
    def __init__(self, verdict, flags=None):
        self.overall_verdict = verdict
        self.flags = flags or []


def _attempt_seq(verdicts, captured_feedback=None):
    """Build an attempt_fn that returns the given verdict sequence and (optionally)
    records the feedback string passed on each call."""
    state = {"i": 0}

    async def attempt(feedback):
        if captured_feedback is not None:
            captured_feedback.append(feedback)
        i = state["i"]
        state["i"] += 1
        v = verdicts[min(i, len(verdicts) - 1)]
        flags = [_Flag("fact 'ISO 27001' has no source quote")] if v == CriticVerdict.BLOCKED else []
        return f"output-{i}", _Critic(v, flags)

    return attempt


def _on_success(output):
    return {"extraction_output_objects": {"v1": output}}


def _build_feedback(critic, output):
    descs = "; ".join(f.description for f in critic.flags)
    return f"PREVIOUS ATTEMPT FAILED: {descs}. Re-extract only those facts."


async def _run(verdicts, *, vendor_id="v1", captured=None, events=None, max_retries=2):
    emit = (lambda status, msg: events.append((status, msg))) if events is not None else None
    return await run_with_critic_retry(
        agent="extraction", vendor_id=vendor_id,
        attempt_fn=_attempt_seq(verdicts, captured),
        build_feedback=_build_feedback, on_success=_on_success,
        max_retries=max_retries, emit=emit,
    )


# ── T1 / P3 — common path: succeed first attempt, no retries ─────────────────

@pytest.mark.asyncio
async def test_succeeds_first_attempt_no_retry():
    events = []
    res = await _run([_OK], events=events)
    assert "extraction_output_objects" in res and "failed_vendors" not in res
    m = res["critic_metrics_accum"]["v1"]["extraction"]
    assert m == {"blocks": 0, "retries": 0, "retry_success": False, "exhausted": False}
    assert events == []  # no retry/recover/block noise on the clean path (P3)


# ── T1 — retry with feedback succeeds on attempt 2 ───────────────────────────

@pytest.mark.asyncio
async def test_retry_succeeds_on_attempt_2():
    captured, events = [], []
    res = await _run([CriticVerdict.BLOCKED, _OK], captured=captured, events=events)
    assert "extraction_output_objects" in res and "failed_vendors" not in res
    m = res["critic_metrics_accum"]["v1"]["extraction"]
    assert m["blocks"] == 1 and m["retry_success"] is True and m["exhausted"] is False
    assert any(s == "recovered" for s, _ in events)
    # feedback propagated: first attempt empty, second carries the critic's note
    assert captured[0] == ""
    assert "PREVIOUS ATTEMPT FAILED" in captured[1] and "ISO 27001" in captured[1]


# ── T3 — exhausted after 3 attempts → failed_vendors (HARD-block guard) ──────

@pytest.mark.asyncio
async def test_exhausted_marks_vendor_failed():
    events = []
    res = await _run([CriticVerdict.BLOCKED] * 3, events=events)
    assert "extraction_output_objects" not in res
    fv = res["failed_vendors"]
    assert len(fv) == 1 and fv[0]["vendor_id"] == "v1" and fv[0]["stage"] == "extraction"
    assert "critic_hard_block after 3 attempts" in fv[0]["error"]
    m = res["critic_metrics_accum"]["v1"]["extraction"]
    assert m["blocks"] == 3 and m["exhausted"] is True and m["retry_success"] is False
    # 2 retry events + 1 final blocked event
    assert [s for s, _ in events].count("retry") == 2
    assert [s for s, _ in events].count("blocked") == 1


# ── T2 — per-vendor isolation ────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_per_vendor_isolation():
    # Vendor A exhausts; Vendor B succeeds first try. Independent calls → no shared state.
    a = await _run([CriticVerdict.BLOCKED] * 3, vendor_id="acme")
    b = await _run([_OK], vendor_id="apex")
    assert "failed_vendors" in a and a["failed_vendors"][0]["vendor_id"] == "acme"
    assert "extraction_output_objects" in b and "failed_vendors" not in b
    assert a["critic_metrics_accum"]["acme"]["extraction"]["exhausted"] is True
    assert b["critic_metrics_accum"]["apex"]["extraction"]["blocks"] == 0


# ── never raises: an agent exception isolates the vendor (Check C) ───────────

@pytest.mark.asyncio
async def test_agent_exception_isolated_not_raised():
    async def boom(feedback):
        raise RuntimeError("LLM timeout")
    res = await run_with_critic_retry(
        agent="evaluation", vendor_id="v9", attempt_fn=boom,
        build_feedback=_build_feedback, on_success=_on_success)
    assert "failed_vendors" in res
    assert res["failed_vendors"][0]["stage"] == "evaluation"
    assert "LLM timeout" in res["failed_vendors"][0]["error"]
