# Agent 01 — Ingestion Agent
**What it does:** Takes a vendor's PDF proposal, extracts the text, cuts it into searchable pieces (chunks), labels each piece by relevance to the evaluation criteria, generates two types of search fingerprints for each piece, and stores everything in Qdrant (vector database). No LLM is used at any point — this agent is entirely deterministic.

---

## Process Flow

```
Vendor PDF (bytes from vendor_documents table)
                │
                ▼
    ┌─────────────────────┐
    │  Step 1             │
    │  Extract text       │
    │  from PDF           │
    └─────────────────────┘
                │  plain text string (in memory only, never saved)
                ▼
    ┌─────────────────────┐
    │  Step 2a            │
    │  Hierarchical cut   │
    │  (large/medium/     │
    │  small chunks)      │
    └─────────────────────┘
                │
    ┌─────────────────────┐
    │  Step 2b            │
    │  Sentence window    │
    │  cut (sentence +    │
    │  3 neighbours)      │
    └─────────────────────┘
                │  combined chunk list, duplicates removed
                ▼
    ┌─────────────────────┐
    │  Step 3             │
    │  Label each chunk   │
    │  (requirement /     │
    │  background /       │
    │  evidence /         │
    │  boilerplate)       │
    └─────────────────────┘
                │
                ▼
    ┌─────────────────────┐
    │  Step 4a            │
    │  Dense embedding    │
    │  (meaning           │
    │  fingerprint)       │
    └─────────────────────┘
                │
    ┌─────────────────────┐
    │  Step 4b            │
    │  Sparse embedding   │
    │  (keyword / BM25    │
    │  fingerprint)       │
    └─────────────────────┘
                │
                ▼
    ┌─────────────────────┐
    │  Step 5             │
    │  Store in Qdrant    │
    │  (tenant-isolated   │
    │  collection)        │
    └─────────────────────┘
                │
                ▼
    ┌─────────────────────┐
    │  Step 6             │
    │  Critic check       │
    │  APPROVED /         │
    │  BLOCKED            │
    └─────────────────────┘
```

---

## Tools Used Per Step

### Step 1 — Extract text from PDF
| What | Tool | LLM? | Cost |
|---|---|---|---|
| Read PDF pages and extract text | **pypdf** (open source) | No | Free |
| Read DOCX files | **python-docx** (open source) | No | Free |
| Read plain TXT files | Python built-in `decode()` | No | Free |

**Output:** One plain text string of the entire document — held in memory only. Never saved to any database. Discarded after chunking.

**Note:** For PDFs over 50 pages or scanned PDFs (images, not text), the code is designed to offload to **Modal** (cloud GPU) for OCR extraction. Not yet exercised in smoke tests.

---

### Step 2a — Hierarchical cut
| What | Tool | LLM? | Cost |
|---|---|---|---|
| Cut document into 3 sizes of chunks | **LlamaIndex** `HierarchicalNodeParser` | No | Free |
| Chunk sizes configured in | `platform.yaml` → `chunk_size_tokens: 500` | No | Free |
| Keep only smallest (leaf) chunks | **LlamaIndex** `get_leaf_nodes()` | No | Free |

**Three sizes used:**
- Large: `500 × 4 = 2000 tokens` (~1500 words) — one full section
- Medium: `500 tokens` (~375 words) — one sub-section
- Small: `500 ÷ 4 = 125 tokens` (~95 words) — one paragraph

Only the small (leaf) chunks are kept for storage.

---

### Step 2b — Sentence window cut
| What | Tool | LLM? | Cost |
|---|---|---|---|
| Cut by sentence boundaries | **LlamaIndex** `SentenceWindowNodeParser` | No | Free |
| Attach 3 surrounding sentences as context window | LlamaIndex (window_size=3) | No | Free |

**Why two cutters?** The hierarchical cutter gives good topic-level chunks. The sentence cutter preserves precise evidence sentences with their surrounding context. Both together give better retrieval coverage.

