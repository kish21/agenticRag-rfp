# SKILL 02 — Planner Agent, Critic Agent & Core Infrastructure
## Nine-agent pipeline overview — all agents built across Skills 02-09

| Skill | Agent | Built in |
|---|---|---|
| **SK02** | **1. Planner** — typed task DAG | **This skill** |
| SK03 | 2. Ingestion — LlamaIndex → Qdrant | Skill 03 |
| SK03b | 3. Retrieval — Cohere Rerank + HyDE | Skill 03b |
| SK04 | 4. Extraction — facts → PostgreSQL | Skill 04 |
| SK05 | 5. Evaluation — reads PostgreSQL NOT Qdrant | Skill 05 |
| SK05 | 6. Comparator — SQL join cross-vendor | Skill 05 |
| SK06 | 7. Decision — governance routing | Skill 06 |
| SK06 | 8. Explanation — grounded report | Skill 06 |
| **SK02** | **9. Critic** — runs after EVERY agent | **This skill** |

**Sequence:** SECOND. Skill 01 complete and all 9 checkpoints passing.
**Time:** 3-4 days.
**Output:** Planner + Critic built. All 9 Pydantic output models defined.
LLM provider abstraction wired — agents call `call_llm()` not openai directly.

---

## VERSION COMPATIBILITY — READ BEFORE STARTING

All code in this skill is written and tested against these April 2026 versions.
Do NOT use older versions — they will produce deprecation warnings or break silently.

| Package | Correct version | Common mistake |
|---|---|---|
| pydantic | 2.11.x | Using @validator instead of @field_validator |
| openai | 2.33.0 | Using 1.x import paths |
| langchain | 1.2.x | Using 0.x import paths |
| qdrant-client | 1.14.x | Using client.search() instead of client.query_points() |
| langfuse | 4.5.x | Using v2.x SDK methods (entire API rewritten) |
| cohere | 5.21.x | Using cohere.Client() instead of cohere.ClientV2() |

Run this before starting each session:
```bash
python -c "
import pydantic, openai, langchain, langfuse, cohere, qdrant_client
assert pydantic.__version__.startswith('2.'), f'Need pydantic 2.x got {pydantic.__version__}'
assert openai.__version__.startswith('2.'), f'Need openai 2.x got {openai.__version__}'
assert langchain.__version__.startswith('1.'), f'Need langchain 1.x got {langchain.__version__}'
assert langfuse.__version__.startswith('4.'), f'Need langfuse 4.x got {langfuse.__version__}'
print('All version checks passed')
"
```

---

## WHAT THIS SKILL BUILDS

The two agents that govern the entire system — the Planner that coordinates and the Critic that audits. Plus the three day-one failure preventions: RFP confirmation, override mechanism, and rate limit handler.

The Planner and Critic are built first because every other agent plugs into them.

---

## STEP 1 — Create all Pydantic output models

This is the most important file in the system. Every agent input and output is defined here. Build this file completely before writing any agent code.

