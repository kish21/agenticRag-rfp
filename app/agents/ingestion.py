"""
Ingestion Agent — the entry point for all documents.

Handles:
- Single PDF/DOCX/TXT files
- ZIP archives containing multiple vendor files
- Heavy PDFs (>50 pages or scanned) are offloaded to Modal for extraction
"""
import io
import uuid
import zipfile
from app.schemas.output_models import IngestionOutput, EvaluationSetup
from app.retrieval.pipeline import process_document
from app.validators.ingestion import (
    compute_content_hash,
    validate_extracted_text,
    validate_zip_contents,
)
from app.retrieval.qdrant import (
    get_qdrant_client,
    org_collection_name,
    create_collection,
    upsert_chunk,
)
from app.agents.critic import critic_after_ingestion
from app.validators.injection import scan_chunks
from app.config import settings


async def run_ingestion_agent(
    content: bytes,
    filename: str,
    vendor_id: str,
    org_id: str,
    rfp_id: str,
    evaluation_setup: EvaluationSetup,
    trusted_source: bool = False,
) -> tuple[IngestionOutput, list]:
    """
    Main ingestion entry point.
    Returns (IngestionOutput, critic_output_list).

    Handles both single files and ZIP archives.
    Accepts EvaluationSetup so section classification uses
    the customer-confirmed criteria, not a generic config dict.

    trusted_source: the prompt-injection scan (#133) targets UNTRUSTED vendor
    proposals. The RFP is the customer's own first-party document — scanning it
    is a category error (legitimate RFP language like "the evaluator must
    approve…" would false-positive and HARD-block the whole run). Pass True only
    for the RFP. Defaults False so every vendor path is scanned by default.
    """
    if filename.lower().endswith(".zip"):
        return await _ingest_zip(
            content, filename, vendor_id, org_id, rfp_id, evaluation_setup,
            trusted_source=trusted_source,
        )
    return await _ingest_single_file(
        content, filename, vendor_id, org_id, rfp_id, evaluation_setup,
        trusted_source=trusted_source,
    )


async def _ingest_zip(
    content: bytes,
    zip_filename: str,
    vendor_id: str,
    org_id: str,
    rfp_id: str,
    evaluation_setup: EvaluationSetup,
    trusted_source: bool = False,
) -> tuple[IngestionOutput, list]:
    """Unpacks ZIP and processes each file as part of the same vendor."""
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as zf:
            file_list = [
                f for f in zf.namelist()
                if not f.startswith("__MACOSX") and not f.endswith("/")
            ]

            is_valid, accepted, warning = validate_zip_contents(file_list)

            if not is_valid:
                return IngestionOutput(
                    doc_id=str(uuid.uuid4()),
                    vendor_id=vendor_id,
                    org_id=org_id,
                    filename=zip_filename,
                    total_chunks=0,
                    chunks_by_type={},
                    filtered_chunks=0,
                    extraction_triggered=False,
                    quality_score=0.0,
                    content_hash=compute_content_hash(content),
                    warnings=[f"ZIP invalid: {warning}"],
                    status="failed",
                ), []

            all_outputs = []
            all_critics = []

            for fname in accepted:
                file_bytes = zf.read(fname)
                output, critics = await _ingest_single_file(
                    file_bytes, fname, vendor_id, org_id, rfp_id, evaluation_setup,
                    trusted_source=trusted_source,
                )
                all_outputs.append(output)
                all_critics.extend(critics)

            total_chunks = sum(o.total_chunks for o in all_outputs)
            merged_types: dict = {}
            for o in all_outputs:
                for k, v in o.chunks_by_type.items():
                    merged_types[k] = merged_types.get(k, 0) + v

            avg_quality = (
                sum(o.quality_score for o in all_outputs) / len(all_outputs)
                if all_outputs else 0.0
            )

            summary = IngestionOutput(
                doc_id=str(uuid.uuid4()),
                vendor_id=vendor_id,
                org_id=org_id,
                filename=zip_filename,
                total_chunks=total_chunks,
                chunks_by_type=merged_types,
                filtered_chunks=sum(o.filtered_chunks for o in all_outputs),
                extraction_triggered=any(o.extraction_triggered for o in all_outputs),
                quality_score=avg_quality,
                content_hash=compute_content_hash(content),
                warnings=[warning] if warning else [],
                status="success" if total_chunks > 0 else "partial",
                # Aggregate per-file injection findings so the summary's typed
                # audit field is truthful (blocking happens via all_critics, but
                # a serialized summary must not under-report packed-file attacks).
                injection_findings=[
                    f for o in all_outputs for f in o.injection_findings
                ],
            )
            return summary, all_critics

    except zipfile.BadZipFile:
        return IngestionOutput(
            doc_id=str(uuid.uuid4()),
            vendor_id=vendor_id,
            org_id=org_id,
            filename=zip_filename,
            total_chunks=0,
            chunks_by_type={},
            filtered_chunks=0,
            extraction_triggered=False,
            quality_score=0.0,
            content_hash=compute_content_hash(content),
            warnings=["Invalid ZIP file — cannot unpack"],
            status="failed",
        ), []


