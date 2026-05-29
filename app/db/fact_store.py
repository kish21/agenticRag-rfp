"""
Writes extracted facts to PostgreSQL.
Called immediately after Extraction Agent runs.
"""
import json
import uuid as _uuid
import sqlalchemy as sa
from app.schemas.output_models import EvaluationSetup, ExtractionOutput, IngestionOutput
from app.config import settings

_engine = None


def get_engine() -> sa.Engine:
    global _engine
    if _engine is None:
        url = (
            f"postgresql://{settings.postgres_user}"
            f":{settings.postgres_password}"
            f"@{settings.postgres_host}"
            f":{settings.postgres_port}"
            f"/{settings.postgres_db}"
        )
        _engine = sa.create_engine(url)
    return _engine


def _safe_uuid(value) -> str | None:
    """Return value as UUID string if valid, else None (avoids FK cast errors)."""
    if value is None:
        return None
    try:
        return str(_uuid.UUID(str(value)))
    except (ValueError, AttributeError):
        return None


def save_extraction_output(
    output: ExtractionOutput,
    doc_id: str
):
    """
    Persists all extracted facts to PostgreSQL.
    Each table call is idempotent — safe to call multiple times.

    Uses engine.begin() for auto-commit and sets app.current_org_id so
    background-task calls pass the RLS policy on all fact tables.
    """
    engine = get_engine()
    org_id = str(output.org_id)
    safe_doc_id = _safe_uuid(doc_id)  # None if caller passed rfp_id-vendor string

    with engine.begin() as conn:
        # RLS: background tasks have no request context, so set the session var
        # that every fact table's USING policy checks before allowing writes.
        conn.execute(sa.text("SET LOCAL app.current_org_id = :oid"), {"oid": org_id})

        for cert in output.certifications:
            conn.execute(sa.text("""
                INSERT INTO extracted_certifications (
                    doc_id, org_id, vendor_id,
                    standard_name, version, cert_number,
                    issuing_body, scope, valid_until, status,
                    confidence, grounding_quote, source_chunk_id
                ) VALUES (
                    CAST(:doc_id AS uuid), CAST(:org_id AS uuid), :vendor_id,
                    :standard_name, :version, :cert_number,
                    :issuing_body, :scope, :valid_until, :status,
                    :confidence, :grounding_quote, :source_chunk_id
                ) ON CONFLICT DO NOTHING
            """), {
                "doc_id": safe_doc_id,
                "org_id": org_id,
                "vendor_id": output.vendor_id,
                "standard_name": cert.standard_name,
                "version": cert.version,
                "cert_number": cert.cert_number,
                "issuing_body": cert.issuing_body,
                "scope": cert.scope,
                "valid_until": cert.valid_until,
                "status": cert.status.value,
                "confidence": cert.confidence,
                "grounding_quote": cert.grounding_quote,
                "source_chunk_id": cert.source_chunk_id,
            })

        for ins in output.insurance:
            conn.execute(sa.text("""
                INSERT INTO extracted_insurance (
                    doc_id, org_id, vendor_id,
                    insurance_type, amount_gbp, provider,
                    confidence, grounding_quote, source_chunk_id
                ) VALUES (
                    CAST(:doc_id AS uuid), CAST(:org_id AS uuid), :vendor_id,
                    :insurance_type, :amount_gbp, :provider,
                    :confidence, :grounding_quote, :source_chunk_id
                ) ON CONFLICT DO NOTHING
            """), {
                "doc_id": safe_doc_id,
                "org_id": org_id,
                "vendor_id": output.vendor_id,
                "insurance_type": ins.insurance_type,
                "amount_gbp": ins.amount_gbp,
                "provider": ins.provider,
                "confidence": ins.confidence,
                "grounding_quote": ins.grounding_quote,
                "source_chunk_id": ins.source_chunk_id,
            })

        for sla in output.slas:
            conn.execute(sa.text("""
                INSERT INTO extracted_slas (
                    doc_id, org_id, vendor_id,
                    priority_level, response_minutes,
                    resolution_hours, uptime_percentage,
                    confidence, grounding_quote, source_chunk_id
                ) VALUES (
                    CAST(:doc_id AS uuid), CAST(:org_id AS uuid), :vendor_id,
                    :priority_level, :response_minutes,
                    :resolution_hours, :uptime_percentage,
                    :confidence, :grounding_quote, :source_chunk_id
                ) ON CONFLICT DO NOTHING
            """), {
                "doc_id": safe_doc_id,
                "org_id": org_id,
                "vendor_id": output.vendor_id,
                "priority_level": sla.priority_level,
                "response_minutes": sla.response_minutes,
                "resolution_hours": sla.resolution_hours,
                "uptime_percentage": sla.uptime_percentage,
                "confidence": sla.confidence,
                "grounding_quote": sla.grounding_quote,
                "source_chunk_id": sla.source_chunk_id,
            })

        for proj in output.projects:
            conn.execute(sa.text("""
                INSERT INTO extracted_projects (
                    doc_id, org_id, vendor_id,
                    client_name, client_sector, user_count,
                    outcomes, reference_available,
                    confidence, grounding_quote, source_chunk_id
                ) VALUES (
                    CAST(:doc_id AS uuid), CAST(:org_id AS uuid), :vendor_id,
                    :client_name, :client_sector, :user_count,
                    :outcomes, :reference_available,
                    :confidence, :grounding_quote, :source_chunk_id
                ) ON CONFLICT DO NOTHING
            """), {
                "doc_id": safe_doc_id,
                "org_id": org_id,
                "vendor_id": output.vendor_id,
                "client_name": proj.client_name,
                "client_sector": proj.client_sector,
                "user_count": proj.user_count,
                "outcomes": proj.outcomes,
                "reference_available": proj.reference_available,
                "confidence": proj.confidence,
                "grounding_quote": proj.grounding_quote,
                "source_chunk_id": proj.source_chunk_id,
            })

        for price in output.pricing:
            conn.execute(sa.text("""
                INSERT INTO extracted_pricing (
                    doc_id, org_id, vendor_id,
                    year, amount_gbp, total_gbp, includes,
                    confidence, grounding_quote, source_chunk_id
                ) VALUES (
                    CAST(:doc_id AS uuid), CAST(:org_id AS uuid), :vendor_id,
                    :year, :amount_gbp, :total_gbp, :includes,
                    :confidence, :grounding_quote, :source_chunk_id
                ) ON CONFLICT DO NOTHING
            """), {
                "doc_id": safe_doc_id,
                "org_id": org_id,
                "vendor_id": output.vendor_id,
                "year": price.year,
                "amount_gbp": price.amount_gbp,
                "total_gbp": price.total_gbp,
                "includes": price.includes,
                "confidence": price.confidence,
                "grounding_quote": price.grounding_quote,
                "source_chunk_id": price.source_chunk_id,
            })

        for fact in output.extracted_facts:
            conn.execute(sa.text("""
                INSERT INTO extracted_facts (
                    doc_id, org_id, vendor_id, setup_id,
                    target_id, fact_type, fact_name,
                    text_value, numeric_value, boolean_value, unit,
                    confidence, grounding_quote, source_chunk_id
                ) VALUES (
                    CAST(:doc_id AS uuid), CAST(:org_id AS uuid), :vendor_id, :setup_id,
                    :target_id, :fact_type, :fact_name,
                    :text_value, :numeric_value, :boolean_value, :unit,
                    :confidence, :grounding_quote, :source_chunk_id
                ) ON CONFLICT DO NOTHING
            """), {
                "doc_id": safe_doc_id,
                "org_id": org_id,
                "vendor_id": output.vendor_id,
                "setup_id": getattr(output, "setup_id", None),
                "target_id": fact.target_id,
                "fact_type": fact.fact_type,
                "fact_name": fact.fact_name,
                "text_value": fact.text_value,
                "numeric_value": fact.numeric_value,
                "boolean_value": fact.boolean_value,
                "unit": getattr(fact, "unit", None),
                "confidence": fact.confidence,
                "grounding_quote": fact.grounding_quote,
                "source_chunk_id": fact.source_chunk_id,
            })