```python
# app/core/output_models.py
from pydantic import BaseModel, Field, field_validator, model_validator
from typing import Optional, Literal, List, Dict, Any
from datetime import date, datetime
from enum import Enum


# ── Enums ────────────────────────────────────────────────

class SectionType(str, Enum):
    REQUIREMENT_RESPONSE = "requirement_response"
    SUPPORTING_EVIDENCE = "supporting_evidence"
    BACKGROUND = "background"
    BOILERPLATE = "boilerplate"

class CriticSeverity(str, Enum):
    HARD = "hard"        # Block pipeline
    SOFT = "soft"        # Proceed with warning
    LOG = "log"          # Log only, no user impact

class CriticVerdict(str, Enum):
    APPROVED = "approved"
    APPROVED_WITH_WARNINGS = "approved_with_warnings"
    BLOCKED = "blocked"
    ESCALATED = "escalated"

class ComplianceStatus(str, Enum):
    PASS = "pass"
    FAIL = "fail"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"

class DocumentStatus(str, Enum):
    CURRENT = "current"
    PENDING = "pending"
    EXPIRED = "expired"
    NOT_MENTIONED = "not_mentioned"

class DecisionBasis(str, Enum):
    EXPLICIT_CONFIRMATION = "explicit_confirmation"
    IMPLICIT_CONFIRMATION = "implicit_confirmation"
    PARTIAL_COMPLIANCE = "partial_compliance"
    EXPLICIT_DENIAL = "explicit_denial"
    NOT_ADDRESSED = "not_addressed"


# ── Planner output ────────────────────────────────────────

class TaskItem(BaseModel):
    task_id: str
    task_type: Literal[
        "retrieve", "extract", "evaluate",
        "compare", "decide", "explain"
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
    rfp_confirmed: bool = False     # Did user confirm correct RFP?


# ── Critic output ─────────────────────────────────────────

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


# ── Ingestion output ──────────────────────────────────────

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


# ── Retrieval output ──────────────────────────────────────

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


# ── Extraction output ─────────────────────────────────────

class ExtractedCertification(BaseModel):
    standard_name: str
    version: Optional[str] = None
    cert_number: Optional[str] = None
    issuing_body: Optional[str] = None
    scope: Optional[str] = None
    valid_until: Optional[date] = None
    status: DocumentStatus
    confidence: float = Field(ge=0.0, le=1.0)
    grounding_quote: str           # REQUIRED — exact text from source
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
    amount_gbp: Optional[float] = None
    provider: Optional[str] = None
    confidence: float = Field(ge=0.0, le=1.0)
    grounding_quote: str
    source_chunk_id: str

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
    amount_gbp: Optional[float] = None
    total_gbp: Optional[float] = None
    includes: List[str] = []
    confidence: float = Field(ge=0.0, le=1.0)
    grounding_quote: str
    source_chunk_id: str

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
    extraction_completeness: float = Field(ge=0.0, le=1.0)
    hallucination_risk: float = Field(ge=0.0, le=1.0)
    warnings: List[str] = []


# ── Evaluation output ─────────────────────────────────────

class ComplianceDecision(BaseModel):
    check_id: str
    vendor_id: str
    decision: ComplianceStatus
    confidence: float = Field(ge=0.0, le=1.0)
    reasoning: str
    evidence_used: List[str]
    contradictions_found: List[str] = []
    decision_basis: DecisionBasis

class CriterionScore(BaseModel):
    criterion_id: str
    vendor_id: str
    raw_score: int = Field(ge=0, le=10)
    weighted_contribution: float
    confidence: float = Field(ge=0.0, le=1.0)
    rubric_band_applied: str
    evidence_used: List[str]
    score_rationale: str
    variance_estimate: float       # ± how much score might vary

class EvaluationOutput(BaseModel):
    evaluation_id: str
    vendor_id: str
    compliance_decisions: List[ComplianceDecision]
    criterion_scores: List[CriterionScore]
    overall_compliance: Literal["pass", "fail", "review_required"]
    total_weighted_score: float
    score_confidence: float = Field(ge=0.0, le=1.0)
    evaluation_warnings: List[str] = []


# ── Comparator output ─────────────────────────────────────

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
    comparison_warnings: List[str] = []


# ── Decision output ───────────────────────────────────────

class RejectionNotice(BaseModel):
    vendor_id: str
    vendor_name: str
    failed_checks: List[str]
    rejection_reasons: List[str]
    evidence_citations: List[str]  # verbatim quotes
    clause_references: List[str]

class ShortlistedVendor(BaseModel):
    vendor_id: str
    vendor_name: str
    rank: int
    total_score: float
    score_confidence: float
    criterion_breakdown: List[CriterionScore]
    recommendation: Literal[
        "strongly_recommended", "recommended",
        "acceptable", "marginal"
    ]

class ApprovalRouting(BaseModel):
    approval_tier: int
    approver_role: str
    contract_value: float
    sla_hours: int
    sla_deadline: datetime
    escalation_reason: Optional[str] = None

class DecisionOutput(BaseModel):
    decision_id: str
    rfp_id: str
    rejected_vendors: List[RejectionNotice]
    shortlisted_vendors: List[ShortlistedVendor]
    approval_routing: ApprovalRouting
    decision_confidence: float
    requires_human_review: bool
    review_reasons: List[str] = []
    decision_warnings: List[str] = []


# ── Explanation output ────────────────────────────────────

class GroundedClaim(BaseModel):
    claim_text: str
    grounding_quote: str
    source_chunk_id: str
    source_filename: str
    source_page: int
    confidence: float

class VendorNarrative(BaseModel):
    vendor_id: str
    vendor_name: str
    executive_summary: str
    compliance_narrative: str
    scoring_narrative: str
    recommendation_rationale: str
    grounded_claims: List[GroundedClaim]
    ungrounded_claims_removed: int = 0

class ExplanationOutput(BaseModel):
    explanation_id: str
    executive_summary: str
    vendor_narratives: List[VendorNarrative]
    methodology_note: str
    limitations: List[str] = []
    grounding_completeness: float = Field(ge=0.0, le=1.0)
    report_confidence: float


# ── Human override ────────────────────────────────────────

class AuditOverride(BaseModel):
    override_id: str
    org_id: str
    run_id: str
    overridden_by: str             # user_id
    original_decision: Dict[str, Any]
    new_decision: Dict[str, Any]
    reason: str                    # MANDATORY — min 20 chars
    timestamp: datetime
    approved_by: Optional[str] = None  # Senior approver if required

    @field_validator("reason")
    @classmethod
    def reason_not_empty(cls, v):
        if len(v.strip()) < 20:
            raise ValueError(
                "Override reason must be at least 20 characters. "
                "Documented reasoning is required for audit compliance."
            )
        return v
```

<!-- CHECKPOINT -->
```bash
python checkpoint_runner.py SK02-CP01
```
**Expected:** All Pydantic models import cleanly and validators work.

