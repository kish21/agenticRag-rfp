"""
Prevents the most common day-one failure: evaluating against the wrong document.
Takes 2 minutes of user time. Saves hours of wasted evaluation.

Phase 5 (2026-05-29) added the RFP domain model below. The async
extract_rfp_identity() helper is unrelated to the new model — it is still
used by the manual-mode upload path to confirm the RFP at confirm-time.
"""
import json
from datetime import datetime
from typing import Literal, Optional
from uuid import UUID

from pydantic import BaseModel, Field

from app.providers.llm import call_llm


SubmissionStatus = Literal["open", "closed", "processing", "facts_ready", "evaluated"]
AutonomyMode = Literal["manual", "auto_to_evaluate", "auto_to_report"]
IngestionJobStatus = Literal[
    "received", "superseded", "queued", "processing", "facts_ready",
    "failed", "duplicate", "needs_attribution", "rejected_late",
]

_ALLOWED_TRANSITIONS: dict[SubmissionStatus, set[SubmissionStatus]] = {
    "open": {"closed"},
    "closed": {"processing"},
    "processing": {"facts_ready"},
    "facts_ready": {"evaluated"},
    "evaluated": set(),
}


def can_transition(current: SubmissionStatus, target: SubmissionStatus) -> bool:
    """Returns True iff target is a legal next state from current."""
    return target in _ALLOWED_TRANSITIONS.get(current, set())


class RFP(BaseModel):
    """Domain model for the rfps table. Phase 5.0."""
    rfp_id: str
    org_id: UUID
    title: str
    department: Optional[str] = None
    created_by_email: str
    created_at: Optional[datetime] = None
    submission_deadline: Optional[datetime] = None
    submission_status: SubmissionStatus = "open"
    autonomy_mode: AutonomyMode = "auto_to_evaluate"


class InvitedVendor(BaseModel):
    rfp_id: str
    vendor_id: str
    vendor_name: Optional[str] = None
    invited_by: str
    invited_at: Optional[datetime] = None


class IngestionJob(BaseModel):
    job_id: UUID
    org_id: UUID
    rfp_id: str
    vendor_id: str
    content_hash: str = Field(min_length=64, max_length=64)
    status: IngestionJobStatus
    filename: Optional[str] = None
    source_uri: Optional[str] = None
    attribution_confidence: Optional[float] = None
    received_at: Optional[datetime] = None
    attempted_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    error: Optional[str] = None
    doc_id: Optional[UUID] = None
    superseded_by: Optional[UUID] = None


async def extract_rfp_identity(rfp_text: str) -> dict:
    """Reads the RFP and extracts identity fields for user confirmation."""
    response_text = await call_llm(
        messages=[
            {
                "role": "system",
                "content": """Extract RFP identity fields. Return JSON only:
{
  "reference": "RFP reference number",
  "issuer": "Organisation issuing the RFP",
  "title": "Title or subject of the RFP",
  "deadline": "Submission deadline if found",
  "mandatory_count": N,
  "scoring_criteria_count": N,
  "confidence": 0.0-1.0
}"""
            },
            {
                "role": "user",
                "content": rfp_text[:3000]
            }
        ],
        temperature=0.0,
        response_format={"type": "json_object"},
    )
    return json.loads(response_text)


def format_confirmation_message(identity: dict) -> str:
    """Formats the confirmation message shown to the user before evaluation."""
    return f"""Before running the evaluation, please confirm this is the correct RFP:

  Reference:        {identity.get('reference', 'Not found')}
  Issuer:           {identity.get('issuer', 'Not found')}
  Title:            {identity.get('title', 'Not found')}
  Deadline:         {identity.get('deadline', 'Not found')}
  Mandatory reqs:   {identity.get('mandatory_count', '?')} found
  Scoring criteria: {identity.get('scoring_criteria_count', '?')} found

Is this the correct RFP document? (yes/no)""".strip()
