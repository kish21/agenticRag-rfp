"""
P1.9 (#60) — fact_store round-trip for evaluation_corrections.

Proves save_evaluation_correction → get_evaluation_corrections against the real
DB: JSONB values survive intact, the org_id + target filter narrows correctly,
and run_id="" is stored as NULL (not a cast error).

Requires Postgres (provisioned by app/db/schema.sql / migration 0016). Cleans up
its own rows. Runs as the owner engine via conftest.

Run: python -m pytest tests/test_correction_store.py -v
"""
import uuid

import sqlalchemy as sa

from app.db.fact_store import (
    get_admin_engine, save_evaluation_correction, get_evaluation_corrections,
)
from app.schemas.output_models import EvaluationCorrection


def test_save_and_get_roundtrip():
    org = str(uuid.uuid4())
    cid = str(uuid.uuid4())
    correction = EvaluationCorrection(
        correction_id=cid, org_id=org, run_id="", vendor_id="v1",
        target_type="criterion", target_id="crit-X", target_name="Security",
        original_value={"raw_score": 3}, corrected_value={"raw_score": 9},
        reason="round-trip store test reason — at least twenty characters long",
        corrected_by="tester@x.test",
    )
    try:
        save_evaluation_correction(correction)

        rows = get_evaluation_corrections(org_id=org, target_type="criterion", target_id="crit-X")
        assert len(rows) == 1
        assert str(rows[0]["correction_id"]) == cid             # driver returns a UUID
        assert rows[0]["corrected_value"] == {"raw_score": 9}   # JSONB intact
        assert rows[0]["original_value"] == {"raw_score": 3}
        assert rows[0]["run_id"] is None                        # "" → NULL

        # idempotent: a second save with the same id does not duplicate.
        save_evaluation_correction(correction)
        assert len(get_evaluation_corrections(org_id=org, target_id="crit-X")) == 1

        # target filter narrows; a different target returns nothing.
        assert get_evaluation_corrections(org_id=org, target_id="other") == []
        # limit=0 short-circuits.
        assert get_evaluation_corrections(org_id=org, limit=0) == []
    finally:
        with get_admin_engine().begin() as conn:
            conn.execute(sa.text(
                "DELETE FROM evaluation_corrections WHERE org_id = CAST(:o AS uuid)"
            ), {"o": org})
