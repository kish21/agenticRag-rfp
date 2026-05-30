"""
LLM cost and latency tracking.

Usage:
    # In agent runner / evaluation orchestrator — set context before calling agents:
    from app.infra.cost_tracker import set_run_context, get_run_cost

    with set_run_context(run_id="abc-123"):
        await run_all_agents(...)
    cost = get_run_cost("abc-123")

call_llm() automatically records usage when a run_id is set in context.
No changes needed in individual agent files.
"""

import time
from contextvars import ContextVar
from dataclasses import dataclass, field
from contextlib import contextmanager
from typing import Optional

# ── Pricing table (USD per 1M tokens) — May 2026 ────────────────────────────
# Sources: OpenAI / Anthropic / OpenRouter pricing pages.
# Format: { model_substring: (input_usd_per_1m, output_usd_per_1m) }
# Matched by substring so "gpt-4o-2024-08-06" matches "gpt-4o".

PRICING: dict[str, tuple[float, float]] = {
    # OpenAI
    "gpt-4o-mini":          (0.15,   0.60),
    "gpt-4o":               (2.50,  10.00),
    "gpt-4-turbo":          (10.00, 30.00),
    "gpt-4":                (30.00, 60.00),
    "gpt-3.5":              (0.50,   1.50),
    "o1-mini":              (3.00,  12.00),
    "o1":                   (15.00, 60.00),
    "o3-mini":              (1.10,   4.40),
    # Anthropic
    "claude-haiku":         (0.25,   1.25),
    "claude-3-5-haiku":     (0.80,   4.00),
    "claude-sonnet":        (3.00,  15.00),
    "claude-3-5-sonnet":    (3.00,  15.00),
    "claude-opus":          (15.00, 75.00),
    # Meta / Llama (via OpenRouter)
    "llama-3":              (0.59,   0.79),
    "llama-3.1":            (0.59,   0.79),
    # Qwen (Modal / OpenRouter)
    "qwen":                 (0.00,   0.00),  # self-hosted Modal: cost is compute, not per-token
    # Mistral
    "mistral":              (2.00,   6.00),
    # Local / unknown
    "ollama":               (0.00,   0.00),
    "_default":             (5.00,  15.00),  # conservative fallback
}


def estimate_cost(model: str, prompt_tokens: int, completion_tokens: int) -> float:
    """Returns estimated cost in USD for a single LLM call."""
    model_lower = model.lower()
    rates = None
    for key, value in PRICING.items():
        if key != "_default" and key in model_lower:
            rates = value
            break
    if rates is None:
        rates = PRICING["_default"]
    input_rate, output_rate = rates
    return (prompt_tokens * input_rate + completion_tokens * output_rate) / 1_000_000


# ── Per-run accumulator ──────────────────────────────────────────────────────

@dataclass
class LLMCall:
    agent: str
    model: str
    prompt_tokens: int
    completion_tokens: int
    latency_ms: int
    cost_usd: float


@dataclass
class RunCostAccumulator:
    run_id: str
    calls: list[LLMCall] = field(default_factory=list)
    # Phase 3 — LLM cache observability
    cache_hits: int = 0
    cache_misses: int = 0
    cache_savings_usd: float = 0.0

    @property
    def total_prompt_tokens(self) -> int:
        return sum(c.prompt_tokens for c in self.calls)

    @property
    def total_completion_tokens(self) -> int:
        return sum(c.completion_tokens for c in self.calls)

    @property
    def total_tokens(self) -> int:
        return self.total_prompt_tokens + self.total_completion_tokens

    @property
    def total_cost_usd(self) -> float:
        return sum(c.cost_usd for c in self.calls)

    @property
    def total_latency_ms(self) -> int:
        return sum(c.latency_ms for c in self.calls)

    @property
    def cache_hit_rate(self) -> float:
        total = self.cache_hits + self.cache_misses
        return (self.cache_hits / total) if total else 0.0

    def summary(self) -> dict:
        by_agent: dict[str, dict] = {}
        for c in self.calls:
            if c.agent not in by_agent:
                by_agent[c.agent] = {"calls": 0, "tokens": 0, "cost_usd": 0.0, "latency_ms": 0}
            a = by_agent[c.agent]
            a["calls"] += 1
            a["tokens"] += c.prompt_tokens + c.completion_tokens
            a["cost_usd"] += c.cost_usd
            a["latency_ms"] += c.latency_ms
        return {
            "run_id": self.run_id,
            "total_calls": len(self.calls),
            "total_tokens": self.total_tokens,
            "total_prompt_tokens": self.total_prompt_tokens,
            "total_completion_tokens": self.total_completion_tokens,
            "total_cost_usd": round(self.total_cost_usd, 6),
            "total_latency_ms": self.total_latency_ms,
            "cache_hits": self.cache_hits,
            "cache_misses": self.cache_misses,
            "cache_hit_rate": round(self.cache_hit_rate, 4),
            "cache_savings_usd": round(self.cache_savings_usd, 6),
            "by_agent": {k: {**v, "cost_usd": round(v["cost_usd"], 6)} for k, v in by_agent.items()},
        }


