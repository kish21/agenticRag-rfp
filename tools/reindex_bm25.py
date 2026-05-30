"""
Rebuild existing Qdrant collections under the real-BM25 sparse scheme (P1.12).

Why this is needed
------------------
Collections created before this change have:
  * sparse vectors built from MD5-hashed term frequency (100k buckets, no IDF), and
  * NO `modifier=IDF` on the sparse vector config.

A live Qdrant cannot retro-fit the IDF modifier onto an existing sparse vector,
and the stored sparse values are the wrong representation anyway. So for each
collection we:
  1. scroll every point, keeping its dense vector + payload,
  2. recompute the sparse vector from `payload["text"]` with the new
     fastembed BM25 document embedding,
  3. recreate the collection with `create_collection()` (now modifier=IDF),
  4. re-upsert every point (dense preserved, sparse rebuilt, payload intact).

Dense vectors are preserved, so no re-embedding cost and no provider calls.

Usage
-----
    python tools/reindex_bm25.py --dry-run                 # report only, no writes
    python tools/reindex_bm25.py                           # reindex ALL prefixed collections
    python tools/reindex_bm25.py --collection <name>       # one collection
    python tools/reindex_bm25.py --yes                     # skip the confirmation prompt

This is a destructive recreate per collection — run during a maintenance window.
"""
from __future__ import annotations

import argparse
import sys

from qdrant_client import models as qm

from app.config import settings
from app.retrieval.qdrant import get_qdrant_client, create_collection
from app.retrieval.pipeline import get_sparse_document_embedding

_SCROLL_BATCH = 256
_UPSERT_BATCH = 128


def _target_collections(client, only: str | None) -> list[str]:
    names = [c.name for c in client.get_collections().collections]
    if only:
        if only not in names:
            sys.exit(f"Collection '{only}' not found. Available: {names}")
        return [only]
    prefix = settings.qdrant_collection_prefix.replace("-", "_").lower()
    return [n for n in names if n.startswith(prefix)]


def _scroll_all(client, name: str) -> list[qm.Record]:
    records: list[qm.Record] = []
    offset = None
    while True:
        batch, offset = client.scroll(
            collection_name=name,
            limit=_SCROLL_BATCH,
            with_payload=True,
            with_vectors=True,
            offset=offset,
        )
        records.extend(batch)
        if offset is None:
            break
    return records


def _dense_of(record: qm.Record) -> list[float] | None:
    vec = record.vector
    if isinstance(vec, dict):
        return vec.get("dense")
    return None  # unnamed/legacy layout — cannot safely preserve


def reindex_collection(client, name: str, dry_run: bool) -> tuple[int, int]:
    """Returns (points_seen, points_reindexed)."""
    records = _scroll_all(client, name)
    rebuildable = [
        r for r in records
        if _dense_of(r) is not None and (r.payload or {}).get("text")
    ]
    skipped = len(records) - len(rebuildable)
    print(f"  {name}: {len(records)} points "
          f"({len(rebuildable)} rebuildable, {skipped} skipped — missing dense or text)")

    if dry_run or not rebuildable:
        return len(records), 0

    dense_size = len(_dense_of(rebuildable[0]))

    # Recreate with the new sparse config (modifier=IDF).
    client.delete_collection(name)
    create_collection(name, vector_size=dense_size, client=client)

    reindexed = 0
    buf: list[qm.PointStruct] = []
    for r in rebuildable:
        idx, val = get_sparse_document_embedding(r.payload["text"])
        buf.append(qm.PointStruct(
            id=r.id,
            vector={"dense": _dense_of(r), "sparse": {"indices": idx, "values": val}},
            payload=r.payload,
        ))
        if len(buf) >= _UPSERT_BATCH:
            client.upsert(collection_name=name, points=buf)
            reindexed += len(buf)
            buf = []
    if buf:
        client.upsert(collection_name=name, points=buf)
        reindexed += len(buf)

    print(f"  {name}: reindexed {reindexed} points")
    return len(records), reindexed


def main() -> None:
    parser = argparse.ArgumentParser(description="Rebuild Qdrant collections with real BM25 sparse vectors.")
    parser.add_argument("--collection", help="Reindex only this collection (default: all prefixed).")
    parser.add_argument("--dry-run", action="store_true", help="Report counts without modifying anything.")
    parser.add_argument("--yes", action="store_true", help="Skip the destructive-recreate confirmation.")
    args = parser.parse_args()

    client = get_qdrant_client()
    collections = _target_collections(client, args.collection)
    if not collections:
        print("No matching collections found.")
        return

    print(f"{'DRY RUN — ' if args.dry_run else ''}Target collections ({len(collections)}):")
    for n in collections:
        print(f"  - {n}")

    if not args.dry_run and not args.yes:
        reply = input("\nThis DELETES and recreates each collection above. Proceed? [y/N] ").strip().lower()
        if reply != "y":
            print("Aborted.")
            return

    total_seen = total_reindexed = 0
    for name in collections:
        seen, done = reindex_collection(client, name, args.dry_run)
        total_seen += seen
        total_reindexed += done

    verb = "would reindex" if args.dry_run else "reindexed"
    print(f"\nDone. {total_seen} points seen, {verb} {total_reindexed}.")


if __name__ == "__main__":
    main()