def get_vendor_facts(
    org_id: str,
    vendor_id: str,
    setup_id: str = None
) -> dict:
    """
    Retrieves all structured facts for a vendor.
    Used by the Evaluation Agent instead of Qdrant search.
    Pass setup_id to also retrieve customer-defined facts
    for that specific evaluation setup.
    """
    engine = get_engine()

    with engine.connect() as conn:
        # Set RLS context so background-task reads pass the org isolation policy
        conn.execute(sa.text("SET LOCAL app.current_org_id = :oid"), {"oid": str(org_id)})

        certs = conn.execute(sa.text("""
            SELECT * FROM extracted_certifications
            WHERE org_id::text = :org_id AND vendor_id = :vendor_id
            ORDER BY confidence DESC
        """), {"org_id": str(org_id), "vendor_id": vendor_id}).fetchall()

        insurance = conn.execute(sa.text("""
            SELECT * FROM extracted_insurance
            WHERE org_id::text = :org_id AND vendor_id = :vendor_id
            ORDER BY confidence DESC
        """), {"org_id": str(org_id), "vendor_id": vendor_id}).fetchall()

        slas = conn.execute(sa.text("""
            SELECT * FROM extracted_slas
            WHERE org_id::text = :org_id AND vendor_id = :vendor_id
            ORDER BY confidence DESC
        """), {"org_id": str(org_id), "vendor_id": vendor_id}).fetchall()

        projects = conn.execute(sa.text("""
            SELECT * FROM extracted_projects
            WHERE org_id::text = :org_id AND vendor_id = :vendor_id
            ORDER BY confidence DESC
        """), {"org_id": str(org_id), "vendor_id": vendor_id}).fetchall()

        pricing = conn.execute(sa.text("""
            SELECT * FROM extracted_pricing
            WHERE org_id::text = :org_id AND vendor_id = :vendor_id
            ORDER BY year ASC
        """), {"org_id": str(org_id), "vendor_id": vendor_id}).fetchall()

        facts_query = """
            SELECT * FROM extracted_facts
            WHERE org_id::text = :org_id AND vendor_id = :vendor_id
        """
        facts_params: dict = {"org_id": str(org_id), "vendor_id": vendor_id}
        if setup_id:
            facts_query += " AND setup_id = :setup_id"
            facts_params["setup_id"] = setup_id
        facts_query += " ORDER BY target_id, confidence DESC"

        facts = conn.execute(
            sa.text(facts_query), facts_params
        ).fetchall()

    return {
        "certifications": [dict(r._mapping) for r in certs],
        "insurance": [dict(r._mapping) for r in insurance],
        "slas": [dict(r._mapping) for r in slas],
        "projects": [dict(r._mapping) for r in projects],
        "pricing": [dict(r._mapping) for r in pricing],
        "extracted_facts": [dict(r._mapping) for r in facts],
    }


