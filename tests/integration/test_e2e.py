"""
End-to-end ingestion test. Seeds PostgreSQL then ingests a vendor PDF.

Usage:
    python scripts/test_e2e.py <path_to_vendor_pdf>

This script must be run before test_extraction.py.
Populates all three PostgreSQL tables:
  evaluation_setups   — seeded before ingestion
  vendor_documents    — written after ingestion
  extracted_facts     — written after extraction (one pass per target)
"""
import asyncio
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.agents.extraction import run_extraction_agent
from app.agents.ingestion import run_ingestion_agent
from app.agents.retrieval import run_retrieval_agent
from app.core.output_models import (
    EvaluationSetup,
    ExtractionTarget,
    MandatoryCheck,
    ScoringCriterion,
)
from app.db.fact_store import save_evaluation_setup, save_vendor_document

SETUP_ID = "test-setup-e2e"
VENDOR_ID = "test-vendor-001"
ORG_ID = "00000000-0000-0000-0000-000000000001"
RFP_ID = "test-rfp-001"


def build_evaluation_setup() -> EvaluationSetup:
    extraction_targets = [
        ExtractionTarget(
            target_id="target-cert",
            name="Security Certification",
            description="Vendor security certifications (ISO 27001, SOC 2, Cyber Essentials, etc.)",
            fact_type="certification",
            is_mandatory=True,
            feeds_check_id="check-cert",
        ),
        ExtractionTarget(
            target_id="target-insurance",
            name="Professional Indemnity Insurance",
            description="Professional indemnity and public liability insurance coverage amounts",
            fact_type="insurance",
            is_mandatory=True,
            feeds_check_id="check-insurance",
        ),
        ExtractionTarget(
            target_id="target-sla",
            name="SLA Commitments",
            description="Service level agreement: response times, resolution times, uptime guarantees",
            fact_type="sla",
            is_mandatory=False,
            feeds_criterion_id="crit-sla",
        ),
        ExtractionTarget(
            target_id="target-projects",
            name="Reference Projects",
            description="Completed projects with client names, sectors, user counts and outcomes",
            fact_type="project",
            is_mandatory=False,
            feeds_criterion_id="crit-experience",
        ),
        ExtractionTarget(
            target_id="target-pricing",
            name="Pricing",
            description="Year-by-year pricing breakdown in GBP",
            fact_type="pricing",
            is_mandatory=False,
            feeds_criterion_id="crit-pricing",
        ),
    ]
    mandatory_checks = [
        MandatoryCheck(
            check_id="check-cert",
            name="Security Certification Required",
            description="Vendor must hold a current, accredited security certification",
            what_passes="Vendor holds a current, valid security certification from an accredited body",
            extraction_target_id="target-cert",
        ),
        MandatoryCheck(
            check_id="check-insurance",
            name="Professional Indemnity Required",
            description="Vendor must carry professional indemnity insurance of at least £1M",
            what_passes="Vendor carries professional indemnity insurance of at least GBP 1,000,000",
            extraction_target_id="target-insurance",
        ),
    ]
    scoring_criteria = [
        ScoringCriterion(
            criterion_id="crit-sla",
            name="SLA Quality",
            weight=0.4,
            rubric_9_10="P1 response < 30 min, uptime 99.9%+",
            rubric_6_8="P1 response < 2 hours, uptime 99.5%+",
            rubric_3_5="P1 response < 8 hours, uptime 99%+",
            rubric_0_2="No SLA commitments or metrics below 99%",
            extraction_target_ids=["target-sla"],
        ),
        ScoringCriterion(
            criterion_id="crit-experience",
            name="Relevant Experience",
            weight=0.4,
            rubric_9_10="3+ public sector projects, 10k+ users, references available",
            rubric_6_8="2+ relevant projects with measurable outcomes",
            rubric_3_5="1 relevant project or limited detail",
            rubric_0_2="No relevant projects evidenced",
            extraction_target_ids=["target-projects"],
        ),
        ScoringCriterion(
            criterion_id="crit-pricing",
            name="Pricing Competitiveness",
            weight=0.2,
            rubric_9_10="Transparent year-by-year breakdown, all costs included",
            rubric_6_8="Clear total cost with partial breakdown",
            rubric_3_5="Indicative pricing only",
            rubric_0_2="No pricing provided",
            extraction_target_ids=["target-pricing"],
        ),
    ]
    return EvaluationSetup(
        setup_id=SETUP_ID,
        org_id=ORG_ID,
        department="procurement",
        rfp_id=RFP_ID,
        rfp_confirmed=True,
        mandatory_checks=mandatory_checks,
        scoring_criteria=scoring_criteria,
        extraction_targets=extraction_targets,
        total_weight=1.0,
        confirmed_by="test-user",
        confirmed_at=datetime.now(timezone.utc),
        source="manually_defined",
    )


