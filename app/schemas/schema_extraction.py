from pydantic import BaseModel, Field, field_validator, model_validator
from typing import Optional, List
from datetime import date

from .schema_enums import DocumentStatus


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
    amount: Optional[float] = None          # currency-neutral; use run.currency for display
    amount_gbp: Optional[float] = None      # deprecated alias — read amount instead
    provider: Optional[str] = None
    confidence: float = Field(ge=0.0, le=1.0)
    grounding_quote: str
    source_chunk_id: str

    @model_validator(mode="after")
    def _backfill_amount(self) -> "ExtractedInsurance":
        if self.amount is None and self.amount_gbp is not None:
            self.amount = self.amount_gbp
        elif self.amount_gbp is None and self.amount is not None:
            self.amount_gbp = self.amount
        return self

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
    amount: Optional[float] = None          # currency-neutral; use run.currency for display
    total_amount: Optional[float] = None    # currency-neutral total
    amount_gbp: Optional[float] = None      # deprecated alias
    total_gbp: Optional[float] = None       # deprecated alias
    description: Optional[str] = None
    includes: List[str] = []
    confidence: float = Field(ge=0.0, le=1.0)
    grounding_quote: str
    source_chunk_id: str

    @model_validator(mode="after")
    def _backfill_amounts(self) -> "ExtractedPricing":
        if self.amount is None and self.amount_gbp is not None:
            self.amount = self.amount_gbp
        elif self.amount_gbp is None and self.amount is not None:
            self.amount_gbp = self.amount
        if self.total_amount is None and self.total_gbp is not None:
            self.total_amount = self.total_gbp
        elif self.total_gbp is None and self.total_amount is not None:
            self.total_gbp = self.total_amount
        return self

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
    retried_fact_types: List[str] = []  # fact types where extraction critic triggered a retry
