"""
Writes extracted facts to PostgreSQL.
Called immediately after Extraction Agent runs.
"""
import json
import uuid as _uuid
import sqlalchemy as sa
from app.schemas.output_models import EvaluationSetup, ExtractionOutput, IngestionOutput
from app.db.session import app_engine_url, admin_engine_url, install_org_listener

_engine = None
_admin_engine = None


def get_engine() -> sa.Engine:
    """The RLS-governed application engine (role: platform_app).

    Every connection it hands out is auto-stamped with app.current_org_id from
    the request/background ContextVar (see app/db/session.py), so route handlers
    and DB helpers do not each have to SET it. Use this for ALL tenant-scoped
    access — it is the engine RLS actually constrains.
    """
    global _engine
    if _engine is None:
        _engine = sa.create_engine(app_engine_url())
        install_org_listener(_engine)
    return _engine


def get_admin_engine() -> sa.Engine:
    """The owner/superuser engine (role: platformuser) — RLS-EXEMPT.

    Use ONLY for paths that legitimately span orgs or precede an org context:
    DDL/migrations, the startup orphaned-run sweep, identity/auth lookups, and
    cross-org cron jobs. Never use it to serve a tenant request.
    """
    global _admin_engine
    if _admin_engine is None:
        _admin_engine = sa.create_engine(admin_engine_url())
    return _admin_engine


# ── GDPR Mode B — whole-tenant PostgreSQL purge (issue #119) ─────────────
# FK-safe ordered deletes for one org, returning per-table counts. Children are
# deleted before parents so no foreign-key constraint is ever violated; the
# `organisations` row is removed last. Runs as ONE transaction on the RLS-EXEMPT
# admin engine — this is a cross-cutting system operation (a customer leaving),
# not a tenant request, and must reach rows the app-role/RLS would scope away.
#
# Ordering is validated against app/db/schema.sql. Most org-scoped tables carry a
# UUID `org_id`; org_settings(+audit) use a TEXT org_id (compared without a cast);
# a few child tables have no org_id and are scoped via a subquery on their parent.
# `audit_log` rows for the org are removed here too — the leaving tenant's audit
# history goes with them; the retained erasure RECEIPT is written separately,
# after this purge (see app/domain/org_erasure.py), and survives because
# audit_log has no FK to organisations.
_PURGE_ORDER: list[tuple[str, str]] = [
    # 1 ── extracted facts (FK → vendor_documents / evaluation_setups) ──────
    ("extracted_certifications", "DELETE FROM extracted_certifications WHERE org_id = CAST(:oid AS uuid)"),
    ("extracted_insurance",      "DELETE FROM extracted_insurance      WHERE org_id = CAST(:oid AS uuid)"),
    ("extracted_slas",           "DELETE FROM extracted_slas           WHERE org_id = CAST(:oid AS uuid)"),
    ("extracted_projects",       "DELETE FROM extracted_projects       WHERE org_id = CAST(:oid AS uuid)"),
    ("extracted_pricing",        "DELETE FROM extracted_pricing        WHERE org_id = CAST(:oid AS uuid)"),
    ("extracted_facts",          "DELETE FROM extracted_facts          WHERE org_id = CAST(:oid AS uuid)"),
    # 2 ── run-scoped children (FK → evaluation_runs / users) ───────────────
    ("decisions",                "DELETE FROM decisions                WHERE org_id = CAST(:oid AS uuid)"),
    ("approvals",                "DELETE FROM approvals                WHERE org_id = CAST(:oid AS uuid)"),
    ("approval_assignments",
     "DELETE FROM approval_assignments WHERE run_id IN "
     "(SELECT run_id FROM evaluation_runs WHERE org_id = CAST(:oid AS uuid))"),
    ("rfp_collaborators",
     "DELETE FROM rfp_collaborators WHERE run_id IN "
     "(SELECT run_id FROM evaluation_runs WHERE org_id = CAST(:oid AS uuid))"),
    ("access_audit_log",         "DELETE FROM access_audit_log         WHERE org_id = CAST(:oid AS uuid)"),
    ("retrieval_log",            "DELETE FROM retrieval_log            WHERE org_id = CAST(:oid AS uuid)"),
    ("audit_overrides",          "DELETE FROM audit_overrides          WHERE org_id = CAST(:oid AS uuid)"),
    ("evaluation_corrections",   "DELETE FROM evaluation_corrections   WHERE org_id = CAST(:oid AS uuid)"),
    ("audit_log",                "DELETE FROM audit_log                WHERE org_id = CAST(:oid AS uuid)"),
    ("ingestion_jobs",           "DELETE FROM ingestion_jobs           WHERE org_id = CAST(:oid AS uuid)"),
    ("event_log",                "DELETE FROM event_log                WHERE org_id = CAST(:oid AS uuid)"),
    # 3 ── documents + runs + setups (parents of the above) ─────────────────
    ("invited_vendors",
     "DELETE FROM invited_vendors WHERE rfp_id IN "
     "(SELECT rfp_id FROM rfps WHERE org_id = CAST(:oid AS uuid))"),
    ("vendor_documents",         "DELETE FROM vendor_documents         WHERE org_id = CAST(:oid AS uuid)"),
    ("evaluation_runs",          "DELETE FROM evaluation_runs          WHERE org_id = CAST(:oid AS uuid)"),
    ("evaluation_setups",        "DELETE FROM evaluation_setups        WHERE org_id = CAST(:oid AS uuid)"),
    ("rfps",                     "DELETE FROM rfps                     WHERE org_id = CAST(:oid AS uuid)"),
    ("agent_registry",           "DELETE FROM agent_registry           WHERE org_id = CAST(:oid AS uuid)"),
    # 4 ── org-level config / billing / templates (FK → organisations) ──────
    ("org_criteria_templates",   "DELETE FROM org_criteria_templates   WHERE org_id = CAST(:oid AS uuid)"),
    ("dept_criteria_templates",  "DELETE FROM dept_criteria_templates  WHERE org_id = CAST(:oid AS uuid)"),
    ("tenant_modules",           "DELETE FROM tenant_modules           WHERE org_id = CAST(:oid AS uuid)"),
    ("tenant_billing",           "DELETE FROM tenant_billing           WHERE org_id = CAST(:oid AS uuid)"),
    ("org_settings",             "DELETE FROM org_settings             WHERE org_id = :oid"),        # TEXT org_id
    ("org_settings_audit",       "DELETE FROM org_settings_audit       WHERE org_id = :oid"),        # TEXT org_id
    # 5 ── users + their auth artefacts (FK → users / organisations) ────────
    ("user_departments",
     "DELETE FROM user_departments WHERE user_id IN "
     "(SELECT user_id FROM users WHERE org_id = CAST(:oid AS uuid))"),
    ("auth_sessions",            "DELETE FROM auth_sessions            WHERE org_id = CAST(:oid AS uuid)"),
    ("auth_onetime_tokens",      "DELETE FROM auth_onetime_tokens      WHERE org_id = CAST(:oid AS uuid)"),
    ("users",                    "DELETE FROM users                    WHERE org_id = CAST(:oid AS uuid)"),
    # 6 ── the tenant row itself, last ──────────────────────────────────────
    ("organisations",            "DELETE FROM organisations            WHERE org_id = CAST(:oid AS uuid)"),
]


