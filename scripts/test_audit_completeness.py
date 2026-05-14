#!/usr/bin/env python3
"""
Audit completeness CI check — P0.9

Verifies that critical agent events carry run_id in audit_log.
The regression this catches: a new code path calls audit() without threading
run_id through, silently creating orphaned events that cannot be queried per-run.

Tests:
  1. audit() round-trip: events written with run_id are readable back by run_id
  2. retrieval_critic run_id threading: _retrieve_top_k_for_check emits
     retrieval_critic.verdict WITH the run_id it receives
  3. extraction_critic run_id threading: run_extraction_agent emits
     extraction_critic.verdict WITH the run_id it receives
  4. No NULL run_ids: for the test org, no critic events have run_id=NULL

Run with:
    python scripts/test_audit_completeness.py
"""
import asyncio
import json
import sys
import uuid
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

import sqlalchemy as sa
from app.db.fact_store import get_engine

PASS = "\033[92mPASS\033[0m"
FAIL = "\033[91mFAIL\033[0m"


# ── DB helpers ────────────────────────────────────────────────────────────────

def _seed_run(run_id: str, org_id: str) -> None:
    """Insert a minimal evaluation_runs row so audit_log FK is satisfied."""
    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(
            sa.text("""
                INSERT INTO evaluation_runs (run_id, org_id, rfp_id, status)
                VALUES (CAST(:run_id AS uuid), CAST(:org_id AS uuid), :rfp_id, 'running')
                ON CONFLICT (run_id) DO NOTHING
            """),
            {"run_id": run_id, "org_id": org_id, "rfp_id": f"test-rfp-{run_id[:8]}"},
        )


def _query_audit(run_id: str, event_type: str | None = None) -> list[dict]:
    engine = get_engine()
    with engine.connect() as conn:
        where = "run_id = CAST(:run_id AS uuid)"
        params: dict = {"run_id": run_id}
        if event_type:
            where += " AND event_type = :event_type"
            params["event_type"] = event_type
        rows = conn.execute(
            sa.text(f"SELECT run_id, event_type, actor, detail FROM audit_log WHERE {where}"),
            params,
        ).fetchall()
    return [{"run_id": str(r[0]), "event_type": r[1], "actor": r[2], "detail": r[3]} for r in rows]


def _count_null_run_id(org_id: str, event_type: str) -> int:
    engine = get_engine()
    with engine.connect() as conn:
        row = conn.execute(
            sa.text(
                "SELECT COUNT(*) FROM audit_log "
                "WHERE org_id = CAST(:org_id AS uuid) AND event_type = :event_type AND run_id IS NULL"
            ),
            {"org_id": org_id, "event_type": event_type},
        ).fetchone()
    return row[0] if row else 0


# ── Tests ─────────────────────────────────────────────────────────────────────

def test_audit_round_trip() -> None:
    """audit() writes event with run_id; reading back by run_id returns it."""
    from app.core.audit import audit

    run_id = str(uuid.uuid4())
    org_id = str(uuid.uuid4())
    _seed_run(run_id, org_id)

    audit(org_id=org_id, run_id=run_id, event_type="run.created",
          actor="ci-test", detail={"test": "round-trip"})

    rows = _query_audit(run_id, "run.created")
    assert len(rows) >= 1, "Expected at least 1 run.created row for test run_id"
    assert rows[0]["run_id"] == run_id, f"run_id mismatch: {rows[0]['run_id']}"
    print(f"  {PASS}  test_audit_round_trip")


