# SKILL 03 — Ingestion Agent
**Sequence:** THIRD.

> **Multi-LLM note:** Section classification in ingestion uses `call_llm()` 
> from `app.core.llm_provider`. Heavy PDFs (>50 pages or scanned) are 
> offloaded to Modal — see `app_modal.py` built in Skill 01. Skills 01 and 02 complete and verified.
**Time:** 2-3 days.
**Output:** Documents ingested into Qdrant with LlamaIndex. Structured facts extracted into PostgreSQL immediately after ingestion. ZIP multi-file submissions handled.

---

## WHAT THIS SKILL BUILDS

The Ingestion Agent is the entry point for all documents. It does two things other RAG systems skip. First — it classifies every section of a document (requirement_response, supporting_evidence, background, boilerplate) so retrieval can filter by section type. Second — it triggers the Extraction Agent immediately on requirement_response sections, so structured facts are in PostgreSQL before any evaluation begins.

This is what prevents the "evaluate at query time on raw prose" problem that causes LLM scoring inconsistency.

---

## RULES FOR CLAUDE CODE

1. Never store raw document bytes in any database — only extracted text and embeddings
2. The Critic Agent runs after every document ingested — never skip
3. ZIP files must be unpacked and each file processed as part of the same vendor submission
4. Every chunk must have org_id and vendor_id in its Qdrant payload — no exceptions

---

## STEP 1 — Create the PostgreSQL schema

Run this SQL before building any Python code. Everything else depends on these tables.

