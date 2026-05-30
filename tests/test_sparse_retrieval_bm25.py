"""
Acceptance tests for real BM25 sparse retrieval (BACKLOG P1.12).

Before this work the "sparse vector" was MD5-hashed term frequency in 100k
buckets with no IDF — it collided distinct procurement vocabulary and could not
tell "ISO 27001" from "ISO 9001" or "£10M" from "£1M". These tests pin the
behaviour that matters for procurement: an exact-term query must rank the chunk
that actually contains that term above near-variants and paraphrases.

They run fully offline against an in-memory Qdrant, exercising the real
production code paths:
  - app.retrieval.qdrant.create_collection  (sparse modifier=IDF)
  - app.retrieval.pipeline.get_sparse_document_embedding  (index side)
  - app.retrieval.pipeline.get_sparse_query_embedding     (query side)

Dense vectors are held constant so the *sparse* (BM25) layer alone decides the
ranking — that is the layer under test.
"""
import pytest

pytest.importorskip("qdrant_client")
pytest.importorskip("fastembed")

from qdrant_client import QdrantClient
from qdrant_client import models as qm

from app.retrieval.pipeline import (
    get_sparse_document_embedding,
    get_sparse_query_embedding,
)
from app.retrieval.qdrant import create_collection

_CONST_DENSE = [0.1, 0.1]


@pytest.fixture(scope="module")
def bm25_ready():
    """Skip (don't fail) if the fastembed BM25 model can't be fetched — e.g. a
    CI runner with no network to huggingface.co. When the model is present
    (local dev + most CI) the tests run for real."""
    try:
        get_sparse_query_embedding("warmup query")
    except Exception as exc:  # noqa: BLE001 — any load/download failure → skip
        pytest.skip(f"fastembed Qdrant/bm25 model unavailable: {exc}")


def _index(docs: dict[str, str]) -> QdrantClient:
    """Build an in-memory collection (real create_collection → modifier=IDF) and
    index each doc with its BM25 document sparse vector + a constant dense vec."""
    client = QdrantClient(":memory:")
    create_collection("acc", vector_size=len(_CONST_DENSE), client=client)
    points = []
    for i, (key, text) in enumerate(docs.items(), start=1):
        idx, val = get_sparse_document_embedding(text)
        points.append(
            qm.PointStruct(
                id=i,
                vector={"dense": _CONST_DENSE, "sparse": {"indices": idx, "values": val}},
                payload={"key": key, "text": text},
            )
        )
    client.upsert("acc", points)
    return client


def _sparse_ranking(client: QdrantClient, query: str, k: int = 10) -> list[str]:
    """Return the ranked list of doc keys for a sparse (BM25) query."""
    idx, val = get_sparse_query_embedding(query)
    res = client.query_points(
        "acc",
        query=qm.SparseVector(indices=idx, values=val),
        using="sparse",
        limit=k,
        with_payload=True,
    ).points
    return [p.payload["key"] for p in res]


def _score(client: QdrantClient, query: str, key: str) -> float:
    idx, val = get_sparse_query_embedding(query)
    res = client.query_points(
        "acc",
        query=qm.SparseVector(indices=idx, values=val),
        using="sparse",
        limit=50,
        with_payload=True,
    ).points
    for p in res:
        if p.payload["key"] == key:
            return p.score
    return 0.0


def test_exact_iso_27001_does_not_surface_iso_9001(bm25_ready):
    """Query "ISO 27001" must rank the 27001 chunk first and strictly above the
    ISO 9001 (and other ISO-family) chunks — the old hash-collision sparse could
    not distinguish these certification numbers."""
    client = _index({
        "iso_27001": "The supplier maintains ISO 27001 certification for information security management",
        "iso_9001": "The supplier maintains ISO 9001 certification for quality management systems",
        "iso_14001": "The supplier maintains ISO 14001 certification for environmental management",
        "iso_45001": "The supplier maintains ISO 45001 certification for occupational health and safety",
        "insurance": "Public liability insurance is maintained at £10M per occurrence",
        "history": "Company background, history and an about-us overview section",
    })

    ranking = _sparse_ranking(client, "ISO 27001")

    assert ranking[0] == "iso_27001", f"expected ISO 27001 chunk first, got {ranking}"
    # The wrong-number variant must not tie or beat the correct one.
    assert _score(client, "ISO 27001", "iso_27001") > _score(client, "ISO 27001", "iso_9001")
    assert ranking.index("iso_27001") < ranking.index("iso_9001")


def test_exact_currency_amount_does_not_surface_wrong_amount(bm25_ready):
    """Query "£10M public liability" must rank the £10M chunk above the £1M
    chunk — currency figures must be distinct tokens, not stripped/collided."""
    client = _index({
        "liability_10m": "Public liability insurance is held at the level of £10M per claim",
        "liability_1m": "Public liability insurance is held at the level of £1M per claim",
        "iso_27001": "The supplier maintains ISO 27001 certification for information security",
        "history": "Company background, history and an about-us overview section",
    })

    ranking = _sparse_ranking(client, "£10M public liability")

    assert ranking[0] == "liability_10m", f"expected £10M chunk first, got {ranking}"
    assert _score(client, "£10M public liability", "liability_10m") > _score(
        client, "£10M public liability", "liability_1m"
    )
    assert ranking.index("liability_10m") < ranking.index("liability_1m")


def test_exact_sla_clause_ranks_above_paraphrase(bm25_ready):
    """An exact SLA clause query must rank the chunk with the literal clause
    above a semantically-similar paraphrase — the lexical signal's whole job."""
    client = _index({
        "sla_exact": "We guarantee 99.9% uptime with a 4-hour priority incident response time",
        "sla_paraphrase": "Our service availability is high and we aim to respond to incidents promptly",
        "iso_27001": "The supplier maintains ISO 27001 certification for information security",
        "insurance": "Public liability insurance is maintained at £10M per occurrence",
    })

    ranking = _sparse_ranking(client, "99.9% uptime 4-hour incident response")

    assert ranking[0] == "sla_exact", f"expected exact SLA clause first, got {ranking}"
    assert _score(client, "99.9% uptime 4-hour incident response", "sla_exact") > _score(
        client, "99.9% uptime 4-hour incident response", "sla_paraphrase"
    )
