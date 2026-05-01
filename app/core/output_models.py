from pydantic import BaseModel, Field, field_validator, model_validator
from typing import Optional, Literal, List, Dict, Any
from datetime import date, datetime
from enum import Enum


# ── Enums ────────────────────────────────────────────────

class SectionType(str, Enum):
    REQUIREMENT_RESPONSE = "requirement_response"
    SUPPORTING_EVIDENCE = "supporting_evidence"
    BACKGROUND = "background"
    BOILERPLATE = "boilerplate"

class CriticSeverity(str, Enum):
    HARD = "hard"
    SOFT = "soft"
    LOG = "log"

class CriticVerdict(str, Enum):
    APPROVED = "approved"
    APPROVED_WITH_WARNINGS = "approved_with_warnings"
    BLOCKED = "blocked"
    ESCALATED = "escalated"

class ComplianceStatus(str, Enum):
    PASS = "pass"
    FAIL = "fail"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"

class DocumentStatus(str, Enum):
    CURRENT = "current"
    PENDING = "pending"
    EXPIRED = "expired"
    NOT_MENTIONED = "not_mentioned"

class DecisionBasis(str, Enum):
    EXPLICIT_CONFIRMATION = "explicit_confirmation"
    IMPLICIT_CONFIRMATION = "implicit_confirmation"
    PARTIAL_COMPLIANCE = "partial_compliance"
    EXPLICIT_DENIAL = "explicit_denial"
    NOT_ADDRESSED = "not_addressed"


# ── Evaluation setup (customer-defined criteria) ─────────

class ExtractionTarget(BaseModel):
    """One thing to extract from vendor documents, derived from customer criteria."""
    target_id: str
    name: str
    description: str
    fact_type: str  # "certification" | "insurance" | "sla" | "project" | "pricing" | "custom"
    is_mandatory: bool
    feeds_criterion_id: Optional[str] = None
    feeds_check_id: Optional[str] = None


class MandatoryCheck(BaseModel):
    """One thing a vendor must have or be rejected outright."""
    check_id: str
    name: str
    description: str
    what_passes: str
    extraction_target_id: str


class ScoringCriterion(BaseModel):
    """One weighted scoring dimension used by the Evaluation Agent."""
    criterion_id: str
    name: str
    weight: float = Field(gt=0, le=1.0)
    rubric_9_10: str
    rubric_6_8: str
    rubric_3_5: str
    rubric_0_2: str
    extraction_target_ids: List[str]


class EvaluationSetup(BaseModel):
    """
    The confirmed customer criteria that drives the entire evaluation.
    The Planner reads this. Nothing is evaluated that is not defined here.
    """
    setup_id: str
    org_id: str
    department: str
    rfp_id: str
    rfp_confirmed: bool
    mandatory_checks: List[MandatoryCheck]
    scoring_criteria: List[ScoringCriterion]
    extraction_targets: List[ExtractionTarget]
    total_weight: float = Field(ge=0.99, le=1.01)
    confirmed_by: str
    confirmed_at: datetime
    source: str  # "department_template" | "rfp_extracted" | "manually_defined" | "mixed"

    @model_validator(mode="after")
    def weights_sum_to_one(self) -> "EvaluationSetup":
        if not self.scoring_criteria:
            return self
        actual = sum(c.weight for c in self.scoring_criteria)
        if not (0.99 <= actual <= 1.01):
            raise ValueError(
                f"scoring_criteria weights must sum to 1.0 (got {actual:.4f})"
            )
        return self

    @model_validator(mode="after")
    def every_check_has_extraction_target(self) -> "EvaluationSetup":
        target_ids = {t.target_id for t in self.extraction_targets}
        for check in self.mandatory_checks:
            if check.extraction_target_id not in target_ids:
                raise ValueError(
                    f"MandatoryCheck '{check.check_id}' references extraction_target_id "
                    f"'{check.extraction_target_id}' which is not in extraction_targets"
                )
        return self


# ── Planner output ────────────────────────────────────────

class TaskItem(BaseModel):
    task_id: str
    task_type: Literal[
        "retrieve", "extract", "evaluate",
        "compare", "decide", "explain",
        "mandatory_check", "scoring"
    ]
    agent: str
    inputs: Dict[str, Any]
    depends_on: List[str] = []
    priority: int = 1
    timeout_seconds: int = 120