```sql
-- app/db/schema.sql
-- Run via: psql -U platformuser -d agenticplatform -f app/db/schema.sql

-- ── Core tables ───────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS organisations (
    org_id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_name        TEXT NOT NULL,
    industry        TEXT,
    subscription_tier TEXT DEFAULT 'starter',
    created_at      TIMESTAMPTZ DEFAULT now(),
    is_active       BOOLEAN DEFAULT true
);

CREATE TABLE IF NOT EXISTS agent_registry (
    agent_id        UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id          UUID REFERENCES organisations(org_id),
    agent_name      TEXT NOT NULL,
    agent_type      TEXT NOT NULL,
    config          JSONB NOT NULL,
    is_active       BOOLEAN DEFAULT true,
    created_at      TIMESTAMPTZ DEFAULT now(),
    updated_at      TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS evaluation_runs (
    run_id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id          UUID NOT NULL,
    rfp_id          TEXT NOT NULL,
    agent_id        UUID,
    status          TEXT DEFAULT 'running',
    vendor_ids      TEXT[],
    config_snapshot JSONB,
    contract_value  NUMERIC,
    approval_tier   INTEGER,
    langsmith_trace TEXT,
    created_at      TIMESTAMPTZ DEFAULT now(),
    completed_at    TIMESTAMPTZ
);

-- ── Vendor documents ──────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS vendor_documents (
    doc_id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id          UUID NOT NULL,
    vendor_id       TEXT NOT NULL,
    rfp_id          TEXT NOT NULL,
    filename        TEXT NOT NULL,
    content_hash    TEXT NOT NULL,
    quality_score   FLOAT,
    total_chunks    INTEGER,
    ingested_at     TIMESTAMPTZ DEFAULT now(),
    UNIQUE(org_id, vendor_id, rfp_id, content_hash)
);

-- ── Structured fact tables ────────────────────────────────────────────
-- Every row links back to Qdrant via source_chunk_id

CREATE TABLE IF NOT EXISTS extracted_certifications (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    doc_id          UUID REFERENCES vendor_documents(doc_id),
    org_id          UUID NOT NULL,
    vendor_id       TEXT NOT NULL,
    standard_name   TEXT,
    version         TEXT,
    cert_number     TEXT,
    issuing_body    TEXT,
    scope           TEXT,
    valid_until     DATE,
    status          TEXT,              -- current | pending | expired | not_mentioned
    confidence      FLOAT,
    grounding_quote TEXT NOT NULL,     -- REQUIRED — verbatim from source
    source_chunk_id TEXT NOT NULL,     -- Links to Qdrant point
    created_at      TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS extracted_insurance (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    doc_id          UUID REFERENCES vendor_documents(doc_id),
    org_id          UUID NOT NULL,
    vendor_id       TEXT NOT NULL,
    insurance_type  TEXT,
    amount_gbp      NUMERIC,
    provider        TEXT,
    confidence      FLOAT,
    grounding_quote TEXT NOT NULL,
    source_chunk_id TEXT NOT NULL,
    created_at      TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS extracted_slas (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    doc_id          UUID REFERENCES vendor_documents(doc_id),
    org_id          UUID NOT NULL,
    vendor_id       TEXT NOT NULL,
    priority_level  TEXT,
    response_minutes INTEGER,
    resolution_hours INTEGER,
    uptime_percentage FLOAT,
    confidence      FLOAT,
    grounding_quote TEXT NOT NULL,
    source_chunk_id TEXT NOT NULL,
    created_at      TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS extracted_projects (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    doc_id          UUID REFERENCES vendor_documents(doc_id),
    org_id          UUID NOT NULL,
    vendor_id       TEXT NOT NULL,
    client_name     TEXT,
    client_sector   TEXT,
    user_count      INTEGER,
    outcomes        TEXT,
    reference_available BOOLEAN,
    confidence      FLOAT,
    grounding_quote TEXT NOT NULL,
    source_chunk_id TEXT NOT NULL,
    created_at      TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS extracted_pricing (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    doc_id          UUID REFERENCES vendor_documents(doc_id),
    org_id          UUID NOT NULL,
    vendor_id       TEXT NOT NULL,
    year            INTEGER,
    amount_gbp      NUMERIC,
    total_gbp       NUMERIC,
    includes        TEXT[],
    confidence      FLOAT,
    grounding_quote TEXT NOT NULL,
    source_chunk_id TEXT NOT NULL,
    created_at      TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS extracted_facts (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    doc_id          UUID REFERENCES vendor_documents(doc_id),
    org_id          UUID NOT NULL,
    vendor_id       TEXT NOT NULL,
    criterion_id    TEXT,
    fact_key        TEXT,
    fact_value      TEXT,
    fact_unit       TEXT,
    confidence      FLOAT,
    grounding_quote TEXT NOT NULL,
    source_chunk_id TEXT NOT NULL,
    created_at      TIMESTAMPTZ DEFAULT now()
);

-- ── Audit tables ──────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS decisions (
    decision_id     UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id          UUID REFERENCES evaluation_runs(run_id),
    org_id          UUID NOT NULL,
    vendor_id       TEXT,
    decision_type   TEXT,
    check_id        TEXT,
    decision        TEXT,
    score_value     NUMERIC,
    confidence      FLOAT,
    reasoning       TEXT,
    evidence_quote  TEXT,
    source_doc      TEXT,
    created_at      TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS audit_overrides (
    override_id         UUID PRIMARY KEY,
    org_id              UUID NOT NULL,
    run_id              UUID,
    overridden_by       TEXT NOT NULL,
    original_decision   JSONB NOT NULL,
    new_decision        JSONB NOT NULL,
    reason              TEXT NOT NULL CHECK (length(reason) >= 20),
    timestamp           TIMESTAMPTZ NOT NULL,
    approved_by         TEXT
);

CREATE TABLE IF NOT EXISTS approvals (
    approval_id     UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id          UUID REFERENCES evaluation_runs(run_id),
    org_id          UUID NOT NULL,
    approval_tier   INTEGER NOT NULL,
    approver_role   TEXT NOT NULL,
    status          TEXT DEFAULT 'pending',
    comments        TEXT,
    requested_at    TIMESTAMPTZ DEFAULT now(),
    responded_at    TIMESTAMPTZ,
    sla_deadline    TIMESTAMPTZ
);

-- ── Row level security ────────────────────────────────────────────────

ALTER TABLE vendor_documents     ENABLE ROW LEVEL SECURITY;
ALTER TABLE extracted_certifications ENABLE ROW LEVEL SECURITY;
ALTER TABLE extracted_insurance  ENABLE ROW LEVEL SECURITY;
ALTER TABLE extracted_slas       ENABLE ROW LEVEL SECURITY;
ALTER TABLE extracted_projects   ENABLE ROW LEVEL SECURITY;
ALTER TABLE extracted_pricing    ENABLE ROW LEVEL SECURITY;
ALTER TABLE extracted_facts      ENABLE ROW LEVEL SECURITY;
ALTER TABLE decisions            ENABLE ROW LEVEL SECURITY;
ALTER TABLE audit_overrides      ENABLE ROW LEVEL SECURITY;

-- Policies enforce org isolation at database level
CREATE POLICY IF NOT EXISTS org_iso_vendor_docs
    ON vendor_documents USING (
        org_id::text = current_setting('app.current_org_id', true)
    );

CREATE POLICY IF NOT EXISTS org_iso_decisions
    ON decisions USING (
        org_id::text = current_setting('app.current_org_id', true)
    );

-- ── Indexes ───────────────────────────────────────────────────────────

CREATE INDEX IF NOT EXISTS idx_vendor_docs_org_vendor
    ON vendor_documents(org_id, vendor_id, rfp_id);

CREATE INDEX IF NOT EXISTS idx_certs_org_vendor
    ON extracted_certifications(org_id, vendor_id);

CREATE INDEX IF NOT EXISTS idx_insurance_org_vendor
    ON extracted_insurance(org_id, vendor_id);

CREATE INDEX IF NOT EXISTS idx_slas_org_vendor
    ON extracted_slas(org_id, vendor_id);

CREATE INDEX IF NOT EXISTS idx_projects_org_vendor
    ON extracted_projects(org_id, vendor_id);

CREATE INDEX IF NOT EXISTS idx_pricing_org_vendor
    ON extracted_pricing(org_id, vendor_id);
```