---

## STEP 2 — Create the rate limiter

This must be built before any LLM calls. Without it, 20 concurrent vendors hit the API rate limit and the run fails midway.

```python
# app/core/rate_limiter.py
import asyncio
import time
from collections import deque
from functools import wraps
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
    before_sleep_log
)
import logging
import openai
from app.config import settings

logger = logging.getLogger(__name__)


class RateLimiter:
    """
    Token bucket rate limiter for OpenAI API calls.
    Enforces max requests per minute with automatic backoff.
    """

    def __init__(self, requests_per_minute: int = None):
        self.rpm = requests_per_minute or settings.rate_limit_requests_per_minute
        self.window = 60.0
        self.timestamps: deque = deque()
        self._lock = asyncio.Lock()

    async def acquire(self):
        """Wait until a request slot is available."""
        async with self._lock:
            now = time.time()
            # Remove timestamps older than the window
            while self.timestamps and now - self.timestamps[0] >= self.window:
                self.timestamps.popleft()

            if len(self.timestamps) >= self.rpm:
                # Must wait
                wait_time = self.window - (now - self.timestamps[0]) + 0.1
                logger.debug(f"Rate limit: waiting {wait_time:.1f}s")
                await asyncio.sleep(wait_time)
                # Clean up again after sleep
                now = time.time()
                while self.timestamps and now - self.timestamps[0] >= self.window:
                    self.timestamps.popleft()

            self.timestamps.append(time.time())


# Global rate limiter instance
_rate_limiter = RateLimiter()


def with_retry(max_attempts: int = 5):
    """
    Decorator for OpenAI API calls with exponential backoff.
    Handles rate limits (429), server errors (500/503), and timeouts.
    """
    def decorator(func):
        @retry(
            stop=stop_after_attempt(max_attempts),
            wait=wait_exponential(multiplier=1, min=2, max=60),
            retry=retry_if_exception_type((
                openai.RateLimitError,
                openai.APITimeoutError,
                openai.InternalServerError,
                openai.APIConnectionError,
            )),
            before_sleep=before_sleep_log(logger, logging.WARNING),
            reraise=True
        )
        @wraps(func)
        async def wrapper(*args, **kwargs):
            await _rate_limiter.acquire()
            return await func(*args, **kwargs)
        return wrapper
    return decorator


async def call_openai_with_backoff(client, **kwargs):
    """
    Legacy name kept for backwards compat.
    New code: use call_llm() from app.core.llm_provider instead.
    This function still works — it wraps any client.chat.completions.create() call.
    """
    """
    Safe OpenAI API call with rate limiting and retry.
    Use this instead of client.chat.completions.create directly.
    """
    await _rate_limiter.acquire()

    @retry(
        stop=stop_after_attempt(5),
        wait=wait_exponential(multiplier=1, min=2, max=60),
        retry=retry_if_exception_type((
            openai.RateLimitError,
            openai.APITimeoutError,
            openai.InternalServerError,
        )),
        reraise=True
    )
    async def _call():
        return await client.chat.completions.create(**kwargs)

    return await _call()
```

<!-- CHECKPOINT -->
```bash
python checkpoint_runner.py SK02-CP02
```

---

## STEP 3 — Create the Qdrant client wrapper

