"""
Human overrides are first-class citizens.
Every override creates an AuditOverride record.
Direct database edits are prohibited — this is the only override path.
"""
import uuid
from datetime import datetime
import sqlalchemy as sa
from app.core.output_models import AuditOverride


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
    Gets the database engine from settings automatically.
    """
    from sqlalchemy import create_engine, text
    from app.config import settings

    db_url = (
        f"postgresql://{settings.postgres_user}:"
        f"{settings.postgres_password}@{settings.postgres_host}:"
        f"{settings.postgres_port}/{settings.postgres_db}"
    )
    engine = create_engine(db_url)

    with engine.connect() as conn:
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
                "original_decision": str(override.original_decision),
                "new_decision": str(override.new_decision),
                "reason": override.reason,
                "timestamp": override.timestamp,
            }
        )
        conn.commit()