**Deduplication:** After combining both cutter outputs, any chunk with identical text is removed. A chunk under 80 characters is also discarded (too short to be useful).

**Chunk ID:** Each chunk gets a deterministic ID derived from `sha256(org_id + vendor_id + text)` formatted as a UUID. This means re-ingesting the same document always produces the same IDs — Qdrant upserts replace rather than duplicate.

---

### Step 3 — Label each chunk (section classification)
| What | Tool | LLM? | Cost |
|---|---|---|---|
| Detect legal boilerplate | Python string matching against fixed phrase list | No | Free |
| Detect company background | Python string matching against fixed phrase list | No | Free |
| Match against evaluation criteria keywords | Python string matching against `EvaluationSetup` criteria names | No | Free |
| Detect supporting evidence (certs, SLAs, case studies) | Python string matching against fixed phrase list | No | Free |

**Four labels assigned:**
| Label | Priority | Meaning |
|---|---|---|
| `requirement_response` | 1 (highest) | Chunk directly addresses an RFP criterion |
| `supporting_evidence` | 2 | Chunk contains certs, SLAs, project references |
| `background` | 3 | Company history, team info, general description |
| `boilerplate` | 4 (lowest) | Legal disclaimers, T&Cs, confidentiality notices |

**Known limitation:** Keyword matching only finds exact or near-exact word matches. A chunk saying "we comply with the 2022 information security standard" will NOT be labelled `requirement_response` for a criterion named "ISO 27001" because those words don't appear. This means some relevant chunks get deprioritised. See **AI-005** in BACKLOG.md.

---

### Step 4a — Dense embedding (meaning fingerprint)
| What | Tool | LLM? | Cost |
|---|---|---|---|
| Convert chunk text to a vector of numbers | **OpenAI** `text-embedding-3-large` (3072 numbers) | No — embedding model, not generative LLM | ~$0.002 per vendor doc |
| OR — run locally for data-private customers | **BAAI/bge-large-en-v1.5** (1024 numbers, runs on machine) | No | Free |
| All chunks embedded in one batch call | `embed_batch()` in `app/providers/embedding.py` | No | One API call total |

**What it captures:** Meaning. "We comply with ISO 27001" and "we are certified under the 2022 information security standard" produce similar vectors and will be found by the same search.

**Provider is configurable:** Set `EMBEDDING_PROVIDER=local` in `.env` to use the local model. No code change needed.

---

### Step 4b — Sparse embedding (keyword fingerprint)
| What | Tool | LLM? | Cost |
|---|---|---|---|
| Count word frequency in chunk | Custom BM25 implementation in `pipeline.py` | No | Free |
| Hash each word to an index | Python `hashlib.md5` | No | Free |
| Normalise scores 0–1 | Pure Python | No | Free |

**What it captures:** Exact keywords. "ISO 27001" will score highly in a chunk that mentions "ISO 27001" multiple times.

**Known limitation:** This is a simplified BM25 approximation, not a trained model. A proper SPLADE model (open source, Apache 2.0) would produce better sparse vectors. See BACKLOG.md.

---

### Step 5 — Store in Qdrant
| What | Tool | LLM? | Cost |
|---|---|---|---|
| Create tenant-isolated collection if not exists | **qdrant-client** SDK | No | Free |
| Store chunk text + metadata as payload | **Qdrant** vector database | No | Free |
| Store dense vector | **Qdrant** `dense` named vector | No | Free |
| Store sparse vector | **Qdrant** `sparse` named vector | No | Free |

**Collection naming:** `platform_{org_id}_{vendor_id}` — each vendor gets their own isolated collection. Acme's data cannot appear in a search for Apex. This is tenant isolation enforced at the database level.

**What is stored per chunk in Qdrant:**
```
chunk_id        — deterministic UUID (sha256-based)
text            — the actual chunk text
dense_vector    — 3072 numbers (meaning fingerprint)
sparse_vector   — keyword index → score map
section_type    — requirement_response / supporting_evidence / background / boilerplate
priority        — 1 / 2 / 3 / 4
section_title   — title of the section this chunk came from
page_number     — page in the original PDF
vendor_id       — tenant isolation filter
org_id          — tenant isolation filter
rfp_id          — which evaluation this belongs to
doc_id          — links back to vendor_documents table in PostgreSQL
filename        — original filename
```

