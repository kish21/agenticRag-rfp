"""
P2.27 — per-setup retention precision.

Before P2.27 the cleanup job deleted at ORG granularity: one expired setup wiped
every vector the org owned, including its other still-live setups. The fix stamps
`setup_id` on each chunk payload at ingestion and deletes by `setup_id`, so an
expired setup removes only its OWN vectors and the per-org collection (E215) is
dropped only when its LAST setup goes.

These tests pin that contract end to end, fully offline:
  - delete_setup_data removes only the target setup, leaving co-tenant setups
    (and the shared collection) intact — and drops the collection only when empty;
  - ingestion stamps setup_id on the chunk payload;
  - run_cleanup calls the precise per-setup delete (never the org-coarse one) and
    removes only the expired PostgreSQL rows.

The Qdrant tests run against an in-memory client and the cleanup test against an
in-memory SQLite engine — neither touches real data (the one #215 piece that was
not live-tested because exercising it deletes data).
"""
import datetime

import pytest

pytest.importorskip("qdrant_client")

import sqlalchemy as sa
from qdrant_client import QdrantClient
from qdrant_client.models import PointStruct

import app.retrieval.qdrant as q
from app.retrieval.qdrant import (
    org_collection_name,
    create_collection,
    delete_setup_data,
    search_dense,
)

_ORG = "org-meridian"
_DIM = 4
_DENSE = [0.1, 0.1, 0.1, 0.1]


def _seed_two_setups(client: QdrantClient, name: str) -> None:
    """One org collection holding two setups: setup-A (2 pts) + setup-B (1 pt),
    all under the same vendor so only `setup_id` distinguishes them."""
    create_collection(name, vector_size=_DIM, client=client)
    points = [
        PointStruct(id=1, vector={"dense": _DENSE},
                    payload={"chunk_id": "a1", "org_id": _ORG,
                             "vendor_id": "v1", "setup_id": "setup-A"}),
        PointStruct(id=2, vector={"dense": _DENSE},
                    payload={"chunk_id": "a2", "org_id": _ORG,
                             "vendor_id": "v1", "setup_id": "setup-A"}),
        PointStruct(id=3, vector={"dense": _DENSE},
                    payload={"chunk_id": "b1", "org_id": _ORG,
                             "vendor_id": "v1", "setup_id": "setup-B"}),
    ]
    client.upsert(collection_name=name, points=points)


def test_delete_setup_data_removes_only_target_setup(monkeypatch):
    client = QdrantClient(":memory:")
    name = org_collection_name(_ORG)
    _seed_two_setups(client, name)
    monkeypatch.setattr(q, "get_qdrant_client", lambda: client)

    matched, dropped = delete_setup_data(_ORG, "setup-A")
    assert matched == 2
    # setup-B is still live → collection must NOT be dropped
    assert dropped is False
    assert name in [c.name for c in client.get_collections().collections]

    # setup-B survives; setup-A is gone (search filters by vendor, both share v1)
    surviving = {r["chunk_id"] for r in search_dense(
        collection=name, query_vector=_DENSE,
        org_id=_ORG, vendor_id="v1", limit=10)}
    assert surviving == {"b1"}, surviving


def test_delete_setup_data_drops_collection_when_last_setup(monkeypatch):
    client = QdrantClient(":memory:")
    name = org_collection_name(_ORG)
    _seed_two_setups(client, name)
    monkeypatch.setattr(q, "get_qdrant_client", lambda: client)

    delete_setup_data(_ORG, "setup-A")
    # now remove the org's LAST setup → collection should be dropped
    matched, dropped = delete_setup_data(_ORG, "setup-B")
    assert matched == 1
    assert dropped is True
    assert name not in [c.name for c in client.get_collections().collections]


def test_delete_setup_data_missing_collection_returns_zero(monkeypatch):
    client = QdrantClient(":memory:")
    monkeypatch.setattr(q, "get_qdrant_client", lambda: client)
    assert delete_setup_data("org-nope", "setup-x") == (0, False)


def test_delete_setup_data_no_match_keeps_other_setups(monkeypatch):
    """A setup_id that matches nothing (e.g. pre-P2.27 points with no setup_id)
    removes zero points and must NOT drop a non-empty collection."""
    client = QdrantClient(":memory:")
    name = org_collection_name(_ORG)
    _seed_two_setups(client, name)
    monkeypatch.setattr(q, "get_qdrant_client", lambda: client)

    matched, dropped = delete_setup_data(_ORG, "setup-does-not-exist")
    assert matched == 0
    assert dropped is False
    assert name in [c.name for c in client.get_collections().collections]