async def test_retrieval_critic_threads_run_id() -> None:
    """_retrieve_top_k_for_check emits retrieval_critic.verdict WITH run_id."""
    from app.agents.evaluation import _retrieve_top_k_for_check

    run_id = str(uuid.uuid4())
    org_id = str(uuid.uuid4())
    _seed_run(run_id, org_id)

    mock_chunk = MagicMock()
    mock_chunk.chunk_id = "c-test"
    mock_chunk.text = "ISO 27001 certified by BSI Group, cert IS 123456, valid until March 2027."
    mock_chunk.section_title = "Security"
    mock_chunk.section_type = "requirement_response"
    mock_chunk.filename = "test.pdf"
    mock_chunk.page_number = 1
    mock_chunk.vendor_id = "vendor-test"
    mock_chunk.vector_similarity_score = 0.9
    mock_chunk.rerank_score = 0.9
    mock_chunk.final_score = 0.9
    mock_chunk.is_answer_bearing = True
    mock_chunk.qdrant_point_id = str(uuid.uuid4())

    mock_output = MagicMock()
    mock_output.chunks = [mock_chunk]
    mock_output.empty_retrieval = False

    mock_verdict = MagicMock()
    mock_verdict.adequate = True
    mock_verdict.confidence = 0.95
    mock_verdict.missing = ""

    # run_retrieval_agent and judge_retrieval are imported inside the function,
    # so patch at their definition modules, not at evaluation module level.
    with patch(
        "app.agents.retrieval.run_retrieval_agent",
        new_callable=AsyncMock,
        return_value=(mock_output, MagicMock()),
    ), patch(
        "app.core.retrieval_critic.judge_retrieval",
        new_callable=AsyncMock,
        return_value=mock_verdict,
    ):
        await _retrieve_top_k_for_check(
            check_name="Information Security Certification",
            vendor_id="vendor-test",
            org_id=org_id,
            run_id=run_id,
        )

    rows = _query_audit(run_id, "retrieval_critic.verdict")
    assert len(rows) >= 1, (
        "Expected retrieval_critic.verdict row with run_id in audit_log — "
        "run_id is not being threaded through _retrieve_top_k_for_check"
    )
    assert rows[0]["run_id"] == run_id, f"run_id mismatch in retrieval_critic event: {rows[0]['run_id']}"
    print(f"  {PASS}  test_retrieval_critic_threads_run_id")


async def test_extraction_critic_threads_run_id() -> None:
    """run_extraction_agent emits extraction_critic.verdict WITH run_id."""
    from app.agents.extraction import run_extraction_agent
    from app.core.output_models import (
        EvaluationSetup, MandatoryCheck, ExtractionTarget, ScoringCriterion,
        RetrievalOutput, RetrievedChunk,
    )

    run_id = str(uuid.uuid4())
    org_id = str(uuid.uuid4())
    _seed_run(run_id, org_id)

    chunk_text = (
        "Apex Technology holds ISO 27001 certification issued by BSI Group. "
        "Certificate number IS 123456, valid until 15 March 2027."
    )
    chunk = RetrievedChunk(
        chunk_id="c-iso",
        qdrant_point_id=str(uuid.uuid4()),
        text=chunk_text,
        section_id="s1",
        section_title="Security",
        section_type="requirement_response",
        filename="apex.pdf",
        page_number=1,
        vendor_id="vendor-test",
        vector_similarity_score=0.92,
        rerank_score=0.92,
        final_score=0.92,
        is_answer_bearing=True,
    )
    retrieval_output = RetrievalOutput(
        query_id=str(uuid.uuid4()),
        original_query="ISO 27001",
        rewritten_query="ISO 27001 certification",
        hyde_query_used=False,
        retrieval_strategy="dense",
        chunks=[chunk],
        total_candidates_before_rerank=1,
        confidence=0.9,
        empty_retrieval=False,
    )

    evaluation_setup = EvaluationSetup(
        setup_id=str(uuid.uuid4()),
        org_id=org_id,
        department="IT",
        rfp_id=str(uuid.uuid4()),
        rfp_confirmed=True,
        mandatory_checks=[
            MandatoryCheck(
                check_id="chk-iso",
                name="Information Security Certification",
                description="Vendor must hold ISO 27001.",
                what_passes="ISO 27001 certificate with number, issuing body, valid-until date",
                extraction_target_id="tgt-cert",
            )
        ],
        scoring_criteria=[
            ScoringCriterion(
                criterion_id="sc-001",
                name="Security Posture",
                weight=1.0,
                rubric_9_10="ISO 27001 with cert number, issuing body, and valid-until date explicitly stated",
                rubric_6_8="ISO 27001 mentioned with partial details",
                rubric_3_5="Security certifications mentioned without specifics",
                rubric_0_2="No security certification evidence",
                extraction_target_ids=["tgt-cert"],
            )
        ],
        extraction_targets=[
            ExtractionTarget(
                target_id="tgt-cert",
                name="Certifications",
                description="Security certifications",
                fact_type="certification",
                is_mandatory=True,
                feeds_check_id="chk-iso",
            )
        ],
        total_weight=1.0,
        confirmed_by="ci-test",
        source="manually_defined",
    )

    llm_extraction = json.dumps({
        "certifications": [{
            "standard_name": "ISO 27001",
            "version": None,
            "cert_number": "IS 123456",
            "issuing_body": "BSI Group",
            "scope": None,
            "valid_until": "2027-03-15",
            "status": "current",
            "confidence": 0.95,
            "grounding_quote": chunk_text,
            "source_chunk_id": "c-iso",
        }],
        "insurance": [], "slas": [], "projects": [], "pricing": [],
        "extracted_facts": [],
    })

    critic_verdict_json = json.dumps({
        "adequate": True, "confidence": 0.95, "missing": "", "should_retry": False,
    })

    with patch(
        "app.agents.extraction.call_llm",
        new_callable=AsyncMock,
        return_value=llm_extraction,
    ), patch(
        "app.core.extraction_critic.call_llm",
        new_callable=AsyncMock,
        return_value=critic_verdict_json,
    ), patch(
        "app.agents.extraction.save_extraction_output",
    ):
        await run_extraction_agent(
            retrieval_output=retrieval_output,
            vendor_id="vendor-test",
            org_id=org_id,
            doc_id=str(uuid.uuid4()),
            setup_id=str(uuid.uuid4()),
            evaluation_setup=evaluation_setup,
            run_id=run_id,
        )

    rows = _query_audit(run_id, "extraction_critic.verdict")
    assert len(rows) >= 1, (
        "Expected extraction_critic.verdict row with run_id in audit_log — "
        "run_id is not being threaded through run_extraction_agent"
    )
    assert rows[0]["run_id"] == run_id, f"run_id mismatch in extraction_critic event: {rows[0]['run_id']}"
    print(f"  {PASS}  test_extraction_critic_threads_run_id")
    return org_id