class PlannerOutput(BaseModel):
    plan_id: str
    rfp_id: str
    org_id: str
    vendor_ids: List[str]
    tasks: List[TaskItem]
    estimated_duration_seconds: int
    confidence: float = Field(ge=0.0, le=1.0)
    warnings: List[str] = []
    rfp_confirmed: bool = False


# ── Critic output ─────────────────────────────────────────

class CriticFlag(BaseModel):
    flag_id: str
    severity: CriticSeverity
    agent: str
    check_name: str
    description: str
    evidence: str
    recommendation: str
    auto_resolvable: bool = False
    resolution_action: Optional[str] = None

class CriticOutput(BaseModel):
    critic_run_id: str
    evaluated_agent: str
    evaluated_output_id: str
    flags: List[CriticFlag] = []
    hard_flag_count: int = 0
    soft_flag_count: int = 0
    overall_verdict: CriticVerdict
    requires_human_review: bool = False
    human_review_reason: Optional[str] = None

    @model_validator(mode="after")
    def count_hard_flags(self):
        self.hard_flag_count = sum(
            1 for f in self.flags if f.severity == CriticSeverity.HARD
        )
        return self


# ── Ingestion output ──────────────────────────────────────

class ChunkRecord(BaseModel):
    chunk_id: str
    vendor_id: str
    org_id: str
    filename: str
    section_id: str
    section_title: str
    section_type: SectionType
    priority: int
    text: str
    token_count: int
    page_number: int
    qdrant_point_id: str

class IngestionOutput(BaseModel):
    doc_id: str
    vendor_id: str
    org_id: str
    filename: str
    total_chunks: int
    chunks_by_type: Dict[str, int]
    filtered_chunks: int
    extraction_triggered: bool
    quality_score: float = Field(ge=0.0, le=1.0)
    content_hash: str
    warnings: List[str] = []
    status: Literal["success", "partial", "failed", "duplicate"]


# ── Retrieval output ──────────────────────────────────────

class RetrievedChunk(BaseModel):
    chunk_id: str
    qdrant_point_id: str
    text: str
    section_id: str
    section_title: str
    section_type: str
    filename: str
    page_number: int
    vendor_id: str
    vector_similarity_score: float
    rerank_score: float
    final_score: float
    is_answer_bearing: bool

class RetrievalOutput(BaseModel):
    query_id: str
    original_query: str
    rewritten_query: str
    hyde_query_used: bool
    retrieval_strategy: str
    chunks: List[RetrievedChunk]
    total_candidates_before_rerank: int
    confidence: float = Field(ge=0.0, le=1.0)
    empty_retrieval: bool
    warnings: List[str] = []


# ── Extraction output ─────────────────────────────────────

class ExtractedCertification(BaseModel):
    standard_name: str
    version: Optional[str] = None
    cert_number: Optional[str] = None
    issuing_body: Optional[str] = None
    scope: Optional[str] = None
    valid_until: Optional[date] = None
    status: DocumentStatus
    confidence: float = Field(ge=0.0, le=1.0)
    grounding_quote: str
    source_chunk_id: str

    @field_validator("grounding_quote")
    @classmethod
    def grounding_not_empty(cls, v):
        if not v or len(v.strip()) < 5:
            raise ValueError(
                "grounding_quote must contain the exact source text. "
                "Empty grounding_quote means hallucination risk."
            )
        return v

class ExtractedInsurance(BaseModel):
    insurance_type: Optional[str] = None
    amount_gbp: Optional[float] = None
    provider: Optional[str] = None
    confidence: float = Field(ge=0.0, le=1.0)
    grounding_quote: str
    source_chunk_id: str

    @field_validator("grounding_quote")
    @classmethod
    def grounding_not_empty(cls, v):
        if not v or len(v.strip()) < 5:
            raise ValueError("grounding_quote required")
        return v

class ExtractedSLA(BaseModel):
    priority_level: Optional[str] = None
    response_minutes: Optional[int] = None
    resolution_hours: Optional[int] = None
    uptime_percentage: Optional[float] = None
    confidence: float = Field(ge=0.0, le=1.0)
    grounding_quote: str
    source_chunk_id: str

