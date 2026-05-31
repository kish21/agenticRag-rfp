"""
B1 — Retrieval recall@k.

Did retrieval surface the evidence for each fact the document actually contains?
A present fact is "retrieved" when its golden grounding substring appears in the
text of any retrieved chunk for that vendor. Absent facts are not counted (there
is nothing to retrieve).
"""
from __future__ import annotations

from benchmark.golden_schema import ExpectedVendor
from benchmark.metrics.actuals import ActualVendor
from benchmark.metrics.matching import safe_div, text_contains


def retrieval_recall(expected: ExpectedVendor, actual: ActualVendor) -> dict:
    present = [f for f in expected.facts if f.present and f.grounding_substring]
    joined = "\n".join(actual.retrieved_texts)
    covered = [f for f in present if text_contains(joined, f.grounding_substring)]
    missed = [
        {"fact_type": f.fact_type, "grounding": f.grounding_substring}
        for f in present if f not in covered
    ]
    return {
        "present_facts": len(present),
        "retrieved": len(covered),
        "recall": round(safe_div(len(covered), len(present)), 4),
        "missed": missed,
    }
