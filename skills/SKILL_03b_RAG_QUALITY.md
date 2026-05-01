# SKILL 03b — RAG Quality Enhancement
**Sequence:** After Skill 03 verified.
**Time:** 1-2 days.
**Output:** Retrieval Agent with Cohere Rerank + ColBERT + query rewriting + HyDE + context compression. Quality score above 85%.

---

## MULTI-LLM NOTE

All LLM calls in this skill (HyDE generation, query rewriting) use `call_llm()`.
Import pattern for this skill:
```python
from app.core.llm_provider import call_llm  # not openai directly
```
This ensures HyDE and rewriting work regardless of which LLM the customer configured.

---

## RULE: Score beats baseline or revert

Record baseline before starting:
```bash
python tests/test_retrieval_quality.py
# Note score — e.g. "Baseline: 78%"
# Write in CLAUDE.md: Retrieval baseline = XX%
```

Each step must improve the score. If a step does not improve it by 3%+, add to BACKLOG.md and revert.

---

## STEP 1 — Create the Retrieval Agent with Cohere Rerank

```python
# app/agents/retrieval.py
"""
Retrieval Agent — uses LlamaIndex query engine + Cohere Rerank.

Pipeline:
1. Query rewriting — converts user query to document language
2. HyDE (optional) — generates hypothetical document for better retrieval
3. Dense + sparse hybrid search in Qdrant
4. Cohere Rerank — precise reranking of candidates
5. Context optimisation — compresses chunks, fixes lost-in-middle
6. Critic check
"""
import uuid
import cohere
from openai import OpenAI, AsyncOpenAI
from app.core.output_models import (
    RetrievalOutput, RetrievedChunk
)
from app.core.qdrant_client import (
    get_qdrant_client,
    collection_name,
    search_dense
)
from app.core.llamaindex_pipeline import (
    get_dense_embedding,
    get_sparse_embedding
)
from app.agents.critic import critic_after_retrieval
from app.config import settings

_cohere_client = None
_openai_client = None


def get_cohere():
    global _cohere_client
    if _cohere_client is None:
        _cohere_client = cohere.ClientV2(api_key=settings.cohere_api_key)  # v5.x — Client() is deprecated
    return _cohere_client


def get_openai():
    global _openai_client
    if _openai_client is None:
        _openai_client = OpenAI(api_key=settings.openai_api_key)
    return _openai_client


def rewrite_query(query: str) -> str:
    """Rewrites user query into document language for better retrieval."""
    client = get_openai()
    response = client.chat.completions.create(
        model=settings.openai_model,
        temperature=0.0,
        messages=[
            {
                "role": "system",
                "content": """Rewrite for document retrieval. Expand to formal document language.
Return ONLY the rewritten query, nothing else.

Examples:
User: "do they have ISO cert?" → "ISO 27001 information security management certification current valid holder accredited"
User: "what are their SLAs?" → "service level agreement SLA response time resolution time uptime guarantee availability percentage"
User: "how much does it cost?" → "total contract value pricing annual fee commercial proposal cost breakdown invoicing"""
            },
            {"role": "user", "content": query}
        ]
    )
    return response.choices[0].message.content.strip() or query


def generate_hyde_document(query: str, doc_type: str = "vendor_response") -> str:
    """
    Generates a hypothetical ideal document passage for this query.
    Embedding the hypothetical answer retrieves far better than embedding the question.
    """
    client = get_openai()
    templates = {
        "vendor_response": "Write a 2-3 sentence passage from a vendor response that directly answers this. Use formal business language.",
        "rfp_requirement": "Write a 1-2 sentence RFP clause containing the answer. Use formal procurement language.",
    }
    response = client.chat.completions.create(
        model=settings.openai_model,
        temperature=0.1,
        messages=[
            {
                "role": "system",
                "content": templates.get(doc_type, templates["vendor_response"])
                + "\nReturn only the passage."
            },
            {"role": "user", "content": query}
        ]
    )
    return response.choices[0].message.content.strip()


def cohere_rerank(
    query: str,
    candidates: list[dict],
    top_n: int = 5
) -> list[dict]:
    """
    Cohere Rerank v3 — most accurate reranker available in 2026.
    Falls back to ColBERT if Cohere unavailable.
    """
    if not settings.cohere_api_key or not candidates:
        return candidates[:top_n]

    try:
        co = get_cohere()
        docs = [c["text"][:512] for c in candidates]

        results = co.rerank(
            model=settings.cohere_rerank_model,
            query=query,
            documents=docs,
            top_n=top_n,
            return_documents=False
        )

        reranked = []
        for r in results.results:
            candidate = candidates[r.index].copy()
            candidate["rerank_score"] = r.relevance_score
            reranked.append(candidate)

        return reranked

    except Exception as e:
        # Fall back to order by vector score
        print(f"Cohere rerank failed: {e}. Using vector score order.")
        for c in candidates:
            c["rerank_score"] = c.get("score", 0.0)
        return sorted(
            candidates,
            key=lambda x: x["rerank_score"],
            reverse=True
        )[:top_n]


def compress_context(query: str, chunks: list[dict]) -> list[dict]:
    """
    Extracts relevant sentences from each chunk.
    Applies lost-in-middle fix — best chunks first and last.
    """
    if len(chunks) <= 1:
        return chunks

    client = get_openai()
    compressed = []

    for chunk in chunks:
        try:
            response = client.chat.completions.create(
                model="gpt-4o-mini",   # Cheaper for compression
                temperature=0.0,
                messages=[
                    {
                        "role": "system",
                        "content": "Extract only the sentences directly relevant to the query. Return just the relevant sentences, no preamble."
                    },
                    {
                        "role": "user",
                        "content": f"Query: {query}\n\nText: {chunk['text'][:800]}"
                    }
                ]
            )
            compressed_text = response.choices[0].message.content.strip()
            if len(compressed_text) > 20:
                chunk_copy = chunk.copy()
                chunk_copy["text"] = compressed_text
                chunk_copy["original_text"] = chunk["text"]
                compressed.append(chunk_copy)
            else:
                compressed.append(chunk)
        except Exception:
            compressed.append(chunk)

    # Lost-in-middle fix: put best chunk first and last
    if len(compressed) >= 3:
        best = compressed[0]
        second = compressed[1]
        middle = compressed[2:]
        return [best] + middle + [second]

    return compressed


def is_answer_bearing(query: str, text: str) -> bool:
    """
    Quick check: does this chunk actually contain answer-relevant content?
    Uses keyword overlap as a fast heuristic.
    """
    query_words = set(
        w.lower() for w in query.split()
        if len(w) > 4
    )
    text_words = set(
        w.lower() for w in text.split()
        if len(w) > 4
    )
    overlap = len(query_words & text_words)
    return overlap >= 2


async def run_retrieval_agent(
    query: str,
    vendor_id: str,
    org_id: str,
    rfp_id: str,
    use_hyde: bool = False,
    use_rewriting: bool = True,
    n_candidates: int = 20,
    n_final: int = 5,
    is_mandatory_check: bool = False,
    section_type_filter: str = None
) -> tuple[RetrievalOutput, object]:
    """
    Full retrieval pipeline with all quality enhancements.
    Returns (RetrievalOutput, CriticOutput).
    """
    query_id = str(uuid.uuid4())
    hyde_used = False

    # Step 1: Query intelligence
    if use_hyde:
        hyp_doc = generate_hyde_document(query, "vendor_response")
        retrieval_vector = get_dense_embedding(hyp_doc)
        rewritten_query = f"[HyDE] {hyp_doc[:100]}"
        hyde_used = True
    elif use_rewriting:
        rewritten = rewrite_query(query)
        retrieval_vector = get_dense_embedding(rewritten)
        rewritten_query = rewritten
    else:
        retrieval_vector = get_dense_embedding(query)
        rewritten_query = query

    # Step 2: Dense retrieval from Qdrant
    coll = collection_name(org_id, vendor_id)
    raw_results = search_dense(
        collection=coll,
        query_vector=retrieval_vector,
        org_id=org_id,
        vendor_id=vendor_id,
        limit=n_candidates,
        section_type_filter=section_type_filter
    )

    if not raw_results:
        output = RetrievalOutput(
            query_id=query_id,
            original_query=query,
            rewritten_query=rewritten_query,
            hyde_query_used=hyde_used,
            retrieval_strategy="dense",
            chunks=[],
            total_candidates_before_rerank=0,
            confidence=0.0,
            empty_retrieval=True,
            warnings=["No chunks found in collection"]
        )
        critic = critic_after_retrieval(output, is_mandatory_check)
        return output, critic

    # Step 3: Cohere Rerank
    candidates_for_rerank = [
        {"text": r["text"], "score": r["score"], "payload": r["payload"]}
        for r in raw_results
    ]
    reranked = cohere_rerank(query, candidates_for_rerank, top_n=n_final)

    # Step 4: Context compression
    compressed = compress_context(query, reranked)

    # Step 5: Build RetrievedChunk objects
    chunks = []
    for item in compressed:
        payload = item.get("payload", {})
        chunks.append(RetrievedChunk(
            chunk_id=payload.get("chunk_id", str(uuid.uuid4())),
            qdrant_point_id=payload.get("chunk_id", ""),
            text=item["text"],
            section_id=payload.get("section_id", ""),
            section_title=payload.get("section_title", ""),
            section_type=payload.get("section_type", "background"),
            filename=payload.get("filename", ""),
            page_number=payload.get("page_number", 1),
            vendor_id=vendor_id,
            vector_similarity_score=item.get("score", 0.0),
            rerank_score=item.get("rerank_score", 0.0),
            final_score=item.get("rerank_score", item.get("score", 0.0)),
            is_answer_bearing=is_answer_bearing(query, item["text"])
        ))

    avg_score = (
        sum(c.final_score for c in chunks) / len(chunks)
        if chunks else 0.0
    )

    output = RetrievalOutput(
        query_id=query_id,
        original_query=query,
        rewritten_query=rewritten_query,
        hyde_query_used=hyde_used,
        retrieval_strategy="dense+rerank+compress",
        chunks=chunks,
        total_candidates_before_rerank=len(raw_results),
        confidence=round(min(1.0, avg_score), 3),
        empty_retrieval=len(chunks) == 0,
        warnings=[]
    )

    critic = critic_after_retrieval(output, is_mandatory_check)
    return output, critic
```

<!-- CHECKPOINT -->
```bash
python checkpoint_runner.py SK03b-CP01
python checkpoint_runner.py SK03b-CP02
python checkpoint_runner.py SK03b-CP03
python checkpoint_runner.py SK03b-CP04
```

---

## STEP 2 — Test retrieval quality

```bash
python tests/test_retrieval_quality.py
# Must be above baseline by at least 3%
```

If below baseline — check Cohere API key first, then check Qdrant has data.

---

## SKILL 03b COMPLETE

```bash
python checkpoint_runner.py SK03b
python contract_tests.py
python drift_detector.py
```

Open SKILL_04_EXTRACTION_AGENT.md
