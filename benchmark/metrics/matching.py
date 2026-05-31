"""
Shared, pure matching helpers used by several metric modules.

Fact matching is deliberately *loose* on the actual side and *exact* on what the
golden asserts: a golden key field is satisfied if the actual fact carries a
compatible value (string containment either direction, numbers within tolerance).
This avoids penalising the pipeline for harmless extra detail (e.g. golden
"ISO 27001" vs actual "ISO 27001:2022") while still catching wrong values.
"""
from __future__ import annotations

import re

_NUM_REL_TOL = 0.01    # 1% for monetary/float amounts
_NUM_ABS_TOL = 0.5     # half-unit for counts/minutes/hours


def norm(s: str) -> str:
    """Whitespace-normalised, lower-cased — the canonical text comparison."""
    return re.sub(r"\s+", " ", str(s)).strip().lower()


def text_contains(haystack: str, needle: str) -> bool:
    """True if `needle` appears in `haystack` after whitespace normalisation."""
    if not needle:
        return False
    return norm(needle) in norm(haystack)


def _to_number(v) -> float | None:
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    if isinstance(v, str):
        cleaned = re.sub(r"[£$,%\s]", "", v)
        try:
            return float(cleaned)
        except ValueError:
            return None
    return None


def values_match(expected, actual) -> bool:
    """Compare one expected value against one actual value (number- or string-aware)."""
    if actual is None:
        return False
    en, an = _to_number(expected), _to_number(actual)
    if en is not None and an is not None:
        if abs(en - an) <= _NUM_ABS_TOL:
            return True
        denom = max(abs(en), 1e-9)
        return abs(en - an) / denom <= _NUM_REL_TOL
    # string comparison: either contains the other (normalised)
    e, a = norm(expected), norm(actual)
    return bool(e) and (e in a or a in e)


def key_fields_match(expected: dict, actual_fields: dict) -> bool:
    """True iff EVERY expected key field has a compatible value in the actual fact."""
    for k, v in expected.items():
        if k not in actual_fields:
            return False
        if not values_match(v, actual_fields[k]):
            return False
    return True


def safe_div(numer: float, denom: float) -> float:
    return numer / denom if denom else 0.0