class ExtractedProject(BaseModel):
    client_name: Optional[str] = None
    client_sector: Optional[str] = None
    user_count: Optional[int] = None
    outcomes: Optional[str] = None
    reference_available: Optional[bool] = None
    confidence: float = Field(ge=0.0, le=1.0)
    grounding_quote: str
    source_chunk_id: str

class ExtractedPricing(BaseModel):
    year: Optional[int] = None
    amount_gbp: Optional[float] = None
    total_gbp: Optional[float] = None
    includes: List[str] = []
    confidence: float = Field(ge=0.0, le=1.0)
    grounding_quote: str
    source_chunk_id: str

class ExtractedFact(BaseModel):
    """Generic extracted fact — used for any ExtractionTarget with fact_type='custom'."""
    fact_id: str
    target_id: str  # links to ExtractionTarget.target_id
    fact_type: str
    fact_name: str
    text_value: str
    numeric_value: Optional[float] = None
    boolean_value: Optional[bool] = None
    confidence: float = Field(ge=0.0, le=1.0)
    grounding_quote: str
    source_chunk_id: str

    @field_validator("grounding_quote")
    @classmethod
    def grounding_not_empty(cls, v):
        if not v or len(v.strip()) < 5:
            raise ValueError(
                "grounding_quote must contain the exact source text. "
                "Empty grounding_quote means hallucination risk."
            )
        return v


class ExtractionOutput(BaseModel):
    extraction_id: str
    vendor_id: str
    org_id: str
    source_chunk_ids: List[str]
    certifications: List[ExtractedCertification] = []
    insurance: List[ExtractedInsurance] = []
    slas: List[ExtractedSLA] = []
    projects: List[ExtractedProject] = []
    pricing: List[ExtractedPricing] = []
    extracted_facts: List[ExtractedFact] = []
    extraction_completeness: float = Field(ge=0.0, le=1.0)
    hallucination_risk: float = Field(ge=0.0, le=1.0)
    warnings: List[str] = []


# ── Evaluation output ─────────────────────────────────────

class ComplianceDecision(BaseModel):
    check_id: str
    vendor_id: str
    decision: ComplianceStatus
    confidence: float = Field(ge=0.0, le=1.0)
    reasoning: str
    evidence_used: List[str]
    contradictions_found: List[str] = []
    decision_basis: DecisionBasis

class CriterionScore(BaseModel):
    criterion_id: str
    vendor_id: str
    raw_score: int = Field(ge=0, le=10)
    weighted_contribution: float
    confidence: float = Field(ge=0.0, le=1.0)
    rubric_band_applied: str
    evidence_used: List[str]
    score_rationale: str
    variance_estimate: float

class EvaluationOutput(BaseModel):
    evaluation_id: str
    vendor_id: str
    compliance_decisions: List[ComplianceDecision]
    criterion_scores: List[CriterionScore]
    overall_compliance: Literal["pass", "fail", "review_required"]
    total_weighted_score: float
    score_confidence: float = Field(ge=0.0, le=1.0)
    evaluation_warnings: List[str] = []


# ── Comparator output ─────────────────────────────────────

class VendorCriterionComparison(BaseModel):
    criterion_id: str
    vendor_id: str
    score: int
    key_differentiator: str
    relative_position: Literal[
        "best", "above_average", "average", "below_average", "weakest"
    ]
    evidence_summary: str

class CriterionComparison(BaseModel):
    criterion_id: str
    criterion_name: str
    weight: float
    vendors: List[VendorCriterionComparison]
    comparison_confidence: float
    rank_stable: bool
    distinguishing_factors: str

class ComparatorOutput(BaseModel):
    comparison_id: str
    rfp_id: str
    vendor_ids: List[str]
    criteria_comparisons: List[CriterionComparison]
    overall_ranking: List[str]
    ranking_confidence: float
    rank_margins: Dict[str, float]
    comparison_warnings: List[str] = []


# ── Decision output ───────────────────────────────────────

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


# ── Explanation output ────────────────────────────────────

class GroundedClaim(BaseModel):
    claim_text: str
    grounding_quote: str
    source_chunk_id: str
    source_filename: str
    source_page: int
    confidence: float

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


# ── Human override ────────────────────────────────────────

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
