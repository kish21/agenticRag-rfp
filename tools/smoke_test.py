#!/usr/bin/env python3
"""
smoke_test.py — Step-pause-verify pipeline runner for all 9 agents
===================================================================
Mirrors the exact same code path as the UI (POST /api/v1/evaluate/start).
Runs one agent at a time, persists state between runs, prints verbose
output so the broken agent can be identified.

Usage:
    python tools/smoke_test.py --reset

    # Step 1 — mirrors POST /api/v1/evaluate/start exactly
    python tools/smoke_test.py --agent rfp \\
        --rfp data/documents/RFP_IT_Managed_Services_MFS_2026.pdf \\
        --criteria data/documents/Vendor_Selection_Criteria_MFS.csv \\
        --vendor-pdf data/documents/Acme_ClearPath_Proposal.pdf \\
        --vendor-pdf data/documents/nightbuilb_Apex_Technology_Proposal.pdf

    # Steps 2–9 — one vendor at a time, then shared agents
    python tools/smoke_test.py --agent ingestion --vendor Acme_ClearPath_Proposal
    python tools/smoke_test.py --agent ingestion --vendor nightbuilb_Apex_Technology_Proposal
    python tools/smoke_test.py --agent extraction
    python tools/smoke_test.py --agent retrieval
    python tools/smoke_test.py --agent planner
    python tools/smoke_test.py --agent evaluation
    python tools/smoke_test.py --agent comparator
    python tools/smoke_test.py --agent decision
    python tools/smoke_test.py --agent explanation

State is persisted in .smoke_test_state.json between runs.
Run --reset before a fresh run to wipe test data (smoke org only).

Environment: Requires running Postgres + Qdrant. No mocks.
"""
import argparse
import asyncio
import json
import os
import sys
import uuid
from pathlib import Path
from datetime import datetime

# Windows terminals default to cp1252 — force UTF-8 so box-drawing chars print correctly
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if sys.stderr.encoding and sys.stderr.encoding.lower() != "utf-8":
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# ── Paths ─────────────────────────────────────────────────────────────────────
ROOT        = Path(__file__).parent.parent
STATE_FILE  = ROOT / ".smoke_test_state.json"
sys.path.insert(0, str(ROOT))

# ── Fixed smoke test identifiers ──────────────────────────────────────────────
SMOKE_ORG_ID        = "00000000-0000-0000-0000-000000000001"
SMOKE_VENDOR_ID     = "smoke_vendor_apex"
SMOKE_RFP_ID        = "smoke_rfp_001"
SMOKE_DEPARTMENT    = "IT"
SMOKE_RFP_TITLE     = "IT Managed Services 2026"
SMOKE_CONTRACT_VALUE= 750_000.0

# ── Default CSV criteria (used if no --criteria file provided) ────────────────
DEFAULT_CRITERIA_CSV = """\
criterion_id,name,weight,description
c01,ISO 27001 Certification,0.25,Vendor must hold a current ISO 27001 certification
c02,SLA Uptime Guarantee,0.30,Vendor must guarantee 99.9% uptime with documented penalties
c03,Past Project Experience,0.20,Minimum 3 enterprise projects over GBP 500k in last 3 years
c04,Incident Response Time,0.15,P1 incidents responded within 15 minutes
c05,Data Residency,0.10,All data must remain in UK/EU data centres
"""

# ── State helpers ──────────────────────────────────────────────────────────────

def load_state() -> dict:
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text())
    return {}


def save_state(state: dict) -> None:
    STATE_FILE.write_text(json.dumps(state, indent=2, default=str))


def require_state(key: str, state: dict, agent_name: str) -> object:
    if key not in state:
        print(f"\n[ABORT] {agent_name} requires '{key}' in state.")
        print(f"        Run the preceding agents first.")
        sys.exit(1)
    return state[key]


# ── Verbose print helpers ──────────────────────────────────────────────────────

def section(title: str) -> None:
    print(f"\n{'─' * 60}")
    print(f"  {title}")
    print(f"{'─' * 60}")


def kv(key: str, value: object) -> None:
    print(f"  {key:<30} {value}")


def fact_row(label: str, fact: object) -> None:
    d = fact if isinstance(fact, dict) else (fact.model_dump() if hasattr(fact, "model_dump") else vars(fact))
    print(f"\n  ── {label}")
    for k, v in d.items():
        if v is None or v == [] or v == "":
            continue
        val_str = str(v)
        if len(val_str) > 120:
            val_str = val_str[:120] + "…"
        print(f"     {k:<26} {val_str}")


def critic_summary(critic) -> None:
    section("CRITIC VERDICT")
    verdict = getattr(critic, "overall_verdict", "?")
    color   = "\033[32m" if str(verdict) == "CriticVerdict.PASS" else "\033[33m" if "SOFT" in str(verdict) else "\033[31m"
    reset   = "\033[0m"
    print(f"  {color}{verdict}{reset}")
    flags = getattr(critic, "flags", [])
    for f in flags:
        sev = getattr(f, "severity", "")
        msg = getattr(f, "message", "")
        print(f"  [{sev}] {msg}")
    if not flags:
        print("  No flags raised.")


# ── --reset ────────────────────────────────────────────────────────────────────

