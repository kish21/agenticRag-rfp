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
