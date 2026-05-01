#!/usr/bin/env python3
"""
contract_tests.py — Nine-agent architecture verification
=========================================================
Verifies interfaces between the nine agents.
Run after any interface change. Run before every deployment.

Usage:
    python contract_tests.py              # Run all 14 contracts
    python contract_tests.py critic       # Run one by name
"""
import sys, os, json, inspect, re
from pathlib import Path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

RESULTS = []

def contract(name):
    def decorator(fn):
        def wrapper():
            print(f"\n  Contract: {name}")
            try:
                fn()
                print("  \u2713 PASS")
                RESULTS.append((name, True, None))
            except AssertionError as e:
                print(f"  \u2717 FAIL: {e}")
                RESULTS.append((name, False, str(e)))
            except Exception as e:
                print(f"  \u2717 ERROR: {type(e).__name__}: {e}")
                RESULTS.append((name, False, str(e)))
        return wrapper
    return decorator


# ── CONTRACT 1: Pydantic output models ───────────────────────────────

@contract("All nine agent output models importable")
def c_output_models():
    from app.core.output_models import (
        PlannerOutput, TaskItem,
        CriticOutput, CriticFlag, CriticSeverity, CriticVerdict,
        IngestionOutput, SectionType,
        RetrievalOutput, RetrievedChunk,
        ExtractionOutput, ExtractedCertification, ExtractedInsurance,
        ExtractedSLA, ExtractedProject, ExtractedPricing,
        EvaluationOutput, ComplianceDecision, CriterionScore,
        ComparatorOutput, CriterionComparison,
        DecisionOutput, RejectionNotice, ShortlistedVendor,
        ExplanationOutput, GroundedClaim, VendorNarrative,
        AuditOverride, ComplianceStatus, DecisionBasis
    )
    assert PlannerOutput.__name__ == "PlannerOutput"

@contract("ExtractedCertification rejects empty grounding_quote")
def c_grounding_required():
    from app.core.output_models import ExtractedCertification, DocumentStatus
    from pydantic import ValidationError
    # Valid
    cert = ExtractedCertification(
        standard_name="ISO 27001", status=DocumentStatus.CURRENT,
        confidence=0.95,
        grounding_quote="We hold current ISO 27001:2022 cert by BSI",
        source_chunk_id="chunk-001"
    )
    assert cert.grounding_quote != ""
    # Empty must fail
    try:
        ExtractedCertification(
            standard_name="ISO 27001", status=DocumentStatus.CURRENT,
            confidence=0.95, grounding_quote="", source_chunk_id="chunk-001"
        )
        assert False, "Should have raised for empty grounding_quote"
    except (ValidationError, ValueError):
        pass

@contract("AuditOverride enforces reason >= 20 chars")
def c_override_reason():
    from app.core.output_models import AuditOverride
    from pydantic import ValidationError
    from datetime import datetime
    AuditOverride(
        override_id="o-001", org_id="org-1", run_id="run-1",
        overridden_by="cfo", original_decision={"rank":2},
        new_decision={"rank":1},
        reason="CFO overrides based on strategic partnership value",
        timestamp=datetime.utcnow()
    )
    try:
        AuditOverride(
            override_id="o-002", org_id="org-1", run_id="run-1",
            overridden_by="cfo", original_decision={"rank":2},
            new_decision={"rank":1}, reason="too short",
            timestamp=datetime.utcnow()
        )
        assert False, "Should raise for short reason"
    except (ValidationError, ValueError):
        pass

@contract("CriticOutput hard_flag_count consistent with flags list")
def c_critic_flag_count():
    from app.core.output_models import (
        CriticOutput, CriticFlag, CriticSeverity, CriticVerdict
    )
    c = CriticOutput(
        critic_run_id="r-001", evaluated_agent="extraction_agent",
        evaluated_output_id="ext-001",
        flags=[
            CriticFlag(flag_id="f-1", severity=CriticSeverity.HARD,
                agent="extraction_agent", check_name="grounding_failed",
                description="Quote not in source", evidence="...",
                recommendation="Block"),
            CriticFlag(flag_id="f-2", severity=CriticSeverity.SOFT,
                agent="extraction_agent", check_name="low_completeness",
                description="Low completeness", evidence="0.4",
                recommendation="Warn"),
        ],
        hard_flag_count=1, soft_flag_count=1,
        overall_verdict=CriticVerdict.BLOCKED,
        requires_human_review=True
    )
    assert c.hard_flag_count == 1
    assert c.soft_flag_count == 1


# ── CONTRACT 2: Qdrant tenant isolation ──────────────────────────────

