"""
Phase 2c — in-branch critic-as-controller for the per-vendor generation agents.

This is the faithful self-correcting controller for the per-vendor LLM-*generation*
steps (Extraction, Evaluation). Because those run as parallel per-vendor branches
(Phase 4 fan-out), the controller lives INSIDE each vendor's branch rather than as
graph-level critic nodes — graph-level retry loops would fight the fan-out. That
keeps **per-vendor isolation** (one vendor's retries never touch another's) while
making the Critic a real decision-maker: on a HARD verdict it hands the agent
specific feedback and retries, and only fails the vendor when correction is
exhausted (preserving the Phase 4 `failed_vendors` HARD-block guard — Check C).

One shared helper so all three generation steps (Extraction, Evaluation,
Explanation) behave identically (exit criterion T4). NEVER raises.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, Optional

from app.schemas.schema_enums import CriticVerdict

# (critic_feedback) -> (agent_output, critic_output)
AttemptFn = Callable[[str], Awaitable[tuple[Any, Any]]]
# (critic_output, agent_output) -> feedback string for the next attempt
FeedbackBuilder = Callable[[Any, Any], str]
# (agent_output) -> the success state update for this vendor
SuccessUpdate = Callable[[Any], dict]
# (status, message) -> None
Emit = Optional[Callable[[str, str], None]]

DEFAULT_MAX_RETRIES = 2  # 2 retries = 3 total attempts (matches Explanation)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _hard_descriptions(critic: Any) -> str:
    flags = getattr(critic, "flags", []) or []
    return "; ".join(
        f.description for f in flags
        if getattr(getattr(f, "severity", None), "value", "") == "hard"
    )[:240]


def _metric(agent: str, vendor_id: str, *, blocks: int, retries: int,
            recovered: bool, exhausted: bool) -> dict:
    """Telemetry, keyed by vendor_id so the per-vendor _merge_dicts reducer can
    accumulate across the parallel branches without collisions."""
    return {vendor_id: {agent: {
        "blocks": blocks, "retries": retries,
        "retry_success": recovered, "exhausted": exhausted,
    }}}


async def run_with_critic_retry(
    *,
    agent: str,
    vendor_id: str,
    attempt_fn: AttemptFn,
    build_feedback: FeedbackBuilder,
    on_success: SuccessUpdate,
    max_retries: int = DEFAULT_MAX_RETRIES,
    emit: Emit = None,
) -> dict:
    """Run a per-vendor generation agent under critic control with
    retry-with-feedback.

    Returns the state update — either the success output (from `on_success`) or a
    `failed_vendors` entry — always including `critic_metrics_accum` telemetry.
    Never raises; a HARD verdict that can't be corrected becomes a failed vendor
    so the rest of the batch continues.
    """
    feedback = ""
    blocks = 0
    last_critic: Any = None

    for attempt in range(max_retries + 1):          # attempts 0..max_retries
        try:
            output, critic = await attempt_fn(feedback)
        except Exception as exc:  # noqa: BLE001 — agent crashed; isolate this vendor
            if emit:
                emit("blocked", f"{agent} for {vendor_id} errored: {exc}")
            return {
                "failed_vendors": [{
                    "vendor_id": vendor_id, "stage": agent,
                    "error": str(exc), "ts": _now(),
                }],
                "critic_metrics_accum": _metric(
                    agent, vendor_id, blocks=blocks, retries=blocks,
                    recovered=False, exhausted=True),
            }
        last_critic = critic

        if critic.overall_verdict != CriticVerdict.BLOCKED:
            update = dict(on_success(output))
            recovered = blocks > 0
            if recovered and emit:
                emit("recovered",
                     f"{agent} for {vendor_id} self-corrected after "
                     f"{blocks} retr{'y' if blocks == 1 else 'ies'}")
            update["critic_metrics_accum"] = _metric(
                agent, vendor_id, blocks=blocks, retries=blocks,
                recovered=recovered, exhausted=False)
            return update

        # HARD blocked — build feedback for the next attempt
        blocks += 1
        feedback = build_feedback(critic, output)
        if attempt < max_retries and emit:
            emit("retry",
                 f"{agent} for {vendor_id} blocked (attempt {attempt + 1}) — "
                 f"retrying with critic feedback")

    # Retries exhausted → fail this vendor (others continue: Phase 4 isolation)
    descs = _hard_descriptions(last_critic)
    if emit:
        emit("blocked",
             f"{agent} for {vendor_id} could not be corrected after "
             f"{blocks} attempts — flagged as failed")
    return {
        "failed_vendors": [{
            "vendor_id": vendor_id, "stage": agent,
            "error": f"critic_hard_block after {blocks} attempts: {descs}",
            "ts": _now(),
        }],
        "critic_metrics_accum": _metric(
            agent, vendor_id, blocks=blocks, retries=max_retries,
            recovered=False, exhausted=True),
    }
