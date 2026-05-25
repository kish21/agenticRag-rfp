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


class SynthesisLLMResponse(BaseModel):
    """Validates the raw LLM JSON output from the synthesis/explanation step."""
    executive_summary: str = ""
    compliance_narrative: str = ""
    scoring_narrative: str = ""
    recommendation_rationale: str = ""
    grounded_claims: List[GroundedClaim] = []

    @field_validator("grounded_claims", mode="before")
    @classmethod
    def _coerce_claims(cls, v: object) -> object:
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

class ExplanationOutput(BaseModel):
    explanation_id: str
    executive_summary: str
    vendor_narratives: List[VendorNarrative]
    methodology_note: str
    limitations: List[str] = []
    grounding_completeness: float = Field(ge=0.0, le=1.0)
    report_confidence: float


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