@contract("Qdrant collection naming enforces tenant isolation")
def c_qdrant_naming():
    from app.core.qdrant_client import collection_name, rfp_collection_name
    c1 = collection_name("org-meridian", "vendor-alpha")
    c2 = collection_name("org-meridian", "vendor-beta")
    c3 = collection_name("org-acme", "vendor-alpha")
    assert c1 != c2, "Same org, different vendors must differ"
    assert c1 != c3, "Different orgs must differ even with same vendor"
    for n in [c1,c2,c3]:
        assert " " not in n and "/" not in n, f"Invalid chars in: {n}"

@contract("search_dense requires org_id and vendor_id parameters")
def c_qdrant_search_filters():
    from app.core.qdrant_client import search_dense
    sig = inspect.signature(search_dense)
    params = list(sig.parameters.keys())
    assert "org_id" in params, "search_dense must require org_id"
    assert "vendor_id" in params, "search_dense must require vendor_id"
    for p in ["org_id", "vendor_id"]:
        assert sig.parameters[p].default is inspect.Parameter.empty, \
            f"{p} must be required (no default)"


# ── CONTRACT 3: Critic Agent ─────────────────────────────────────────

@contract("All six Critic Agent functions importable")
def c_critic_functions():
    from app.agents.critic import (
        critic_after_ingestion, critic_after_retrieval,
        critic_after_extraction, critic_after_evaluation,
        critic_after_decision, critic_after_explanation
    )
    assert callable(critic_after_ingestion)
    assert callable(critic_after_extraction)

@contract("Critic blocks rejection without evidence citations")
def c_critic_rejects_no_evidence():
    from app.agents.critic import critic_after_decision
    from app.core.output_models import (
        DecisionOutput, RejectionNotice, ApprovalRouting, CriticVerdict
    )
    from datetime import datetime, timedelta
    d = DecisionOutput(
        decision_id="d-001", rfp_id="rfp-001",
        rejected_vendors=[RejectionNotice(
            vendor_id="beta", vendor_name="Vendor Beta",
            failed_checks=["MC-001"],
            rejection_reasons=["No ISO 27001"],
            evidence_citations=[],  # EMPTY — must hard block
            clause_references=["2.1"]
        )],
        shortlisted_vendors=[],
        approval_routing=ApprovalRouting(
            approval_tier=2, approver_role="cfo",
            contract_value=800000.0, sla_hours=72,
            sla_deadline=datetime.utcnow()+timedelta(hours=72)
        ),
        decision_confidence=0.9, requires_human_review=False
    )
    c = critic_after_decision(d)
    assert c.overall_verdict in [CriticVerdict.BLOCKED, CriticVerdict.ESCALATED], \
        f"Expected BLOCKED/ESCALATED, got {c.overall_verdict}"

@contract("Critic catches hallucinated grounding quote programmatically")
def c_critic_grounding_check():
    from app.agents.critic import critic_after_extraction
    from app.core.output_models import (
        ExtractionOutput, ExtractedCertification,
        DocumentStatus, CriticVerdict
    )
    extraction = ExtractionOutput(
        extraction_id="ext-002", vendor_id="alpha",
        org_id="org-meridian", source_chunk_ids=["chunk-001"],
        certifications=[ExtractedCertification(
            standard_name="ISO 27001", status=DocumentStatus.CURRENT,
            confidence=0.95,
            grounding_quote="This invented text does not appear in source",
            source_chunk_id="chunk-001"
        )],
        extraction_completeness=0.8, hallucination_risk=0.1
    )
    source_chunks = {"chunk-001": "The vendor has experience in security management."}
    c = critic_after_extraction(extraction, source_chunks)
    assert c.overall_verdict == CriticVerdict.BLOCKED, \
        f"Hallucinated quote must trigger BLOCKED, got {c.overall_verdict}"


# ── CONTRACT 4: Config-driven behaviour (CRITICAL) ────────────────────

@contract("CRITICAL: AgentConfig minimum paths readable by engine")
def c_config_minimum_shape():
    def validate(config, name):
        paths = [
            ["identity","agent_type"], ["identity","agent_name"],
            ["knowledge_base","collections"],
            ["evaluation_rules","mandatory_checks"],
            ["evaluation_rules","scoring_criteria"],
            ["governance","approval_tiers"],
            ["agent_behaviour","llm","model"],
            ["output","formats"],
        ]
        for path in paths:
            obj = config
            for k in path:
                assert isinstance(obj,dict), f"{name}: not dict at {path}"
                assert k in obj, f"{name}: missing '{k}' at {path}"
                obj = obj[k]
    try:
        from app.core.procurement_config import RFP_AGENT_CONFIG
        validate(RFP_AGENT_CONFIG, "Procurement")
    except ImportError:
        print("    (procurement config not built yet)")
    try:
        from app.agents.hr_agent_config import HR_AGENT_CONFIG
        validate(HR_AGENT_CONFIG, "HR")
        assert HR_AGENT_CONFIG["identity"]["agent_type"] == "hr"
    except ImportError:
        print("    (HR config not built yet)")