def do_reset() -> None:
    print(f"\nResetting smoke test data for org_id={SMOKE_ORG_ID}…")

    # PostgreSQL: delete rows for smoke org
    try:
        from app.db.fact_store import get_engine
        import sqlalchemy as sa
        engine = get_engine()
        tables = [
            "extracted_certifications", "extracted_insurance",
            "extracted_slas", "extracted_projects", "extracted_pricing",
            "extracted_facts", "evaluation_runs",
        ]
        with engine.begin() as conn:
            for t in tables:
                result = conn.execute(
                    sa.text(f"DELETE FROM {t} WHERE org_id::text = :oid"),
                    {"oid": SMOKE_ORG_ID},
                )
                print(f"  Deleted {result.rowcount:>4} rows from {t}")
        print("  PostgreSQL: done")
    except Exception as e:
        print(f"  PostgreSQL: SKIP ({e})")

    # Qdrant: delete vectors for smoke org
    try:
        from qdrant_client import QdrantClient
        from qdrant_client.http import models as qm
        from app.config import settings
        client = QdrantClient(host=settings.qdrant_host, port=settings.qdrant_port)
        collection = f"{settings.qdrant_collection_prefix}_{SMOKE_ORG_ID}"
        try:
            client.delete(
                collection_name=collection,
                points_selector=qm.FilterSelector(
                    filter=qm.Filter(
                        must=[qm.FieldCondition(key="org_id", match=qm.MatchValue(value=SMOKE_ORG_ID))]
                    )
                ),
            )
            print(f"  Qdrant: deleted vectors from {collection}")
        except Exception:
            print(f"  Qdrant: collection {collection} not found or already empty")
    except Exception as e:
        print(f"  Qdrant: SKIP ({e})")

    # State file
    if STATE_FILE.exists():
        STATE_FILE.unlink()
        print("  Deleted .smoke_test_state.json")

    print("\n[OK] Reset complete. Ready for: --agent ingestion --pdf <path>\n")


# ── Step 0: RFP setup — mirrors POST /api/v1/evaluate/start exactly ───────────

