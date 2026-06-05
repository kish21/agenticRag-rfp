from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance, VectorParams, SparseVectorParams,
    PointStruct, Filter, FieldCondition, MatchValue,
    SparseIndexParams, Modifier, FilterSelector
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


def org_collection_name(org_id: str) -> str:
    """
    Naming convention: {prefix}_{org_id}  — one collection per org (tenant).

    The org collection is the physical cross-tenant boundary. Vendor scoping
    WITHIN an org is enforced by the mandatory `org_id` + `vendor_id` payload
    filters applied on every query (see search_dense / search_hybrid), not by a
    separate collection per vendor. See docs/dev/E215_QDRANT_PER_ORG_COLLECTION.md.
    """
    prefix = settings.qdrant_collection_prefix
    return f"{prefix}_{org_id}".replace("-", "_").lower()


def rfp_collection_name(org_id: str, rfp_id: str) -> str:
    prefix = settings.qdrant_collection_prefix
    return f"{prefix}_{org_id}_rfp_{rfp_id}".replace("-", "_").lower()


def _tenant_must(org_id: str, vendor_id: str) -> list[FieldCondition]:
    """
    The mandatory tenant-isolation predicate, single-sourced. Since E215 moved
    to one collection per org, vendor scoping lives ENTIRELY in this payload
    filter — every read/delete that touches vendor data must use it, so it is
    defined once here rather than re-built per call site.
    """
    return [
        FieldCondition(key="org_id", match=MatchValue(value=org_id)),
        FieldCondition(key="vendor_id", match=MatchValue(value=vendor_id)),
    ]


def create_collection(name: str, vector_size: int | None = None, client: QdrantClient | None = None):
    """
    Creates a Qdrant collection with both dense and sparse vectors.
    Dense: for semantic similarity search (OpenAI embeddings)
    Sparse: real BM25 keyword search — sparse vectors carry length-normalised
            term frequencies (from fastembed Qdrant/bm25) and `modifier=IDF`
            makes Qdrant apply the corpus IDF server-side, completing BM25.

    `client` is injectable so tests can pass an in-memory QdrantClient.
    """
    from app.providers.embedding import get_embedding_dimensions
    if vector_size is None:
        vector_size = get_embedding_dimensions()

    if client is None:
        client = get_qdrant_client()

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
                index=SparseIndexParams(on_disk=False),
                modifier=Modifier.IDF,
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
            id=chunk_id,
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

    must_conditions = _tenant_must(org_id, vendor_id)

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


def search_hybrid(
    collection: str,
    query_text: str,
    org_id: str,
    vendor_id: str,
    limit: int,
    dense_vector: list[float] | None = None,
    section_type_filter: str = None,
) -> list[dict]:
    """
    Hybrid retrieval combining dense semantic and sparse lexical signals
    via Reciprocal Rank Fusion (RRF).

    If dense_vector is provided (e.g. HyDE already produced one) it is
    used directly; otherwise query_text is embedded fresh. Sparse vector
    is always computed from query_text so lexical signals are grounded
    in the literal query, not the hypothetical document.

    Returns the same dict shape as search_dense so callers are
    interchangeable.
    """
    from qdrant_client import models as qm
    from app.providers.embedding import embed_text
    from app.retrieval.pipeline import get_sparse_query_embedding
    from app.config import settings

    cfg = settings.platform.retrieval
    client = get_qdrant_client()

    dense_vec = dense_vector if dense_vector is not None else embed_text(query_text)
    sparse_indices, sparse_values = get_sparse_query_embedding(query_text)

    must_conditions = _tenant_must(org_id, vendor_id)
    if section_type_filter:
        must_conditions.append(
            FieldCondition(
                key="section_type",
                match=MatchValue(value=section_type_filter)
            )
        )
    qfilter = Filter(must=must_conditions)

    prefetch = [
        qm.Prefetch(
            query=dense_vec,
            using=cfg.dense_vector_name,
            limit=limit * 2,
            filter=qfilter,
        ),
    ]
    # A query of only stopwords yields an empty sparse vector — skip the sparse
    # prefetch entirely rather than sending an empty SparseVector (which would
    # contribute nothing and, on some Qdrant versions, error).
    if sparse_indices:
        prefetch.append(
            qm.Prefetch(
                query=qm.SparseVector(
                    indices=sparse_indices,
                    values=sparse_values,
                ),
                using=cfg.sparse_vector_name,
                limit=limit * 2,
                filter=qfilter,
            )
        )

    result = client.query_points(
        collection_name=collection,
        prefetch=prefetch,
        query=qm.FusionQuery(fusion=qm.Fusion.RRF),
        limit=limit,
        with_payload=True,
        with_vectors=False,
    )

    return [
        {
            "chunk_id": p.payload.get("chunk_id"),
            "text": p.payload.get("text", ""),
            "score": p.score,
            "payload": p.payload,
        }
        for p in result.points
    ]


