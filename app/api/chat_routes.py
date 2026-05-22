"""
Personal AI chat endpoints — document Q&A and success criteria storage.

POST /api/v1/chat/document  — upload ERP doc + question, returns answer + suggested criteria
GET  /api/v1/chat/criteria  — fetch saved success criteria for the current user
POST /api/v1/chat/criteria  — save/replace success criteria for the current user
"""
import io
import re
from typing import Optional

import sqlalchemy as sa
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from pydantic import BaseModel

from app.auth.dependencies import get_current_user, get_db
from app.auth.jwt import TokenData
from app.providers.llm import call_llm

router = APIRouter(prefix="/api/v1/chat", tags=["chat"])

_SUPPORTED_TYPES = {
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "text/csv",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/octet-stream",  # fallback when browser sends generic type
}

_MAX_FILE_BYTES = 10 * 1024 * 1024  # 10 MB


# ── Text extraction ────────────────────────────────────────────────────────────

def _extract_pdf(data: bytes) -> str:
    from pypdf import PdfReader
    reader = PdfReader(io.BytesIO(data))
    parts = []
    for page in reader.pages:
        text = page.extract_text() or ""
        parts.append(text)
    return "\n".join(parts)


def _extract_docx(data: bytes) -> str:
    from docx import Document
    doc = Document(io.BytesIO(data))
    return "\n".join(p.text for p in doc.paragraphs if p.text.strip())


def _extract_csv_or_xlsx(data: bytes, filename: str) -> str:
    import pandas as pd
    if filename.lower().endswith(".xlsx"):
        df = pd.read_excel(io.BytesIO(data))
    else:
        df = pd.read_csv(io.BytesIO(data))
    # Return first 200 rows as markdown-ish table to keep context size sane
    return df.head(200).to_string(index=False)


def _extract_text(data: bytes, filename: str) -> str:
    name = filename.lower()
    if name.endswith(".pdf"):
        return _extract_pdf(data)
    if name.endswith(".docx"):
        return _extract_docx(data)
    if name.endswith((".csv", ".xlsx")):
        return _extract_csv_or_xlsx(data, filename)
    # Unknown — try to decode as plain text
    return data.decode("utf-8", errors="replace")


# ── Criteria extraction from LLM response ─────────────────────────────────────

def _parse_criteria(text: str) -> list[str]:
    """
    Extract bullet-point success criteria from LLM response.
    Looks for lines starting with •, -, *, or numbered lists.
    Returns empty list if none found.
    """
    criteria = []
    for line in text.splitlines():
        stripped = line.strip()
        # Match bullet or numbered list items
        m = re.match(r"^(?:[•\-\*]|\d+[\.\)])\s+(.+)$", stripped)
        if m:
            criteria.append(m.group(1).strip())
    return criteria


# ── Endpoints ─────────────────────────────────────────────────────────────────

class DocumentChatResponse(BaseModel):
    answer: str
    suggested_criteria: list[str]


@router.post("/document", response_model=DocumentChatResponse)
async def chat_with_document(
    message: str = Form(...),
    file: Optional[UploadFile] = File(None),
    current_user: TokenData = Depends(get_current_user),
):
    """
    Accepts an optional ERP document (PDF/DOCX/CSV/XLSX) and a user question.
    Returns an AI answer grounded in the document content, plus any success
    criteria surfaced by the model.
    """
    document_text = ""
    if file is not None:
        raw = await file.read()
        if len(raw) > _MAX_FILE_BYTES:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail="File exceeds 10 MB limit.",
            )
        try:
            document_text = _extract_text(raw, file.filename or "upload")
        except Exception as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Could not extract text from document: {exc}",
            )

    # Trim to ~8 000 chars to stay within context budget
    if len(document_text) > 8000:
        document_text = document_text[:8000] + "\n\n[document truncated]"

    system_prompt = (
        "You are an enterprise procurement analyst helping a procurement manager "
        "understand their organisation's ERP data and define success criteria for "
        "vendor evaluations. Be concise, precise, and grounded in the document. "
        "When you identify measurable success criteria, list them as bullet points "
        "starting with '• ' so they can be saved. If no document is provided, "
        "answer from your general procurement knowledge."
    )

    user_content = message
    if document_text:
        user_content = f"Document content:\n\n{document_text}\n\n---\n\nQuestion: {message}"

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_content},
    ]

    answer = await call_llm(messages, temperature=0.2, max_tokens=1024)
    suggested_criteria = _parse_criteria(answer)

    return DocumentChatResponse(answer=answer, suggested_criteria=suggested_criteria)


class CriteriaPayload(BaseModel):
    criteria: list[str]


class CriteriaResponse(BaseModel):
    criteria: list[str]


@router.get("/criteria", response_model=CriteriaResponse)
async def get_criteria(
    current_user: TokenData = Depends(get_current_user),
    db=Depends(get_db),
):
    """Return saved success criteria for the current user."""
    row = db.execute(
        sa.text("SELECT criteria FROM user_criteria WHERE email = :email"),
        {"email": current_user.email},
    ).fetchone()
    return CriteriaResponse(criteria=row[0] if row else [])


@router.post("/criteria", response_model=CriteriaResponse)
async def save_criteria(
    payload: CriteriaPayload,
    current_user: TokenData = Depends(get_current_user),
    db=Depends(get_db),
):
    """Upsert success criteria for the current user."""
    import json
    db.execute(
        sa.text("""
            INSERT INTO user_criteria (email, org_id, criteria, updated_at)
            VALUES (:email, :org_id, CAST(:criteria AS jsonb), NOW())
            ON CONFLICT (email)
            DO UPDATE SET criteria = CAST(:criteria AS jsonb), updated_at = NOW()
        """),
        {
            "email": current_user.email,
            "org_id": current_user.org_id,
            "criteria": json.dumps(payload.criteria),
        },
    )
    db.commit()
    return CriteriaResponse(criteria=payload.criteria)