async def run_rfp(rfp_path: str, vendor_pdfs: list[str], criteria_path: str | None, state: dict) -> None:
    section("STEP 0 — RFP SETUP  (mirrors POST /api/v1/evaluate/start)")

    rfp_pdf = Path(rfp_path)
    if not rfp_pdf.exists():
        print(f"[ABORT] RFP PDF not found: {rfp_pdf}")
        sys.exit(1)

    rfp_bytes = rfp_pdf.read_bytes()
    kv("RFP file",  rfp_pdf.name)
    kv("RFP size",  f"{len(rfp_bytes):,} bytes")

    criteria_bytes: bytes | None = None
    criteria_filename: str | None = None
    if criteria_path:
        cp = Path(criteria_path)
        if cp.exists():
            criteria_bytes   = cp.read_bytes()
            criteria_filename = cp.name
            kv("Criteria file", cp.name)
        else:
            print(f"[WARN] Criteria file not found: {cp} — continuing without it")

    vendor_file_map: dict[str, tuple[bytes, str]] = {}
    for vpath in vendor_pdfs:
        vp = Path(vpath)
        if not vp.exists():
            print(f"[ABORT] Vendor PDF not found: {vp}")
            sys.exit(1)
        vid = vp.stem
        vendor_file_map[vid] = (vp.read_bytes(), vp.name)
        kv(f"Vendor PDF", f"{vp.name}  →  vendor_id={vid}")

    run_id   = str(uuid.uuid4())
    rfp_id   = f"rfp-{run_id[:8]}"
    setup_id = f"setup-{run_id[:8]}"
    vendor_list = list(vendor_file_map.keys())

    # ── Criteria extraction (same calls as the API) ────────────────────────────
    from app.domain.criteria import (
        get_org_criteria, get_dept_criteria,
        extract_rfp_text, extract_criteria_from_user_sheet,
        merge_criteria,
    )

    section("EXTRACTING RFP TEXT + CRITERIA")
    rfp_text      = extract_rfp_text(rfp_bytes)
    org_criteria  = get_org_criteria(SMOKE_ORG_ID)
    dept_criteria = get_dept_criteria(SMOKE_ORG_ID, SMOKE_DEPARTMENT)
    kv("RFP text chars",   len(rfp_text))
    kv("Org criteria",     len(org_criteria))
    kv("Dept criteria",    len(dept_criteria))

    user_criteria: dict | None = None
    if criteria_bytes and criteria_filename:
        user_criteria = await extract_criteria_from_user_sheet(criteria_bytes, criteria_filename)
        kv("User mandatory checks", len((user_criteria or {}).get("mandatory_checks", [])))
        kv("User scoring criteria", len((user_criteria or {}).get("scoring_criteria", [])))

    from app.domain.criteria import extract_criteria_from_rfp, detect_and_fill_gaps
    print("\n  Extracting criteria from RFP text via LLM…")
    rfp_criteria = await extract_criteria_from_rfp(rfp_text)
    kv("RFP mandatory checks", len(rfp_criteria.get("mandatory_checks", [])))
    kv("RFP scoring criteria", len(rfp_criteria.get("scoring_criteria", [])))

    merged = merge_criteria(
        org_criteria=org_criteria,
        dept_criteria=dept_criteria,
        rfp_criteria=rfp_criteria,
        department=SMOKE_DEPARTMENT,
        rfp_id=rfp_id,
        org_id=SMOKE_ORG_ID,
        user_criteria=user_criteria,
    )

    print("\n  Running gap detection…")
    merged, gaps_report = await detect_and_fill_gaps(merged, SMOKE_DEPARTMENT)
    if gaps_report["has_gaps"]:
        section("GAPS DETECTED + FILLED")
        if gaps_report["score_guides_generated"]:
            print(f"  Score guides generated for {len(gaps_report['score_guides_generated'])} criteria:")
            for g in gaps_report["score_guides_generated"]:
                print(f"    ⚠  {g['criterion_name']}  [source: generated — needs customer review]")
        if gaps_report["mandatory_checks_suggested"]:
            print(f"\n  Mandatory checks suggested ({len(gaps_report['mandatory_checks_suggested'])}):")
            for m in gaps_report["mandatory_checks_suggested"]:
                print(f"    ⚠  {m['name']}  [source: generated — needs customer review]")
    else:
        kv("Gap detection", "no gaps found — all criteria have score guides")

    from app.schemas.output_models import (
        EvaluationSetup, MandatoryCheck, ScoringCriterion, ExtractionTarget,
    )

    def _to_model(cls, raw):
        if isinstance(raw, cls):
            return raw
        try:
            return cls(**raw)
        except Exception:
            return raw

    mandatory_checks     = [_to_model(MandatoryCheck,     c) for c in (merged["mandatory_checks"] or [])]
    scoring_criteria_list= [_to_model(ScoringCriterion,   c) for c in (merged["scoring_criteria"] or [])]
    extraction_targets   = [_to_model(ExtractionTarget,    c) for c in (merged.get("extraction_targets") or [])]

    if not mandatory_checks:
        mandatory_checks = [MandatoryCheck(
            check_id="chk-default-001",
            name="Legal entity registration",
            description="Vendor must be a registered legal entity.",
            what_passes="Registration number provided.",
            extraction_target_id="ext-legal-default",
        )]
    if not scoring_criteria_list:
        scoring_criteria_list = [
            ScoringCriterion(criterion_id="crit-default-tech",   name="Technical capability", weight=0.50,
                             rubric_9_10="Fully meets requirements.", rubric_6_8="Meets most.",
                             rubric_3_5="Partially meets.", rubric_0_2="Does not meet.",
                             extraction_target_ids=["ext-sla-default"]),
            ScoringCriterion(criterion_id="crit-default-comm",   name="Commercial value",      weight=0.50,
                             rubric_9_10="Best value.", rubric_6_8="Competitive.",
                             rubric_3_5="Above-market.", rubric_0_2="Pricing absent.",
                             extraction_target_ids=["ext-pricing-default"]),
        ]

    evaluation_setup = EvaluationSetup(
        setup_id=setup_id,
        org_id=SMOKE_ORG_ID,
        department=SMOKE_DEPARTMENT,
        rfp_id=rfp_id,
        rfp_confirmed=False,
        confirmed_by="smoke-test",
        confirmed_at=None,
        source=merged.get("source", "merged"),
        mandatory_checks=mandatory_checks,
        scoring_criteria=scoring_criteria_list,
        extraction_targets=extraction_targets,
        total_weight=round(sum(
            float(c.weight) if hasattr(c, "weight") else float(c.get("weight", 0))
            for c in scoring_criteria_list
        ), 3),
    )

    section("EVALUATION SETUP BUILT")
    kv("setup_id",          setup_id)
    kv("mandatory checks",  len(mandatory_checks))
    kv("scoring criteria",  len(scoring_criteria_list))
    kv("extraction targets",len(extraction_targets))
    kv("total_weight",      evaluation_setup.total_weight)
    kv("source",            evaluation_setup.source)
    print("\n  Scoring criteria:")
    for sc in scoring_criteria_list:
        w  = getattr(sc, "weight", "?")
        n  = getattr(sc, "name", "?")
        r9 = getattr(sc, "rubric_9_10", "")
        r6 = getattr(sc, "rubric_6_8",  "")
        r3 = getattr(sc, "rubric_3_5",  "")
        r0 = getattr(sc, "rubric_0_2",  "")
        has_guide = any([r9, r6, r3, r0])
        guide_tag = "  [score guide: YES]" if has_guide else "  [score guide: MISSING]"
        print(f"\n    {n}  weight={w}{guide_tag}")
        if r9: print(f"      Top score:     {r9[:100]}")
        if r6: print(f"      Good score:    {r6[:100]}")
        if r3: print(f"      Average score: {r3[:100]}")
        if r0: print(f"      Poor score:    {r0[:100]}")

    # ── Persist to PostgreSQL (same as the API) ────────────────────────────────
    from app.db.fact_store import get_engine, save_evaluation_setup
    import hashlib, sqlalchemy as sa

    section("SAVING TO POSTGRESQL")
    setup_dict = evaluation_setup.model_dump(mode="json")
    save_evaluation_setup(setup_dict, org_id=SMOKE_ORG_ID)
    kv("evaluation_setup", "saved")

    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(sa.text("""
            INSERT INTO evaluation_runs
                (run_id, org_id, rfp_id, setup_id, rfp_title, department,
                 rfp_filename, rfp_bytes, status, vendor_ids, contract_value,
                 vendor_names, created_by_email, creator_dept_id, currency)
            VALUES
                (CAST(:run_id AS uuid), CAST(:org_id AS uuid), :rfp_id, :setup_id,
                 :rfp_title, :department, :rfp_filename, :rfp_bytes,
                 'pending_confirm', :vendor_ids, :contract_value,
                 CAST(:vendor_names AS jsonb), :created_by_email, :creator_dept_id, :currency)
        """), {
            "run_id":           run_id,
            "org_id":           SMOKE_ORG_ID,
            "rfp_id":           rfp_id,
            "setup_id":         setup_id,
            "rfp_title":        SMOKE_RFP_TITLE,
            "department":       SMOKE_DEPARTMENT,
            "rfp_filename":     rfp_pdf.name,
            "rfp_bytes":        rfp_bytes,
            "vendor_ids":       vendor_list,
            "contract_value":   SMOKE_CONTRACT_VALUE,
            "vendor_names":     "{}",
            "created_by_email": "smoke@test.local",
            "creator_dept_id":  None,
            "currency":         "GBP",
        })
        kv("evaluation_runs", "inserted")

        for vid, (vbytes, vfilename) in vendor_file_map.items():
            content_hash = hashlib.sha256(vbytes).hexdigest()
            conn.execute(sa.text("""
                INSERT INTO vendor_documents
                    (org_id, vendor_id, rfp_id, setup_id, filename,
                     file_name, file_bytes, content_hash)
                VALUES
                    (CAST(:org_id AS uuid), :vendor_id, :rfp_id, :setup_id,
                     :filename, :file_name, :file_bytes, :content_hash)
                ON CONFLICT (org_id, vendor_id, rfp_id, content_hash) DO NOTHING
            """), {
                "org_id":        SMOKE_ORG_ID,
                "vendor_id":     vid,
                "rfp_id":        rfp_id,
                "setup_id":      setup_id,
                "filename":      vfilename,
                "file_name":     vfilename,
                "file_bytes":    vbytes,
                "content_hash":  content_hash,
            })
            kv(f"vendor_documents[{vid}]", "inserted")

    state.update({
        "run_id":      run_id,
        "org_id":      SMOKE_ORG_ID,
        "rfp_id":      rfp_id,
        "setup_id":    setup_id,
        "vendor_ids":  vendor_list,
        "gaps_report": gaps_report,
    })
    save_state(state)
    print(f"\n  run_id:    {run_id}")
    print(f"  rfp_id:    {rfp_id}")
    print(f"  setup_id:  {setup_id}")
    print(f"\n[OK] RFP SETUP DONE — {len(vendor_list)} vendor(s) registered.")
    print(f"     Next: --agent ingestion --vendor {vendor_list[0]}\n")


