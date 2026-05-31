from pydantic import BaseModel, Field
from typing import Literal, List, Dict

from .schema_enums import ComplianceStatus, DecisionBasis


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
    # E3: True when NO evidence fed this criterion. The LLM is NOT asked to invent
    # a score in that case — raw_score stays 0 but this flag means "not scored,
    # evidence insufficient", which the comparator/decision/report/UI surface
    # distinctly from a genuine 0/10. Default False keeps older payloads valid.
    insufficient_evidence: bool = False

class EvaluationOutput(BaseModel):
    evaluation_id: str
    vendor_id: str
    compliance_decisions: List[ComplianceDecision]
    criterion_scores: List[CriterionScore]
    overall_compliance: Literal["pass", "fail", "review_required"]
    total_weighted_score: float
    score_confidence: float = Field(ge=0.0, le=1.0)
    evaluation_warnings: List[str] = []


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
