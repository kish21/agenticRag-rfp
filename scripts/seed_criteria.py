import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
import uuid, json
from app.db.fact_store import get_engine
import sqlalchemy as sa

ORG_ID = "00000000-0000-0000-0000-000000000001"


def _insert_org(conn, check_type, name, desc, passes, weight, rubric, locked):
    conn.execute(sa.text("""
        INSERT INTO org_criteria_templates
            (template_id, org_id, check_type, name,
             description, what_passes, default_weight,
             rubric, is_locked, created_by)
        VALUES (:tid, CAST(:oid AS uuid), :ct, :name,
                :desc, :passes, :weight,
                CAST(:rubric AS jsonb), :locked, 'seed')
    """), {
        "tid": str(uuid.uuid4()), "oid": ORG_ID,
        "ct": check_type, "name": name,
        "desc": desc, "passes": passes,
        "weight": weight, "rubric": json.dumps(rubric), "locked": locked,
    })


def _insert_dept(conn, dept, check_type, name, desc, passes, weight, rubric, locked):
    conn.execute(sa.text("""
        INSERT INTO dept_criteria_templates
            (template_id, org_id, department, check_type,
             name, description, what_passes, default_weight,
             rubric, is_locked, created_by)
        VALUES (:tid, CAST(:oid AS uuid), :dept, :ct, :name,
                :desc, :passes, :weight,
                CAST(:rubric AS jsonb), :locked, 'seed')
    """), {
        "tid": str(uuid.uuid4()), "oid": ORG_ID, "dept": dept,
        "ct": check_type, "name": name,
        "desc": desc, "passes": passes,
        "weight": weight, "rubric": json.dumps(rubric), "locked": locked,
    })


def seed():
    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(sa.text("SET LOCAL app.current_org_id = :oid"), {"oid": ORG_ID})

        # Clear existing
        conn.execute(sa.text("DELETE FROM org_criteria_templates  WHERE org_id::text = :oid"), {"oid": ORG_ID})
        conn.execute(sa.text("DELETE FROM dept_criteria_templates WHERE org_id::text = :oid"), {"oid": ORG_ID})

        # ── Org-level mandatory (locked — apply to every evaluation) ──────────────
        _insert_org(conn, "mandatory", "ISO 27001 Certification",
            "Vendor must hold current ISO 27001 issued by an accredited certification body.",
            "Certificate number, issuing body, and expiry date present. Expiry in future.",
            0.0, {}, True)

        _insert_org(conn, "mandatory", "Professional Indemnity Insurance ≥ £5M",
            "Vendor must carry PI insurance of at least £5 million per claim.",
            "Named insurer, cover amount ≥ £5M, and current expiry date stated.",
            0.0, {}, True)

        _insert_org(conn, "mandatory", "GDPR / UK Data Protection Compliance",
            "Vendor must demonstrate GDPR or UK GDPR compliance for all data processing activities.",
            "Data Processing Agreement provided, ICO registration or equivalent EU DPA present.",
            0.0, {}, True)

        _insert_org(conn, "mandatory", "Registered Legal Entity",
            "Vendor must be a registered company in the UK, EU, or equivalent jurisdiction.",
            "Companies House number, EU registry number, or equivalent official registration provided.",
            0.0, {}, True)

        # ── Org-level scoring (locked — weighted in every evaluation) ─────────────
        _insert_org(conn, "scoring", "Financial Stability",
            "Vendor financial health: revenue, profitability, debt levels, and credit rating.",
            "", 0.15, {
                "9_10": "Audited accounts show strong revenue growth, healthy margins, no material debt. Credit rating A or above.",
                "6_8":  "Accounts stable, minor concerns but no material risk identified.",
                "3_5":  "Some financial weakness — late filings, thin margins, or declining revenue.",
                "0_2":  "No accounts provided, significant debt, or active credit warning flags.",
            }, True)

        _insert_org(conn, "scoring", "Information Security Posture",
            "Breadth and currency of vendor's data and cyber security certifications, audits, and practices.",
            "", 0.20, {
                "9_10": "ISO 27001 + SOC 2 Type II + annual CREST pentest report provided. Incident response plan documented.",
                "6_8":  "ISO 27001 or SOC 2, security policies documented and dated within 12 months.",
                "3_5":  "Basic security policies exist but no formal certification or recent audit.",
                "0_2":  "No security documentation provided.",
            }, True)

        # ── Procurement department ────────────────────────────────────────────────
        for dept, items in _dept_criteria().items():
            for item in items:
                _insert_dept(conn, dept, *item)

    from app.core.org_settings import upsert_org_settings
    upsert_org_settings(ORG_ID, updated_by="seed")

    print("Seeded org criteria:  4 mandatory (locked) + 2 scoring (locked)")
    for dept, items in _dept_criteria().items():
        mandatory = sum(1 for i in items if i[0] == "mandatory")
        scoring   = sum(1 for i in items if i[0] == "scoring")
        print(f"  dept/{dept}: {mandatory} mandatory, {scoring} scoring")
    print(f"Org settings upserted for {ORG_ID}")


