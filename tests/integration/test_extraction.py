import asyncio
import sqlalchemy as sa
from app.agents.retrieval import run_retrieval_agent
from app.agents.extraction import run_extraction_agent
from app.db.fact_store import get_evaluation_setup, get_engine

async def main():
    setup_id = "test-setup-e2e"
    vendor_id = "test-vendor-001"
    org_id = "00000000-0000-0000-0000-000000000001"

    print("\nLoading EvaluationSetup from PostgreSQL...")
    setup = get_evaluation_setup(setup_id)
    print(f"Setup loaded: {setup.setup_id}")
    print(f"Extraction targets: {len(setup.extraction_targets)}")

    # Look up doc_id from vendor_documents
    with get_engine().connect() as conn:
        row = conn.execute(sa.text(
            "SELECT doc_id FROM vendor_documents "
            "WHERE vendor_id = :v AND org_id = :o ORDER BY ingested_at DESC LIMIT 1"
        ), {"v": vendor_id, "o": org_id}).fetchone()
    if not row:
        print("ERROR: No vendor_documents row found. Run test_e2e.py first.")
        return
    doc_id = str(row._mapping["doc_id"])
    print(f"Doc ID: {doc_id}")

    for target in setup.extraction_targets:
        print(f"\n{'-' * 50}")
        print(f"Target: {target.name}")

        print("\nRunning Retrieval Agent...")
        retrieval_output, retrieval_critic = await run_retrieval_agent(
            query=target.description,
            vendor_id=vendor_id,
            org_id=org_id,
            rfp_id="test-rfp-001",
            use_hyde=False,
            use_rewriting=True
        )

        print(f"Chunks retrieved:     {len(retrieval_output.chunks)}")
        print(f"Retrieval confidence: {retrieval_output.confidence}")
        print(f"Retrieval critic:     {retrieval_critic.overall_verdict}")

        if not retrieval_output.chunks:
            print("No chunks found — skipping extraction")
            continue

        print("\nRunning Extraction Agent...")
        extraction_output, extraction_critic = await run_extraction_agent(
            retrieval_output=retrieval_output,
            vendor_id=vendor_id,
            org_id=org_id,
            doc_id=doc_id,
            setup_id=setup_id,
            evaluation_setup=setup,
        )

        print(f"Extraction critic:    {extraction_critic.overall_verdict}")
        print(f"Certifications:       {len(extraction_output.certifications)}")
        print(f"Insurance:            {len(extraction_output.insurance)}")
        print(f"SLAs:                 {len(extraction_output.slas)}")
        print(f"Projects:             {len(extraction_output.projects)}")
        print(f"Pricing:              {len(extraction_output.pricing)}")
        print(f"Custom facts:         {len(extraction_output.extracted_facts)}")

        if extraction_output.extracted_facts:
            print("\nSample custom facts:")
            for fact in extraction_output.extracted_facts[:3]:
                print(f"  {fact.target_id}: {fact.text_value or fact.numeric_value or fact.boolean_value}")
                print(f"  Quote: {fact.grounding_quote[:80]}")

if __name__ == "__main__":
    asyncio.run(main())
