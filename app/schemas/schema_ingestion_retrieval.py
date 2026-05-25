from pydantic import BaseModel, Field
from typing import Literal, List, Dict

from .schema_enums import SectionType


class ChunkRecord(BaseModel):
    chunk_id: str
    vendor_id: str
    org_id: str
    filename: str
    section_id: str
    section_title: str
    section_type: SectionType
    priority: int
    text: str
    token_count: int
    page_number: int
    qdrant_point_id: str

class IngestionOutput(BaseModel):
    doc_id: str
    vendor_id: str
    org_id: str
    filename: str
    total_chunks: int
    chunks_by_type: Dict[str, int]
    filtered_chunks: int
    extraction_triggered: bool
    quality_score: float = Field(ge=0.0, le=1.0)
    content_hash: str
    warnings: List[str] = []
    status: Literal["success", "partial", "failed", "duplicate"]


class RetrievedChunk(BaseModel):
    chunk_id: str
    qdrant_point_id: str
    text: str
    section_id: str
    section_title: str
    section_type: str
    filename: str
    page_number: int
    vendor_id: str
    vector_similarity_score: float
    rerank_score: float
    final_score: float
    is_answer_bearing: bool

class RetrievalOutput(BaseModel):
    query_id: str
    original_query: str
    rewritten_query: str
    hyde_query_used: bool
    retrieval_strategy: str
    chunks: List[RetrievedChunk]
    total_candidates_before_rerank: int
    confidence: float = Field(ge=0.0, le=1.0)
    empty_retrieval: bool
    warnings: List[str] = []
