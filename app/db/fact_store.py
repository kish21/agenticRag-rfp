"""
Writes extracted facts to PostgreSQL.
Called immediately after Extraction Agent runs.
"""
import json
import sqlalchemy as sa
from app.core.output_models import EvaluationSetup, ExtractionOutput, IngestionOutput
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


def save_extraction_output(
    output: ExtractionOutput,
    doc_id: str
):
    """
    Persists all extracted facts to PostgreSQL.
    Each table call is idempotent — safe to call multiple times.
    """
    engine = get_engine()

    with engine.connect() as conn:
        for cert in output.certifications:
            conn.execute(sa.text("""
                INSERT INTO extracted_certifications (
                    doc_id, org_id, vendor_id,
                    standard_name, version, cert_number,
                    issuing_body, scope, valid_until, status,
                    confidence, grounding_quote, source_chunk_id
                ) VALUES (
                    :doc_id, :org_id, :vendor_id,
                    :standard_name, :version, :cert_number,
                    :issuing_body, :scope, :valid_until, :status,
                    :confidence, :grounding_quote, :source_chunk_id
                ) ON CONFLICT DO NOTHING
            """), {
                "doc_id": doc_id,
                "org_id": output.org_id,
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
                    :doc_id, :org_id, :vendor_id,
                    :insurance_type, :amount_gbp, :provider,
                    :confidence, :grounding_quote, :source_chunk_id
                ) ON CONFLICT DO NOTHING
            """), {
                "doc_id": doc_id,
                "org_id": output.org_id,
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
                    :doc_id, :org_id, :vendor_id,
                    :priority_level, :response_minutes,
                    :resolution_hours, :uptime_percentage,
                    :confidence, :grounding_quote, :source_chunk_id
                ) ON CONFLICT DO NOTHING
            """), {
                "doc_id": doc_id,
                "org_id": output.org_id,
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
                    :doc_id, :org_id, :vendor_id,
                    :client_name, :client_sector, :user_count,
                    :outcomes, :reference_available,
                    :confidence, :grounding_quote, :source_chunk_id
                ) ON CONFLICT DO NOTHING
            """), {
                "doc_id": doc_id,
                "org_id": output.org_id,
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
                    :doc_id, :org_id, :vendor_id,
                    :year, :amount_gbp, :total_gbp, :includes,
                    :confidence, :grounding_quote, :source_chunk_id
                ) ON CONFLICT DO NOTHING
            """), {
                "doc_id": doc_id,
                "org_id": output.org_id,
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
                    :doc_id, :org_id, :vendor_id, :setup_id,
                    :target_id, :fact_type, :fact_name,
                    :text_value, :numeric_value, :boolean_value, :unit,
                    :confidence, :grounding_quote, :source_chunk_id
                ) ON CONFLICT DO NOTHING
            """), {
                "doc_id": doc_id,
                "org_id": output.org_id,
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

        conn.commit()


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
        certs = conn.execute(sa.text("""
            SELECT * FROM extracted_certifications
            WHERE org_id::text = :org_id AND vendor_id = :vendor_id
            ORDER BY confidence DESC
        """), {"org_id": org_id, "vendor_id": vendor_id}).fetchall()

        insurance = conn.execute(sa.text("""
            SELECT * FROM extracted_insurance
            WHERE org_id::text = :org_id AND vendor_id = :vendor_id
            ORDER BY confidence DESC
        """), {"org_id": org_id, "vendor_id": vendor_id}).fetchall()

        slas = conn.execute(sa.text("""
            SELECT * FROM extracted_slas
            WHERE org_id::text = :org_id AND vendor_id = :vendor_id
            ORDER BY confidence DESC
        """), {"org_id": org_id, "vendor_id": vendor_id}).fetchall()

        projects = conn.execute(sa.text("""
            SELECT * FROM extracted_projects
            WHERE org_id::text = :org_id AND vendor_id = :vendor_id
            ORDER BY confidence DESC
        """), {"org_id": org_id, "vendor_id": vendor_id}).fetchall()

        pricing = conn.execute(sa.text("""
            SELECT * FROM extracted_pricing
            WHERE org_id::text = :org_id AND vendor_id = :vendor_id
            ORDER BY year ASC
        """), {"org_id": org_id, "vendor_id": vendor_id}).fetchall()

        facts_query = """
            SELECT * FROM extracted_facts
            WHERE org_id::text = :org_id AND vendor_id = :vendor_id
        """
        facts_params: dict = {"org_id": org_id, "vendor_id": vendor_id}
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
    with engine.connect() as conn:
        conn.execute(sa.text("""
            INSERT INTO evaluation_setups (
                setup_id, org_id, department, rfp_id,
                setup_json, confirmed_by, confirmed_at, source
            ) VALUES (
                :setup_id, :org_id, :department, :rfp_id,
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
        conn.commit()


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
    with engine.connect() as conn:
        conn.execute(sa.text("""
            INSERT INTO vendor_documents (
                doc_id, org_id, vendor_id, rfp_id, setup_id,
                filename, content_hash, quality_score, total_chunks
            ) VALUES (
                :doc_id, CAST(:org_id AS uuid), :vendor_id, :rfp_id, :setup_id,
                :filename, :content_hash, :quality_score, :total_chunks
            ) ON CONFLICT (org_id, vendor_id, rfp_id, content_hash) DO NOTHING
        """), {
            "doc_id": output.doc_id,
            "org_id": org_id,
            "vendor_id": output.vendor_id,
            "rfp_id": rfp_id,
            "setup_id": setup_id,
            "filename": output.filename,
            "content_hash": output.content_hash,
            "quality_score": output.quality_score,
            "total_chunks": output.total_chunks,
        })
        conn.commit()


def get_evaluation_setup(setup_id: str) -> EvaluationSetup:
    """
    Reads an EvaluationSetup back from the evaluation_setups table.
    Called by test scripts and agents that need the full setup object.
    """
    engine = get_engine()
    with engine.connect() as conn:
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
