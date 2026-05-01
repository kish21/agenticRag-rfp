"""
Prevents the most common day-one failure: evaluating against the wrong document.
Takes 2 minutes of user time. Saves hours of wasted evaluation.
"""
import json
from app.core.llm_provider import call_llm


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