async def test_no_null_run_id_for_known_run() -> None:
    """For a newly created run, no critic events have run_id=NULL."""
    from app.agents.evaluation import _retrieve_top_k_for_check

    run_id = str(uuid.uuid4())
    org_id = str(uuid.uuid4())
    _seed_run(run_id, org_id)

    mock_output = MagicMock()
    mock_output.chunks = []
    mock_output.empty_retrieval = True

    mock_verdict = MagicMock()
    mock_verdict.adequate = False
    mock_verdict.confidence = 0.8
    mock_verdict.missing = "no chunks"

    with patch(
        "app.agents.retrieval.run_retrieval_agent",
        new_callable=AsyncMock,
        return_value=(mock_output, MagicMock()),
    ), patch(
        "app.core.retrieval_critic.judge_retrieval",
        new_callable=AsyncMock,
        return_value=mock_verdict,
    ):
        await _retrieve_top_k_for_check(
            check_name="Test check",
            vendor_id="vendor-null-test",
            org_id=org_id,
            run_id=run_id,
        )

    null_count = _count_null_run_id(org_id, "retrieval_critic.verdict")
    assert null_count == 0, (
        f"Found {null_count} retrieval_critic.verdict event(s) with run_id=NULL for org {org_id} — "
        "run_id is not being threaded correctly"
    )
    print(f"  {PASS}  test_no_null_run_id_for_known_run")


# ── Main ──────────────────────────────────────────────────────────────────────

async def main():
    print("\n--- Audit Completeness CI Tests ---\n")
    failures = 0

    for test_fn, is_async in [
        (test_audit_round_trip, False),
        (test_retrieval_critic_threads_run_id, True),
        (test_extraction_critic_threads_run_id, True),
        (test_no_null_run_id_for_known_run, True),
    ]:
        try:
            if is_async:
                await test_fn()
            else:
                test_fn()
        except Exception as e:
            print(f"  {FAIL}  {test_fn.__name__}: {e}")
            failures += 1

    print(f"\n{'All tests passed' if not failures else f'{failures} test(s) failed'}\n")
    sys.exit(failures)


if __name__ == "__main__":
    asyncio.run(main())