# ── Agent 1: Ingestion ─────────────────────────────────────────────────────────

async def run_ingestion(vendor_id_or_pdf: str, state: dict) -> None:
    section("AGENT 1 — INGESTION")

    org_id = state.get("org_id", SMOKE_ORG_ID)
    rfp_id = state.get("rfp_id")
    doc_id = str(uuid.uuid4())

    # Resolve vendor bytes: from DB (after --agent rfp) or from a direct --pdf path
    file_bytes: bytes | None = None
    filename: str = ""
    vendor_id: str = ""

    if vendor_id_or_pdf and Path(vendor_id_or_pdf).exists():
        # Legacy / override: direct PDF path
        pdf = Path(vendor_id_or_pdf)
        file_bytes = pdf.read_bytes()
        filename   = pdf.name
        vendor_id  = pdf.stem
    elif vendor_id_or_pdf:
        # vendor_id passed — read bytes from vendor_documents table
        from app.db.fact_store import get_engine
        import sqlalchemy as sa
        engine = get_engine()
        with engine.connect() as conn:
            row = conn.execute(sa.text("""
                SELECT file_bytes, file_name FROM vendor_documents
                WHERE org_id = CAST(:org_id AS uuid)
                  AND vendor_id = :vendor_id
                ORDER BY ingested_at DESC LIMIT 1
            """), {"org_id": org_id, "vendor_id": vendor_id_or_pdf}).fetchone()
        if not row:
            print(f"[ABORT] No vendor document found for vendor_id={vendor_id_or_pdf}")
            print("        Run --agent rfp first, or pass a --pdf path directly.")
            sys.exit(1)
        file_bytes = bytes(row[0])
        filename   = row[1]
        vendor_id  = vendor_id_or_pdf
    else:
        print("[ABORT] --agent ingestion requires --vendor <vendor_id> or --pdf <path>")
        sys.exit(1)

    run_id = state.get("run_id", str(uuid.uuid4()))

    kv("PDF file",  filename)
    kv("File size", f"{len(file_bytes):,} bytes")
    kv("doc_id",    doc_id)
    kv("vendor_id", vendor_id)
    kv("org_id",    org_id)

    from app.agents.ingestion import run_ingestion_agent
    from app.agents.critic import critic_after_ingestion
    from app.schemas.output_models import EvaluationSetup
    from app.db.fact_store import get_engine
    import sqlalchemy as sa, json as _json

    # Load EvaluationSetup from DB
    _engine = get_engine()
    with _engine.connect() as _conn:
        _row = _conn.execute(sa.text(
            "SELECT setup_json FROM evaluation_setups WHERE rfp_id = :rfp_id AND org_id = CAST(:org_id AS uuid) ORDER BY created_at DESC LIMIT 1"
        ), {"rfp_id": rfp_id, "org_id": org_id}).fetchone()
    if not _row:
        print(f"[ABORT] No evaluation_setup found for rfp_id={rfp_id}")
        sys.exit(1)
    _raw = _row[0]
    evaluation_setup = EvaluationSetup.model_validate(_raw if isinstance(_raw, dict) else _json.loads(_raw))

    print("\n  Running ingestion agent…")
    output, critics = await run_ingestion_agent(
        content=file_bytes,
        filename=filename,
        vendor_id=vendor_id,
        org_id=org_id,
        rfp_id=rfp_id,
        evaluation_setup=evaluation_setup,
    )

    section("INGESTION OUTPUT")
    kv("Total chunks", output.total_chunks)
    kv("Status", output.status)
    kv("Quality score", f"{output.quality_score:.2f}" if output.quality_score is not None else "n/a")
    if output.chunks_by_type:
        kv("Chunks by type", str(output.chunks_by_type))
    if output.warnings:
        for w in output.warnings:
            print(f"  [WARNING] {w}")

    critic = critic_after_ingestion(output)
    critic_summary(critic)

    from app.schemas.output_models import CriticVerdict
    if critic.overall_verdict == CriticVerdict.BLOCKED:
        print("\n[HARD BLOCK] Ingestion critic blocked. Fix issues above before continuing.")
        sys.exit(1)

    # Accumulate per-vendor ingestion state (supports multiple vendors)
    ingested = state.get("ingested_vendors", {})
    ingested[vendor_id] = {"doc_id": doc_id, "chunk_count": output.total_chunks}
    state.update({
        "run_id":             run_id,
        "org_id":             org_id,
        "vendor_id":          vendor_id,   # last ingested — used by extraction
        "doc_id":             doc_id,
        "ingested_vendors":   ingested,
        "ingestion_chunk_ids": [],
        "ingestion_chunk_count": output.total_chunks,
    })
    save_state(state)
    remaining = [v for v in state.get("vendor_ids", []) if v not in ingested]
    if remaining:
        print(f"\n[OK] INGESTION DONE — {output.total_chunks} chunks indexed.")
        print(f"     Next vendor to ingest: --agent ingestion --vendor {remaining[0]}\n")
    else:
        print(f"\n[OK] INGESTION DONE — {output.total_chunks} chunks indexed. All vendors ingested.")
        print(f"     Next: --agent extraction\n")