Run it:
```bash
psql -U platformuser -d agenticplatform -h localhost -f app/db/schema.sql
echo "Schema created"
```

<!-- CHECKPOINT -->
```bash
python checkpoint_runner.py SK03-CP01
# Must show all tables exist
```

---

## STEP 2 — Create the fact store writer

```python
# app/db/fact_store.py
"""
Writes extracted facts to PostgreSQL.
Called immediately after Extraction Agent runs.
"""
import json
import sqlalchemy as sa
from app.core.output_models import ExtractionOutput
from app.config import settings

_engine = None


def get_engine() -> sa.Engine:
    global _engine
    if _engine is None:
        url = (
            f"postgresql://{settings.postgres_user}"
            f":{settings.postgres_password}"
            f"@{settings.postgres_host}"
            f":{settings.postgres_port}"
            f"/{settings.postgres_db}"
        )
        _engine = sa.create_engine(url)
    return _engine


def save_extraction_output(
    output: ExtractionOutput,
    doc_id: str
):
    """
    Persists all extracted facts to PostgreSQL.
    Each table call is idempotent — safe to call multiple times.
    """
    engine = get_engine()

    with engine.connect() as conn:
        # Certifications
        for cert in output.certifications:
            conn.execute(sa.text("""
                INSERT INTO extracted_certifications (
                    doc_id, org_id, vendor_id,
                    standard_name, version, cert_number,
                    issuing_body, scope, valid_until, status,
                    confidence, grounding_quote, source_chunk_id
                ) VALUES (
                    :doc_id, :org_id, :vendor_id,
                    :standard_name, :version, :cert_number,
                    :issuing_body, :scope, :valid_until, :status,
                    :confidence, :grounding_quote, :source_chunk_id
                ) ON CONFLICT DO NOTHING
            """), {
                "doc_id": doc_id,
                "org_id": output.org_id,
                "vendor_id": output.vendor_id,
                "standard_name": cert.standard_name,
                "version": cert.version,
                "cert_number": cert.cert_number,
                "issuing_body": cert.issuing_body,
                "scope": cert.scope,
                "valid_until": cert.valid_until,
                "status": cert.status.value,
                "confidence": cert.confidence,
                "grounding_quote": cert.grounding_quote,
                "source_chunk_id": cert.source_chunk_id,
            })

        # Insurance
        for ins in output.insurance:
            conn.execute(sa.text("""
                INSERT INTO extracted_insurance (
                    doc_id, org_id, vendor_id,
                    insurance_type, amount_gbp, provider,
                    confidence, grounding_quote, source_chunk_id
                ) VALUES (
                    :doc_id, :org_id, :vendor_id,
                    :insurance_type, :amount_gbp, :provider,
                    :confidence, :grounding_quote, :source_chunk_id
                ) ON CONFLICT DO NOTHING
            """), {
                "doc_id": doc_id,
                "org_id": output.org_id,
                "vendor_id": output.vendor_id,
                "insurance_type": ins.insurance_type,
                "amount_gbp": ins.amount_gbp,
                "provider": ins.provider,
                "confidence": ins.confidence,
                "grounding_quote": ins.grounding_quote,
                "source_chunk_id": ins.source_chunk_id,
            })

        # SLAs
        for sla in output.slas:
            conn.execute(sa.text("""
                INSERT INTO extracted_slas (
                    doc_id, org_id, vendor_id,
                    priority_level, response_minutes,
                    resolution_hours, uptime_percentage,
                    confidence, grounding_quote, source_chunk_id
                ) VALUES (
                    :doc_id, :org_id, :vendor_id,
                    :priority_level, :response_minutes,
                    :resolution_hours, :uptime_percentage,
                    :confidence, :grounding_quote, :source_chunk_id
                ) ON CONFLICT DO NOTHING
            """), {
                "doc_id": doc_id,
                "org_id": output.org_id,
                "vendor_id": output.vendor_id,
                "priority_level": sla.priority_level,
                "response_minutes": sla.response_minutes,
                "resolution_hours": sla.resolution_hours,
                "uptime_percentage": sla.uptime_percentage,
                "confidence": sla.confidence,
                "grounding_quote": sla.grounding_quote,
                "source_chunk_id": sla.source_chunk_id,
            })

        # Projects
        for proj in output.projects:
            conn.execute(sa.text("""
                INSERT INTO extracted_projects (
                    doc_id, org_id, vendor_id,
                    client_name, client_sector, user_count,
                    outcomes, reference_available,
                    confidence, grounding_quote, source_chunk_id
                ) VALUES (
                    :doc_id, :org_id, :vendor_id,
                    :client_name, :client_sector, :user_count,
                    :outcomes, :reference_available,
                    :confidence, :grounding_quote, :source_chunk_id
                ) ON CONFLICT DO NOTHING
            """), {
                "doc_id": doc_id,
                "org_id": output.org_id,
                "vendor_id": output.vendor_id,
                "client_name": proj.client_name,
                "client_sector": proj.client_sector,
                "user_count": proj.user_count,
                "outcomes": proj.outcomes,
                "reference_available": proj.reference_available,
                "confidence": proj.confidence,
                "grounding_quote": proj.grounding_quote,
                "source_chunk_id": proj.source_chunk_id,
            })

        # Pricing
        for price in output.pricing:
            conn.execute(sa.text("""
                INSERT INTO extracted_pricing (
                    doc_id, org_id, vendor_id,
                    year, amount_gbp, total_gbp, includes,
                    confidence, grounding_quote, source_chunk_id
                ) VALUES (
                    :doc_id, :org_id, :vendor_id,
                    :year, :amount_gbp, :total_gbp, :includes,
                    :confidence, :grounding_quote, :source_chunk_id
                ) ON CONFLICT DO NOTHING
            """), {
                "doc_id": doc_id,
                "org_id": output.org_id,
                "vendor_id": output.vendor_id,
                "year": price.year,
                "amount_gbp": price.amount_gbp,
                "total_gbp": price.total_gbp,
                "includes": price.includes,
                "confidence": price.confidence,
                "grounding_quote": price.grounding_quote,
                "source_chunk_id": price.source_chunk_id,
            })

        conn.commit()


def get_vendor_facts(
    org_id: str,
    vendor_id: str
) -> dict:
    """
    Retrieves all structured facts for a vendor.
    Used by the Evaluation Agent instead of Qdrant search.
    """
    engine = get_engine()

    with engine.connect() as conn:
        certs = conn.execute(sa.text("""
            SELECT * FROM extracted_certifications
            WHERE org_id = :org_id AND vendor_id = :vendor_id
            ORDER BY confidence DESC
        """), {"org_id": org_id, "vendor_id": vendor_id}).fetchall()

        insurance = conn.execute(sa.text("""
            SELECT * FROM extracted_insurance
            WHERE org_id = :org_id AND vendor_id = :vendor_id
            ORDER BY confidence DESC
        """), {"org_id": org_id, "vendor_id": vendor_id}).fetchall()

        slas = conn.execute(sa.text("""
            SELECT * FROM extracted_slas
            WHERE org_id = :org_id AND vendor_id = :vendor_id
            ORDER BY confidence DESC
        """), {"org_id": org_id, "vendor_id": vendor_id}).fetchall()

        projects = conn.execute(sa.text("""
            SELECT * FROM extracted_projects
            WHERE org_id = :org_id AND vendor_id = :vendor_id
            ORDER BY confidence DESC
        """), {"org_id": org_id, "vendor_id": vendor_id}).fetchall()

        pricing = conn.execute(sa.text("""
            SELECT * FROM extracted_pricing
            WHERE org_id = :org_id AND vendor_id = :vendor_id
            ORDER BY year ASC
        """), {"org_id": org_id, "vendor_id": vendor_id}).fetchall()

    return {
        "certifications": [dict(r._mapping) for r in certs],
        "insurance": [dict(r._mapping) for r in insurance],
        "slas": [dict(r._mapping) for r in slas],
        "projects": [dict(r._mapping) for r in projects],
        "pricing": [dict(r._mapping) for r in pricing],
    }
```

