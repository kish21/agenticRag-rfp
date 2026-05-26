from pydantic import BaseModel, Field, model_validator
from typing import Optional, List
from datetime import datetime


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
    source: Optional[str] = None
    is_locked: Optional[bool] = None
    page_reference: Optional[str] = None


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
    source: Optional[str] = None
    is_locked: Optional[bool] = None
    page_reference: Optional[str] = None


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
    confirmed_at: Optional[datetime] = None
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