# ── Agent 2: Extraction ────────────────────────────────────────────────────────

async def run_extraction(state: dict) -> None:
    section("AGENT 2 — EXTRACTION")

    run_id    = require_state("run_id",    state, "extraction")
    org_id    = require_state("org_id",    state, "extraction")
    vendor_id = require_state("vendor_id", state, "extraction")
    doc_id    = require_state("doc_id",    state, "extraction")

    kv("org_id",    org_id)
    kv("vendor_id", vendor_id)
    kv("doc_id",    doc_id)

    # Build a minimal EvaluationSetup from default criteria
    from app.schemas.output_models import EvaluationSetup, MandatoryCheck, ScoringCriterion
    setup_id = str(uuid.uuid4())
    evaluation_setup = EvaluationSetup(
        setup_id=setup_id, org_id=org_id, rfp_id=SMOKE_RFP_ID,
        mandatory_checks=[], scoring_criteria=[], extraction_targets=[],
    )

    # Build RetrievalOutput from stored chunks (retrieve all for extraction)
    from app.agents.retrieval import run_retrieval_agent
    from app.schemas.output_models import EvaluationSetup as ES

    print("\n  Retrieving chunks for extraction…")
    retrieval_output = await run_retrieval_agent(
        query="vendor certifications SLA insurance projects pricing",
        vendor_id=vendor_id,
        org_id=org_id,
        top_k=50,
    )
    kv("Chunks retrieved", len(retrieval_output.chunks))

    from app.agents.extraction import run_extraction_agent
    print("\n  Running extraction agent…")
    output, critic = await run_extraction_agent(
        retrieval_output=retrieval_output,
        vendor_id=vendor_id,
        org_id=org_id,
        doc_id=doc_id,
        setup_id=setup_id,
        evaluation_setup=evaluation_setup,
        run_id=run_id,
    )

    section("EXTRACTED FACTS")
    fact_groups = {
        "certifications": getattr(output, "certifications", []),
        "insurance":      getattr(output, "insurance",      []),
        "slas":           getattr(output, "slas",           []),
        "projects":       getattr(output, "projects",       []),
        "pricing":        getattr(output, "pricing",        []),
        "extracted_facts":getattr(output, "extracted_facts",[]),
    }
    total_facts = 0
    for ftype, facts in fact_groups.items():
        kv(ftype, len(facts))
        total_facts += len(facts)
        for f in facts:
            fact_row(ftype.upper(), f)

    kv("extraction_completeness", f"{output.extraction_completeness:.2f}")
    kv("hallucination_risk",      f"{output.hallucination_risk:.2f}")

    if output.warnings:
        section("WARNINGS")
        for w in output.warnings:
            print(f"  ⚠  {w}")

    critic_summary(critic)

    from app.schemas.output_models import CriticVerdict
    if critic.overall_verdict == CriticVerdict.BLOCKED:
        print("\n[HARD BLOCK] Extraction critic blocked. Fix issues above before continuing.")
        sys.exit(1)

    state.update({
        "setup_id":    setup_id,
        "extraction_total": total_facts,
    })
    save_state(state)
    print(f"\n[OK] EXTRACTION DONE — {total_facts} facts stored. Ready for: --agent retrieval\n")


# ── Agent 3: Retrieval ─────────────────────────────────────────────────────────

