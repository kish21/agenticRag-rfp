"""
B4 / B6 — Evaluation quality.

  * band agreement      — for criteria with an expected rubric band, does the
                          raw score land in it?
  * insufficient rate   — for criteria the golden marks "insufficient" (no evidence),
                          did the system say so instead of forcing a score? (the E3
                          no-forced-score promise — expected to be low until Stage 4)
  * mandatory accuracy  — do compliance decisions match the expected pass/fail/
                          insufficient_evidence outcome?
  * rejection accuracy  — is a vendor missing a mandatory item actually rejected?
  * score consistency   — variance of raw scores across repeat runs (determinism).
"""
from __future__ import annotations

from statistics import pstdev

from benchmark.golden_schema import ExpectedVendor
from benchmark.metrics.actuals import ActualVendor
from benchmark.metrics.matching import safe_div

_BANDS = {"9-10": (9, 10), "6-8": (6, 8), "3-5": (3, 5), "0-2": (0, 2)}


def _score_for(actual: ActualVendor, criterion_id: str):
    for cs in actual.criterion_scores:
        if cs.criterion_id == criterion_id:
            return cs
    return None


def _blocked_result(actual: ActualVendor) -> dict:
    """E3.b.2 — a blocked/dropped vendor never produced an assessment, so its empty
    scores must NOT be read as 'forced' or mandatory-wrong. Per the signed-off policy
    (exclude + report separately), every quality rate is excluded (None / 0-denominator)
    and the vendor is surfaced only via `blocked` / `blocked_stage`."""
    return {
        "band_agreement": None, "band_checked": 0,
        "insufficient_expected": 0, "insufficient_correct": 0, "insufficient_rate": None,
        "forced_when_insufficient": 0,
        "mandatory_accuracy": None, "mandatory_checked": 0,
        "rejection_correct": None,
        "blocked": True, "blocked_stage": actual.blocked_stage,
    }


def scoring_quality(expected: ExpectedVendor, actual: ActualVendor) -> dict:
    if actual.blocked_stage is not None:
        return _blocked_result(actual)

    band_total = band_ok = 0
    insf_expected = insf_correct = 0
    forced_when_insufficient = 0       # golden=insufficient but system emitted a score

    for c in expected.criteria:
        cs = _score_for(actual, c.criterion_id)
        if c.expectation == "insufficient":
            insf_expected += 1
            if cs is not None and (cs.insufficient or cs.raw_score is None):
                insf_correct += 1
            else:
                forced_when_insufficient += 1
        elif c.expectation in _BANDS:
            band_total += 1
            lo, hi = _BANDS[c.expectation]
            if cs is not None and cs.raw_score is not None and lo <= cs.raw_score <= hi:
                band_ok += 1

    # Mandatory decision accuracy.
    mand_total = len(expected.mandatory)
    mand_ok = 0
    for m in expected.mandatory:
        got = next((d.decision for d in actual.compliance_decisions if d.check_id == m.check_id), None)
        if got == m.outcome:
            mand_ok += 1

    rejection = None
    if expected.expected_rejected is not None:
        rejection = bool(actual.rejected) == bool(expected.expected_rejected)

    return {
        "band_agreement": round(safe_div(band_ok, band_total), 4) if band_total else None,
        "band_checked": band_total,
        "insufficient_expected": insf_expected,
        "insufficient_correct": insf_correct,
        "insufficient_rate": round(safe_div(insf_correct, insf_expected), 4) if insf_expected else None,
        "forced_when_insufficient": forced_when_insufficient,
        "mandatory_accuracy": round(safe_div(mand_ok, mand_total), 4) if mand_total else None,
        "mandatory_checked": mand_total,
        "rejection_correct": rejection,
        "blocked": False, "blocked_stage": None,
    }


def score_consistency(actual: ActualVendor) -> dict:
    """Mean population stdev of raw scores across repeat runs (lower = more deterministic).

    `actual.repeat_scores` is {criterion_id: [score, ...]}."""
    samples = actual.repeat_scores or {}
    stdevs = [pstdev(v) for v in samples.values() if len(v) >= 2]
    return {
        "criteria_with_repeats": len(stdevs),
        "mean_score_stdev": round(sum(stdevs) / len(stdevs), 4) if stdevs else None,
        "max_score_stdev": round(max(stdevs), 4) if stdevs else None,
    }
