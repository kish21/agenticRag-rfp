"""
B2 — Extraction precision & recall, per fact type.

Recall  = present golden facts that were extracted (matched on key fields).
Precision = extracted facts that correspond to a present golden fact, over all
            extracted facts of that type.
Hallucinated-against-absent = extracted facts of a type the golden marks ABSENT
            (the document does not contain it) — a strong hallucination signal,
            reported separately so it can never be hidden inside precision.

Matching is loose on the actual side (see matching.py): a golden fact is found
if some extracted fact of the same type satisfies all its key fields.
"""
from __future__ import annotations

from collections import defaultdict

from benchmark.golden_schema import ExpectedVendor
from benchmark.metrics.actuals import ActualVendor
from benchmark.metrics.matching import key_fields_match, safe_div


def _by_type(items, type_attr):
    out = defaultdict(list)
    for it in items:
        out[getattr(it, type_attr)].append(it)
    return out


def extraction_quality(expected: ExpectedVendor, actual: ActualVendor) -> dict:
    exp_by_type = _by_type(expected.facts, "fact_type")
    act_by_type = _by_type(actual.facts, "fact_type")
    all_types = sorted(set(exp_by_type) | set(act_by_type))

    per_type: dict[str, dict] = {}
    tp = fp_absent = total_present = total_extracted = 0

    for ft in all_types:
        present = [e for e in exp_by_type.get(ft, []) if e.present]
        absent = [e for e in exp_by_type.get(ft, []) if not e.present]
        extracted = act_by_type.get(ft, [])

        matched_present = sum(
            1 for e in present
            if any(key_fields_match(e.key_fields, a.fields) for a in extracted)
        )
        # An extracted fact "supports a present fact" if it matches any present golden.
        supported = sum(
            1 for a in extracted
            if any(key_fields_match(e.key_fields, a.fields) for e in present)
        )
        # Hallucination: the golden says this fact type is ABSENT, yet something was extracted.
        hallucinated = len(extracted) if (absent and not present) else 0

        per_type[ft] = {
            "present": len(present),
            "extracted": len(extracted),
            "recall": round(safe_div(matched_present, len(present)), 4) if present else None,
            "precision": round(safe_div(supported, len(extracted)), 4) if extracted else None,
            "hallucinated_against_absent": hallucinated,
        }
        tp += matched_present
        total_present += len(present)
        total_extracted += len(extracted)
        fp_absent += hallucinated

    return {
        "per_type": per_type,
        "recall": round(safe_div(tp, total_present), 4) if total_present else None,
        "precision_present": round(safe_div(tp, total_extracted), 4) if total_extracted else None,
        "hallucinated_against_absent": fp_absent,
        "total_present": total_present,
        "total_extracted": total_extracted,
    }