async def run_retrieval(state: dict) -> None:
    section("AGENT 3 — RETRIEVAL")

    org_id    = require_state("org_id",    state, "retrieval")
    vendor_id = require_state("vendor_id", state, "retrieval")

    query = "vendor SLA uptime guarantee ISO 27001 certification incident response"
    kv("query", query)
    kv("org_id",    org_id)
    kv("vendor_id", vendor_id)

    from app.agents.retrieval import run_retrieval_agent

    print("\n  Running retrieval agent (with HyDE + BGE reranker)…")
    output = await run_retrieval_agent(
        query=query,
        vendor_id=vendor_id,
        org_id=org_id,
        top_k=10,
    )

    section("TOP 10 RETRIEVED CHUNKS")
    for i, c in enumerate(output.chunks[:10], 1):
        score = getattr(c, "score", None)
        rerank_score = getattr(c, "rerank_score", None)
        print(f"\n  [{i:02d}] chunk_id={c.chunk_id}")
        print(f"       score={score}  rerank_score={rerank_score}")
        print(f"       text: {c.text[:150]!r}")

    if hasattr(output, "hyde_query") and output.hyde_query:
        section("HYDE-EXPANDED QUERY")
        print(f"  {output.hyde_query[:300]}")

    from app.agents.critic import critic_after_retrieval
    critic = critic_after_retrieval(output)
    critic_summary(critic)

    from app.schemas.output_models import CriticVerdict
    if critic.overall_verdict == CriticVerdict.BLOCKED:
        print("\n[HARD BLOCK] Retrieval critic blocked. Fix issues above before continuing.")
        sys.exit(1)

    state["retrieval_chunk_count"] = len(output.chunks)
    save_state(state)
    print(f"\n[OK] RETRIEVAL DONE — {len(output.chunks)} chunks returned. Ready for: --agent planner\n")


# ── Agent 4: Planner ──────────────────────────────────────────────────────────

async def run_planner(state: dict) -> None:
    section("AGENT 4 — PLANNER")

    org_id   = require_state("org_id",   state, "planner")
    setup_id = require_state("setup_id", state, "planner")

    # Load EvaluationSetup from PostgreSQL — same object the UI built in run_rfp
    from app.db.fact_store import get_engine
    from app.schemas.output_models import EvaluationSetup
    import sqlalchemy as sa

    engine = get_engine()
    with engine.connect() as conn:
        row = conn.execute(sa.text("""
            SELECT setup_json FROM evaluation_setups
            WHERE setup_id = :setup_id AND org_id = CAST(:org_id AS uuid)
            LIMIT 1
        """), {"setup_id": setup_id, "org_id": org_id}).fetchone()

    if not row:
        print(f"[ABORT] EvaluationSetup not found for setup_id={setup_id}")
        print("        Run --agent rfp first.")
        sys.exit(1)

    import json
    evaluation_setup = EvaluationSetup(**json.loads(row[0]))
    vendor_ids = state.get("vendor_ids", [SMOKE_VENDOR_ID])

    section("CRITERIA FROM DATABASE")
    for sc in evaluation_setup.scoring_criteria:
        print(f"  {getattr(sc,'criterion_id',''):<20} {getattr(sc,'name',''):<40} weight={getattr(sc,'weight','?')}")

    from app.agents.planner import run_planner_agent
    print("\n  Running planner agent…")
    output = await run_planner_agent(
        criteria=[sc.model_dump() for sc in evaluation_setup.scoring_criteria],
        vendor_ids=vendor_ids,
        org_id=org_id,
    )

    section("TASK DAG")
    tasks = getattr(output, "tasks", [])
    kv("Total tasks", len(tasks))
    for t in tasks:
        deps = getattr(t, "depends_on", [])
        print(f"  {getattr(t,'task_id',''):<30} agent={getattr(t,'assigned_agent','?'):<14} priority={getattr(t,'priority','?')}  deps={deps}")

    from app.agents.critic import critic_after_planner
    critic = critic_after_planner(output)
    critic_summary(critic)

    from app.schemas.output_models import CriticVerdict
    if critic.overall_verdict == CriticVerdict.BLOCKED:
        print("\n[HARD BLOCK] Planner critic blocked. Fix issues above before continuing.")
        sys.exit(1)

    state.update({
        "planner_task_count": len(tasks),
    })
    save_state(state)
    print(f"\n[OK] PLANNER DONE — {len(tasks)} tasks in DAG. Ready for: --agent evaluation\n")


# ── Agent 5: Evaluation ───────────────────────────────────────────────────────