async def main(pdf_path: str):
    print(f"\nVendor PDF: {pdf_path}")
    print(f"Setup ID:  {SETUP_ID}")
    print(f"Vendor ID: {VENDOR_ID}")
    print(f"Org ID:    {ORG_ID}")
    print(f"RFP ID:    {RFP_ID}")

    # Step 1 — seed evaluation_setups
    print("\n[1/5] Saving EvaluationSetup to PostgreSQL...")
    setup = build_evaluation_setup()
    save_evaluation_setup(setup.model_dump(mode="json"), org_id=ORG_ID)
    print(f"      OK — setup_id={SETUP_ID} saved to evaluation_setups")

    # Step 2 — load PDF
    print(f"\n[2/5] Loading PDF: {pdf_path}")
    with open(pdf_path, "rb") as f:
        content = f.read()
    filename = os.path.basename(pdf_path)
    print(f"      OK — {len(content):,} bytes, filename={filename}")

    # Step 3 — run ingestion agent (LlamaIndex → Qdrant)
    print("\n[3/5] Running Ingestion Agent (LlamaIndex -> Qdrant)...")
    ingestion_output, ingestion_critics = await run_ingestion_agent(
        content=content,
        filename=filename,
        vendor_id=VENDOR_ID,
        org_id=ORG_ID,
        rfp_id=RFP_ID,
        evaluation_setup=setup,
    )
    print(f"      doc_id:            {ingestion_output.doc_id}")
    print(f"      status:            {ingestion_output.status}")
    print(f"      total_chunks:      {ingestion_output.total_chunks}")
    print(f"      quality_score:     {ingestion_output.quality_score:.2f}")
    print(f"      chunks_by_type:    {ingestion_output.chunks_by_type}")
    if ingestion_output.warnings:
        print(f"      warnings:          {ingestion_output.warnings}")
    if ingestion_critics:
        print(f"      critic verdict:    {ingestion_critics[0].overall_verdict}")
        if ingestion_critics[0].hard_flag_count:
            for f in ingestion_critics[0].flags:
                print(f"      HARD FLAG: {f.check_name} — {f.description}")

    if ingestion_output.status == "failed":
        print("\nERROR: Ingestion failed — aborting")
        sys.exit(1)

    # Step 4 — persist vendor_documents row
    print("\n[4/5] Saving vendor_document to PostgreSQL...")
    save_vendor_document(
        output=ingestion_output,
        org_id=ORG_ID,
        rfp_id=RFP_ID,
        setup_id=SETUP_ID,
    )
    print(f"      OK — doc_id={ingestion_output.doc_id} saved to vendor_documents")

    # Step 5 — run retrieval + extraction per target → extracted_facts
    print(f"\n[5/5] Running Retrieval + Extraction for {len(setup.extraction_targets)} targets...")
    total_facts = 0

    for i, target in enumerate(setup.extraction_targets, 1):
        print(f"\n  [{i}/{len(setup.extraction_targets)}] Target: {target.name}")

        print(f"      Retrieval: query='{target.description[:60]}...'")
        retrieval_output, retrieval_critic = await run_retrieval_agent(
            query=target.description,
            vendor_id=VENDOR_ID,
            org_id=ORG_ID,
            rfp_id=RFP_ID,
            use_hyde=False,
            use_rewriting=True,
        )
        print(f"      chunks retrieved:  {len(retrieval_output.chunks)}")
        print(f"      retrieval verdict: {retrieval_critic.overall_verdict}")

        if not retrieval_output.chunks:
            print(f"      SKIP — no chunks for this target")
            continue

        print(f"      Extraction: running LLM extraction...")
        extraction_output, extraction_critic = await run_extraction_agent(
            retrieval_output=retrieval_output,
            vendor_id=VENDOR_ID,
            org_id=ORG_ID,
            doc_id=ingestion_output.doc_id,
            setup_id=SETUP_ID,
            evaluation_setup=setup,
        )
        print(f"      extraction verdict:{extraction_critic.overall_verdict}")
        print(f"      certifications:    {len(extraction_output.certifications)}")
        print(f"      insurance:         {len(extraction_output.insurance)}")
        print(f"      slas:              {len(extraction_output.slas)}")
        print(f"      projects:          {len(extraction_output.projects)}")
        print(f"      pricing:           {len(extraction_output.pricing)}")
        print(f"      custom facts:      {len(extraction_output.extracted_facts)}")

        target_facts = (
            len(extraction_output.certifications)
            + len(extraction_output.insurance)
            + len(extraction_output.slas)
            + len(extraction_output.projects)
            + len(extraction_output.pricing)
            + len(extraction_output.extracted_facts)
        )
        total_facts += target_facts

        if extraction_critic.hard_flag_count:
            for f in extraction_critic.flags:
                if f.severity.value == "hard":
                    print(f"      HARD FLAG: {f.check_name} — {f.description}")

    print(f"\nDONE")
    print(f"  evaluation_setups: 1 row")
    print(f"  vendor_documents:  1 row  (doc_id={ingestion_output.doc_id})")
    print(f"  extracted facts:   {total_facts} facts across all targets")
    print(f"\nRun: python scripts/test_extraction.py")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python scripts/test_e2e.py <path_to_vendor_pdf>")
        sys.exit(1)

    pdf_path = sys.argv[1]
    if not os.path.exists(pdf_path):
        print(f"ERROR: File not found: {pdf_path}")
        sys.exit(1)

    try:
        asyncio.run(main(pdf_path))
    except Exception as e:
        print(f"\nERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
