"""
B5 — Runtime, cost, failure rate.

Pure aggregation of the operational telemetry the runner captures from each run
(node timings + RunCostAccumulator summary + blocked flag). No judgement here —
just surfaces wall-clock, USD, and whether the run failed operationally.
"""
from __future__ import annotations

from benchmark.metrics.actuals import ActualScenario


def runtime_cost(actual: ActualScenario) -> dict:
    timings = actual.node_timings_s or {}
    wall = round(sum(float(v) for v in timings.values()), 3)
    cost = actual.cost or {}
    return {
        "wall_clock_s": wall,
        "slowest_stage": max(timings, key=timings.get) if timings else None,
        "node_timings_s": timings,
        "total_cost_usd": round(float(cost.get("total_cost_usd", 0.0)), 6),
        "total_llm_calls": int(cost.get("total_calls", 0)),
        "cache_hit_rate": cost.get("cache_hit_rate"),
        "blocked": actual.blocked,
        "blocked_agent": actual.blocked_agent,
        "errored": bool(actual.error),
    }