```python
# app/core/qdrant_client.py
from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance, VectorParams, SparseVectorParams,
    PointStruct, Filter, FieldCondition, MatchValue,
    SparseIndexParams
)
from app.config import settings
import uuid

_client = None


def get_qdrant_client() -> QdrantClient:
    global _client
    if _client is None:
        _client = QdrantClient(
            host=settings.qdrant_host,
            port=settings.qdrant_port
        )
    return _client


def collection_name(org_id: str, vendor_id: str) -> str:
    """
    Naming convention: {prefix}_{org_id}_{vendor_id}
    Enforces tenant isolation at collection level.
    """
    prefix = settings.qdrant_collection_prefix
    return f"{prefix}_{org_id}_{vendor_id}".replace("-", "_").lower()


def rfp_collection_name(org_id: str, rfp_id: str) -> str:
    prefix = settings.qdrant_collection_prefix
    return f"{prefix}_{org_id}_rfp_{rfp_id}".replace("-", "_").lower()


def create_collection(name: str, vector_size: int = 3072):
    """
    Creates a Qdrant collection with both dense and sparse vectors.
    Dense: for semantic similarity search (OpenAI embeddings)
    Sparse: for BM25 keyword search
    """
    client = get_qdrant_client()

    # Check if already exists
    existing = [c.name for c in client.get_collections().collections]
    if name in existing:
        return

    client.create_collection(
        collection_name=name,
        vectors_config={
            "dense": VectorParams(
                size=vector_size,
                distance=Distance.COSINE
            )
        },
        sparse_vectors_config={
            "sparse": SparseVectorParams(
                index=SparseIndexParams(on_disk=False)
            )
        }
    )


def upsert_chunk(
    collection: str,
    chunk_id: str,
    dense_vector: list[float],
    sparse_indices: list[int],
    sparse_values: list[float],
    payload: dict
):
    """
    Inserts a chunk with both dense and sparse vectors.
    Payload contains all metadata for filtering.
    """
    client = get_qdrant_client()
    client.upsert(
        collection_name=collection,
        points=[PointStruct(
            id=str(uuid.uuid4()),
            vector={
                "dense": dense_vector,
                "sparse": {
                    "indices": sparse_indices,
                    "values": sparse_values
                }
            },
            payload={**payload, "chunk_id": chunk_id}
        )]
    )


def search_dense(
    collection: str,
    query_vector: list[float],
    org_id: str,
    vendor_id: str,
    limit: int = 20,
    section_type_filter: str = None
) -> list[dict]:
    """
    Dense vector search with mandatory tenant isolation filters.
    org_id and vendor_id filters are ALWAYS applied.
    """
    client = get_qdrant_client()

    must_conditions = [
        FieldCondition(key="org_id", match=MatchValue(value=org_id)),
        FieldCondition(key="vendor_id", match=MatchValue(value=vendor_id)),
    ]

    if section_type_filter:
        must_conditions.append(
            FieldCondition(
                key="section_type",
                match=MatchValue(value=section_type_filter)
            )
        )

    # qdrant-client 1.10+ deprecated search() — use query_points()
    results = client.query_points(
        collection_name=collection,
        query=query_vector,
        using="dense",
        query_filter=Filter(must=must_conditions),
        limit=limit,
        with_payload=True,
        with_vectors=False
    ).points

    return [
        {
            "chunk_id": r.payload.get("chunk_id"),
            "text": r.payload.get("text", ""),
            "score": r.score,
            "payload": r.payload
        }
        for r in results
    ]


def delete_vendor_collection(org_id: str, vendor_id: str):
    """
    Deletes all data for a vendor (GDPR / data retention).
    Called by the cleanup job.
    """
    client = get_qdrant_client()
    name = collection_name(org_id, vendor_id)
    existing = [c.name for c in client.get_collections().collections]
    if name in existing:
        client.delete_collection(name)
```

<!-- CHECKPOINT -->
```bash
python checkpoint_runner.py SK02-CP03
```

---

## STEP 4 — Create Planner Agent

```python
# app/agents/planner.py
import uuid
import json
from openai import AsyncOpenAI
from app.core.output_models import PlannerOutput, TaskItem
from app.core.rate_limiter import call_openai_with_backoff
from app.config import settings

client = AsyncOpenAI(api_key=settings.openai_api_key)


async def run_planner(
    rfp_id: str,
    org_id: str,
    vendor_ids: list[str],
    agent_config: dict
) -> PlannerOutput:
    """
    Decomposes evaluation into ordered task list.
    Every task is typed. Every dependency is explicit.
    Does not retrieve, extract, or evaluate anything itself.
    """
    mandatory_checks = agent_config.get(
        "evaluation_rules", {}
    ).get("mandatory_checks", [])

    scoring_criteria = agent_config.get(
        "evaluation_rules", {}
    ).get("scoring_criteria", [])

    response = await call_openai_with_backoff(
        client,
        model=settings.openai_model,
        temperature=0.0,
        response_format={"type": "json_object"},
        messages=[
            {
                "role": "system",
                "content": """You are an evaluation planner. Create an ordered task list.

Each task must have:
- task_id: unique string like "task-001"
- task_type: "retrieve" | "extract" | "evaluate" | "compare" | "decide" | "explain"
- agent: the agent name
- inputs: what to pass to the agent
- depends_on: list of task_ids that must complete first
- priority: 1 (high) to 3 (low)

Return JSON:
{
  "tasks": [...],
  "estimated_duration_seconds": N,
  "warnings": []
}"""
            },
            {
                "role": "user",
                "content": f"""Create evaluation plan:
RFP ID: {rfp_id}
Vendors: {vendor_ids}
Mandatory checks: {[c['check_id'] for c in mandatory_checks]}
Scoring criteria: {[c['criterion_id'] for c in scoring_criteria]}"""
            }
        ]
    )

    raw = json.loads(response.choices[0].message.content)
    tasks = [TaskItem(**t) for t in raw.get("tasks", [])]

    return PlannerOutput(
        plan_id=str(uuid.uuid4()),
        rfp_id=rfp_id,
        org_id=org_id,
        vendor_ids=vendor_ids,
        tasks=tasks,
        estimated_duration_seconds=raw.get(
            "estimated_duration_seconds", 300
        ),
        confidence=0.9,
        warnings=raw.get("warnings", [])
    )


def validate_plan(plan: PlannerOutput, agent_config: dict) -> list[str]:
    """
    Planner guardrail. Returns list of errors.
    Empty list = plan is valid.
    """
    errors = []

    # Check task count
    if len(plan.tasks) < 5:
        errors.append(
            f"Plan has only {len(plan.tasks)} tasks — suspiciously low"
        )
    if len(plan.tasks) > 500:
        errors.append(
            f"Plan has {len(plan.tasks)} tasks — suspiciously high, "
            f"planner may have misunderstood input"
        )

    # Check all mandatory checks have evaluation tasks
    mandatory_ids = {
        c["check_id"]
        for c in agent_config.get(
            "evaluation_rules", {}
        ).get("mandatory_checks", [])
    }
    planned_check_ids = set()
    for task in plan.tasks:
        if task.task_type == "evaluate":
            check_id = task.inputs.get("check_id")
            if check_id:
                planned_check_ids.add(check_id)

    missing = mandatory_ids - planned_check_ids
    if missing:
        errors.append(
            f"Mandatory checks not in plan: {missing}. "
            f"These vendors will not be checked against "
            f"these requirements."
        )

    # Check for circular dependencies
    task_map = {t.task_id: t for t in plan.tasks}
    visited = set()

    def has_cycle(task_id, path=None):
        if path is None:
            path = []
        if task_id in path:
            return True
        if task_id in visited:
            return False
        visited.add(task_id)
        task = task_map.get(task_id)
        if not task:
            return False
        for dep in task.depends_on:
            if has_cycle(dep, path + [task_id]):
                return True
        return False

    for task in plan.tasks:
        if has_cycle(task.task_id):
            errors.append(
                f"Circular dependency detected involving task "
                f"{task.task_id}"
            )
            break

    return errors
```