<!-- CHECKPOINT -->
```bash
python checkpoint_runner.py SK03-CP02
```

---

## STEP 3 — Create the LlamaIndex ingestion pipeline

```python
# app/core/llamaindex_pipeline.py
"""
LlamaIndex document processing pipeline.
Replaces the raw chunking code from earlier versions.

Key improvements over raw chunking:
1. HierarchicalNodeParser — stores both summary and detail chunks
2. SentenceWindowNodeParser — preserves sentence context around each chunk
3. Section classification — tags each node with document role
4. Sparse vector generation — enables hybrid BM25 + dense search in Qdrant
"""
import re
import uuid
import hashlib
from typing import Optional
from llama_index.core import Document as LlamaDocument  # llama-index-core==0.12.x
from llama_index.core.node_parser import (  # API stable in 0.12.x
    HierarchicalNodeParser,
    SentenceWindowNodeParser,
    get_leaf_nodes,
)
from llama_index.core.schema import TextNode
from openai import OpenAI
from app.config import settings

_embed_client = None


def get_embed_client():
    global _embed_client
    if _embed_client is None:
        _embed_client = OpenAI(api_key=settings.openai_api_key)
    return _embed_client


def get_dense_embedding(text: str) -> list[float]:
    """OpenAI text-embedding-3-large — 3072 dimensions."""
    client = get_embed_client()
    response = client.embeddings.create(
        model=settings.openai_embedding_model,
        input=text[:8000]
    )
    return response.data[0].embedding


def get_sparse_embedding(text: str) -> tuple[list[int], list[float]]:
    """
    BM25-style sparse embedding for keyword search.
    Returns (indices, values) for Qdrant sparse vector storage.
    Uses simple TF-IDF approximation — replace with proper
    SPLADE model for production if needed.
    """
    # Simple word-frequency based sparse vector
    words = re.sub(r'[^\w\s]', ' ', text.lower()).split()
    word_freq: dict[int, float] = {}

    for word in words:
        if len(word) < 3:
            continue
        # Hash word to integer index
        idx = int(hashlib.md5(word.encode()).hexdigest()[:8], 16) % 100000
        word_freq[idx] = word_freq.get(idx, 0) + 1.0

    # Normalise
    if word_freq:
        max_val = max(word_freq.values())
        word_freq = {k: v / max_val for k, v in word_freq.items()}

    indices = list(word_freq.keys())
    values = list(word_freq.values())
    return indices, values


def classify_section(
    section_text: str,
    section_title: str,
    config: dict
) -> str:
    """
    Classifies a section as requirement_response, supporting_evidence,
    background, or boilerplate.

    Uses the evaluation config to identify requirement-response sections.
    Sections that match mandatory check or scoring criterion keywords
    are classified as requirement_response.
    """
    title_lower = section_title.lower()
    text_lower = section_text.lower()

    # Boilerplate patterns
    boilerplate_markers = [
        "terms and conditions", "legal notice", "disclaimer",
        "copyright", "all rights reserved", "confidentiality",
        "this document is confidential"
    ]
    if any(m in text_lower for m in boilerplate_markers):
        return "boilerplate"

    # Background patterns
    background_markers = [
        "company history", "about us", "our story", "founded in",
        "team bios", "management team", "our offices"
    ]
    if any(m in text_lower for m in background_markers):
        return "background"

    # Check against evaluation config for requirement_response
    all_search_queries = []
    for check in config.get(
        "evaluation_rules", {}
    ).get("mandatory_checks", []):
        all_search_queries.append(
            check.get("search_query", "").lower()
        )
    for crit in config.get(
        "evaluation_rules", {}
    ).get("scoring_criteria", []):
        all_search_queries.append(
            crit.get("search_query", "").lower()
        )

    # If section title or text contains requirement-related keywords
    for query in all_search_queries:
        keywords = query.split()[:3]  # Use first 3 words of query
        if any(kw in title_lower or kw in text_lower for kw in keywords):
            return "requirement_response"

    # Certifications, insurance, SLAs are always supporting_evidence
    evidence_markers = [
        "certificate", "certification", "insurance", "sla",
        "service level", "case study", "project reference",
        "client testimonial", "award"
    ]
    if any(m in title_lower or m in text_lower for m in evidence_markers):
        return "supporting_evidence"

    return "background"


def process_document(
    content: bytes,
    filename: str,
    vendor_id: str,
    org_id: str,
    config: dict
) -> list[dict]:
    """
    Full LlamaIndex processing pipeline.

    Returns list of chunk dicts ready for Qdrant insertion:
    {
        chunk_id, text, dense_vector, sparse_indices, sparse_values,
        section_id, section_title, section_type, priority,
        page_number, filename, vendor_id, org_id
    }
    """
    # Extract raw text
    raw_text = _extract_text(content, filename)

    if not raw_text or len(raw_text.strip()) < 100:
        return []

    # Create LlamaIndex document
    doc = LlamaDocument(
        text=raw_text,
        metadata={
            "filename": filename,
            "vendor_id": vendor_id,
            "org_id": org_id,
        }
    )

    # Use HierarchicalNodeParser for structured documents
    # This creates parent chunks (sections) and child chunks (paragraphs)
    # enabling both broad and precise retrieval
    hierarchical_parser = HierarchicalNodeParser.from_defaults(
        chunk_sizes=[2048, 512, 128]  # Parent, child, grandchild
    )

    # Also use SentenceWindowNodeParser to preserve sentence context
    # This stores the surrounding sentences alongside each chunk
    sentence_parser = SentenceWindowNodeParser.from_defaults(
        window_size=3,  # 3 sentences before and after
        window_metadata_key="window",
        original_text_metadata_key="original_text"
    )

    # Parse into nodes
    all_nodes = hierarchical_parser.get_nodes_from_documents([doc])
    leaf_nodes = get_leaf_nodes(all_nodes)

    # Also parse with sentence window for fine-grained retrieval
    sentence_nodes = sentence_parser.get_nodes_from_documents([doc])

    chunks = []
    seen_texts = set()

    for node in leaf_nodes + sentence_nodes:
        text = node.get_content().strip()

        if len(text) < 80:
            continue

        # Deduplicate
        text_hash = hashlib.md5(text.encode()).hexdigest()
        if text_hash in seen_texts:
            continue
        seen_texts.add(text_hash)

        # Detect section from node metadata or text
        section_title = node.metadata.get(
            "section_title",
            _detect_section_title(text)
        )
        section_id = node.metadata.get(
            "section_id",
            _generate_section_id(section_title)
        )
        section_type = classify_section(text, section_title, config)

        # Priority: requirement_response = 1, supporting = 2, rest = 3
        priority_map = {
            "requirement_response": 1,
            "supporting_evidence": 2,
            "background": 3,
            "boilerplate": 4
        }
        priority = priority_map.get(section_type, 3)

        # Generate embeddings
        dense = get_dense_embedding(text)
        sparse_indices, sparse_values = get_sparse_embedding(text)

        chunks.append({
            "chunk_id": str(uuid.uuid4()),
            "text": text,
            "dense_vector": dense,
            "sparse_indices": sparse_indices,
            "sparse_values": sparse_values,
            "section_id": section_id,
            "section_title": section_title,
            "section_type": section_type,
            "priority": priority,
            "page_number": node.metadata.get("page_label", 1),
            "filename": filename,
            "vendor_id": vendor_id,
            "org_id": org_id,
            "window": node.metadata.get("window", ""),
        })

    return chunks


def _extract_text(content: bytes, filename: str) -> str:
    """Extract text from PDF, DOCX, or TXT."""
    import io
    if filename.lower().endswith(".pdf"):
        from pypdf import PdfReader
        reader = PdfReader(io.BytesIO(content))
        return "\n\n".join(
            page.extract_text() or ""
            for page in reader.pages
        )
    elif filename.lower().endswith(".docx"):
        from docx import Document
        doc = Document(io.BytesIO(content))
        return "\n\n".join(p.text for p in doc.paragraphs if p.text)
    else:
        return content.decode("utf-8", errors="ignore")


def _detect_section_title(text: str) -> str:
    """Extract section title from the beginning of a chunk."""
    lines = text.strip().split("\n")
    first_line = lines[0].strip() if lines else ""
    if len(first_line) < 100 and first_line:
        return first_line
    return "General"


def _generate_section_id(title: str) -> str:
    """Generate a short section ID from title."""
    clean = re.sub(r'[^\w\s]', '', title.lower())
    words = clean.split()[:3]
    return "-".join(words) if words else "general"
```

