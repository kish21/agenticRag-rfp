"""
Author the E3 benchmark scenarios — the single source of truth.

For every fact, the SAME verbatim statement is (a) written into the vendor PDF
and (b) recorded as the golden `grounding_substring`. That construction is what
makes exit-criterion A2 (golden grounding appears verbatim in the source) true
by design rather than by hope.

Run once; the emitted PDFs + setup.json + golden.json are committed:

    python -m benchmark.generation.build_scenarios

Outputs to benchmark/scenarios/<scenario_id>/.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from app.schemas.output_models import (
    EvaluationSetup, ExtractionTarget, MandatoryCheck, ScoringCriterion,
)
from benchmark.golden_schema import (
    ExpectedCriterion, ExpectedFact, ExpectedMandatory, ExpectedVendor, ScenarioGolden,
)
from benchmark.generation.pdf_builder import (
    Document, Filler, Heading, PageBreak, Para, Table, build_pdf,
)

SCENARIOS_DIR = Path(__file__).resolve().parents[1] / "scenarios"
# Placeholder org_id — the runner overrides org_id/rfp_id/setup_id per run.
BENCH_ORG_ID = "00000000-0000-0000-0000-0000000000e3"


# ── Shared evaluation setup (constant across scenarios) ───────────────────────
# Criteria/checks are FIXED so the benchmark measures the downstream pipeline,
# not LLM criteria extraction. IDs here are what the golden files reference.

def _setup() -> EvaluationSetup:
    targets = [
        ExtractionTarget(target_id="ext-cert-iso", name="ISO 27001 certification",
                         description="Current ISO 27001 information-security certification.",
                         fact_type="certification", is_mandatory=True,
                         feeds_check_id="chk-iso27001", feeds_criterion_id="crit-security"),
        ExtractionTarget(target_id="ext-ins-pi", name="Professional Indemnity insurance",
                         description="Professional indemnity insurance and coverage amount.",
                         fact_type="insurance", is_mandatory=True,
                         feeds_check_id="chk-pi-insurance"),
        ExtractionTarget(target_id="ext-proj-fs", name="Financial-services reference project",
                         description="Reference engagement in the financial-services sector.",
                         fact_type="project", is_mandatory=False,
                         feeds_criterion_id="crit-experience"),
        ExtractionTarget(target_id="ext-sla-p1", name="Priority-1 SLA commitments",
                         description="Response/resolution times and uptime guarantee.",
                         fact_type="sla", is_mandatory=False,
                         feeds_criterion_id="crit-sla"),
        ExtractionTarget(target_id="ext-pricing-annual", name="Annual managed-services fee",
                         description="Proposed annual price for the managed service.",
                         fact_type="pricing", is_mandatory=False,
                         feeds_criterion_id="crit-pricing"),
    ]
    checks = [
        MandatoryCheck(check_id="chk-iso27001", name="ISO 27001 certification",
                       description="Vendor must hold a current ISO 27001 certificate.",
                       what_passes="A valid, in-date ISO 27001 certificate is evidenced.",
                       extraction_target_id="ext-cert-iso"),
        MandatoryCheck(check_id="chk-pi-insurance", name="Professional Indemnity >= £5M",
                       description="Vendor must hold professional indemnity insurance of at least £5M.",
                       what_passes="Evidence of PI cover of £5,000,000 or more.",
                       extraction_target_id="ext-ins-pi"),
    ]
    criteria = [
        ScoringCriterion(criterion_id="crit-experience", name="Relevant financial-services experience",
                         weight=0.35, extraction_target_ids=["ext-proj-fs"],
                         rubric_9_10="Multiple directly-comparable FS engagements with measurable outcomes.",
                         rubric_6_8="At least one relevant FS engagement.",
                         rubric_3_5="Tangential or non-FS experience only.",
                         rubric_0_2="No relevant experience evidenced."),
        ScoringCriterion(criterion_id="crit-sla", name="Service-level commitments",
                         weight=0.30, extraction_target_ids=["ext-sla-p1"],
                         rubric_9_10="Strong, specific SLAs with high uptime and fast P1 response.",
                         rubric_6_8="Reasonable documented SLAs.",
                         rubric_3_5="Vague or weak SLAs.",
                         rubric_0_2="No SLA commitments evidenced."),
        ScoringCriterion(criterion_id="crit-security", name="Security approach",
                         weight=0.20, extraction_target_ids=["ext-cert-iso"],
                         rubric_9_10="Independently certified, robust security posture.",
                         rubric_6_8="Sound security approach.",
                         rubric_3_5="Partial security evidence.",
                         rubric_0_2="No security evidence."),
        ScoringCriterion(criterion_id="crit-pricing", name="Commercial proposal",
                         weight=0.15, extraction_target_ids=["ext-pricing-annual"],
                         rubric_9_10="Clear, transparent, competitive pricing.",
                         rubric_6_8="Clear pricing.",
                         rubric_3_5="Unclear pricing.",
                         rubric_0_2="No pricing evidenced."),
    ]
    return EvaluationSetup(
        setup_id="setup-benchmark", org_id=BENCH_ORG_ID, department="Procurement",
        rfp_id="rfp-benchmark", rfp_confirmed=True, confirmed_by="benchmark",
        source="manually_defined", mandatory_checks=checks,
        scoring_criteria=criteria, extraction_targets=targets,
        total_weight=round(sum(c.weight for c in criteria), 3),
    )


# ── Fact / scenario authoring model ───────────────────────────────────────────

@dataclass
class FactSpec:
    fact_type: str
    key_fields: dict
    statement: str                 # verbatim text written into the PDF
    grounding: str                 # distinctive verbatim substring (must be in statement)
    present: bool = True
    layout: str = "prose"          # "prose" | "table"
    table_rows: list | None = None
    bury: bool = False             # place behind filler (long-doc scenario)
    note: str = ""


@dataclass
class ScenarioSpec:
    scenario_id: str
    title: str
    stresses: list[str]
    vendor_id: str
    facts: list[FactSpec]
    mandatory: list[ExpectedMandatory]
    criteria: list[ExpectedCriterion]
    expected_rejected: bool = False
    long_doc: bool = False


# Strong, complete fact set parametrised by vendor display name + cert number.
def _full_facts(v: str, cn: str) -> list[FactSpec]:
    return [
        # key_fields = the IDENTIFYING facts only. `status` is an interpretation
        # (the model emits "current" for an in-date cert, not "valid"), so it is
        # not part of identity — the cert number + validity date identify it.
        FactSpec("certification", {"standard_name": "ISO 27001", "valid_until": "2027-08-31"},
                 f"{v} holds ISO 27001:2022 certification, certificate number {cn}, "
                 f"independently audited and valid until 31 August 2027.",
                 grounding=f"certificate number {cn}"),
        FactSpec("insurance", {"amount": 10000000},
                 f"{v} maintains Professional Indemnity insurance providing coverage of "
                 f"£10,000,000, underwritten by Hiscox.",
                 grounding="coverage of £10,000,000"),
        FactSpec("sla", {"priority_level": "P1", "response_minutes": 15,
                         "resolution_hours": 4, "uptime_percentage": 99.9},
                 f"For Priority 1 incidents {v} guarantees a 15-minute response time and a "
                 f"4-hour resolution target, supported by a 99.9% uptime guarantee.",
                 grounding="15-minute response time"),
        FactSpec("project", {"client_name": "Northbridge Building Society",
                             "client_sector": "financial services", "user_count": 5000},
                 f"{v} delivered managed IT services to Northbridge Building Society, a UK "
                 f"financial-services institution with 5,000 users, cutting incident "
                 f"resolution time by 35%.",
                 grounding="Northbridge Building Society"),
        FactSpec("pricing", {"amount": 1200000},
                 f"{v}'s proposed annual managed-services fee is £1,200,000, inclusive of "
                 f"24/7 support and quarterly service reviews.",
                 grounding="£1,200,000"),
    ]


def _all_pass_mandatory() -> list[ExpectedMandatory]:
    return [ExpectedMandatory(check_id="chk-iso27001", outcome="pass"),
            ExpectedMandatory(check_id="chk-pi-insurance", outcome="pass")]


def _strong_criteria() -> list[ExpectedCriterion]:
    return [ExpectedCriterion(criterion_id="crit-experience", expectation="6-8"),
            ExpectedCriterion(criterion_id="crit-sla", expectation="9-10"),
            ExpectedCriterion(criterion_id="crit-security", expectation="9-10"),
            ExpectedCriterion(criterion_id="crit-pricing", expectation="6-8")]


def _scenarios() -> list[ScenarioSpec]:
    s = []

    # 1 — clean: complete facts in prose. Everything passes.
    s.append(ScenarioSpec(
        "01_clean", "Clean prose proposal", ["baseline", "prose"],
        "acme", _full_facts("Acme Managed Services", "ISO-ACM-44821"),
        _all_pass_mandatory(), _strong_criteria()))

    # 2 — table_heavy: same facts, presented in tables (stresses table parsing).
    tbl = _full_facts("Beta Systems", "ISO-BET-77310")
    for f in tbl:
        f.layout = "table"
    tbl[0].table_rows = [["Field", "Value"], ["Standard", "ISO 27001:2022"],
                         ["Certificate number", "ISO-BET-77310"], ["Valid until", "31 August 2027"]]
    tbl[0].grounding = "ISO-BET-77310"
    tbl[1].table_rows = [["Field", "Value"], ["Insurance type", "Professional Indemnity"],
                         ["Coverage", "£10,000,000"], ["Underwriter", "Hiscox"]]
    tbl[1].grounding = "£10,000,000"
    tbl[2].table_rows = [["Priority", "Response", "Resolution", "Uptime"],
                         ["P1", "15 minutes", "4 hours", "99.9%"]]
    tbl[2].grounding = "15 minutes"
    tbl[3].table_rows = [["Client", "Sector", "Users", "Outcome"],
                         ["Northbridge Building Society", "Financial services", "5,000",
                          "35% faster resolution"]]
    tbl[3].grounding = "Northbridge Building Society"
    tbl[4].table_rows = [["Item", "Amount"], ["Annual managed-services fee", "£1,200,000"],
                         ["Includes", "24/7 support; quarterly reviews"]]
    tbl[4].grounding = "£1,200,000"
    s.append(ScenarioSpec("02_table_heavy", "Table-heavy proposal", ["tables", "parsing"],
                          "beta", tbl, _all_pass_mandatory(), _strong_criteria()))

    # 3 — long: complete facts buried in many pages of filler (stresses retrieval recall).
    lng = _full_facts("Gamma IT Partners", "ISO-GAM-90122")
    for f in lng:
        f.bury = True
    s.append(ScenarioSpec("03_long", "Long proposal, facts buried", ["long", "retrieval"],
                          "gamma", lng, _all_pass_mandatory(), _strong_criteria(), long_doc=True))

    # 4 — short: only cert + insurance + pricing present; SLA + project ABSENT.
    #     Mandatory both pass (not rejected), but two criteria have no evidence
    #     → must be insufficient, NOT a forced 0.
    sh = _full_facts("Delta Services", "ISO-DEL-31007")
    short_facts = [sh[0], sh[1], sh[4]]              # cert, insurance, pricing
    short_facts += [FactSpec("sla", {}, "", grounding="", present=False,
                             note="No SLA commitments stated in this brief proposal."),
                    FactSpec("project", {}, "", grounding="", present=False,
                             note="No reference project stated.")]
    s.append(ScenarioSpec(
        "04_short", "Short proposal, partial evidence", ["short", "insufficient_evidence"],
        "delta", short_facts, _all_pass_mandatory(),
        [ExpectedCriterion(criterion_id="crit-experience", expectation="insufficient",
                           note="No project evidenced — must be insufficient, not forced 0."),
         ExpectedCriterion(criterion_id="crit-sla", expectation="insufficient",
                           note="No SLA evidenced — must be insufficient, not forced 0."),
         ExpectedCriterion(criterion_id="crit-security", expectation="9-10"),
         ExpectedCriterion(criterion_id="crit-pricing", expectation="6-8")]))

    # 5 — conflicting: cert claimed valid AND lapsed; PI £10M AND £2M (< £5M threshold).
    #     The honest outcome is insufficient_evidence, not an auto-pass.
    conf = [
        FactSpec("certification", {"standard_name": "ISO 27001"},
                 "Epsilon Group holds ISO 27001:2022 certification, valid until 31 August 2027.",
                 grounding="valid until 31 August 2027",
                 note="Conflicts with the lapse statement below."),
        FactSpec("certification", {"standard_name": "ISO 27001", "status": "expired"},
                 "Please note: Epsilon Group's ISO 27001 certificate lapsed in 2023 and "
                 "re-audit is currently pending.",
                 grounding="lapsed in 2023", note="Conflicts with the validity claim above."),
        FactSpec("insurance", {"amount": 10000000},
                 "Epsilon Group maintains Professional Indemnity insurance of £10,000,000.",
                 grounding="Professional Indemnity insurance of £10,000,000",
                 note="Conflicts with the £2M statement below."),
        FactSpec("insurance", {"amount": 2000000},
                 "Current Professional Indemnity cover is £2,000,000 pending policy renewal.",
                 grounding="cover is £2,000,000", note="Below the £5M threshold; conflicts above."),
        FactSpec("sla", {"priority_level": "P1", "response_minutes": 15},
                 "For Priority 1 incidents Epsilon Group guarantees a 15-minute response time.",
                 grounding="15-minute response time"),
        FactSpec("pricing", {"amount": 1500000},
                 "Epsilon Group's proposed annual fee is £1,500,000.", grounding="£1,500,000"),
    ]
    s.append(ScenarioSpec(
        "05_conflicting", "Internally conflicting proposal", ["conflicting", "contradiction"],
        "epsilon", conf,
        [ExpectedMandatory(check_id="chk-iso27001", outcome="insufficient_evidence",
                           note="Validity contradicted by lapse statement — cannot confirm."),
         ExpectedMandatory(check_id="chk-pi-insurance", outcome="insufficient_evidence",
                           note="£10M vs £2M conflict; £2M < £5M — cannot confirm >= £5M.")],
        [ExpectedCriterion(criterion_id="crit-experience", expectation="insufficient"),
         ExpectedCriterion(criterion_id="crit-sla", expectation="6-8"),
         ExpectedCriterion(criterion_id="crit-security", expectation="insufficient"),
         ExpectedCriterion(criterion_id="crit-pricing", expectation="6-8")]))

    # 6 — missing_evidence: both MANDATORY facts omitted → vendor must be rejected.
    miss = _full_facts("Omega Solutions", "ISO-OMG-00000")
    missing_facts = [miss[2], miss[3], miss[4]]      # sla, project, pricing only
    missing_facts += [FactSpec("certification", {}, "", grounding="", present=False,
                               note="No ISO 27001 certificate mentioned anywhere."),
                      FactSpec("insurance", {}, "", grounding="", present=False,
                               note="No professional indemnity insurance mentioned.")]
    s.append(ScenarioSpec(
        "06_missing_evidence", "Mandatory evidence missing", ["missing", "rejection"],
        "omega", missing_facts,
        [ExpectedMandatory(check_id="chk-iso27001", outcome="insufficient_evidence"),
         ExpectedMandatory(check_id="chk-pi-insurance", outcome="insufficient_evidence")],
        [ExpectedCriterion(criterion_id="crit-experience", expectation="6-8"),
         ExpectedCriterion(criterion_id="crit-sla", expectation="9-10"),
         ExpectedCriterion(criterion_id="crit-security", expectation="insufficient"),
         ExpectedCriterion(criterion_id="crit-pricing", expectation="6-8")],
        expected_rejected=True))
    return s


# ── RFP + vendor PDF assembly ─────────────────────────────────────────────────

def _rfp_doc() -> Document:
    return Document(
        "RFP — IT Managed Services (Meridian Financial Services, 2026)",
        [Heading("1. Overview"),
         Para("Meridian Financial Services invites proposals for the provision of IT "
              "managed services. Vendors will be evaluated on relevant financial-services "
              "experience, service-level commitments, security approach, and commercial proposal."),
         Heading("2. Mandatory requirements"),
         Para("Vendors must hold a current ISO 27001 information-security certification and "
              "professional indemnity insurance of at least £5,000,000. Failure to evidence "
              "either requirement will result in disqualification."),
         Heading("3. Scoring criteria"),
         Para("Relevant financial-services experience (35%); service-level commitments (30%); "
              "security approach (20%); commercial proposal (15%).")])


def _vendor_doc(spec: ScenarioSpec) -> Document:
    blocks: list = [Heading(f"Proposal — {spec.vendor_id.title()}"),
                    Para("Submitted in response to the Meridian Financial Services RFP for "
                         "IT managed services.")]
    present = [f for f in spec.facts if f.present]
    if spec.long_doc:
        # Bury each fact between large filler blocks across many pages.
        for f in present:
            blocks.append(Filler(paragraphs=14))
            blocks.append(PageBreak())
            blocks.append(Para(f.statement))
        blocks.append(Filler(paragraphs=14))
    else:
        for f in present:
            if f.layout == "table" and f.table_rows:
                blocks.append(Heading(_fact_heading(f.fact_type), level=2))
                blocks.append(Table(f.table_rows))
            else:
                blocks.append(Para(f.statement))
    return Document(f"{spec.vendor_id.title()} — IT Managed Services Proposal", blocks)


def _fact_heading(fact_type: str) -> str:
    return {"certification": "Certifications", "insurance": "Insurance",
            "sla": "Service Levels", "project": "Reference Projects",
            "pricing": "Commercial Proposal"}.get(fact_type, fact_type.title())


def _golden(spec: ScenarioSpec) -> ScenarioGolden:
    facts = []
    for f in spec.facts:
        facts.append(ExpectedFact(
            fact_type=f.fact_type, key_fields=f.key_fields,
            grounding_substring=(f.grounding or None) if f.present else None,
            present=f.present, note=f.note))
    vendor = ExpectedVendor(
        vendor_id=spec.vendor_id, vendor_pdf=f"vendor_{spec.vendor_id}.pdf",
        facts=facts, mandatory=spec.mandatory, criteria=spec.criteria,
        expected_rejected=spec.expected_rejected)
    return ScenarioGolden(
        scenario_id=spec.scenario_id, title=spec.title, stresses=spec.stresses,
        rfp_pdf="rfp.pdf", setup_json="setup.json", vendors=[vendor])


def main() -> None:
    setup = _setup()
    setup_dict = setup.model_dump(mode="json")
    n = 0
    for spec in _scenarios():
        d = SCENARIOS_DIR / spec.scenario_id
        d.mkdir(parents=True, exist_ok=True)
        build_pdf(_rfp_doc(), d / "rfp.pdf")
        build_pdf(_vendor_doc(spec), d / f"vendor_{spec.vendor_id}.pdf")
        (d / "setup.json").write_text(json.dumps(setup_dict, indent=2), encoding="utf-8")
        golden = _golden(spec)                       # validates via Pydantic
        (d / "golden.json").write_text(
            golden.model_dump_json(indent=2), encoding="utf-8")
        present = len(golden.present_facts())
        absent = len(golden.absent_facts())
        print(f"  [{spec.scenario_id}] vendor={spec.vendor_id}  "
              f"facts: {present} present / {absent} absent  -> {d}")
        n += 1
    print(f"\nBuilt {n} scenarios under {SCENARIOS_DIR}")


if __name__ == "__main__":
    main()