<!-- CHECKPOINT -->
```bash
python checkpoint_runner.py SK02-CP04
```

---

## STEP 5 — Create Critic Agent

```python
# app/agents/critic.py
"""
The Critic Agent runs after every other agent.
It is the only agent whose job is to be skeptical.
It does NOT retrieve, generate, or fix — it only validates and flags.
"""
import uuid
from app.core.output_models import (
    CriticOutput, CriticFlag, CriticSeverity, CriticVerdict,
    RetrievalOutput, ExtractionOutput, EvaluationOutput,
    ComparatorOutput, DecisionOutput, ExplanationOutput,
    IngestionOutput
)
from app.config import settings


def _make_flag(
    severity: CriticSeverity,
    agent: str,
    check: str,
    description: str,
    evidence: str,
    recommendation: str,
    auto_resolvable: bool = False
) -> CriticFlag:
    return CriticFlag(
        flag_id=str(uuid.uuid4()),
        severity=severity,
        agent=agent,
        check_name=check,
        description=description,
        evidence=evidence,
        recommendation=recommendation,
        auto_resolvable=auto_resolvable
    )


def _verdict(flags: list[CriticFlag]) -> CriticVerdict:
    hard = any(f.severity == CriticSeverity.HARD for f in flags)
    soft = any(f.severity == CriticSeverity.SOFT for f in flags)
    escalated = any(
        "escalate" in f.recommendation.lower()
        for f in flags
        if f.severity == CriticSeverity.HARD
    )
    if escalated:
        return CriticVerdict.ESCALATED
    if hard:
        return CriticVerdict.BLOCKED
    if soft:
        return CriticVerdict.APPROVED_WITH_WARNINGS
    return CriticVerdict.APPROVED


def critic_after_ingestion(output: IngestionOutput) -> CriticOutput:
    flags = []

    if output.quality_score < 0.4:
        flags.append(_make_flag(
            CriticSeverity.HARD, "ingestion_agent",
            "quality_score_critical",
            "Document quality score below 0.4 — document may be "
            "unreadable",
            f"quality_score={output.quality_score}",
            "Reject document. Ask vendor to resubmit as a "
            "digital PDF."
        ))
    elif output.quality_score < 0.65:
        flags.append(_make_flag(
            CriticSeverity.SOFT, "ingestion_agent",
            "quality_score_low",
            "Document quality score below 0.65",
            f"quality_score={output.quality_score}",
            "Proceed with caution. Some sections may not be "
            "retrievable."
        ))

    req_resp = output.chunks_by_type.get("requirement_response", 0)
    if req_resp == 0:
        flags.append(_make_flag(
            CriticSeverity.HARD, "ingestion_agent",
            "no_requirement_sections",
            "Zero requirement_response sections found",
            f"chunks_by_type={output.chunks_by_type}",
            "Document does not address any RFP requirements. "
            "Do not evaluate. Contact vendor."
        ))

    if output.status == "duplicate":
        flags.append(_make_flag(
            CriticSeverity.SOFT, "ingestion_agent",
            "duplicate_document",
            "Document already ingested with identical content",
            f"content_hash={output.content_hash}",
            "Skip re-ingestion. Use existing data.",
            auto_resolvable=True
        ))

    return CriticOutput(
        critic_run_id=str(uuid.uuid4()),
        evaluated_agent="ingestion_agent",
        evaluated_output_id=output.doc_id,
        flags=flags,
        hard_flag_count=sum(
            1 for f in flags if f.severity == CriticSeverity.HARD
        ),
        soft_flag_count=sum(
            1 for f in flags if f.severity == CriticSeverity.SOFT
        ),
        overall_verdict=_verdict(flags),
        requires_human_review=any(
            f.severity == CriticSeverity.HARD for f in flags
        )
    )


def critic_after_retrieval(
    output: RetrievalOutput,
    is_mandatory: bool = False
) -> CriticOutput:
    flags = []

    if output.empty_retrieval:
        severity = (
            CriticSeverity.HARD
            if is_mandatory
            else CriticSeverity.SOFT
        )
        flags.append(_make_flag(
            severity, "retrieval_agent",
            "empty_retrieval",
            "Retrieval returned zero chunks" + (
                " for mandatory requirement" if is_mandatory else ""
            ),
            f"query='{output.original_query}'",
            "Widen search query and retry. If still empty, "
            "mark as insufficient_evidence."
        ))

    if not output.empty_retrieval:
        answer_bearing = [
            c for c in output.chunks
            if c.is_answer_bearing
        ]
        if not answer_bearing:
            flags.append(_make_flag(
                CriticSeverity.SOFT, "retrieval_agent",
                "no_answer_bearing_chunks",
                "Retrieved chunks do not appear to contain "
                "answer-bearing content",
                f"top_score={output.chunks[0].final_score if output.chunks else 0}",
                "Try HyDE retrieval or broaden query."
            ))

        all_background = all(
            c.section_type == "background"
            for c in output.chunks
        )
        if all_background and is_mandatory:
            flags.append(_make_flag(
                CriticSeverity.SOFT, "retrieval_agent",
                "wrong_section_type",
                "All retrieved chunks are from 'background' sections",
                f"section_types={[c.section_type for c in output.chunks]}",
                "Retrieval may be searching wrong sections. "
                "Add section_type filter for requirement_response."
            ))

    return CriticOutput(
        critic_run_id=str(uuid.uuid4()),
        evaluated_agent="retrieval_agent",
        evaluated_output_id=output.query_id,
        flags=flags,
        hard_flag_count=sum(
            1 for f in flags if f.severity == CriticSeverity.HARD
        ),
        soft_flag_count=sum(
            1 for f in flags if f.severity == CriticSeverity.SOFT
        ),
        overall_verdict=_verdict(flags),
        requires_human_review=any(
            f.severity == CriticSeverity.HARD for f in flags
        )
    )


def critic_after_extraction(
    output: ExtractionOutput,
    source_chunks: dict[str, str]
) -> CriticOutput:
    """
    source_chunks: {chunk_id: chunk_text} — used for grounding verification.
    Grounding verification is PROGRAMMATIC, not LLM.
    """
    flags = []

    # Collect all extracted items
    all_items = (
        output.certifications
        + output.insurance
        + output.slas
        + output.projects
        + output.pricing
    )

    for item in all_items:
        # Check grounding quote is in source text
        source_text = source_chunks.get(item.source_chunk_id, "")
        if source_text and item.grounding_quote:
            if item.grounding_quote.strip() not in source_text:
                flags.append(_make_flag(
                    CriticSeverity.HARD,
                    "extraction_agent",
                    "grounding_verification_failed",
                    f"Extracted grounding_quote not found in source chunk",
                    f"quote='{item.grounding_quote[:80]}...' "
                    f"not in chunk {item.source_chunk_id}",
                    "HALLUCINATION DETECTED. Discard this "
                    "extraction result. Do not use for evaluation."
                ))

    if output.hallucination_risk > 0.5:
        flags.append(_make_flag(
            CriticSeverity.HARD, "extraction_agent",
            "high_hallucination_risk",
            f"Extraction agent reported high hallucination risk",
            f"hallucination_risk={output.hallucination_risk}",
            "Do not use extracted facts. Re-run extraction "
            "with stricter prompt."
        ))

    if output.extraction_completeness < 0.5:
        flags.append(_make_flag(
            CriticSeverity.SOFT, "extraction_agent",
            "low_extraction_completeness",
            f"Only {output.extraction_completeness:.0%} of "
            f"required fields extracted",
            f"completeness={output.extraction_completeness}",
            "Vendor may not have addressed all requirements. "
            "Evaluation will use insufficient_evidence "
            "for missing facts."
        ))

    return CriticOutput(
        critic_run_id=str(uuid.uuid4()),
        evaluated_agent="extraction_agent",
        evaluated_output_id=output.extraction_id,
        flags=flags,
        hard_flag_count=sum(
            1 for f in flags if f.severity == CriticSeverity.HARD
        ),
        soft_flag_count=sum(
            1 for f in flags if f.severity == CriticSeverity.SOFT
        ),
        overall_verdict=_verdict(flags),
        requires_human_review=any(
            f.severity == CriticSeverity.HARD for f in flags
        )
    )


def critic_after_evaluation(
    output: EvaluationOutput,
    extraction_output: ExtractionOutput
) -> CriticOutput:
    flags = []

    for decision in output.compliance_decisions:
        # Decision contradicts extracted facts
        if (
            decision.decision.value == "pass"
            and decision.decision_basis.value == "implicit_confirmation"
        ):
            flags.append(_make_flag(
                CriticSeverity.SOFT, "evaluation_agent",
                "implicit_confirmation_on_mandatory",
                f"Check {decision.check_id} passed on implicit "
                f"confirmation only",
                f"basis={decision.decision_basis}",
                "Mandatory requirements need explicit confirmation. "
                "Review decision."
            ))

        if decision.contradictions_found:
            flags.append(_make_flag(
                CriticSeverity.HARD, "evaluation_agent",
                "contradictions_in_evidence",
                f"Check {decision.check_id} has contradictory evidence",
                f"contradictions={decision.contradictions_found}",
                "Cannot make reliable compliance decision with "
                "contradictory evidence. Human review required."
            ))

    for score in output.criterion_scores:
        if score.variance_estimate >= 2.0:
            flags.append(_make_flag(
                CriticSeverity.SOFT, "evaluation_agent",
                "high_score_variance",
                f"Score for {score.criterion_id} has high variance "
                f"(±{score.variance_estimate})",
                f"score={score.raw_score}±{score.variance_estimate}",
                "Score may not be reliable. Note in report."
            ))

    return CriticOutput(
        critic_run_id=str(uuid.uuid4()),
        evaluated_agent="evaluation_agent",
        evaluated_output_id=output.evaluation_id,
        flags=flags,
        hard_flag_count=sum(
            1 for f in flags if f.severity == CriticSeverity.HARD
        ),
        soft_flag_count=sum(
            1 for f in flags if f.severity == CriticSeverity.SOFT
        ),
        overall_verdict=_verdict(flags),
        requires_human_review=any(
            f.severity == CriticSeverity.HARD for f in flags
        )
    )


def critic_after_decision(output: DecisionOutput) -> CriticOutput:
    flags = []

    # Rejection without evidence
    for rej in output.rejected_vendors:
        if not rej.evidence_citations:
            flags.append(_make_flag(
                CriticSeverity.HARD, "decision_agent",
                "rejection_without_evidence",
                f"Vendor {rej.vendor_id} rejected without evidence",
                f"evidence_citations=[]",
                "CANNOT REJECT WITHOUT EVIDENCE. Legal exposure. "
                "Find evidence or change decision."
            ))

    # All vendors rejected
    if not output.shortlisted_vendors and output.rejected_vendors:
        flags.append(_make_flag(
            CriticSeverity.HARD, "decision_agent",
            "all_vendors_rejected",
            "All vendors were rejected",
            f"rejected={len(output.rejected_vendors)}, "
            f"shortlisted=0",
            "ESCALATE. Requirements may be too restrictive. "
            "Review mandatory requirements with procurement team."
        ))

    return CriticOutput(
        critic_run_id=str(uuid.uuid4()),
        evaluated_agent="decision_agent",
        evaluated_output_id=output.decision_id,
        flags=flags,
        hard_flag_count=sum(
            1 for f in flags if f.severity == CriticSeverity.HARD
        ),
        soft_flag_count=sum(
            1 for f in flags if f.severity == CriticSeverity.SOFT
        ),
        overall_verdict=_verdict(flags),
        requires_human_review=any(
            f.severity == CriticSeverity.HARD for f in flags
        )
    )


def critic_after_explanation(
    output: ExplanationOutput,
    source_chunks: dict[str, str]
) -> CriticOutput:
    flags = []

    # Check grounding completeness
    if output.grounding_completeness < 0.70:
        flags.append(_make_flag(
            CriticSeverity.HARD, "explanation_agent",
            "low_grounding_completeness",
            f"Only {output.grounding_completeness:.0%} of claims "
            f"are grounded in source text",
            f"grounding_completeness={output.grounding_completeness}",
            "Report contains too many unverified claims. "
            "Do not send to customer."
        ))
    elif output.grounding_completeness < 0.90:
        flags.append(_make_flag(
            CriticSeverity.SOFT, "explanation_agent",
            "moderate_grounding",
            f"Grounding completeness {output.grounding_completeness:.0%}",
            f"grounding_completeness={output.grounding_completeness}",
            "Report contains some unverified claims. "
            "Review before sending."
        ))

    # Check ungrounded claims removed
    for narrative in output.vendor_narratives:
        if narrative.ungrounded_claims_removed > 3:
            flags.append(_make_flag(
                CriticSeverity.SOFT, "explanation_agent",
                "many_claims_removed",
                f"Explanation agent removed {narrative.ungrounded_claims_removed} "
                f"ungrounded claims for {narrative.vendor_id}",
                f"vendor={narrative.vendor_id}, "
                f"removed={narrative.ungrounded_claims_removed}",
                "High hallucination in explanation. Check source data quality."
            ))

    # Programmatic grounding verification on sample
    for narrative in output.vendor_narratives:
        for claim in narrative.grounded_claims[:5]:  # Check first 5
            source = source_chunks.get(claim.source_chunk_id, "")
            if source and claim.grounding_quote:
                if claim.grounding_quote not in source:
                    flags.append(_make_flag(
                        CriticSeverity.HARD, "explanation_agent",
                        "grounding_verification_failed",
                        "Claim grounding quote not found in source",
                        f"quote='{claim.grounding_quote[:60]}'",
                        "HALLUCINATION. Remove claim from report."
                    ))
                    break

    return CriticOutput(
        critic_run_id=str(uuid.uuid4()),
        evaluated_agent="explanation_agent",
        evaluated_output_id=output.explanation_id,
        flags=flags,
        hard_flag_count=sum(
            1 for f in flags if f.severity == CriticSeverity.HARD
        ),
        soft_flag_count=sum(
            1 for f in flags if f.severity == CriticSeverity.SOFT
        ),
        overall_verdict=_verdict(flags),
        requires_human_review=any(
            f.severity == CriticSeverity.HARD for f in flags
        )
    )
```