def _dept_criteria():
    return {
        "procurement": [
            ("mandatory", "EU or UK Domiciled Service Desk",
             "Primary support desk must be physically located in the EU or UK.",
             "City and country explicitly stated as EU or UK. No offshore-only support.",
             0.0, {}, False),
            ("mandatory", "UK Modern Slavery Act Statement",
             "Vendors with turnover > £36M must publish a current Modern Slavery Act statement.",
             "Statement published on company website, dated within past 12 months, or statutory exemption evidence.",
             0.0, {}, False),
            ("scoring", "Commercial Value for Money",
             "Total cost of ownership relative to scope, quality, and market benchmarks.",
             "", 0.25, {
                 "9_10": "Detailed pricing schedule with unit rates, best market rate evidenced, no hidden fees, volume discounts offered.",
                 "6_8":  "Clear pricing, minor ambiguity in some line items, broadly competitive.",
                 "3_5":  "Above-market or incomplete pricing, some fees unclear or omitted.",
                 "0_2":  "No pricing provided or contract value significantly exceeds budget.",
             }, False),
            ("scoring", "Relevant Contract Experience",
             "Proven track record delivering comparable contracts in size, sector, and complexity.",
             "", 0.20, {
                 "9_10": "3+ comparable references with named contacts, contract values, and measurable outcomes documented.",
                 "6_8":  "2 references provided, at least one comparable in scope and budget.",
                 "3_5":  "1 reference or references in adjacent sector only.",
                 "0_2":  "No references provided.",
             }, False),
            ("scoring", "Implementation & Onboarding Plan",
             "Quality of proposed project plan, milestones, and risk management.",
             "", 0.20, {
                 "9_10": "Detailed Gantt/project plan, named PM, risk register with mitigations, change control process defined.",
                 "6_8":  "Clear phases and milestones, reasonable timeline, project owner named.",
                 "3_5":  "High-level plan only, no milestones or accountable owner identified.",
                 "0_2":  "No implementation plan provided.",
             }, False),
            ("scoring", "Service Level Commitments",
             "SLA targets for availability, incident response, and resolution with financial remedy.",
             "", 0.15, {
                 "9_10": "99.9%+ uptime SLA, P1 response ≤1h, resolution ≤4h, service credits defined.",
                 "6_8":  "99.5% uptime, reasonable P1 response and resolution targets.",
                 "3_5":  "Vague SLA or no financial remedy clause.",
                 "0_2":  "No SLAs provided.",
             }, False),
            ("scoring", "ESG & Sustainability",
             "Vendor's environmental, social, and governance credentials and targets.",
             "", 0.10, {
                 "9_10": "Net-zero commitment with verified Science Based Targets, Scope 3 disclosed, supplier code of conduct.",
                 "6_8":  "Carbon reduction plan published, ESG policy in place.",
                 "3_5":  "Basic ESG statement, no measurable targets.",
                 "0_2":  "No ESG information provided.",
             }, False),
            ("scoring", "Technical Capability & Innovation",
             "Depth of technical expertise and roadmap for continuous improvement.",
             "", 0.10, {
                 "9_10": "Dedicated R&D team, published product roadmap, accredited certifications relevant to scope.",
                 "6_8":  "Solid technical team, some innovation evidence.",
                 "3_5":  "Adequate capability but limited innovation.",
                 "0_2":  "No technical capability information.",
             }, False),
        ],
        "finance": [
            ("mandatory", "FCA Authorisation or Equivalent",
             "Vendors handling financial data or regulated services must be FCA authorised.",
             "FCA register number confirmed as 'Authorised' on public register, or equivalent EU licence.",
             0.0, {}, False),
            ("mandatory", "Cyber Essentials Plus",
             "Finance vendors must hold current Cyber Essentials Plus certification.",
             "CE+ certificate from IASME-accredited assessor, dated within 12 months.",
             0.0, {}, False),
            ("scoring", "Regulatory Reporting Capability",
             "Ability to produce FCA-compliant, IFRS, or UK GAAP regulatory reports.",
             "", 0.30, {
                 "9_10": "Automated IFRS/UK GAAP reports, built-in regulatory templates, independent auditor attestation.",
                 "6_8":  "Strong reporting capability, some manual transformation steps.",
                 "3_5":  "Basic reporting, significant manual reconciliation needed.",
                 "0_2":  "No regulatory reporting capability described.",
             }, False),
            ("scoring", "Audit Trail & Data Integrity",
             "Immutability of audit logs, segregation of client data, and forensic traceability.",
             "", 0.25, {
                 "9_10": "Immutable audit logs with hash verification, SOC 2 Type II, complete data lineage per transaction.",
                 "6_8":  "Audit logs maintained with regular review, data segregated per client.",
                 "3_5":  "Logs exist but not immutable or incomplete.",
                 "0_2":  "No audit trail described.",
             }, False),
            ("scoring", "Business Continuity & Disaster Recovery",
             "Tested BCP/DR plans with documented RTO and RPO targets.",
             "", 0.20, {
                 "9_10": "RTO ≤4h, RPO ≤1h, annual DR exercise with results and remediation plan.",
                 "6_8":  "BCP plan exists, tested within 12 months.",
                 "3_5":  "BCP plan exists but not recently tested.",
                 "0_2":  "No BCP/DR plan provided.",
             }, False),
            ("scoring", "Data Residency & Sovereignty",
             "Contractual guarantees that all financial data remains in UK or EEA.",
             "", 0.15, {
                 "9_10": "Contractual UK/EEA-only data residency, SCCs for all sub-processors, full data map.",
                 "6_8":  "UK/EEA residency confirmed, sub-processors listed.",
                 "3_5":  "Data residency mentioned but sub-processors or transfers unclear.",
                 "0_2":  "No data residency commitment.",
             }, False),
            ("scoring", "Commercial Terms & Flexibility",
             "Contract flexibility, exit provisions, and commercial transparency.",
             "", 0.10, {
                 "9_10": "Clear exit rights, data portability guaranteed, no auto-renewal lock-in, open-book pricing.",
                 "6_8":  "Reasonable exit provisions, pricing transparent.",
                 "3_5":  "Some lock-in, limited exit rights.",
                 "0_2":  "No commercial terms provided.",
             }, False),
        ],
        "it": [
            ("mandatory", "SOC 2 Type II Report",
             "IT vendors must hold a current SOC 2 Type II covering systems in scope.",
             "Report covering past 12 months from Big 4 or equivalent auditor, no material exceptions.",
             0.0, {}, False),
            ("mandatory", "Annual Penetration Test",
             "External penetration test by CREST-accredited firm within the past 12 months.",
             "Pentest report, scope includes production environment, conducted by CREST member firm.",
             0.0, {}, False),
            ("scoring", "Integration & API Capability",
             "REST/GraphQL API quality, documentation completeness, and pre-built connector ecosystem.",
             "", 0.25, {
                 "9_10": "OpenAPI 3.0 spec, sandbox, Postman collection, certified connectors for ERP/HRMS/CRM.",
                 "6_8":  "API documented, integration guide available, some pre-built connectors.",
                 "3_5":  "Basic API, limited or outdated documentation.",
                 "0_2":  "No API or integration capability described.",
             }, False),
            ("scoring", "Scalability & Performance",
             "Demonstrated ability to scale to enterprise-grade load with documented benchmarks.",
             "", 0.20, {
                 "9_10": "Load test results at 10x current volume, auto-scaling architecture, CDN and caching documented.",
                 "6_8":  "Performance benchmarks provided, architecture supports horizontal scaling.",
                 "3_5":  "Anecdotal performance claims, no benchmarks.",
                 "0_2":  "No scalability information.",
             }, False),
            ("scoring", "Data Residency & Sovereignty",
             "UK/EEA data residency guarantee with sub-processor transparency.",
             "", 0.20, {
                 "9_10": "Contractual UK/EEA residency, all sub-processors listed with residency, data map provided.",
                 "6_8":  "UK/EEA residency confirmed, sub-processor list available on request.",
                 "3_5":  "Residency mentioned but sub-processors not fully disclosed.",
                 "0_2":  "No data residency commitment.",
             }, False),
            ("scoring", "Support & Incident Response",
             "24/7 support availability, SLA commitments, and incident escalation process.",
             "", 0.20, {
                 "9_10": "24/7 UK NOC, P1 ≤15min acknowledgement, dedicated TAM, published incident history.",
                 "6_8":  "Business hours UK support, clear escalation path, P1 ≤1h.",
                 "3_5":  "Email support only, response times unclear.",
                 "0_2":  "No support terms provided.",
             }, False),
            ("scoring", "Vendor Lock-in & Portability",
             "Ability to export data and migrate away without proprietary dependencies.",
             "", 0.15, {
                 "9_10": "Open standards, full data export in multiple formats, documented migration runbook.",
                 "6_8":  "Standard export formats, migration support available.",
                 "3_5":  "Some proprietary formats, migration complex.",
                 "0_2":  "Significant lock-in, no export path described.",
             }, False),
        ],
        "legal": [
            ("mandatory", "SRA or Bar Council Registration",
             "Legal services vendors must be authorised by the SRA or Bar Council.",
             "SRA authorisation number or barrister chambers confirmed on public register.",
             0.0, {}, False),
            ("scoring", "Legal Technology & eDiscovery",
             "Matter management platform capability and eDiscovery readiness.",
             "", 0.30, {
                 "9_10": "Full matter management system, Relativity-certified eDiscovery, complete audit trail.",
                 "6_8":  "Solid matter management, basic eDiscovery capability.",
                 "3_5":  "Manual processes with some tooling.",
                 "0_2":  "No matter management described.",
             }, False),
            ("scoring", "Conflict of Interest Management",
             "Formal conflict-check process and ethical wall procedures.",
             "", 0.25, {
                 "9_10": "Automated conflict check system, documented ethical wall, annual independence training.",
                 "6_8":  "Documented conflict policy, manual check process.",
                 "3_5":  "Basic conflict policy exists.",
                 "0_2":  "No conflict policy described.",
             }, False),
            ("scoring", "Qualified Legal Personnel",
             "Seniority and experience of lawyers assigned to this matter.",
             "", 0.25, {
                 "9_10": "Partner-led team, CVs provided, relevant sector specialism confirmed.",
                 "6_8":  "Senior associate-led, appropriate experience.",
                 "3_5":  "Junior team, supervision structure unclear.",
                 "0_2":  "No personnel information provided.",
             }, False),
            ("scoring", "Pricing Transparency",
             "Billing rate clarity, estimate methodology, and blended rate options.",
             "", 0.20, {
                 "9_10": "Fixed fee or capped options offered, blended rates available, matter budget discipline demonstrated.",
                 "6_8":  "Clear hourly rates, budget estimate methodology described.",
                 "3_5":  "Hourly rates only, no estimate provided.",
                 "0_2":  "No pricing information.",
             }, False),
        ],
        "hr": [
            ("mandatory", "DBS Enhanced Check Capability",
             "Vendors providing people-related services must be able to conduct enhanced DBS checks.",
             "Registered with DBS as umbrella body or direct access confirmed with reference number.",
             0.0, {}, False),
            ("scoring", "Payroll Accuracy & HMRC Compliance",
             "Track record of accurate, HMRC-compliant payroll processing.",
             "", 0.30, {
                 "9_10": "Error rate < 0.1%, BACS accredited, fully automated RTI submissions, no HMRC penalties.",
                 "6_8":  "Low error rate, HMRC compliant, RTI supported.",
                 "3_5":  "Basic payroll, some manual steps, occasional errors.",
                 "0_2":  "No payroll accuracy evidence provided.",
             }, False),
            ("scoring", "HRIS Integration Capability",
             "Pre-built integrations with major HRIS platforms.",
             "", 0.25, {
                 "9_10": "Certified integrations with Workday, SAP SuccessFactors, and Oracle HCM; real-time sync.",
                 "6_8":  "Integration available for at least one major HRIS, setup required.",
                 "3_5":  "CSV/flat-file export only.",
                 "0_2":  "No HRIS integration.",
             }, False),
            ("scoring", "Employee Data Privacy",
             "GDPR-compliant handling of employee personal data and subject access request processes.",
             "", 0.25, {
                 "9_10": "Automated erasure workflows, employee self-service portal, DPA signed, DPO appointed.",
                 "6_8":  "Manual erasure process, GDPR policy documented.",
                 "3_5":  "Basic privacy policy, SAR process unclear.",
                 "0_2":  "No employee data privacy information.",
             }, False),
            ("scoring", "Candidate Experience & D&I Tooling",
             "Tools and processes that reduce bias and improve candidate experience.",
             "", 0.20, {
                 "9_10": "Blind-sift tooling, structured interview guides, D&I analytics dashboard, accessibility AA compliant.",
                 "6_8":  "Some bias-reduction features, good candidate communication.",
                 "3_5":  "Standard ATS with minimal D&I features.",
                 "0_2":  "No D&I tooling described.",
             }, False),
        ],
        "operations": [
            ("mandatory", "ISO 9001 Quality Management",
             "Operational vendors must hold current ISO 9001 quality management certification.",
             "ISO 9001 certificate, accredited body, expiry date in future.",
             0.0, {}, False),
            ("scoring", "Operational Resilience & Continuity",
             "Documented processes for maintaining operations through disruption.",
             "", 0.30, {
                 "9_10": "Tested BCP/DR, RTO ≤8h, incident playbooks published, resilience tested annually.",
                 "6_8":  "BCP documented and tested within 18 months.",
                 "3_5":  "BCP exists but not recently tested.",
                 "0_2":  "No continuity plans.",
             }, False),
            ("scoring", "Performance Reporting & Transparency",
             "Quality and cadence of operational reporting.",
             "", 0.25, {
                 "9_10": "Real-time dashboard, monthly executive report, QBR format defined, RAG status visible.",
                 "6_8":  "Monthly reporting, KPIs tracked.",
                 "3_5":  "Quarterly reporting, limited KPIs.",
                 "0_2":  "No reporting described.",
             }, False),
            ("scoring", "Supply Chain Robustness",
             "Vendor sub-contractor management and supply chain risk processes.",
             "", 0.25, {
                 "9_10": "Tiered supplier audit programme, SC risk register, alternative sourcing strategy documented.",
                 "6_8":  "Key sub-contractors identified, periodic audits.",
                 "3_5":  "Sub-contractors named but no audit process.",
                 "0_2":  "Supply chain information absent.",
             }, False),
            ("scoring", "Health, Safety & Wellbeing",
             "HSE compliance and active safety management culture.",
             "", 0.20, {
                 "9_10": "ISO 45001, zero RIDDOR incidents past 3 years, wellbeing programme.",
                 "6_8":  "Good HSE record, active safety management.",
                 "3_5":  "Basic HSE compliance, limited safety culture.",
                 "0_2":  "No HSE information.",
             }, False),
        ],
    }


if __name__ == "__main__":
    seed()
