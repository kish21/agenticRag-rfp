"""
The "actual" side of the comparison — what the pipeline produced for a scenario.

These are the contract between the runner (which fills them from a real pipeline
run) and the metric functions (which read them). Keeping them as plain validated
models means the metric functions never touch the pipeline and stay unit-testable.
"""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class ActualFact(BaseModel):
    """One extracted fact, normalised across the typed/custom extraction tables."""
    fact_type: str                       # certification|insurance|sla|project|pricing|custom
    fields: dict = Field(default_factory=dict)   # the fact's own fields (standard_name, amount, …)
    grounding_quote: str = ""
    source_chunk_id: str = ""
    confidence: float = 0.0


class ActualCriterionScore(BaseModel):
    criterion_id: str
    raw_score: Optional[int] = None      # None when the system declared insufficient evidence
    confidence: float = 0.0
    insufficient: bool = False           # the E3 no-forced-score state (Stage 4)


class ActualComplianceDecision(BaseModel):
    check_id: str
    decision: str                        # pass|fail|insufficient_evidence|...
    confidence: float = 0.0


class ActualVendor(BaseModel):
    vendor_id: str
    source_text: str = ""                # full vendor-document text (for grounding checks)
    retrieved_texts: list[str] = Field(default_factory=list)  # text of retrieved chunks
    facts: list[ActualFact] = Field(default_factory=list)
    criterion_scores: list[ActualCriterionScore] = Field(default_factory=list)
    compliance_decisions: list[ActualComplianceDecision] = Field(default_factory=list)
    rejected: bool = False
    # For scoring-consistency (B4): repeat-run raw scores, {criterion_id: [score, ...]}.
    repeat_scores: dict = Field(default_factory=dict)


class ActualScenario(BaseModel):
    scenario_id: str
    vendors: list[ActualVendor] = Field(default_factory=list)
    node_timings_s: dict = Field(default_factory=dict)
    cost: dict = Field(default_factory=dict)
    blocked: bool = False
    blocked_agent: str = ""
    error: str = ""