<!-- CHECKPOINT -->
```bash
python checkpoint_runner.py SK03-CP03
```

---

## STEP 4 — Create ingestion validator

```python
# app/core/ingestion_validator.py
"""
Validates documents before ingestion.
Prevents silent failures from scanned PDFs and corrupt files.
"""
import hashlib
import re


def compute_content_hash(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def validate_extracted_text(
    text: str,
    filename: str
) -> tuple[bool, str]:
    """
    Returns (is_valid, reason).
    is_valid=False means do not ingest — return error to user.
    """
    if not text or len(text.strip()) < 100:
        return False, (
            f"{filename}: Only {len(text)} characters extracted. "
            f"This is likely a scanned PDF with no extractable text. "
            f"Please provide a digital PDF or use OCR to convert first."
        )

    words = text.split()
    if not words:
        return False, f"{filename}: No readable words found."

    avg_word_len = len(text) / len(words)
    if avg_word_len > 15:
        return False, (
            f"{filename}: Average word length {avg_word_len:.1f} "
            f"suggests garbled encoding. Check PDF character encoding."
        )

    # Check for minimum content variety
    unique_words = set(w.lower() for w in words if len(w) > 3)
    if len(unique_words) < 20:
        return False, (
            f"{filename}: Very low vocabulary diversity "
            f"({len(unique_words)} unique words). Document may be "
            f"mostly images or symbols."
        )

    return True, "ok"


def validate_zip_contents(
    file_list: list[str]
) -> tuple[bool, list[str], str]:
    """
    Validates contents of a ZIP submission.
    Returns (is_valid, accepted_files, warning_message).
    """
    supported = {".pdf", ".docx", ".txt", ".doc"}
    accepted = []
    rejected = []

    for f in file_list:
        ext = "." + f.rsplit(".", 1)[-1].lower() if "." in f else ""
        if ext in supported:
            accepted.append(f)
        else:
            rejected.append(f)

    if not accepted:
        return False, [], (
            "ZIP contains no supported document files. "
            f"Found: {file_list}. "
            f"Supported: {supported}"
        )

    warning = ""
    if rejected:
        warning = (
            f"Skipped unsupported files: {rejected}. "
            f"Processing: {accepted}"
        )

    return True, accepted, warning
```