async def _ingest_single_file(
    content: bytes,
    filename: str,
    vendor_id: str,
    org_id: str,
    rfp_id: str,
    evaluation_setup: EvaluationSetup,
    trusted_source: bool = False,
) -> tuple[IngestionOutput, list]:
    """Processes a single document file."""
    doc_id = str(uuid.uuid4())
    content_hash = compute_content_hash(content)
    warnings = []

    chunks = process_document(
        content, filename, vendor_id, org_id, evaluation_setup
    )

    if not chunks:
        output = IngestionOutput(
            doc_id=doc_id,
            vendor_id=vendor_id,
            org_id=org_id,
            filename=filename,
            total_chunks=0,
            chunks_by_type={},
            filtered_chunks=0,
            extraction_triggered=False,
            quality_score=0.0,
            content_hash=content_hash,
            warnings=["No usable chunks produced from document"],
            status="failed",
        )
        critic = critic_after_ingestion(output)
        return output, [critic]

    combined_text = " ".join(c["text"] for c in chunks[:5])
    is_valid, reason = validate_extracted_text(combined_text, filename)
    if not is_valid:
        warnings.append(reason)

    chunks_by_type: dict = {}
    for chunk in chunks:
        st = chunk["section_type"]
        chunks_by_type[st] = chunks_by_type.get(st, 0) + 1

    # issue #133 — scan UNTRUSTED vendor text for prompt-injection patterns
    # BEFORE any LLM (Extraction/Explanation) consumes these chunks. Findings
    # are recorded as typed data; the Critic turns them into a HARD, pipeline-
    # blocking flag (fail-CLOSED). Config-gated and config-driven patterns.
    # The trusted first-party RFP is exempt (trusted_source=True) — see
    # run_ingestion_agent: scanning it would false-positive on legitimate
    # RFP-evaluation directive language.
    injection_findings = []
    _inj = settings.platform.injection_defence
    if not trusted_source and _inj.enabled and _inj.patterns:
        injection_findings = scan_chunks(chunks, _inj.patterns)

    req_resp = chunks_by_type.get("requirement_response", 0)
    total = len(chunks)
    quality_score = min(1.0, (
        0.4 * min(1.0, total / 20)
        + 0.4 * min(1.0, req_resp / 5)
        + 0.2 * (1.0 if is_valid else 0.3)
    ))

    coll_name = org_collection_name(org_id)
    create_collection(coll_name)

    for chunk in chunks:
        payload = {
            "chunk_id": chunk["chunk_id"],
            "text": chunk["text"],
            "section_id": chunk["section_id"],
            "section_title": chunk["section_title"],
            "section_type": chunk["section_type"],
            "priority": chunk["priority"],
            "page_number": chunk["page_number"],
            "filename": filename,
            "vendor_id": vendor_id,
            "org_id": org_id,
            "rfp_id": rfp_id,
            "doc_id": doc_id,
            # Stamp the setup this chunk belongs to so retention (the cleanup
            # job) can delete one expired setup's vectors precisely, without
            # wiping the org's other live setups (BACKLOG P2.27).
            "setup_id": evaluation_setup.setup_id,
        }
        upsert_chunk(
            collection=coll_name,
            chunk_id=chunk["chunk_id"],
            dense_vector=chunk["dense_vector"],
            sparse_indices=chunk["sparse_indices"],
            sparse_values=chunk["sparse_values"],
            payload=payload,
        )

    extraction_triggered = req_resp > 0

    output = IngestionOutput(
        doc_id=doc_id,
        vendor_id=vendor_id,
        org_id=org_id,
        filename=filename,
        total_chunks=total,
        chunks_by_type=chunks_by_type,
        filtered_chunks=0,
        extraction_triggered=extraction_triggered,
        quality_score=quality_score,
        content_hash=content_hash,
        warnings=warnings,
        status="success",
        injection_findings=injection_findings,
    )

    critic = critic_after_ingestion(output)
    return output, [critic]
