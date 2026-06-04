"""
E215 — one Qdrant collection per org (was one per vendor).

These tests pin the new contract:
  - naming is per-ORG (vendor is no longer part of the collection name);
  - two vendors of one org share ONE collection, yet a retrieval scoped to
    vendor A returns ZERO of vendor B's chunks (the within-org isolation that
    used to be physical is now the org_id+vendor_id payload filter — this is the
    security-critical property and must hold);
  - delete_vendor_data removes only the target vendor's points and leaves the
    other vendor (and the collection) intact.

Runs fully offline against an in-memory Qdrant exercising the real production
code paths (search_dense, delete_vendor_data, create_collection).
"""
import pytest

pytest.importorskip("qdrant_client")

from qdrant_client import QdrantClient
from qdrant_client.models import PointStruct

import app.retrieval.qdrant as q
from app.retrieval.qdrant import (
    org_collection_name,
    create_collection,
    search_dense,
    delete_vendor_data,
)

_ORG = "org-meridian"
_DIM = 4
_DENSE = [0.1, 0.1, 0.1, 0.1]  # constant → the FILTER, not similarity, decides


def _seed_two_vendors(client: QdrantClient, name: str) -> None:
    create_collection(name, vector_size=_DIM, client=client)
    points = [
        PointStruct(id=1, vector={"dense": _DENSE},
                    payload={"chunk_id": "a1", "text": "alpha doc",
                             "org_id": _ORG, "vendor_id": "vendor-alpha"}),
        PointStruct(id=2, vector={"dense": _DENSE},
                    payload={"chunk_id": "a2", "text": "alpha doc 2",
                             "org_id": _ORG, "vendor_id": "vendor-alpha"}),
        PointStruct(id=3, vector={"dense": _DENSE},
                    payload={"chunk_id": "b1", "text": "beta doc",
                             "org_id": _ORG, "vendor_id": "vendor-beta"}),
    ]
    client.upsert(collection_name=name, points=points)


def test_org_collection_name_is_per_org():
    # vendor is no longer part of the name → both vendors map to one collection
    assert org_collection_name(_ORG) == org_collection_name(_ORG)
    # different orgs stay physically separate (the tenant boundary)
    assert org_collection_name("org-a") != org_collection_name("org-b")
    # no per-vendor suffix
    name = org_collection_name(_ORG)
    assert name.endswith("meridian")


def test_two_vendors_share_one_collection_but_search_isolates(monkeypatch):
    client = QdrantClient(":memory:")
    name = org_collection_name(_ORG)
    _seed_two_vendors(client, name)
    monkeypatch.setattr(q, "get_qdrant_client", lambda: client)

    # Search scoped to vendor-alpha inside the SHARED org collection
    results = search_dense(
        collection=name, query_vector=_DENSE,
        org_id=_ORG, vendor_id="vendor-alpha", limit=10,
    )
    returned_chunks = {r["chunk_id"] for r in results}
    # alpha's two chunks returned, beta's chunk NEVER leaks across vendors
    assert returned_chunks == {"a1", "a2"}, returned_chunks
    assert "b1" not in returned_chunks


def test_delete_vendor_data_removes_only_target_vendor(monkeypatch):
    client = QdrantClient(":memory:")
    name = org_collection_name(_ORG)
    _seed_two_vendors(client, name)
    monkeypatch.setattr(q, "get_qdrant_client", lambda: client)

    removed = delete_vendor_data(_ORG, "vendor-alpha")
    assert removed == 2

    # beta survives in the same collection; collection still exists
    surviving = search_dense(
        collection=name, query_vector=_DENSE,
        org_id=_ORG, vendor_id="vendor-beta", limit=10,
    )
    assert {r["chunk_id"] for r in surviving} == {"b1"}
    # alpha is gone
    gone = search_dense(
        collection=name, query_vector=_DENSE,
        org_id=_ORG, vendor_id="vendor-alpha", limit=10,
    )
    assert gone == []


def test_delete_vendor_data_missing_collection_returns_zero(monkeypatch):
    client = QdrantClient(":memory:")
    monkeypatch.setattr(q, "get_qdrant_client", lambda: client)
    # nothing ingested → no collection → no-op, not an error
    assert delete_vendor_data("org-nope", "vendor-x") == 0