async def run_evaluation(state: dict) -> None:
    section("AGENT 5 — EVALUATION  ⚠  SUSPECTED PROBLEM AREA")

    org_id    = require_state("org_id",    state, "evaluation")
    vendor_id = require_state("vendor_id", state, "evaluation")
    setup_id  = require_state("setup_id",  state, "evaluation")

    kv("org_id",    org_id)
    kv("vendor_id", vendor_id)
    kv("setup_id",  setup_id)

    # Build EvaluationSetup from saved criteria
    criteria_rows = state.get("criteria_rows", [])
    if not criteria_rows:
        import csv, io
        criteria_rows = list(csv.DictReader(io.StringIO(DEFAULT_CRITERIA_CSV)))

    from app.schemas.output_models import EvaluationSetup, ScoringCriterion, MandatoryCheck
    scoring = [
        ScoringCriterion(
            criterion_id=r.get("criterion_id", f"c{i}"),
            name=r.get("name", ""),
            weight=float(r.get("weight", 0.0)),
            source="csv",
        )
        for i, r in enumerate(criteria_rows)
    ]
    evaluation_setup = EvaluationSetup(
        setup_id=setup_id, org_id=org_id, rfp_id=SMOKE_RFP_ID,
        mandatory_checks=[], scoring_criteria=scoring, extraction_targets=[],
    )

    from app.agents.evaluation import run_evaluation_agent
    print("\n  Running evaluation agent (reads PostgreSQL facts, NOT Qdrant)…")

    # Monkey-patch call_llm to capture raw LLM reasoning
    raw_llm_calls: list[dict] = []
    import app.providers.llm as _llm_mod
    _orig_call_llm = _llm_mod.call_llm

    async def _capturing_call_llm(messages, **kwargs):
        result = await _orig_call_llm(messages, **kwargs)
        raw_llm_calls.append({"messages": messages, "response": result})
        return result

    _llm_mod.call_llm = _capturing_call_llm
    try:
        output, critic = await run_evaluation_agent(
            vendor_id=vendor_id,
            org_id=org_id,
            evaluation_setup=evaluation_setup,
            run_id=state.get("run_id", ""),
        )
    finally:
        _llm_mod.call_llm = _orig_call_llm

    section("CRITERION SCORES")
    scores = getattr(output, "criterion_scores", [])
    for s in scores:
        cid     = getattr(s, "criterion_id", "?")
        raw     = getattr(s, "raw_score", "?")
        wt      = getattr(s, "weighted_contribution", "?")
        conf    = getattr(s, "confidence", "?")
        band    = getattr(s, "rubric_band_applied", "?")
        rationale = getattr(s, "score_rationale", "")
        evidence  = getattr(s, "evidence_used", [])
        print(f"\n  {cid}")
        print(f"    raw_score={raw}  weighted={wt:.3f}  confidence={conf}  band={band!r}")
        print(f"    evidence ({len(evidence)} items):")
        for e in evidence[:3]:
            print(f"      · {str(e)[:120]}")
        print(f"    rationale: {rationale[:200]}")

    kv("\n  total_weighted_score", getattr(output, "total_weighted_score", "?"))
    kv("score_confidence",     getattr(output, "score_confidence", "?"))
    kv("overall_compliance",   getattr(output, "overall_compliance", "?"))

    section("RAW LLM REASONING (first call)")
    if raw_llm_calls:
        first = raw_llm_calls[0]
        print(f"  {len(raw_llm_calls)} LLM call(s) total")
        print(f"\n  RESPONSE:\n  {first['response'][:600]}")
    else:
        print("  No LLM calls captured.")

    critic_summary(critic)

    from app.schemas.output_models import CriticVerdict
    if critic.overall_verdict == CriticVerdict.BLOCKED:
        print("\n[HARD BLOCK] Evaluation critic blocked. Fix issues above before continuing.")
        sys.exit(1)

    state.update({
        "evaluation_total_score": getattr(output, "total_weighted_score", 0),
        "evaluation_score_confidence": getattr(output, "score_confidence", 0),
    })
    save_state(state)
    score = getattr(output, "total_weighted_score", 0)
    print(f"\n[OK] EVALUATION DONE — total score: {score}. Ready for: --agent comparator\n")


# ── Agent 6: Comparator ───────────────────────────────────────────────────────

async def run_comparator(state: dict) -> None:
    section("AGENT 6 — COMPARATOR")

    org_id   = require_state("org_id",   state, "comparator")
    setup_id = require_state("setup_id", state, "comparator")

    from app.agents.comparator import run_comparator_agent
    print("\n  Running comparator agent…")
    output, critic = await run_comparator_agent(
        org_id=org_id,
        setup_id=setup_id,
        vendor_ids=[SMOKE_VENDOR_ID],
        run_id=state.get("run_id", ""),
    )

    section("RANKING")
    rankings = getattr(output, "vendor_rankings", []) or getattr(output, "rankings", [])
    for v in rankings:
        name  = getattr(v, "vendor_id", "?")
        score = getattr(v, "total_score", "?")
        rank  = getattr(v, "rank", "?")
        print(f"  #{rank}  {name:<30}  score={score}")

    critic_summary(critic)

    from app.schemas.output_models import CriticVerdict
    if critic.overall_verdict == CriticVerdict.BLOCKED:
        print("\n[HARD BLOCK] Comparator critic blocked.")
        sys.exit(1)

    state["comparator_vendor_count"] = len(rankings)
    save_state(state)
    print(f"\n[OK] COMPARATOR DONE — {len(rankings)} vendors ranked. Ready for: --agent decision\n")


# ── Agent 7: Decision ─────────────────────────────────────────────────────────

