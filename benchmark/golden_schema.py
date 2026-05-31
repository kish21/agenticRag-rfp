"""
Golden-file (answer-key) schema for the E3 evidence-quality benchmark.

Each synthetic scenario ships a golden.json validated against `ScenarioGolden`.
Because the documents are authored by us, the ground truth is known *by
construction* — every expected fact below is something we deliberately wrote
into (or deliberately left out of) the scenario PDFs.

The metrics engine (benchmark/metrics.py) compares the pipeline's actual output
against these expectations to compute retrieval recall, extraction
precision/recall, grounding/citation accuracy, mandatory correctness, scoring
consistency, and the insufficient-evidence rate.

Design notes
------------
* `ExpectedFact` is fact-type agnostic: `key_fields` holds the few fields that
  must match (e.g. {"standard_name": "ISO 27001"}); `grounding_substring` is a
  verbatim snippet that MUST appear in the source document (whitespace-
  normalised) — this is how we score grounding/citation honesty.
* `expected_page` lets us approximate retrieval recall: a fact is "retrieved"
  if any retrieved chunk for the owning vendor covers its grounding text.
* `present=False` marks a fact the document deliberately OMITS — the pipeline
  must NOT invent it (a hallucination if extracted), and any mandatory check or
  criterion that depends on it must resolve to insufficient_evidence, not a
  forced score.
"""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field, model_validator

FactType = Literal["certification", "insurance", "sla", "project", "pricing", "custom"]
MandatoryOutcome = Literal["pass", "fail", "insufficient_evidence"]
# Expected scoring signal for a criterion: a rubric band, or "insufficient"
# when the document gives no evidence to score on (the E3 product change —
# we must not fold a fabricated 0 into the ranking).
ScoreExpectation = Literal["9-10", "6-8", "3-5", "0-2", "insufficient"]


class ExpectedFact(BaseModel):
    """One fact the document either contains (present=True) or omits (present=False)."""
    fact_type: FactType
    # The minimal set of fields whose values must match what we wrote. Values are
    # compared loosely (str: normalised substring/equality; numbers: within tol).
    key_fields: dict = Field(default_factory=dict)
    # Verbatim snippet from the source doc that should back this fact. Required
    # when present=True; the grounding check verifies the pipeline's
    # grounding_quote maps to real source text containing this.
    grounding_substring: Optional[str] = None
    expected_page: Optional[int] = None
    present: bool = True
    # Free-text note for the human reading the golden file.
    note: str = ""

    @model_validator(mode="after")
    def _present_facts_need_grounding(self) -> "ExpectedFact":
        if self.present and not self.grounding_substring:
            raise ValueError(
                f"present fact ({self.fact_type}, {self.key_fields}) must declare a "
                "grounding_substring so grounding accuracy can be scored"
            )
        return self


class ExpectedMandatory(BaseModel):
    check_id: str
    outcome: MandatoryOutcome
    note: str = ""


class ExpectedCriterion(BaseModel):
    criterion_id: str
    expectation: ScoreExpectation
    note: str = ""


class ExpectedVendor(BaseModel):
    vendor_id: str
    vendor_pdf: str                      # filename within the scenario dir
    facts: list[ExpectedFact] = Field(default_factory=list)
    mandatory: list[ExpectedMandatory] = Field(default_factory=list)
    criteria: list[ExpectedCriterion] = Field(default_factory=list)
    # If set, the whole vendor is expected to be rejected on mandatory grounds.
    expected_rejected: Optional[bool] = None


class ScenarioGolden(BaseModel):
    """The complete answer key for one benchmark scenario."""
    scenario_id: str
    title: str
    # What this scenario is built to stress (table parsing, long-doc retrieval,
    # contradictions, missing evidence, …). Documentation + grouping only.
    stresses: list[str] = Field(default_factory=list)
    rfp_pdf: str
    # A fixed EvaluationSetup (deterministic criterion_id/check_id/target_id),
    # injected directly so the benchmark measures the DOWNSTREAM pipeline against
    # a known answer key rather than re-deriving criteria via the LLM each run.
    setup_json: str
    vendors: list[ExpectedVendor]

    def present_facts(self) -> list[ExpectedFact]:
        return [f for v in self.vendors for f in v.facts if f.present]

    def absent_facts(self) -> list[ExpectedFact]:
        return [f for v in self.vendors for f in v.facts if not f.present]
