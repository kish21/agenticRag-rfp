from pydantic import BaseModel, Field, model_validator
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
    # P1.7 — self-consistency voting audit trail. Populated only for BORDERLINE checks
    # that were resampled (primary confidence in the configured band): keys are
    # {samples, tally, winner}. {"samples": 1} (or empty) means the check was decided by
    # a single call (clear-cut, or voting disabled). Defaulted → older payloads stay valid;
    # downstream consumers ignore it unless they want the breakdown.
    vote_breakdown: Dict = {}

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
    # E3.d — coverage-normalised ranking. `coverage` is the fraction of total criterion
    # weight actually assessed (criteria with insufficient_evidence are excluded);
    # `coverage_normalised_score` projects the observed quality over that assessed weight
    # onto 0–10 (== total_weighted_score when coverage == 1.0). Ranking/recommendation
    # use the normalised score so a vendor that simply wasn't fully assessed is not
    # treated as if it scored 0 on the un-assessed criteria. Defaults keep older payloads
    # valid: coverage 1.0 + normalised falls back to total_weighted_score at use-site.
    coverage: float = Field(default=1.0, ge=0.0, le=1.0)
    coverage_normalised_score: float = 0.0
    score_confidence: float = Field(ge=0.0, le=1.0)
    evaluation_warnings: List[str] = []

    @model_validator(mode="after")
    def _derive_normalised_at_full_coverage(self) -> "EvaluationOutput":
        # Back-compat: at full coverage the normalised score IS the absolute total (maths:
        # total / 1.0). Older payloads / fixtures that set only total_weighted_score and
        # leave coverage at its 1.0 default therefore rank exactly as before, instead of
        # defaulting normalised to 0.0 and being mislabelled 'marginal' / ranked last.
        # The evaluation agent sets both explicitly; this only fills the unset default.
        if self.coverage >= 1.0 and self.coverage_normalised_score == 0.0:
            object.__setattr__(self, "coverage_normalised_score", self.total_weighted_score)
        return self


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
    # E3.d — vendors ranked but assessed on less than platform.ranking.min_coverage_for_trust
    # of the criterion weight; surfaced so the decision agent flags them for human review.
    low_coverage_vendors: List[str] = []
    comparison_warnings: List[str] = []