def delete_vendor_data(org_id: str, vendor_id: str) -> int:
    """
    Deletes one vendor's points from the org collection (GDPR / data retention),
    WITHOUT dropping the collection — other vendors of the same org share it.

    Returns the number of points matched for deletion (0 if the collection does
    not exist). Isolation: filters on org_id AND vendor_id so it can never touch
    another tenant's data.
    """
    client = get_qdrant_client()
    name = org_collection_name(org_id)
    existing = [c.name for c in client.get_collections().collections]
    if name not in existing:
        return 0

    selector = Filter(must=_tenant_must(org_id, vendor_id))
    # count before delete so callers/audit can see how much was removed
    matched = client.count(
        collection_name=name, count_filter=selector, exact=True
    ).count
    client.delete(
        collection_name=name,
        points_selector=FilterSelector(filter=selector),
    )
    return matched


def _delete_by_filter_and_maybe_drop(
    org_id: str, must: list[FieldCondition]
) -> tuple[int, bool]:
    """
    Delete the points of the org collection matching `must`, then drop the
    collection if it is now empty. Returns (points_matched, collection_dropped);
    (0, False) if the collection does not exist.

    Single-sources the count -> delete-by-filter -> drop-if-empty sequence shared
    by delete_setup_data (org+setup filter) and delete_org_data (org-only) so a
    change to the drop semantics is made once (mirrors _tenant_must on the read
    path). Keeps the Qdrant SDK confined to this module (ADR-001).
    """
    client = get_qdrant_client()
    name = org_collection_name(org_id)
    existing = [c.name for c in client.get_collections().collections]
    if name not in existing:
        return 0, False

    selector = Filter(must=must)
    matched = client.count(
        collection_name=name, count_filter=selector, exact=True
    ).count
    client.delete(
        collection_name=name,
        points_selector=FilterSelector(filter=selector),
    )
    dropped = False
    if client.count(collection_name=name, exact=True).count == 0:
        client.delete_collection(name)
        dropped = True
    return matched, dropped


def delete_setup_data(org_id: str, setup_id: str) -> tuple[int, bool]:
    """
    Deletes the points of ONE evaluation setup from the org collection, then
    drops the collection only if it is now empty (i.e. that was the org's last
    setup). Returns (points_matched, collection_dropped); (0, False) if the
    collection does not exist.

    This is the precise retention path the cleanup job uses (BACKLOG P2.27): a
    point is stamped with `setup_id` at ingestion, so an expired setup removes
    only its OWN vectors and leaves the org's other, still-live setups intact —
    unlike delete_org_data, which wipes the whole tenant. Filtering on org_id
    AND setup_id keeps the tenant boundary explicit (defence in depth).

    NOTE: points ingested before P2.27 carry no `setup_id` and so are not matched
    here (they are pre-fix disposable test data, bounded by 90-day retention).
    """
    return _delete_by_filter_and_maybe_drop(org_id, [
        FieldCondition(key="org_id", match=MatchValue(value=org_id)),
        FieldCondition(key="setup_id", match=MatchValue(value=setup_id)),
    ])


def delete_org_data(org_id: str) -> tuple[int, bool]:
    """
    Deletes ALL of an org's points from its collection (whole-tenant GDPR
    erasure — "delete this customer"), then drops the collection if it is now
    empty. The retention/cleanup job no longer uses this; it deletes per-setup
    via delete_setup_data (P2.27) so one expired setup does not wipe the tenant.

    Returns (points_matched, collection_dropped). 0 / False if the collection
    does not exist. Keeps the Qdrant SDK confined to this module (ADR-001:
    app/retrieval/qdrant.py wraps all Qdrant operations).
    """
    return _delete_by_filter_and_maybe_drop(org_id, [
        FieldCondition(key="org_id", match=MatchValue(value=org_id)),
    ])