def purge_org_postgres(org_id: str) -> dict[str, int]:
    """Delete EVERY PostgreSQL row for one org, FK-safe, in one transaction.

    Returns a per-table count of rows deleted (table name → rowcount). The
    leaving tenant's own audit/decision history is removed too; the retained,
    anonymized erasure receipt is written by the caller AFTER this returns.

    Uses the RLS-exempt admin engine — this is a system offboarding operation,
    not a tenant request. Does NOT touch the tenant-blind `llm_response_cache`
    (no org_id column — documented residual gap, see docs/dev/119.md).
    """
    counts: dict[str, int] = {}
    engine = get_admin_engine()
    with engine.begin() as conn:
        for table, sql in _PURGE_ORDER:
            result = conn.execute(sa.text(sql), {"oid": str(org_id)})
            counts[table] = result.rowcount or 0
    return counts


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


def get_rfp_lifecycle(*, rfp_id: str) -> dict | None:
    """Returns minimal RFP context the watcher needs at file-arrival time.
    Returns None if the rfp_id is unknown. None of the values can be NULL."""
    engine = get_engine()
    with engine.connect() as conn:
        row = conn.execute(
            sa.text(
                """
                SELECT rfp_id, org_id::text AS org_id, submission_status,
                       submission_deadline, autonomy_mode
                FROM rfps WHERE rfp_id = :r
                """
            ),
            {"r": rfp_id},
        ).fetchone()
    if not row:
        return None
    return {
        "rfp_id": row.rfp_id,
        "org_id": row.org_id,
        "submission_status": row.submission_status,
        "submission_deadline": row.submission_deadline,
        "autonomy_mode": row.autonomy_mode,
    }


def is_invited_vendor(*, rfp_id: str, vendor_id: str) -> bool:
    """Returns True iff (rfp_id, vendor_id) exists in invited_vendors."""
    engine = get_engine()
    with engine.connect() as conn:
        row = conn.execute(
            sa.text(
                "SELECT 1 FROM invited_vendors "
                "WHERE rfp_id = :r AND vendor_id = :v LIMIT 1"
            ),
            {"r": rfp_id, "v": vendor_id},
        ).fetchone()
    return row is not None