async def run_decision(state: dict) -> None:
    section("AGENT 7 — DECISION")

    org_id   = require_state("org_id",   state, "decision")
    setup_id = require_state("setup_id", state, "decision")

    from app.agents.decision import run_decision_agent
    print("\n  Running decision agent…")
    output, critic = await run_decision_agent(
        org_id=org_id,
        setup_id=setup_id,
        vendor_ids=[SMOKE_VENDOR_ID],
        run_id=state.get("run_id", ""),
    )

    section("DECISION OUTPUT")
    shortlisted = getattr(output, "shortlisted_vendors", [])
    rejected    = getattr(output, "rejected_vendors",    [])
    routing     = getattr(output, "approval_routing",    None)
    kv("shortlisted", len(shortlisted))
    kv("rejected",    len(rejected))
    kv("decision_confidence", getattr(output, "decision_confidence", "?"))
    kv("requires_human_review", getattr(output, "requires_human_review", "?"))

    if routing:
        kv("approval_tier",   getattr(routing, "approval_tier", "?"))
        kv("approver_role",   getattr(routing, "approver_role", "?"))
        kv("sla_hours",       getattr(routing, "sla_hours", "?"))

    for v in shortlisted:
        fact_row(f"SHORTLISTED: {getattr(v,'vendor_name','?')}", v)
    for v in rejected:
        print(f"\n  REJECTED: {getattr(v,'vendor_name','?')}")
        for r in getattr(v, "rejection_reasons", []):
            print(f"    · {r}")

    critic_summary(critic)

    from app.schemas.output_models import CriticVerdict
    if critic.overall_verdict == CriticVerdict.BLOCKED:
        print("\n[HARD BLOCK] Decision critic blocked.")
        sys.exit(1)

    save_state(state)
    decision_str = "SHORTLISTED" if shortlisted else "REJECTED"
    tier = getattr(routing, "approval_tier", "?") if routing else "?"
    print(f"\n[OK] DECISION DONE — {decision_str} / tier: {tier}. Ready for: --agent explanation\n")


# ── Agent 8: Explanation ──────────────────────────────────────────────────────

async def run_explanation(state: dict) -> None:
    section("AGENT 8 — EXPLANATION")

    org_id   = require_state("org_id",   state, "explanation")
    setup_id = require_state("setup_id", state, "explanation")

    from app.agents.explanation import run_explanation_agent
    print("\n  Running explanation agent…")
    output, critic = await run_explanation_agent(
        org_id=org_id,
        setup_id=setup_id,
        vendor_ids=[SMOKE_VENDOR_ID],
        run_id=state.get("run_id", ""),
    )

    section("REPORT SUMMARY")
    narratives = getattr(output, "vendor_narratives", [])
    kv("vendor narratives", len(narratives))
    kv("grounding_completeness", getattr(output, "grounding_completeness", "?"))
    kv("report_confidence",      getattr(output, "report_confidence", "?"))
    kv("limitations",            len(getattr(output, "limitations", [])))

    for n in narratives:
        print(f"\n  ── {getattr(n,'vendor_name','?')}")
        print(f"     executive_summary: {getattr(n,'executive_summary','')[:200]}")
        claims = getattr(n, "grounded_claims", [])
        print(f"     grounded_claims:   {len(claims)}")
        uncited = getattr(n, "ungrounded_claims_removed", 0)
        print(f"     uncited_removed:   {uncited}")
        for c in claims[:3]:
            print(f"\n     claim:  {getattr(c,'claim_text','')[:120]}")
            print(f"     quote:  {getattr(c,'grounding_quote','')[:120]}")

    critic_summary(critic)

    from app.schemas.output_models import CriticVerdict
    if critic.overall_verdict == CriticVerdict.BLOCKED:
        print("\n[HARD BLOCK] Explanation critic blocked.")
        sys.exit(1)

    save_state(state)
    print(f"\n[OK] EXPLANATION DONE — report generated. Pipeline complete.\n")
    print("     Full state saved to .smoke_test_state.json")
    print("     Run --reset to start a fresh run.\n")


# ── Entry point ───────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="Smoke test — step-pause-verify runner")
    parser.add_argument("--reset",      action="store_true", help="Wipe smoke test data and state")
    parser.add_argument("--agent",      choices=["rfp","ingestion","extraction","retrieval","planner",
                                                 "evaluation","comparator","decision","explanation"])
    # --agent rfp args
    parser.add_argument("--rfp",        help="Path to RFP PDF (required for --agent rfp)")
    parser.add_argument("--vendor-pdf", dest="vendor_pdfs", action="append", default=[],
                        help="Path to a vendor PDF (repeat for multiple vendors)")
    parser.add_argument("--criteria",   help="Path to criteria CSV (optional for --agent rfp)")
    # --agent ingestion args
    parser.add_argument("--vendor",     help="vendor_id to ingest (from vendor_documents table)")
    parser.add_argument("--pdf",        help="Direct PDF path override for ingestion (legacy)")
    args = parser.parse_args()

    if args.reset:
        do_reset()
        return

    if not args.agent:
        parser.print_help()
        sys.exit(1)

    state = load_state()

    # Resolve ingestion target: --vendor (from DB) takes priority over --pdf
    ingestion_target = args.vendor or args.pdf or ""

    agent_map = {
        "rfp":         lambda: run_rfp(args.rfp or "", args.vendor_pdfs, args.criteria, state),
        "ingestion":   lambda: run_ingestion(ingestion_target, state),
        "extraction":  lambda: run_extraction(state),
        "retrieval":   lambda: run_retrieval(state),
        "planner":     lambda: run_planner(state),
        "evaluation":  lambda: run_evaluation(state),
        "comparator":  lambda: run_comparator(state),
        "decision":    lambda: run_decision(state),
        "explanation": lambda: run_explanation(state),
    }

    if args.agent == "rfp" and not args.rfp:
        print("[ABORT] --agent rfp requires --rfp <path>")
        sys.exit(1)
    if args.agent == "ingestion" and not ingestion_target:
        print("[ABORT] --agent ingestion requires --vendor <vendor_id> or --pdf <path>")
        sys.exit(1)

    asyncio.run(agent_map[args.agent]())


if __name__ == "__main__":
    main()
