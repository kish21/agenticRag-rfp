"""
Retrieval Agent — LlamaIndex query engine + configurable reranker.

Pipeline:
1. Query rewriting — converts user query to document language
2. HyDE (optional) — generates hypothetical document for better retrieval
3. Dense hybrid search in Qdrant
4. Reranking — provider selected via RERANKER_PROVIDER in .env
5. Context compression — extracts relevant sentences, fixes lost-in-middle
6. Critic check
"""
import asyncio
import time
import uuid

from app.core.llm_provider import call_llm
from app.core.output_models import RetrievalOutput, RetrievedChunk
from app.core.qdrant_client import collection_name, search_dense, search_hybrid
from app.core.llamaindex_pipeline import get_dense_embedding
from app.core.reranker_provider import rerank as rerank_candidates
from app.agents.critic import critic_after_retrieval
from app.config import settings
from app.core.audit import log_retrieval


# ---------------------------------------------------------------------------
# Async internals (used by run_retrieval_agent)
# ---------------------------------------------------------------------------

async def _rewrite_query(query: str) -> str:
    messages = [
        {
            "role": "system",
            "content": (
                "Rewrite for document retrieval. Expand to formal document language.\n"
                "Return ONLY the rewritten query, nothing else.\n\n"
                "Examples:\n"
                'User: "do they have ISO cert?" → '
                '"ISO 27001 information security management certification current valid holder accredited"\n'
                'User: "what are their SLAs?" → '
                '"service level agreement SLA response time resolution time uptime guarantee availability percentage"\n'
                'User: "how much does it cost?" → '
                '"total contract value pricing annual fee commercial proposal cost breakdown invoicing"'
            ),
        },
        {"role": "user", "content": query},
    ]
    result = await call_llm(messages, temperature=0.0)
    return result.strip() or query


async def _generate_hyde_document(query: str, doc_type: str = "vendor_response") -> str:
    templates = settings.platform.hyde_templates
    template = templates.get(doc_type) or templates.get("vendor_response", "")
    messages = [
        {"role": "system", "content": template},
        {"role": "user", "content": query},
    ]
    result = await call_llm(messages, temperature=0.1)
    return result.strip()


async def _compress_context(query: str, chunks: list[dict]) -> list[dict]:
    if len(chunks) <= 1:
        return chunks

    compressed = []
    for chunk in chunks:
        try:
            messages = [
                {
                    "role": "system",
                    "content": (
                        "Extract only the sentences directly relevant to the query. "
                        "Return just the relevant sentences, no preamble."
                    ),
                },
                {"role": "user", "content": f"Query: {query}\n\nText: {chunk['text'][:800]}"},
            ]
            text = (await call_llm(messages, temperature=0.0)).strip()
            if len(text) > 20:
                copy = chunk.copy()
                copy["text"] = text
                copy["original_text"] = chunk["text"]
                compressed.append(copy)
            else:
                compressed.append(chunk)
        except Exception:
            compressed.append(chunk)

    # Lost-in-middle fix: best chunk first, second-best chunk last
    if len(compressed) >= 3:
        best, second, *middle = compressed
        return [best] + middle + [second]

    return compressed


# ---------------------------------------------------------------------------
# Sync public API (importable directly by checkpoint tests and callers)
# ---------------------------------------------------------------------------

def rewrite_query(query: str) -> str:
    return asyncio.run(_rewrite_query(query))


def generate_hyde_document(query: str, doc_type: str = "vendor_response") -> str:
    return asyncio.run(_generate_hyde_document(query, doc_type))


def compress_context(query: str, chunks: list[dict]) -> list[dict]:
    return asyncio.run(_compress_context(query, chunks))


def is_answer_bearing(query: str, text: str) -> bool:
    query_words = {w.lower() for w in query.split() if len(w) > 4}
    text_words = {w.lower() for w in text.split() if len(w) > 4}
    return len(query_words & text_words) >= 2


