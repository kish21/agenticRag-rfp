"""
Shared decision-output summariser.

Reach for this whenever you need a stable, comparable headline of a
DecisionOutput: bypass-cache divergence flag (Phase 3), audit-grade PDF
report header (Phase 7), delivery channel subject lines (Phase 8),
re-evaluation diffing (Phase 6).

Defining it once here prevents the inevitable copy-paste with subtle
divergences (whether `winner` falls back to `shortlist[0]`, whether
`rejected` is sorted by score or by id, etc.).
"""
from __future__ import annotations

from typing import Any, Optional, TypedDict


class DecisionSummary(TypedDict):
    """Headline fields a decision-comparison or report consumer needs."""
    winner: Optional[str]
    shortlist: list[str]
    rejected: list[str]


def _safe_vendor_ids(items: Any) -> list[str]:
    """
    Returns the sorted list of distinct, non-empty vendor_id strings from
    a list of vendor dicts. Tolerates missing keys, None values, duplicates,
    and non-list inputs so sorted() never sees a None and never blows up
    on a partially-populated DecisionOutput (e.g., from a blocked run).
    """
    if not isinstance(items, list):
        return []
    out: set[str] = set()
    for v in items:
        if not isinstance(v, dict):
            continue
        vid = v.get("vendor_id")
        if isinstance(vid, str) and vid.strip():
            out.add(vid)
    return sorted(out)


def extract_decision_summary(d: Optional[dict]) -> DecisionSummary:
    """
    Reduce a DecisionOutput dict to its headline fields. None-safe, missing-
    key-safe, sort-stable. Cheap; safe to call repeatedly without memoising.

    >>> extract_decision_summary({
    ...     "recommended_vendor": {"vendor_id": "acme"},
    ...     "shortlisted_vendors": [{"vendor_id": "acme"}, {}, {"vendor_id": "apex"}],
    ...     "rejected_vendors": [{"vendor_id": None}, {"vendor_id": "stranger"}],
    ... })
    {'winner': 'acme', 'shortlist': ['acme', 'apex'], 'rejected': ['stranger']}
    """
    if not isinstance(d, dict):
        return {"winner": None, "shortlist": [], "rejected": []}
    recommended = d.get("recommended_vendor")
    winner = recommended.get("vendor_id") if isinstance(recommended, dict) else None
    return {
        "winner": winner if isinstance(winner, str) else None,
        "shortlist": _safe_vendor_ids(d.get("shortlisted_vendors")),
        "rejected": _safe_vendor_ids(d.get("rejected_vendors")),
    }