@pytest.mark.asyncio
async def test_ingestion_stamps_setup_id_on_payload(monkeypatch):
    """The real payload-build path must put the setup's id on every chunk."""
    import app.agents.ingestion as ing
    from app.schemas.schema_setup import EvaluationSetup

    setup = EvaluationSetup(
        setup_id="setup-XYZ", org_id="", department="proc", rfp_id="r1",
        rfp_confirmed=True, mandatory_checks=[], scoring_criteria=[],
        extraction_targets=[], total_weight=1.0, confirmed_by="a@b",
        source="manually_defined",
    )
    fake_chunk = {
        "chunk_id": "c1", "text": "hello world", "section_id": "s1",
        "section_title": "Intro", "section_type": "requirement_response",
        "priority": "P1", "page_number": 1,
        "dense_vector": _DENSE, "sparse_indices": [1], "sparse_values": [0.5],
    }
    captured: list[dict] = []
    monkeypatch.setattr(ing, "process_document", lambda *a, **k: [fake_chunk])
    monkeypatch.setattr(ing, "create_collection", lambda *a, **k: None)
    monkeypatch.setattr(ing, "upsert_chunk",
                        lambda **kw: captured.append(kw["payload"]))

    await ing._ingest_single_file(
        content=b"x", filename="doc.txt", vendor_id="v1",
        org_id="org1", rfp_id="r1", evaluation_setup=setup)

    assert captured, "no chunk was upserted"
    assert all(p["setup_id"] == "setup-XYZ" for p in captured)


@pytest.mark.asyncio
async def test_run_cleanup_deletes_only_expired_setups_per_setup(monkeypatch):
    """run_cleanup must call the precise per-setup delete for each expired setup
    and remove only the expired PostgreSQL rows — the fresh setup is untouched."""
    import app.jobs.cleanup as cleanup

    engine = sa.create_engine("sqlite://")  # in-memory, single connection
    with engine.begin() as conn:
        conn.execute(sa.text(
            "CREATE TABLE evaluation_setups "
            "(setup_id TEXT, org_id TEXT, created_at TIMESTAMP)"))
        old = datetime.datetime.utcnow() - datetime.timedelta(days=200)
        fresh = datetime.datetime.utcnow()
        conn.execute(
            sa.text("INSERT INTO evaluation_setups VALUES (:s, :o, :t)"),
            [
                {"s": "expired-1", "o": "orgA", "t": old},
                {"s": "expired-2", "o": "orgA", "t": old},
                {"s": "live-1", "o": "orgA", "t": fresh},
            ],
        )

    calls: list[tuple[str, str]] = []
    monkeypatch.setattr(cleanup, "delete_setup_data",
                        lambda org, sid: (calls.append((org, sid)) or (1, False)))
    monkeypatch.setattr(cleanup, "log_evaluation_run", lambda **kw: None)

    summary = await cleanup.run_cleanup(engine, retention_days=90)

    # precise: one delete call per EXPIRED setup, never an org-coarse delete
    assert sorted(calls) == [("orgA", "expired-1"), ("orgA", "expired-2")]
    assert summary["purged_setups"] == 2
    assert summary["deleted_points"] == 2
    assert summary["deleted_pg_rows"] == 2

    # the live setup row survives in PostgreSQL
    with engine.connect() as conn:
        remaining = conn.execute(
            sa.text("SELECT setup_id FROM evaluation_setups")).fetchall()
    assert [r.setup_id for r in remaining] == ["live-1"]


@pytest.mark.asyncio
async def test_run_cleanup_keeps_pg_row_when_vector_delete_fails(monkeypatch):
    """If the Qdrant delete raises (transient outage), the setup's PostgreSQL
    row must be KEPT so a future run retries it — never deleted, which would
    orphan its vectors forever. The failure is counted for observability."""
    import app.jobs.cleanup as cleanup

    engine = sa.create_engine("sqlite://")
    with engine.begin() as conn:
        conn.execute(sa.text(
            "CREATE TABLE evaluation_setups "
            "(setup_id TEXT, org_id TEXT, created_at TIMESTAMP)"))
        old = datetime.datetime.utcnow() - datetime.timedelta(days=200)
        conn.execute(
            sa.text("INSERT INTO evaluation_setups VALUES (:s, :o, :t)"),
            {"s": "expired-1", "o": "orgA", "t": old})

    def _boom(org, sid):
        raise RuntimeError("qdrant unreachable")

    monkeypatch.setattr(cleanup, "delete_setup_data", _boom)
    monkeypatch.setattr(cleanup, "log_evaluation_run", lambda **kw: None)

    summary = await cleanup.run_cleanup(engine, retention_days=90)

    assert summary["failed_setups"] == 1
    assert summary["purged_setups"] == 0
    assert summary["deleted_pg_rows"] == 0
    # the row is still there to be retried next run
    with engine.connect() as conn:
        remaining = conn.execute(
            sa.text("SELECT setup_id FROM evaluation_setups")).fetchall()
    assert [r.setup_id for r in remaining] == ["expired-1"]