# ---------------------------------------------------------------------------
# Main async pipeline
# ---------------------------------------------------------------------------

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
    section_type_filter: str = None,
    org_settings=None,
    run_id: str | None = None,
    criterion_id: str | None = None,
) -> tuple[RetrievalOutput, object]:
    query_id = str(uuid.uuid4())
    hyde_used = False
    use_hybrid_search = False
    _t0 = time.monotonic()

    # Apply org_settings overrides when provided
    if org_settings is not None:
        use_hyde = org_settings.use_hyde
        use_rewriting = org_settings.use_query_rewriting
        n_candidates = org_settings.retrieval_top_k
        n_final = org_settings.rerank_top_n
        use_hybrid_search = org_settings.use_hybrid_search

    # Step 1: Query intelligence — track retrieval_text for sparse embedding
    if use_hyde:
        hyp_doc = await _generate_hyde_document(query, "vendor_response")
        retrieval_vector = get_dense_embedding(hyp_doc)
        retrieval_text = hyp_doc          # HyDE doc used for both dense + sparse
        rewritten_query = f"[HyDE] {hyp_doc[:100]}"
        hyde_used = True
    elif use_rewriting:
        rewritten = await _rewrite_query(query)
        retrieval_vector = get_dense_embedding(rewritten)
        retrieval_text = rewritten
        rewritten_query = rewritten
    else:
        retrieval_vector = get_dense_embedding(query)
        retrieval_text = query
        rewritten_query = query

    # Step 2: Retrieval — hybrid (dense+sparse RRF) or dense-only
    coll = collection_name(org_id, vendor_id)
    if use_hybrid_search:
        raw_results = search_hybrid(
            collection=coll,
            query_text=retrieval_text,
            org_id=org_id,
            vendor_id=vendor_id,
            limit=n_candidates,
            dense_vector=retrieval_vector,
        )
    else:
        raw_results = search_dense(
            collection=coll,
            query_vector=retrieval_vector,
            org_id=org_id,
            vendor_id=vendor_id,
            limit=n_candidates,
            section_type_filter=section_type_filter,
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
            warnings=["No chunks found in collection"],
        )
        log_retrieval(
            org_id=org_id, vendor_id=vendor_id, run_id=run_id, criterion_id=criterion_id,
            query_text=query, rewritten_query=rewritten_query, retrieval_strategy="dense",
            chunks=[], timing_ms=int((time.monotonic() - _t0) * 1000),
        )
        return output, critic_after_retrieval(output, is_mandatory_check)

    # Step 3: Cohere Rerank
    candidates = [
        {"text": r["text"], "score": r["score"], "payload": r["payload"]}
        for r in raw_results
    ]
    import asyncio
    reranked = await asyncio.get_event_loop().run_in_executor(
        None,
        lambda: rerank_candidates(
            query, candidates, top_n=n_final,
            provider=org_settings.reranker_provider if org_settings else None,
        )
    )

    # Step 4: Lost-in-middle reorder (best first, second-best last)
    # Context compression is intentionally skipped: compressing chunk text
    # causes the extraction critic's verbatim grounding check to fail because
    # the LLM produces quotes from the original text which no longer appear
    # in the rewritten/paraphrased version, blocking all fact saves.
    if len(reranked) >= 3:
        best, second, *middle = reranked
        reranked = [best] + middle + [second]

    # Step 5: Build typed output
    chunks = []
    for item in reranked:
        payload = item.get("payload", {})
        chunks.append(
            RetrievedChunk(
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
                is_answer_bearing=is_answer_bearing(query, item["text"]),
            )
        )

    avg_score = sum(c.final_score for c in chunks) / len(chunks) if chunks else 0.0

    mode = "hybrid" if use_hybrid_search else "dense"
    if hyde_used:
        mode += "+hyde"
    retrieval_strategy = f"{mode}+rerank"

    output = RetrievalOutput(
        query_id=query_id,
        original_query=query,
        rewritten_query=rewritten_query,
        hyde_query_used=hyde_used,
        retrieval_strategy=retrieval_strategy,
        chunks=chunks,
        total_candidates_before_rerank=len(raw_results),
        confidence=round(min(1.0, avg_score), 3),
        empty_retrieval=len(chunks) == 0,
        warnings=[],
    )

    log_retrieval(
        org_id=org_id, vendor_id=vendor_id, run_id=run_id, criterion_id=criterion_id,
        query_text=query, rewritten_query=rewritten_query,
        retrieval_strategy=retrieval_strategy, chunks=chunks,
        scores={"avg": round(avg_score, 3), "n_candidates": len(raw_results)},
        timing_ms=int((time.monotonic() - _t0) * 1000),
    )
    return output, critic_after_retrieval(output, is_mandatory_check)