**What is NOT stored:** The full original PDF. That is stored in `vendor_documents.file_bytes` in PostgreSQL by the API at upload time, not by the ingestion agent.

---

### Step 6 — Critic check
| What | Tool | LLM? | Cost |
|---|---|---|---|
| Check quality score ≥ 0.4 | Pure Python threshold | No | Free |
| Check at least 1 `requirement_response` chunk exists | Pure Python | No | Free |
| Check for duplicate document (same content_hash) | Pure Python | No | Free |
| Produce structured CriticOutput | `app/agents/critic.py` | No | Free |

**Quality score formula:**
```
quality_score = 0.4 × min(1.0, total_chunks / 20)       ← chunk volume
              + 0.4 × min(1.0, requirement_chunks / 5)   ← relevance
              + 0.2 × (1.0 if text readable else 0.3)    ← readability
```

**Critic verdicts:**
| Verdict | Condition | Action |
|---|---|---|
| `APPROVED` | No flags | Pipeline continues |
| `APPROVED_WITH_WARNINGS` | Soft flags only (e.g. quality < 0.65) | Pipeline continues, warnings shown |
| `BLOCKED` | Hard flag (e.g. quality < 0.4, zero requirement chunks) | Pipeline stops, vendor must resubmit |

---

## LLM Call Summary

**Zero LLM calls in the entire ingestion agent.**

The only external API call is the embedding model (Step 4a) — which converts text to numbers. It does not reason, generate, or interpret. It is not a language model in the generative sense.

| Step | External call | LLM? | Cost |
|---|---|---|---|
| 1 | None | No | Free |
| 2 | None | No | Free |
| 3 | None | No | Free |
| 4a | OpenAI embeddings API (one batch) | No | ~$0.002 |
| 4b | None | No | Free |
| 5 | Qdrant (local) | No | Free |
| 6 | None | No | Free |

**Total per vendor document:** ~$0.002 (under half a penny).

---

## Data Saved

| Where | What |
|---|---|
| **Qdrant** | All chunks with dense + sparse vectors and metadata |
| **PostgreSQL** `vendor_documents` | `quality_score`, `total_chunks` updated after ingestion (when called via API) |

**Note:** When run via the smoke test (`tools/smoke_test.py`), the vendor_documents row is NOT updated with quality_score/total_chunks. This only happens via the real API pipeline.

---

## Key Files

| File | Role |
|---|---|
| `app/agents/ingestion.py` | Main ingestion agent — orchestrates all steps |
| `app/retrieval/pipeline.py` | Text extraction, chunking, classification, embedding |
| `app/retrieval/qdrant.py` | Qdrant client — collection creation and chunk storage |
| `app/providers/embedding.py` | `embed_batch()` — provider-agnostic embedding |
| `app/agents/critic.py` | `critic_after_ingestion()` — quality check |
| `app/validators/ingestion.py` | Text quality validation helpers |
| `app/config/platform.yaml` | `chunk_size_tokens: 500` — configurable chunk size |

---

## Known Issues Fixed This Session

| Bug | Symptom | Fix |
|---|---|---|
| Random chunk IDs | Every re-ingest added new duplicate chunks — Acme had 392 points instead of 49 | Changed chunk_id to `sha256(org_id:vendor_id:text_hash)` formatted as UUID |

---

## Known Limitations (Backlog)

| # | Issue | Backlog item |
|---|---|---|
| 1 | Section labelling uses keyword matching — misses paraphrased content | AI-005 |
| 2 | Sparse vectors are simplified BM25 approximation, not SPLADE | AI-005 |
| 3 | No criterion-to-chunk pre-index built at ingestion time | AI-005 |
| 4 | Smoke test does not save quality_score/total_chunks back to vendor_documents | TI-001 |
