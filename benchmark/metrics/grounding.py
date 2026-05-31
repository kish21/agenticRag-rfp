"""
B3 — Grounding / citation accuracy (the anti-hallucination metric).

For every extracted fact, does its `grounding_quote` actually appear (verbatim,
whitespace-normalised) in the vendor's source document? A fact whose quote is NOT
in the source has a fabricated citation — the single most important failure for an
"audit-ready, evidence-grounded" product, so fabricated citations are counted and
listed explicitly, never averaged away.
"""
from __future__ import annotations

from benchmark.metrics.actuals import ActualVendor
from benchmark.metrics.matching import safe_div, text_contains


def grounding_accuracy(actual: ActualVendor) -> dict:
    facts = [f for f in actual.facts if f.grounding_quote]
    fabricated = [
        {"fact_type": f.fact_type, "quote": f.grounding_quote[:120]}
        for f in facts if not text_contains(actual.source_text, f.grounding_quote)
    ]
    honest = len(facts) - len(fabricated)
    # Facts that were extracted with NO grounding quote at all (also a failure).
    ungrounded = sum(1 for f in actual.facts if not f.grounding_quote)
    return {
        "facts_with_quote": len(facts),
        "honest_citations": honest,
        "fabricated_citations": len(fabricated),
        "ungrounded_facts": ungrounded,
        "grounding_accuracy": round(safe_div(honest, len(facts)), 4) if facts else None,
        "fabricated": fabricated,
    }