<!-- CHECKPOINT -->
```bash
python checkpoint_runner.py SK02-CP05
python checkpoint_runner.py SK02-CP06
```

---

## STEP 6 — Create RFP confirmation step

```python
# app/core/rfp_confirmation.py
"""
Prevents the most common day-one failure: evaluating against wrong document.
Takes 2 minutes of user time. Saves hours of wasted evaluation.
"""
from openai import AsyncOpenAI
from app.core.rate_limiter import call_openai_with_backoff
from app.config import settings
import json

client = AsyncOpenAI(api_key=settings.openai_api_key)


async def extract_rfp_identity(rfp_text: str) -> dict:
    """
    Reads the RFP and extracts identity fields for user confirmation.
    """
    response = await call_openai_with_backoff(
        client,
        model=settings.openai_model,
        temperature=0.0,
        response_format={"type": "json_object"},
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
        ]
    )
    return json.loads(response.choices[0].message.content)


def format_confirmation_message(identity: dict) -> str:
    """
    Formats the confirmation message shown to the user before evaluation.
    """
    return f"""
Before running the evaluation, please confirm this is the correct RFP:

  Reference:      {identity.get('reference', 'Not found')}
  Issuer:         {identity.get('issuer', 'Not found')}
  Title:          {identity.get('title', 'Not found')}
  Deadline:       {identity.get('deadline', 'Not found')}
  Mandatory reqs: {identity.get('mandatory_count', '?')} found
  Scoring criteria: {identity.get('scoring_criteria_count', '?')} found

Is this the correct RFP document? (yes/no)
""".strip()
```

