# Agent 02 — Retrieval Agent
**What it does:** Takes a single evaluation question (e.g. "Does this vendor hold ISO 27001?") and finds the most relevant chunks of text from that vendor's ingested document. It makes the question smarter before searching, searches using two complementary techniques combined, re-orders results so the best evidence is in the most readable position, and returns a ranked list of text snippets ready for the Extraction Agent. Every result is scoped to one vendor — no cross-tenant data can appear.

---

## Process Flow

```
Evaluation question (e.g. "does vendor hold ISO 27001?")
                │
                ▼
    ┌─────────────────────┐
    │  Step 1             │
    │  Query rewriting    │
    │  (optional)         │
    └─────────────────────┘
                │
                ▼
    ┌─────────────────────┐
    │  Step 2             │
    │  HyDE — generate    │
    │  hypothetical       │
    │  vendor answer      │
    │  (optional)         │
    └─────────────────────┘
                │
                ▼
    ┌─────────────────────┐
    │  Step 3a            │
    │  Hybrid search      │
    │  (dense meaning     │
    │  + sparse keyword   │
    │  fused via RRF)     │
    └─────────────────────┘
                │  OR (if hybrid disabled)
    ┌─────────────────────┐
    │  Step 3b            │
    │  Dense-only search  │
    └─────────────────────┘
                │  top N candidates
                ▼
    ┌─────────────────────┐
    │  Step 4             │
    │  BGE CrossEncoder   │
    │  reranker           │
    └─────────────────────┘
                │
                ▼
    ┌─────────────────────┐
    │  Step 5             │
    │  Lost-in-middle     │
    │  reorder            │
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

### Step 1 — Query rewriting
| What | Tool | LLM? | Cost |
|---|---|---|---|
| Expand short user query to formal document language | **GPT-4o** via `call_llm()` | Yes | ~$0.0002 |
| Prompt loaded from config | Inline system prompt in `retrieval.py` | No | Free |

**What it does:** A short question like "do they have ISO cert?" becomes "ISO 27001 information security management certification current valid holder accredited". Documents use formal language — the rewritten query matches it better.

**Configurable:** Set `use_query_rewriting: false` in org settings to skip this step.

**Output:** Expanded query string.

---

### Step 2 — HyDE (Hypothetical Document Embedding)
| What | Tool | LLM? | Cost |
|---|---|---|---|
| Write a fake ideal vendor answer to the question | **GPT-4o** via `call_llm()` | Yes | ~$0.001 |
| Embed the fake answer into a meaning vector | Embedding model (`embed_text()`) | No | ~$0.00001 |

**What it does:** Instead of searching with the question ("do they have ISO 27001?"), it generates a fake answer ("Yes, our company holds ISO 27001 certification renewed annually...") and searches using the *meaning of that answer*. This finds chunks that look like answers, not chunks that look like questions.

**Key constraint:** HyDE's fake document is used ONLY for the meaning/dense search. The keyword/BM25 search always uses the original user question — so exact keyword matches are not disrupted by the fake text.

**Configurable:** Set `use_hyde: false` in org settings to skip. When skipped, the rewritten query (or original query) is embedded directly.

**Output:** Dense vector (list of 1024 or 3072 numbers representing meaning).

---

### Step 3a — Hybrid search (dense + sparse, RRF fusion)
| What | Tool | LLM? | Cost |
|---|---|---|---|
| Search by meaning | **Qdrant** dense vector search | No | Free |
| Search by keywords | **Qdrant** sparse/BM25 vector search | No | Free |
| Combine both ranked lists | **Qdrant** RRF fusion (`query_points` with `FusionQuery`) | No | Free |
| Filter by tenant + section type | Qdrant `Filter` with `must` conditions | No | Free |

**What it does:** Runs two searches in parallel — one that finds chunks with similar *meaning*, one that finds chunks with matching *keywords* — then combines the two ranked lists using Reciprocal Rank Fusion (RRF). A chunk that appears high in both lists scores higher than one that only appears in one.

**Tenant isolation:** Every search applies `org_id` and `vendor_id` as mandatory filters. Acme's chunks can never appear when searching Apex.

**Section type filter (optional):** Can narrow to `requirement_response` chunks only — useful for mandatory compliance checks where background text is irrelevant.

**Output:** Up to `retrieval_top_k` (default: 20) candidate chunks with scores.

---

### Step 3b — Dense-only search (fallback)
| What | Tool | LLM? | Cost |
|---|---|---|---|
| Search by meaning only | **Qdrant** dense vector search | No | Free |

Used when `use_hybrid_search: false` in org settings. Simpler but misses exact keyword matches.

---

### Step 4 — BGE CrossEncoder reranker
| What | Tool | LLM? | Cost |
|---|---|---|---|
| Score each candidate chunk against the original question | **BGE CrossEncoder** (`BAAI/bge-reranker-large`) | No | Free |
| Keep top N | Pure Python `sorted()` | No | Free |

**What it does:** The vector search finds chunks that are *similar* to the query. The reranker reads both the question and each chunk together and scores how directly the chunk *answers* the question. These are different — a chunk about "security audits" might be similar to "ISO 27001" but not actually answer "do they hold the cert?".

**Why BGE and not Cohere:** BGE CrossEncoder is open source (Apache 2.0) and runs locally with no rate limits. Cohere Rerank requires API keys and has per-call limits.

**Configurable:** `reranker_provider` in org settings. Options: `bge` (default), `cohere`, `none`.

**Output:** Top `rerank_top_n` (default: 5) chunks ranked by relevance score.

---

### Step 5 — Lost-in-middle reorder
| What | Tool | LLM? | Cost |
|---|---|---|---|
| Reorder chunks for optimal LLM reading | Pure Python list reorder | No | Free |

**What it does:** Research shows LLMs read the first and last items in a list more carefully than items in the middle ("lost in the middle" problem). After reranking, the #1 chunk goes first, the #2 chunk goes last, and everything else fills the middle. This ensures the two best pieces of evidence are in the positions the LLM actually pays attention to.

**Output:** Same chunks, reordered.

---

### Step 6 — Critic check
| What | Tool | LLM? | Cost |
|---|---|---|---|
| Check at least 1 chunk returned | Pure Python | No | Free |
| Check confidence score above threshold | Pure Python | No | Free |
| Check mandatory checks have at least 1 result | Pure Python | No | Free |
| Produce structured CriticOutput | `app/agents/critic.py` | No | Free |

**Critic verdicts:**
| Verdict | Condition | Action |
|---|---|---|
| `APPROVED` | Chunks found, confidence acceptable | Pipeline continues to Extraction |
| `APPROVED_WITH_WARNINGS` | Low confidence but result returned | Continues with warning flag |
| `BLOCKED` | Zero chunks found for a mandatory check | Pipeline stops — that criterion flagged as unresolvable |

---

## LLM Call Summary

| Step | When called | Approx cost |
|---|---|---|
| Step 1 — query rewriting | Every retrieval (if enabled) | ~$0.0002 |
| Step 2 — HyDE generation | Every retrieval (if enabled) | ~$0.001 |

**Total per retrieval call:** ~$0.0012 (about a tenth of a penny).

For a typical RFP evaluation with 10 criteria × 3 vendors = 30 retrieval calls: ~$0.036 total.

---

## Data Flow

| From | To | What |
|---|---|---|
| Qdrant (ingested chunks) | Retrieval Agent | Vector search results |
| Retrieval Agent | Extraction Agent | `RetrievalOutput` — typed list of `RetrievedChunk` objects |

**What is NOT stored:** Retrieval results are not written to PostgreSQL. They are passed directly to the Extraction Agent as structured Python objects. The Extraction Agent then saves facts to PostgreSQL.

**What IS logged:** Every retrieval call is written to the audit log via `log_retrieval()` — query text, rewritten query, strategy used, number of candidates, timing, and final scores.

---

## Key Files

| File | Role |
|---|---|
| `app/agents/retrieval.py` | Main retrieval agent — orchestrates all steps |
| `app/retrieval/qdrant.py` | `search_hybrid()`, `search_dense()` — Qdrant queries |
| `app/providers/reranker.py` | `rerank()` — provider-agnostic reranker |
| `app/providers/embedding.py` | `embed_text()`, `embed_batch()` — dense vectors |
| `app/retrieval/pipeline.py` | `get_sparse_embedding()` — BM25 keyword vectors |
| `app/infra/audit.py` | `log_retrieval()` — audit trail per retrieval call |
| `app/schemas/output_models.py` | `RetrievalOutput`, `RetrievedChunk` — typed output |

---

## Org Settings That Control This Agent

All configurable per org in the `org_settings` table — no code changes needed.

| Setting | Default | Effect |
|---|---|---|
| `use_query_rewriting` | `true` | Expand short queries to formal language before search |
| `use_hyde` | `true` | Generate hypothetical vendor answer for dense embedding |
| `use_hybrid_search` | `true` | Combine dense + sparse search via RRF |
| `use_reranking` | `true` | Apply BGE CrossEncoder reranker after initial search |
| `retrieval_top_k` | `20` | How many candidates to fetch before reranking |
| `rerank_top_n` | `5` | How many chunks to keep after reranking |
| `reranker_provider` | `bge` | Which reranker to use (`bge`, `cohere`, `none`) |

---

## Known Limitations (Backlog)

| # | Issue | Backlog item |
|---|---|---|
| 1 | Context compression disabled — compressing chunk text causes grounding check failures in Extraction Agent | AI-007 |
| 2 | No criterion-to-chunk pre-index — every criterion runs a fresh Qdrant search even when chunks overlap significantly | AI-005 |
| 3 | HyDE template is generic ("vendor_response") — no per-criterion templates tuned to domain | AI-005 |

---

## Fixes Applied This Session

Four bugs were identified and fixed before end-to-end testing. All four were silent failures — no errors were thrown, but retrieval quality was degraded.

### Fix 1 — Section type filter missing from hybrid search
**What was wrong:** The filter that limits results to `requirement_response` chunks was applied in dense-only search but silently dropped when hybrid search was used. In hybrid mode, background text, legal boilerplate, and company history competed equally with relevant criteria sections in every search.

**Fix:** Added `section_type_filter` parameter to `search_hybrid()` in `app/retrieval/qdrant.py` and applied it to Qdrant `must_conditions` — matching the behaviour already present in `search_dense()`.

---

### Fix 2 — Too few candidates before reranking
**What was wrong:** `retrieval_top_k` was set to 10 in org settings. The reranker was then asked to pick the best 5 from those 10. With such a small pool, genuinely relevant chunks that scored slightly lower in vector search (but would have ranked top after reranking) were never seen.

**Fix:** Updated `retrieval_top_k` from 10 to 20 in the `org_settings` database for all organisations. The reranker now has 20 candidates to sort through before returning the top 5 — giving it real signal to work with.

---

### Fix 3 — HyDE document used for keyword search
**What was wrong:** When HyDE was active, the 200-word hypothetical document ("Yes, our company holds ISO 27001 certification, renewed annually under UKAS accreditation...") was being passed as `query_text` to `search_hybrid()`. Inside that function, `query_text` is used to generate the BM25/sparse embedding. This means the keyword search was looking for the vocabulary of a fake vendor answer, not the original user question's keywords. Short specific terms like "ISO 27001" were drowned out.

**Fix:** Changed the `search_hybrid()` call in `run_retrieval_agent()` to always pass the original `query` as `query_text` (for sparse/BM25), while the HyDE dense vector is passed separately via the `dense_vector` parameter. The two search signals now use the inputs they were designed for.

---

### Fix 4 — Section type filter not passed to the search call
**What was wrong:** Even after Fix 1 added the parameter to `search_hybrid()`, the calling code in `run_retrieval_agent()` never passed `section_type_filter` through to that call. The parameter existed but was unused — the filter was applied in dense-only mode but not in hybrid mode.

**Fix:** Added `section_type_filter=section_type_filter` to the `search_hybrid()` call in `app/agents/retrieval.py`, matching the argument already present in the `search_dense()` call.