def save_evaluation_setup(setup_dict: dict, org_id: str) -> None:
    """
    Persists an EvaluationSetup to the database as a JSONB blob.
    Called from the API when the customer confirms their criteria on Page 4b.
    """
    engine = get_engine()
    setup_json_str = json.dumps(setup_dict, default=str)
    with engine.begin() as conn:
        conn.execute(sa.text("SET LOCAL app.current_org_id = :oid"), {"oid": str(org_id)})
        conn.execute(sa.text("""
            INSERT INTO evaluation_setups (
                setup_id, org_id, department, rfp_id,
                setup_json, confirmed_by, confirmed_at, source
            ) VALUES (
                :setup_id, CAST(:org_id AS uuid), :department, :rfp_id,
                CAST(:setup_json AS jsonb), :confirmed_by, :confirmed_at, :source
            ) ON CONFLICT (setup_id) DO UPDATE SET
                setup_json = EXCLUDED.setup_json,
                confirmed_at = EXCLUDED.confirmed_at
        """), {
            "setup_id": setup_dict["setup_id"],
            "org_id": org_id,
            "department": setup_dict.get("department", "procurement"),
            "rfp_id": setup_dict.get("rfp_id", ""),
            "setup_json": setup_json_str,
            "confirmed_by": setup_dict.get("confirmed_by", "system"),
            "confirmed_at": setup_dict.get("confirmed_at", ""),
            "source": setup_dict.get("source", "manually_defined"),
        })