---

## STEP 7 — Create human override mechanism

```python
# app/core/override_mechanism.py
"""
Human overrides are first-class citizens.
Every override creates an AuditOverride record.
Direct database edits are prohibited — this is the only override path.
"""
import uuid
from datetime import datetime
import sqlalchemy as sa
from app.core.output_models import AuditOverride
from app.config import settings


def create_override_record(
    org_id: str,
    run_id: str,
    overridden_by: str,
    original_decision: dict,
    new_decision: dict,
    reason: str
) -> AuditOverride:
    """
    Creates a validated override record.
    Reason is mandatory and must be at least 20 characters.
    This enforces documented reasoning for audit compliance.
    """
    # AuditOverride validator enforces reason length
    override = AuditOverride(
        override_id=str(uuid.uuid4()),
        org_id=org_id,
        run_id=run_id,
        overridden_by=overridden_by,
        original_decision=original_decision,
        new_decision=new_decision,
        reason=reason,
        timestamp=datetime.utcnow()
    )
    return override


def save_override(override: AuditOverride, engine: sa.Engine):
    """
    Writes override to audit_overrides table.
    This is the ONLY permitted way to change an evaluation decision.
    """
    with engine.connect() as conn:
        conn.execute(
            sa.text("""
                INSERT INTO audit_overrides (
                    override_id, org_id, run_id, overridden_by,
                    original_decision, new_decision, reason, timestamp
                ) VALUES (
                    :override_id, :org_id, :run_id, :overridden_by,
                    :original_decision::jsonb, :new_decision::jsonb,
                    :reason, :timestamp
                )
            """),
            {
                "override_id": override.override_id,
                "org_id": override.org_id,
                "run_id": override.run_id,
                "overridden_by": override.overridden_by,
                "original_decision": override.original_decision,
                "new_decision": override.new_decision,
                "reason": override.reason,
                "timestamp": override.timestamp,
            }
        )
        conn.commit()
```

<!-- CHECKPOINT -->
```bash
python checkpoint_runner.py SK02-CP07
python checkpoint_runner.py SK02-CP08
```

---

## SKILL 02 COMPLETE

```bash
python checkpoint_runner.py SK02    # All 8 must pass
python contract_tests.py            # All must pass
python drift_detector.py            # Clean
```

Open SKILL_03_INGESTION_AGENT.md