---

## STEP 5 — Create the Ingestion Agent

```python
# app/agents/ingestion.py
"""
Ingestion Agent — the entry point for all documents.

Handles:
- Single PDF/DOCX/TXT files
- ZIP archives containing multiple vendor files
- Heavy PDFs (>50 pages or scanned) are offloaded to Modal for extraction

## MODAL INTEGRATION IN INGESTION

The Ingestion Agent decides per-document whether to extract locally or on Modal:
- Small PDFs (<50 pages, digital text): extracted locally via pypdf
- Large PDFs (>50 pages): sent to Modal's `extract_pdf_on_modal` function
- Scanned PDFs (no extractable text): sent to Modal for OCR processing

```python
# app/agents/ingestion.py — dispatch logic
from app.config import settings

MODAL_THRESHOLD_PAGES = 50  # PDFs above this go to Modal

async def dispatch_extraction(file_bytes: bytes, filename: str, 
                               org_id: str, vendor_id: str, run_id: str):
    """Routes to local or Modal extraction based on document size."""
    from app.core.ingestion_validator import estimate_page_count, is_scanned_pdf
    
    page_count = estimate_page_count(file_bytes, filename)
    is_scanned = is_scanned_pdf(file_bytes) if filename.endswith('.pdf') else False
    
    use_modal = page_count > MODAL_THRESHOLD_PAGES or is_scanned
    
    if use_modal:
        # Import Modal function — runs serverless, no timeout limits
        import modal
        extract_fn = modal.Function.lookup("agentic-platform", "extract_pdf_on_modal")
        result_dict = await extract_fn.remote.aio(
            file_bytes=file_bytes,
            filename=filename,
            org_id=org_id,
            vendor_id=vendor_id,
            run_id=run_id,
        )
        return result_dict
    else:
        # Local extraction for small documents
        from app.agents.ingestion import run_ingestion_for_file
        result = await run_ingestion_for_file(
            file_bytes=file_bytes,
            filename=filename,
            org_id=org_id,
            vendor_id=vendor_id,
            run_id=run_id,
        )
        return result.model_dump()