def supersede_prior_received(*, rfp_id: str, vendor_id: str, new_job_id: str) -> int:
    """
    Marks any existing (rfp_id, vendor_id) jobs in status='received' as
    'superseded', pointing them at new_job_id. Returns the number of
    rows affected. Called by the watcher AFTER it inserts the new job.
    """
    engine = get_engine()
    with engine.begin() as conn:
        result = conn.execute(
            sa.text(
                """
                UPDATE ingestion_jobs
                SET status = 'superseded', superseded_by = :new_id
                WHERE rfp_id = :r AND vendor_id = :v
                  AND status = 'received'
                  AND job_id <> :new_id
                """
            ),
            {"r": rfp_id, "v": vendor_id, "new_id": new_job_id},
        )
        return result.rowcount


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


# ── P1.9 (#60) — human feedback capture → few-shot bank ──────────────────
# Criterion/check-level corrections that the Evaluation Agent's few-shot bank
# selects on. Same RLS-context pattern as every other tenant write/read: set
# app.current_org_id so background-task calls pass the evaluation_corrections
# policy (the few-shot lookup runs inside the evaluation pipeline, off-request).

def save_evaluation_correction(correction) -> None:
    """Persist one human correction. Idempotent on correction_id.

    `correction` is an EvaluationCorrection (typed contract). JSONB payloads are
    serialised with json.dumps — Python repr() produces single-quoted pseudo-JSON
    a jsonb column rejects.
    """
    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(sa.text("SET LOCAL app.current_org_id = :oid"),
                     {"oid": str(correction.org_id)})
        conn.execute(
            sa.text("""
                INSERT INTO evaluation_corrections (
                    correction_id, org_id, run_id, vendor_id,
                    target_type, target_id, target_name,
                    original_value, corrected_value, reason, corrected_by, active
                ) VALUES (
                    CAST(:correction_id AS uuid), CAST(:org_id AS uuid),
                    CAST(NULLIF(:run_id, '') AS uuid), :vendor_id,
                    :target_type, :target_id, :target_name,
                    CAST(:original_value AS jsonb), CAST(:corrected_value AS jsonb),
                    :reason, :corrected_by, :active
                )
                ON CONFLICT (correction_id) DO NOTHING
            """),
            {
                "correction_id": correction.correction_id,
                "org_id": str(correction.org_id),
                "run_id": str(correction.run_id or ""),
                "vendor_id": correction.vendor_id,
                "target_type": correction.target_type,
                "target_id": correction.target_id,
                "target_name": correction.target_name,
                "original_value": json.dumps(correction.original_value, default=str),
                "corrected_value": json.dumps(correction.corrected_value, default=str),
                "reason": correction.reason,
                "corrected_by": correction.corrected_by,
                "active": correction.active,
            },
        )


def get_evaluation_corrections(
    org_id: str,
    target_type: str = None,
    target_id: str = None,
    run_id: str = None,
    limit: int = 50,
    active_only: bool = True,
) -> list[dict]:
    """Fetch corrections for an org, newest first.

    Org isolation is enforced by RLS (set below) AND by the explicit org_id
    filter. target_type/target_id narrow to one criterion/check for the few-shot
    bank; run_id narrows to a single run for the reviewer UI — all applied in SQL
    BEFORE the LIMIT so a busy org never silently truncates a run's corrections.
    `limit` is clamped to a sane ceiling so a caller can never pull an unbounded
    result set into a prompt.
    """
    safe_limit = max(0, min(int(limit), 200))
    if safe_limit == 0:
        return []
    clauses = ["org_id = CAST(:org_id AS uuid)"]
    params: dict = {"org_id": str(org_id), "limit": safe_limit}
    if active_only:
        clauses.append("active = true")
    if target_type:
        clauses.append("target_type = :target_type")
        params["target_type"] = target_type
    if target_id:
        clauses.append("target_id = :target_id")
        params["target_id"] = target_id
    if run_id:
        clauses.append("run_id = CAST(:run_id AS uuid)")
        params["run_id"] = str(run_id)
    where = " AND ".join(clauses)

    engine = get_engine()
    with engine.connect() as conn:
        conn.execute(sa.text("SET LOCAL app.current_org_id = :oid"), {"oid": str(org_id)})
        rows = conn.execute(
            sa.text(f"""
                SELECT correction_id, org_id, run_id, vendor_id,
                       target_type, target_id, target_name,
                       original_value, corrected_value, reason, corrected_by,
                       active, created_at
                FROM evaluation_corrections
                WHERE {where}
                ORDER BY created_at DESC
                LIMIT :limit
            """),
            params,
        ).fetchall()
    return [dict(r._mapping) for r in rows]