def save_vendor_document(
    output: IngestionOutput,
    org_id: str,
    rfp_id: str,
    setup_id: str,
) -> None:
    """
    Persists the ingestion result to vendor_documents.
    Called immediately after run_ingestion_agent succeeds.
    """
    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(sa.text("SET LOCAL app.current_org_id = :oid"), {"oid": str(org_id)})
        conn.execute(sa.text("""
            INSERT INTO vendor_documents (
                doc_id, org_id, vendor_id, rfp_id, setup_id,
                filename, content_hash, quality_score, total_chunks
            ) VALUES (
                CAST(:doc_id AS uuid), CAST(:org_id AS uuid), :vendor_id, :rfp_id, :setup_id,
                :filename, :content_hash, :quality_score, :total_chunks
            ) ON CONFLICT (org_id, vendor_id, rfp_id, content_hash) DO NOTHING
        """), {
            "doc_id": str(output.doc_id),
            "org_id": str(org_id),
            "vendor_id": output.vendor_id,
            "rfp_id": rfp_id,
            "setup_id": setup_id,
            "filename": output.filename,
            "content_hash": output.content_hash,
            "quality_score": output.quality_score,
            "total_chunks": output.total_chunks,
        })


# ── Phase 5 — Background ingestion foundation helpers ────────────────
# See docs/dev/PRODUCTION_READINESS_PLAN.md Phase 5.0.


def create_rfp(
    *,
    rfp_id: str,
    org_id: str,
    title: str,
    created_by_email: str,
    department: str | None = None,
    submission_deadline=None,
    autonomy_mode: str = "auto_to_evaluate",
) -> None:
    """Inserts a new RFP shell. submission_status defaults to 'open'."""
    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(
            sa.text(
                """
                INSERT INTO rfps (
                    rfp_id, org_id, title, department,
                    created_by_email, submission_deadline, autonomy_mode
                ) VALUES (
                    :rfp_id, :org_id, :title, :department,
                    :created_by_email, :submission_deadline, :autonomy_mode
                )
                """
            ),
            {
                "rfp_id": rfp_id,
                "org_id": org_id,
                "title": title,
                "department": department,
                "created_by_email": created_by_email,
                "submission_deadline": submission_deadline,
                "autonomy_mode": autonomy_mode,
            },
        )


def invite_vendor(
    *, rfp_id: str, vendor_id: str, invited_by: str, vendor_name: str | None = None
) -> None:
    """Adds a vendor to an RFP's invited list. Idempotent on (rfp_id, vendor_id)."""
    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(
            sa.text(
                """
                INSERT INTO invited_vendors (rfp_id, vendor_id, vendor_name, invited_by)
                VALUES (:rfp_id, :vendor_id, :vendor_name, :invited_by)
                ON CONFLICT (rfp_id, vendor_id) DO NOTHING
                """
            ),
            {
                "rfp_id": rfp_id,
                "vendor_id": vendor_id,
                "vendor_name": vendor_name,
                "invited_by": invited_by,
            },
        )


def set_deadline(*, rfp_id: str, submission_deadline) -> bool:
    """
    Updates submission_deadline. Only allowed while submission_status='open'.
    Returns True if updated, False if RFP is locked.
    """
    engine = get_engine()
    with engine.begin() as conn:
        result = conn.execute(
            sa.text(
                """
                UPDATE rfps
                SET submission_deadline = :deadline
                WHERE rfp_id = :rfp_id AND submission_status = 'open'
                """
            ),
            {"deadline": submission_deadline, "rfp_id": rfp_id},
        )
        return result.rowcount > 0


def enqueue_ingestion_job(
    *,
    org_id: str,
    rfp_id: str,
    vendor_id: str,
    content_hash: str,
    filename: str | None = None,
    source_uri: str | None = None,
    status: str = "received",
    attribution_confidence: float | None = None,
) -> str | None:
    """
    Inserts an ingestion_jobs row. Returns job_id, or None on UNIQUE conflict
    (duplicate content_hash for the same rfp_id+vendor_id).
    """
    engine = get_engine()
    with engine.begin() as conn:
        row = conn.execute(
            sa.text(
                """
                INSERT INTO ingestion_jobs (
                    org_id, rfp_id, vendor_id, content_hash,
                    filename, source_uri, status, attribution_confidence
                ) VALUES (
                    :org_id, :rfp_id, :vendor_id, :content_hash,
                    :filename, :source_uri, :status, :confidence
                )
                ON CONFLICT (rfp_id, vendor_id, content_hash) DO NOTHING
                RETURNING job_id
                """
            ),
            {
                "org_id": org_id,
                "rfp_id": rfp_id,
                "vendor_id": vendor_id,
                "content_hash": content_hash,
                "filename": filename,
                "source_uri": source_uri,
                "status": status,
                "confidence": attribution_confidence,
            },
        ).fetchone()
        return str(row[0]) if row else None