```
- Duplicate detection
- Quality validation
- LlamaIndex processing → Qdrant storage
- Immediate Extraction Agent trigger on req_response sections
- Critic Agent check after ingestion
"""
import io
import uuid
import zipfile
import hashlib
from app.core.output_models import IngestionOutput, SectionType
from app.core.llamaindex_pipeline import process_document
from app.core.ingestion_validator import (
    compute_content_hash,
    validate_extracted_text,
    validate_zip_contents
)
from app.core.qdrant_client import (
    get_qdrant_client,
    collection_name,
    create_collection,
    upsert_chunk
)
from app.agents.critic import critic_after_ingestion
from app.config import settings


async def run_ingestion_agent(
    content: bytes,
    filename: str,
    vendor_id: str,
    org_id: str,
    rfp_id: str,
    agent_config: dict
) -> tuple[IngestionOutput, list]:
    """
    Main ingestion entry point.
    Returns (IngestionOutput, critic_output_list).

    Handles both single files and ZIP archives.
    """
    # Handle ZIP files
    if filename.lower().endswith(".zip"):
        return await _ingest_zip(
            content, filename, vendor_id,
            org_id, rfp_id, agent_config
        )

    return await _ingest_single_file(
        content, filename, vendor_id,
        org_id, rfp_id, agent_config
    )


async def _ingest_zip(
    content: bytes,
    zip_filename: str,
    vendor_id: str,
    org_id: str,
    rfp_id: str,
    agent_config: dict
) -> tuple[IngestionOutput, list]:
    """
    Unpacks ZIP and processes each file as part of the same vendor.
    """
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as zf:
            file_list = [
                f for f in zf.namelist()
                if not f.startswith("__MACOSX")
                and not f.endswith("/")
            ]

            is_valid, accepted, warning = validate_zip_contents(file_list)

            if not is_valid:
                return IngestionOutput(
                    doc_id=str(uuid.uuid4()),
                    vendor_id=vendor_id,
                    org_id=org_id,
                    filename=zip_filename,
                    total_chunks=0,
                    chunks_by_type={},
                    filtered_chunks=0,
                    extraction_triggered=False,
                    quality_score=0.0,
                    content_hash=compute_content_hash(content),
                    warnings=[f"ZIP invalid: {warning}"],
                    status="failed"
                ), []

            all_outputs = []
            all_critics = []

            for fname in accepted:
                file_bytes = zf.read(fname)
                output, critics = await _ingest_single_file(
                    file_bytes, fname, vendor_id,
                    org_id, rfp_id, agent_config
                )
                all_outputs.append(output)
                all_critics.extend(critics)

            # Merge outputs into one summary
            total_chunks = sum(o.total_chunks for o in all_outputs)
            merged_types: dict = {}
            for o in all_outputs:
                for k, v in o.chunks_by_type.items():
                    merged_types[k] = merged_types.get(k, 0) + v

            avg_quality = (
                sum(o.quality_score for o in all_outputs)
                / len(all_outputs)
                if all_outputs else 0.0
            )

            summary = IngestionOutput(
                doc_id=str(uuid.uuid4()),
                vendor_id=vendor_id,
                org_id=org_id,
                filename=zip_filename,
                total_chunks=total_chunks,
                chunks_by_type=merged_types,
                filtered_chunks=sum(
                    o.filtered_chunks for o in all_outputs
                ),
                extraction_triggered=any(
                    o.extraction_triggered for o in all_outputs
                ),
                quality_score=avg_quality,
                content_hash=compute_content_hash(content),
                warnings=[warning] if warning else [],
                status="success" if total_chunks > 0 else "partial"
            )

            return summary, all_critics

    except zipfile.BadZipFile:
        return IngestionOutput(
            doc_id=str(uuid.uuid4()),
            vendor_id=vendor_id,
            org_id=org_id,
            filename=zip_filename,
            total_chunks=0,
            chunks_by_type={},
            filtered_chunks=0,
            extraction_triggered=False,
            quality_score=0.0,
            content_hash=compute_content_hash(content),
            warnings=["Invalid ZIP file — cannot unpack"],
            status="failed"
        ), []


async def _ingest_single_file(
    content: bytes,
    filename: str,
    vendor_id: str,
    org_id: str,
    rfp_id: str,
    agent_config: dict
) -> tuple[IngestionOutput, list]:
    """Processes a single document file."""
    doc_id = str(uuid.uuid4())
    content_hash = compute_content_hash(content)
    warnings = []

    # Process with LlamaIndex
    chunks = process_document(
        content, filename, vendor_id, org_id, agent_config
    )

    if not chunks:
        output = IngestionOutput(
            doc_id=doc_id,
            vendor_id=vendor_id,
            org_id=org_id,
            filename=filename,
            total_chunks=0,
            chunks_by_type={},
            filtered_chunks=0,
            extraction_triggered=False,
            quality_score=0.0,
            content_hash=content_hash,
            warnings=["No usable chunks produced from document"],
            status="failed"
        )
        critic = critic_after_ingestion(output)
        return output, [critic]

    # Validate text quality on combined text
    combined_text = " ".join(c["text"] for c in chunks[:5])
    is_valid, reason = validate_extracted_text(combined_text, filename)
    if not is_valid:
        warnings.append(reason)

    # Count chunks by type
    chunks_by_type: dict = {}
    for chunk in chunks:
        st = chunk["section_type"]
        chunks_by_type[st] = chunks_by_type.get(st, 0) + 1

    # Quality score
    req_resp = chunks_by_type.get("requirement_response", 0)
    total = len(chunks)
    quality_score = min(1.0, (
        0.4 * min(1.0, total / 20) +          # Doc length
        0.4 * min(1.0, req_resp / 5) +         # Req response sections
        0.2 * (1.0 if is_valid else 0.3)       # Text quality
    ))

    # Store in Qdrant
    coll_name = collection_name(org_id, vendor_id)
    create_collection(coll_name)

    for chunk in chunks:
        payload = {
            "chunk_id": chunk["chunk_id"],
            "text": chunk["text"],
            "section_id": chunk["section_id"],
            "section_title": chunk["section_title"],
            "section_type": chunk["section_type"],
            "priority": chunk["priority"],
            "page_number": chunk["page_number"],
            "filename": filename,
            "vendor_id": vendor_id,
            "org_id": org_id,
            "rfp_id": rfp_id,
            "doc_id": doc_id,
        }
        upsert_chunk(
            collection=coll_name,
            chunk_id=chunk["chunk_id"],
            dense_vector=chunk["dense_vector"],
            sparse_indices=chunk["sparse_indices"],
            sparse_values=chunk["sparse_values"],
            payload=payload
        )

    req_chunks = [
        c for c in chunks
        if c["section_type"] == "requirement_response"
    ]
    extraction_triggered = len(req_chunks) > 0

    output = IngestionOutput(
        doc_id=doc_id,
        vendor_id=vendor_id,
        org_id=org_id,
        filename=filename,
        total_chunks=len(chunks),
        chunks_by_type=chunks_by_type,
        filtered_chunks=0,
        extraction_triggered=extraction_triggered,
        quality_score=quality_score,
        content_hash=content_hash,
        warnings=warnings,
        status="success"
    )

    # Critic check
    critic = critic_after_ingestion(output)

    return output, [critic]
```

<!-- CHECKPOINT -->
```bash
python checkpoint_runner.py SK03-CP04
python checkpoint_runner.py SK03-CP05
```

---

## SKILL 03 COMPLETE

```bash
python checkpoint_runner.py SK03
python contract_tests.py
python drift_detector.py
```

Open SKILL_03b_RAG_QUALITY.md