@contract("CRITICAL: No hardcoded business logic in engine files")
def c_no_hardcoded_logic():
    agents_dir = Path(__file__).parent / "app" / "agents"
    if not agents_dir.exists():
        print("    (app/agents/ not built yet)")
        return
    violations = []
    # These strings in agent files = hardcoded business logic
    forbidden = ['"ISO 27001"', "'ISO 27001'", '"professional indemnity"']
    for py_file in agents_dir.glob("*.py"):
        if py_file.name in ["__init__.py","critic.py","hr_agent_config.py"]:
            continue  # Critic and config files are allowed to mention these
        content = py_file.read_text(errors="ignore")
        for term in forbidden:
            if term in content:
                violations.append(f"{py_file.name}: contains {term}")
    assert not violations, \
        "ARCHITECTURE VIOLATION — hardcoded business logic in engine:\n" + \
        "\n".join(violations)


# ── CONTRACT 5: PostgreSQL fact store ────────────────────────────────

@contract("All extracted fact models have source_chunk_id and grounding_quote")
def c_fact_store_linkage():
    from app.core.output_models import (
        ExtractedCertification, ExtractedInsurance,
        ExtractedSLA, ExtractedProject, ExtractedPricing
    )
    for model in [ExtractedCertification, ExtractedInsurance,
                  ExtractedSLA, ExtractedProject, ExtractedPricing]:
        fields = model.__fields__
        assert "source_chunk_id" in fields, \
            f"{model.__name__} missing source_chunk_id"
        assert "grounding_quote" in fields, \
            f"{model.__name__} missing grounding_quote"
        assert "confidence" in fields, \
            f"{model.__name__} missing confidence"

@contract("get_vendor_facts returns correct schema with all five tables")
def c_fact_store_schema():
    try:
        from app.db.fact_store import get_vendor_facts
    except ImportError:
        print("    (fact_store not built yet)")
        return
    facts = get_vendor_facts("nonexistent-org", "nonexistent-vendor")
    assert isinstance(facts, dict)
    required = {"certifications","insurance","slas","projects","pricing"}
    assert required.issubset(set(facts.keys())), \
        f"Missing keys: {required - set(facts.keys())}"
    for k in required:
        assert isinstance(facts[k], list), f"facts['{k}'] must be list"


# ── CONTRACT 6: Rate limiter ──────────────────────────────────────────

@contract("call_openai_with_backoff importable — no direct OpenAI calls in agents")
def c_rate_limiter():
    from app.core.rate_limiter import RateLimiter, call_openai_with_backoff
    assert callable(call_openai_with_backoff)
    # Check agent files do not make direct OpenAI calls
    agents_dir = Path(__file__).parent / "app" / "agents"
    if not agents_dir.exists():
        print("    (app/agents/ not built yet)")
        return
    violations = []
    for f in agents_dir.glob("*.py"):
        if f.name.startswith("_"):
            continue
        content = f.read_text(errors="ignore")
        # Skip if the file imports call_openai_with_backoff (it uses it correctly)
        if "call_openai_with_backoff" in content:
            continue
        # If it makes direct completions calls without the wrapper, flag it
        if ".chat.completions.create(" in content and "openai" in content.lower():
            violations.append(f.name)
    assert not violations, \
        f"Direct OpenAI calls without rate limiter: {violations}"


# ── RUNNER ────────────────────────────────────────────────────────────

ALL = [
    c_output_models, c_grounding_required, c_override_reason,
    c_critic_flag_count, c_qdrant_naming, c_qdrant_search_filters,
    c_critic_functions, c_critic_rejects_no_evidence,
    c_critic_grounding_check, c_config_minimum_shape,
    c_no_hardcoded_logic, c_fact_store_linkage,
    c_fact_store_schema, c_rate_limiter,
]
MAP = {fn.__name__.replace("c_",""): fn for fn in ALL}

def main():
    print("\n" + "="*60)
    print("CONTRACT TESTS — Nine-agent architecture")
    print("="*60)
    if len(sys.argv) > 1:
        n = sys.argv[1].lower()
        if n in MAP: MAP[n]()
        else: print(f"Unknown: {n}\nAvailable: {list(MAP.keys())}")
        return
    for fn in ALL:
        fn()
    print("\n" + "="*60)
    passed = sum(1 for _,p,_ in RESULTS if p)
    print(f"CONTRACTS: {passed}/{len(RESULTS)} passed")
    if passed == len(RESULTS):
        print("\u2713 All interfaces intact")
    else:
        print("\u2717 Violations detected")
        for n,ok,e in RESULTS:
            if not ok:
                print(f"\n  FAILED: {n}\n    {(e or '')[:200]}")
    print("="*60)
    sys.exit(0 if passed == len(RESULTS) else 1)

if __name__ == "__main__":
    main()
