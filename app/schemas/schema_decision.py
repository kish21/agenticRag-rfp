from pydantic import BaseModel, Field, field_validator
from typing import Optional, Literal, List, Dict, Any
from datetime import datetime

from .schema_evaluation import CriterionScore


class RejectionNotice(BaseModel):
    vendor_id: str
    vendor_name: str
    failed_checks: List[str]
    rejection_reasons: List[str]
    evidence_citations: List[str]
    clause_references: List[str]

class ShortlistedVendor(BaseModel):
    vendor_id: str
    vendor_name: str
    rank: int
    total_score: float
    score_confidence: float
    criterion_breakdown: List[CriterionScore]
    recommendation: Literal[
        "strongly_recommended", "recommended",
        "acceptable", "marginal"
    ]

class ApprovalRouting(BaseModel):
    approval_tier: int
    approver_role: str
    contract_value: float
    sla_hours: int
    sla_deadline: datetime
    escalation_reason: Optional[str] = None

class DecisionOutput(BaseModel):
    decision_id: str
    rfp_id: str
    rejected_vendors: List[RejectionNotice]
    shortlisted_vendors: List[ShortlistedVendor]
    approval_routing: ApprovalRouting
    decision_confidence: float
    requires_human_review: bool
    review_reasons: List[str] = []
    decision_warnings: List[str] = []


class GroundedClaim(BaseModel):
    claim_text: str
    grounding_quote: str
    source_chunk_id: str
    source_filename: str = ""
    source_page: int = 1
    confidence: float = 0.8


class SystemFact(BaseModel):
    """A claim sourced from upstream agent outputs (decision/evaluation/comparator/
    extraction) rather than from a PDF chunk. Has NO grounding_quote — the source
    is the system's own structured output, which is trusted by definition.
    Keeping this separate from GroundedClaim is what stops the Explanation LLM
    from fabricating chunk_ids for facts like 'Rank: 2' or 'Score: 8.5/10'."""
    fact_text: str
    origin: Literal["decision", "evaluation", "extraction", "comparator"]
    origin_id: str = ""  # check_id | criterion_id | vendor rank as string | etc.


class SynthesisLLMResponse(BaseModel):
    """Validates the raw LLM JSON output from the synthesis/explanation step."""
    executive_summary: str = ""
    compliance_narrative: str = ""
    scoring_narrative: str = ""
    recommendation_rationale: str = ""
    grounded_claims: List[GroundedClaim] = []
    # System-computed facts (rank, score, check pass/fail). NO grounding required —
    # these come from trusted upstream agents, not PDF chunks.
    system_facts: List[SystemFact] = []

    @field_validator("grounded_claims", mode="before")
    @classmethod
    def _coerce_claims(cls, v: object) -> object:
        if not isinstance(v, list):
            return []
        return v

    @field_validator("system_facts", mode="before")
    @classmethod
    def _coerce_system_facts(cls, v: object) -> object:
        if not isinstance(v, list):
            return []
        return v


class VendorNarrative(BaseModel):
    vendor_id: str
    vendor_name: str
    executive_summary: str
    compliance_narrative: str
    scoring_narrative: str
    recommendation_rationale: str
    grounded_claims: List[GroundedClaim]
    ungrounded_claims_removed: int = 0
    # System-computed facts that don't need grounding (decision rank, scores, etc.)
    system_facts: List[SystemFact] = []
    # Diagnostic — captures each claim that failed verify_grounding() with the
    # LLM-supplied quote next to a slice of the actual source chunk so the
    # drift pattern (unicode, paraphrase, wrong chunk) can be inspected.
    ungrounded_examples: List[dict] = []

# ── Phase 7 — customer-grade PDF report models ───────────────────────────────


class PodiumEntry(BaseModel):
    """One row of the ranked podium (section 4 of the report)."""
    rank: int
    vendor_id: str
    vendor_name: str
    total_score: float
    score_delta_vs_next: float = 0.0   # gap to the next-ranked vendor
    tipping_factor: str = ""           # one-line "what decided this rank"


class CriterionScorecard(BaseModel):
    """One criterion row of the criterion × vendor scorecard matrix (section 5)."""
    criterion_id: str
    criterion_name: str
    weight: float
    per_vendor_scores: Dict[str, float] = {}   # vendor_id -> raw score
    rubric_used: str = ""


class PairwiseComparison(BaseModel):
    """Winner-vs-runner-up narrative (section 6). Every claim in key_evidence is
    a GroundedClaim with a verbatim quote from one of the two vendors' chunks."""
    winner_id: str
    runner_up_id: str
    narrative: str
    key_evidence: List[GroundedClaim] = []


class AuditTrailEntry(BaseModel):
    """One agent event for the audit-trail appendix (section 12). Rendered from
    the run's `agent_events` / `event_log` — NOT recomputed. `timestamp` is the
    ISO string as stored, to avoid parse-fragility on render."""
    timestamp: str = ""
    agent: str = ""
    action: str = ""
    detail: Dict[str, Any] = {}


class ExplanationOutput(BaseModel):
    explanation_id: str
    executive_summary: str
    vendor_narratives: List[VendorNarrative]
    methodology_note: str
    limitations: List[str] = []
    grounding_completeness: float = Field(ge=0.0, le=1.0)
    report_confidence: float
    # ── Phase 7 report fields (all optional → backward-compatible with the
    #    pre-Phase-7 Explanation agent). The report's cover-page "decision
    #    confidence" REUSES `report_confidence` above — there is deliberately
    #    NO separate `decision_confidence` field (see PRODUCTION_READINESS_PLAN
    #    Phase 7 alignment note #1). ──
    winner_declaration: str = ""
    podium: List[PodiumEntry] = []
    criterion_scorecards: List[CriterionScorecard] = []
    pairwise_comparisons: List[PairwiseComparison] = []
    mandatory_check_table: List[Dict[str, Any]] = []
    rejection_reasons: Dict[str, List[GroundedClaim]] = {}
    audit_trail: List[AuditTrailEntry] = []
    risks_and_open_questions: List[str] = []


class AuditOverride(BaseModel):
    override_id: str
    org_id: str
    run_id: str
    overridden_by: str
    original_decision: Dict[str, Any]
    new_decision: Dict[str, Any]
    reason: str
    timestamp: datetime
    approved_by: Optional[str] = None

    @field_validator("reason")
    @classmethod
    def reason_not_empty(cls, v):
        if len(v.strip()) < 20:
            raise ValueError(
                "Override reason must be at least 20 characters. "
                "Documented reasoning is required for audit compliance."
            )
        return v
