from pydantic import BaseModel, Field, model_validator
from typing import Optional, Literal, List, Dict, Any

from .schema_enums import CriticSeverity, CriticVerdict


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