# ── Global registry and ContextVar ───────────────────────────────────────────

_accumulators: dict[str, RunCostAccumulator] = {}
_current_run_id: ContextVar[Optional[str]] = ContextVar("_current_run_id", default=None)
_current_agent: ContextVar[str] = ContextVar("_current_agent", default="unknown")


@contextmanager
def set_run_context(run_id: str, agent: str = "unknown"):
    """Context manager that sets the active run and agent for cost tracking."""
    run_token = _current_run_id.set(run_id)
    agent_token = _current_agent.set(agent)
    if run_id not in _accumulators:
        _accumulators[run_id] = RunCostAccumulator(run_id=run_id)
    try:
        yield _accumulators[run_id]
    finally:
        _current_run_id.reset(run_token)
        _current_agent.reset(agent_token)


@contextmanager
def set_current_agent(agent: str):
    """Set the active agent label for cost attribution for the duration of the block.

    `set_run_context` sets the run once at pipeline scope with agent="pipeline";
    without re-setting per agent every LLM call is bucketed under "pipeline" and
    the by-agent cost breakdown is useless. Each agent's run_* function enters
    this so `record_llm_call` attributes its calls correctly. ContextVars are
    per-task, so concurrent per-vendor agents do not clobber each other.
    """
    token = _current_agent.set(agent)
    try:
        yield
    finally:
        _current_agent.reset(token)


def mark_agent(agent: str) -> None:
    """Set the active agent label for cost attribution (no reset).

    One-liner for the top of an agent's run_* function. ContextVars are copied
    per asyncio task, so under the per-vendor fan-out each agent task sets its own
    label without clobbering siblings; the label simply persists for the rest of
    that task (which only runs that one agent's work). Prefer this over editing
    every LLM call site. Use `set_current_agent` when you need a scoped reset.
    """
    _current_agent.set(agent)


def record_llm_call(
    model: str,
    prompt_tokens: int,
    completion_tokens: int,
    latency_ms: int,
) -> None:
    """Called automatically by call_llm() when a run context is active."""
    run_id = _current_run_id.get()
    if run_id is None:
        return
    agent = _current_agent.get()
    acc = _accumulators.get(run_id)
    if acc is None:
        return
    cost = estimate_cost(model, prompt_tokens, completion_tokens)
    acc.calls.append(LLMCall(
        agent=agent,
        model=model,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        latency_ms=latency_ms,
        cost_usd=cost,
    ))


def record_cache_event(
    *,
    hit: bool,
    model: str,
    prompt_tokens: Optional[int],
    completion_tokens: Optional[int],
) -> None:
    """
    Phase 3 — record an LLM cache lookup outcome on the active run.
    On `hit=True`, increments cache_hits and adds the avoided cost to
    cache_savings_usd (estimated from the cached row's token counts).
    On `hit=False`, increments cache_misses only — the provider call
    that follows will be recorded separately via record_llm_call().
    """
    run_id = _current_run_id.get()
    if run_id is None:
        return
    acc = _accumulators.get(run_id)
    if acc is None:
        return
    if hit:
        acc.cache_hits += 1
        if prompt_tokens is not None and completion_tokens is not None:
            acc.cache_savings_usd += estimate_cost(model, prompt_tokens, completion_tokens)
    else:
        acc.cache_misses += 1


def get_run_cost(run_id: str) -> Optional[RunCostAccumulator]:
    return _accumulators.get(run_id)


def clear_run_cost(run_id: str) -> None:
    _accumulators.pop(run_id, None)
