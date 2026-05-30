"""
Human overrides are first-class citizens.
Every override creates an AuditOverride record.
Direct database edits are prohibited — this is the only override path.
"""
import uuid
from datetime import datetime
import sqlalchemy as sa
from app.schemas.output_models import AuditOverride


def create_override_record(
    org_id: str,
    run_id: str,
    overridden_by: str,
    original_decision: dict,
    new_decision: dict,
    reason: str
) -> AuditOverride:
    """
    Creates a validated override record.
    Reason is mandatory and must be at least 20 characters.
    AuditOverride validator enforces this for audit compliance.
    """
    return AuditOverride(
        override_id=str(uuid.uuid4()),
        org_id=org_id,
        run_id=run_id,
        overridden_by=overridden_by,
        original_decision=original_decision,
        new_decision=new_decision,
        reason=reason,
        timestamp=datetime.utcnow()
    )


def save_override(override: AuditOverride):
    """
    Writes override to audit_overrides table.
    This is the ONLY permitted way to change an evaluation decision.

    Uses the shared engine and sets the RLS org context (app.current_org_id) on
    the same transaction so the write passes the audit_overrides tenant policy.
    Decision payloads are stored as real JSON via json.dumps — NOT Python repr
    (str() produces single-quoted pseudo-JSON that a jsonb column rejects).
    """
    import json
    from sqlalchemy import text
    from app.db.fact_store import get_engine

    engine = get_engine()

    with engine.begin() as conn:
        # RLS: callers may run outside a request context (background tasks), so
        # set the session var the audit_overrides policy checks before writing.
        conn.execute(text("SET LOCAL app.current_org_id = :oid"), {"oid": str(override.org_id)})
        conn.execute(
            text("""
                INSERT INTO audit_overrides (
                    override_id, org_id, run_id, overridden_by,
                    original_decision, new_decision, reason, timestamp
                ) VALUES (
                    :override_id, :org_id, :run_id, :overridden_by,
                    :original_decision::jsonb, :new_decision::jsonb,
                    :reason, :timestamp
                )
                ON CONFLICT (override_id) DO NOTHING
            """),
            {
                "override_id": override.override_id,
                "org_id": override.org_id,
                "run_id": override.run_id,
                "overridden_by": override.overridden_by,
                "original_decision": json.dumps(override.original_decision, default=str),
                "new_decision": json.dumps(override.new_decision, default=str),
                "reason": override.reason,
                "timestamp": override.timestamp,
            }
        )
