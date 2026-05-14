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


def create_collection(name: str, vector_size: int | None = None):
    """
    Creates a Qdrant collection with both dense and sparse vectors.
    Dense: for semantic similarity search (OpenAI embeddings)
    Sparse: for BM25 keyword search
    """
    from app.core.embedding_provider import get_embedding_dimensions
    if vector_size is None:
        vector_size = get_embedding_dimensions()

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


def search_hybrid(
    collection: str,
    query_text: str,
    org_id: str,
    vendor_id: str,
    limit: int,
    dense_vector: list[float] | None = None,
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
    from app.core.embedding_provider import embed_text
    from app.core.llamaindex_pipeline import get_sparse_embedding
    from app.config import settings

    cfg = settings.platform.retrieval
    client = get_qdrant_client()

    dense_vec = dense_vector if dense_vector is not None else embed_text(query_text)
    sparse_indices, sparse_values = get_sparse_embedding(query_text)

    must_conditions = [
        FieldCondition(key="org_id", match=MatchValue(value=org_id)),
        FieldCondition(key="vendor_id", match=MatchValue(value=vendor_id)),
    ]
    qfilter = Filter(must=must_conditions)

    prefetch = [
        qm.Prefetch(
            query=dense_vec,
            using=cfg.dense_vector_name,
            limit=limit * 2,
            filter=qfilter,
        ),
        qm.Prefetch(
            query=qm.SparseVector(
                indices=sparse_indices,
                values=sparse_values,
            ),
            using=cfg.sparse_vector_name,
            limit=limit * 2,
            filter=qfilter,
        ),
    ]

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
