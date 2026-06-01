"""
Phase 7 — report context builder.

Assembles the customer-grade report's 12 sections **from already-persisted run
data** — `decision_output`, `explanation_output`, and `agent_events`. It does
NOT recompute anything (alignment note #3 in PRODUCTION_READINESS_PLAN Phase 7):

  • podium / scorecards / winner   ← decision_output.shortlisted_vendors
  • mandatory_check_table / rejection_reasons ← decision_output.rejected_vendors
  • narratives / exec summary / methodology ← explanation_output
  • pairwise key_evidence          ← explanation_output narratives' grounded_claims
                                       (already verbatim-verified upstream)
  • audit_trail                    ← agent_events (1 row per event)
  • report cover "decision confidence" ← decision_output.decision_confidence
                                       (reused as report_confidence — no new field)

Pure function, no I/O — the caller passes a run-row dict (from `_db_get_run`).
This keeps it trivially unit-testable offline.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel

from app.schemas.schema_decision import (
    PodiumEntry, CriterionScorecard, PairwiseComparison,
    AuditTrailEntry, GroundedClaim,
)


class ReportContext(BaseModel):
    """Everything the report template needs — one flat, JSON-serialisable object
    (so the golden-snapshot test is stable)."""
    org_name: str
    rfp_title: str
    rfp_id: str
    decision_id: str
    decision_date: str
    report_confidence: float            # REUSES decision_confidence (alignment #1)
    requires_human_review: bool = False

    executive_summary: str = ""
    winner_declaration: str = ""
    methodology_note: str = ""

    podium: list[PodiumEntry] = []
    criterion_scorecards: list[CriterionScorecard] = []
    pairwise_comparisons: list[PairwiseComparison] = []
    mandatory_check_table: list[dict[str, Any]] = []
    rejection_reasons: dict[str, list[GroundedClaim]] = {}
    approval: dict[str, Any] = {}
    risks_and_open_questions: list[str] = []
    audit_trail: list[AuditTrailEntry] = []

    grounding_completeness: float = 0.0
    vendor_narratives: list[dict[str, Any]] = []   # prose, from explanation_output
    vendor_names: dict[str, Any] = {}              # vendor_id -> display name
    generated_at: str = ""


# ── helpers ───────────────────────────────────────────────────────────────────


def _vendor_name(vid: str, names: dict[str, Any], fallback: str | None = None) -> str:
    return names.get(vid) or fallback or vid


def _podium(shortlisted: list[dict], names: dict) -> list[PodiumEntry]:
    ranked = sorted(shortlisted, key=lambda v: v.get("rank", 9_999))
    out: list[PodiumEntry] = []
    for i, v in enumerate(ranked):
        nxt = ranked[i + 1] if i + 1 < len(ranked) else None
        delta = round(float(v.get("total_score", 0)) - float(nxt.get("total_score", 0)), 2) if nxt else 0.0
        # tipping factor: the criterion where this vendor scored highest
        breakdown = v.get("criterion_breakdown", []) or []
        top = max(breakdown, key=lambda c: c.get("raw_score", 0), default=None)
        tipping = (f"Strongest on {top.get('criterion_id', '')}"
                   if top else v.get("recommendation", "").replace("_", " "))
        out.append(PodiumEntry(
            rank=v.get("rank", i + 1),
            vendor_id=v.get("vendor_id", ""),
            vendor_name=_vendor_name(v.get("vendor_id", ""), names, v.get("vendor_name")),
            total_score=round(float(v.get("total_score", 0)), 2),
            score_delta_vs_next=delta,
            tipping_factor=tipping,
        ))
    return out


def _scorecards(shortlisted: list[dict]) -> list[CriterionScorecard]:
    """Pivot per-vendor criterion_breakdown into a criterion × vendor matrix."""
    cards: dict[str, CriterionScorecard] = {}
    for v in shortlisted:
        vid = v.get("vendor_id", "")
        for c in v.get("criterion_breakdown", []) or []:
            cid = c.get("criterion_id", "")
            if cid not in cards:
                cards[cid] = CriterionScorecard(
                    criterion_id=cid,
                    criterion_name=cid,        # name not on CriterionScore; id is the stable label
                    weight=0.0,
                    per_vendor_scores={},
                    rubric_used=c.get("rubric_band_applied", ""),
                )
            # E3 — do NOT emit a fabricated 0 for a criterion with no evidence;
            # omit the score so the report never shows it as a genuine 0/10.
            if not c.get("insufficient_evidence"):
                cards[cid].per_vendor_scores[vid] = float(c.get("raw_score", 0))
    return list(cards.values())


def _mandatory_table(rejected: list[dict], shortlisted: list[dict]) -> list[dict]:
    """One row per (vendor, mandatory check). Rejected vendors list their failed
    checks; shortlisted vendors are recorded as having passed mandatory checks."""
    rows: list[dict] = []
    for r in rejected:
        vid = r.get("vendor_id", "")
        vname = r.get("vendor_name", vid)
        for chk in r.get("failed_checks", []) or []:
            rows.append({"vendor_id": vid, "vendor_name": vname,
                         "check": chk, "result": "FAIL"})
    for v in shortlisted:
        rows.append({"vendor_id": v.get("vendor_id", ""),
                     "vendor_name": v.get("vendor_name", v.get("vendor_id", "")),
                     "check": "All mandatory requirements", "result": "PASS"})
    return rows


def _rejection_reasons(rejected: list[dict]) -> dict[str, list[GroundedClaim]]:
    """Map each rejected vendor to grounded claims. The evidence_citations are
    verbatim quotes captured upstream, so each reason pairs with a quote."""
    out: dict[str, list[GroundedClaim]] = {}
    for r in rejected:
        vid = r.get("vendor_id", "")
        reasons = r.get("rejection_reasons", []) or []
        citations = r.get("evidence_citations", []) or []
        claims: list[GroundedClaim] = []
        for idx, reason in enumerate(reasons):
            quote = citations[idx] if idx < len(citations) else (citations[0] if citations else "")
            claims.append(GroundedClaim(
                claim_text=reason,
                grounding_quote=quote,
                source_chunk_id="",        # decision-level reason; quote is the grounding
            ))
        out[vid] = claims
    return out


def _grounded_claims_of(narrative: dict) -> list[GroundedClaim]:
    out: list[GroundedClaim] = []
    for gc in narrative.get("grounded_claims", []) or []:
        try:
            out.append(GroundedClaim(**gc))
        except Exception:  # noqa: BLE001 — skip malformed legacy claims
            continue
    return out


def _pairwise(shortlisted: list[dict], narratives_by_vid: dict[str, dict], names: dict) -> list[PairwiseComparison]:
    """Winner vs runner-up, grounded BY CONSTRUCTION: key_evidence is drawn from
    each vendor's already-verified grounded_claims (no new LLM call, no chunks
    needed), so every claim carries a verbatim grounding_quote."""
    ranked = sorted(shortlisted, key=lambda v: v.get("rank", 9_999))
    if len(ranked) < 2:
        return []
    w, r = ranked[0], ranked[1]
    wid, rid = w.get("vendor_id", ""), r.get("vendor_id", "")
    wname = _vendor_name(wid, names, w.get("vendor_name"))
    rname = _vendor_name(rid, names, r.get("vendor_name"))
    gap = round(float(w.get("total_score", 0)) - float(r.get("total_score", 0)), 2)

    evidence = (_grounded_claims_of(narratives_by_vid.get(wid, {}))[:3]
                + _grounded_claims_of(narratives_by_vid.get(rid, {}))[:3])

    narrative = (
        f"{wname} ranked above {rname} by {gap} points "
        f"({w.get('total_score', 0)} vs {r.get('total_score', 0)}). "
        f"{wname} was assessed as '{w.get('recommendation', '').replace('_', ' ')}' "
        f"versus '{r.get('recommendation', '').replace('_', ' ')}' for {rname}. "
        "Supporting evidence below is quoted verbatim from each vendor's submission."
    )
    return [PairwiseComparison(winner_id=wid, runner_up_id=rid,
                               narrative=narrative, key_evidence=evidence)]


def _audit_trail(events: list[dict]) -> list[AuditTrailEntry]:
    """1:1 with agent_events (exit criterion: rendered count == events count)."""
    out: list[AuditTrailEntry] = []
    for ev in events:
        detail = {k: v for k, v in ev.items()
                  if k not in ("agent", "status", "ts", "timestamp", "message")}
        out.append(AuditTrailEntry(
            timestamp=str(ev.get("ts") or ev.get("timestamp") or ""),
            agent=str(ev.get("agent", "")),
            action=str(ev.get("status") or ev.get("message", "")),
            detail=detail,
        ))
    return out


# ── main entry ────────────────────────────────────────────────────────────────


def build_report_context(run: dict, org_name: str = "Meridian Financial Services") -> ReportContext:
    """Assemble the full report context from one persisted run-row dict."""
    dec = run.get("decision_output") or {}
    exp = run.get("explanation_output") or {}
    events = run.get("agent_events") or []
    names = run.get("vendor_names") or {}

    shortlisted = dec.get("shortlisted_vendors", []) or []
    rejected = dec.get("rejected_vendors", []) or []
    ranked = sorted(shortlisted, key=lambda v: v.get("rank", 9_999))

    narratives = exp.get("vendor_narratives", []) or []
    narratives_by_vid = {n.get("vendor_id", ""): n for n in narratives}

    # Winner declaration
    if ranked:
        top = ranked[0]
        winner = (f"{_vendor_name(top.get('vendor_id', ''), names, top.get('vendor_name'))} "
                  f"is recommended (score {round(float(top.get('total_score', 0)), 1)}/10, "
                  f"{top.get('recommendation', '').replace('_', ' ')}).")
    else:
        winner = "No vendor met the requirements for shortlisting."

    risks = list(dec.get("review_reasons", []) or []) \
        + list(dec.get("decision_warnings", []) or []) \
        + list(exp.get("limitations", []) or [])

    completed = run.get("completed_at") or run.get("created_at")

    return ReportContext(
        org_name=org_name,
        rfp_title=run.get("rfp_title") or run.get("rfp_id", "RFP Evaluation"),
        rfp_id=run.get("rfp_id", ""),
        decision_id=dec.get("decision_id", ""),
        decision_date=str(completed) if completed else "",
        report_confidence=float(dec.get("decision_confidence", 0.0)),
        requires_human_review=bool(dec.get("requires_human_review", False)),
        executive_summary=exp.get("executive_summary", "") or _fallback_exec(shortlisted, rejected),
        winner_declaration=winner,
        methodology_note=exp.get("methodology_note", "") or _DEFAULT_METHODOLOGY,
        podium=_podium(shortlisted, names),
        criterion_scorecards=_scorecards(shortlisted),
        pairwise_comparisons=_pairwise(shortlisted, narratives_by_vid, names),
        mandatory_check_table=_mandatory_table(rejected, shortlisted),
        rejection_reasons=_rejection_reasons(rejected),
        approval=dec.get("approval_routing", {}) or {},
        risks_and_open_questions=risks,
        audit_trail=_audit_trail(events),
        grounding_completeness=float(exp.get("grounding_completeness", 0.0)),
        vendor_narratives=narratives,
        vendor_names=dict(names),
        generated_at=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
    )


_DEFAULT_METHODOLOGY = (
    "This evaluation was conducted by an automated multi-agent AI pipeline. Every "
    "factual claim is grounded to a verbatim quote from the vendor submission. "
    "Mandatory compliance checks were evaluated against extracted structured facts; "
    "scoring was performed against the weighted criteria in the evaluation setup. "
    "Human review is recommended before any final procurement decision."
)


def _fallback_exec(shortlisted: list[dict], rejected: list[dict]) -> str:
    return (f"{len(shortlisted) + len(rejected)} vendor(s) were evaluated. "
            f"{len(rejected)} were rejected for failing mandatory requirements and "
            f"{len(shortlisted)} were shortlisted and scored.")