def mark_rfp_facts_ready(*, rfp_id: str) -> None:
    """Transitions rfps.submission_status to 'facts_ready' once all jobs done."""
    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(
            sa.text(
                """
                UPDATE rfps
                SET submission_status = 'facts_ready'
                WHERE rfp_id = :rfp_id AND submission_status = 'processing'
                """
            ),
            {"rfp_id": rfp_id},
        )


def get_rfp_rollup(*, rfp_id: str) -> dict:
    """
    Returns a rollup of an RFP's current state for UI / scheduler:
    {rfp_id, submission_status, autonomy_mode, submission_deadline,
     vendor_count, job_counts_by_status}.
    """
    engine = get_engine()
    with engine.connect() as conn:
        rfp = conn.execute(
            sa.text(
                """
                SELECT rfp_id, submission_status, autonomy_mode,
                       submission_deadline, title, org_id
                FROM rfps WHERE rfp_id = :rfp_id
                """
            ),
            {"rfp_id": rfp_id},
        ).fetchone()
        if not rfp:
            return {}
        vendor_count = conn.execute(
            sa.text("SELECT COUNT(*) FROM invited_vendors WHERE rfp_id = :rfp_id"),
            {"rfp_id": rfp_id},
        ).scalar()
        job_rows = conn.execute(
            sa.text(
                """
                SELECT status, COUNT(*) FROM ingestion_jobs
                WHERE rfp_id = :rfp_id GROUP BY status
                """
            ),
            {"rfp_id": rfp_id},
        ).fetchall()
        return {
            "rfp_id": rfp.rfp_id,
            "org_id": str(rfp.org_id),
            "title": rfp.title,
            "submission_status": rfp.submission_status,
            "autonomy_mode": rfp.autonomy_mode,
            "submission_deadline": rfp.submission_deadline,
            "vendor_count": vendor_count,
            "job_counts_by_status": {r.status: r.count for r in job_rows},
        }


def emit_event(
    *, event_type: str, org_id: str, rfp_id: str, payload: dict | None = None
) -> str:
    """Writes an event_log row. Phase 8 delivery dispatcher reads these."""
    engine = get_engine()
    with engine.begin() as conn:
        row = conn.execute(
            sa.text(
                """
                INSERT INTO event_log (event_type, org_id, rfp_id, payload)
                VALUES (:event_type, :org_id, :rfp_id, CAST(:payload AS JSONB))
                RETURNING event_id
                """
            ),
            {
                "event_type": event_type,
                "org_id": org_id,
                "rfp_id": rfp_id,
                "payload": json.dumps(payload or {}),
            },
        ).fetchone()
        return str(row[0])


def facts_already_extracted(*, rfp_id: str, vendor_id: str) -> bool:
    """
    Returns True if extracted_facts rows exist for (rfp_id, vendor_id).
    Used by the pipeline short-circuit in PR-E.
    """
    engine = get_engine()
    with engine.connect() as conn:
        row = conn.execute(
            sa.text(
                """
                SELECT 1
                FROM extracted_facts ef
                JOIN vendor_documents vd ON vd.doc_id = ef.doc_id
                WHERE vd.rfp_id = :rfp_id AND ef.vendor_id = :vendor_id
                LIMIT 1
                """
            ),
            {"rfp_id": rfp_id, "vendor_id": vendor_id},
        ).fetchone()
        return row is not None


def get_evaluation_setup(setup_id: str, org_id: str = None) -> EvaluationSetup:
    """
    Reads an EvaluationSetup back from the evaluation_setups table.
    Called by test scripts and agents that need the full setup object.
    Pass org_id when calling from a background task (sets RLS context).
    """
    engine = get_engine()
    with engine.connect() as conn:
        if org_id:
            conn.execute(sa.text("SET LOCAL app.current_org_id = :oid"), {"oid": str(org_id)})
        row = conn.execute(sa.text("""
            SELECT setup_json
            FROM evaluation_setups
            WHERE setup_id = :setup_id
        """), {"setup_id": setup_id}).fetchone()

    if not row:
        raise ValueError(
            f"EvaluationSetup not found for setup_id={setup_id}. "
            f"Run test_e2e.py first to ingest a document and create the setup."
        )

    return EvaluationSetup(**row._mapping["setup_json"])
