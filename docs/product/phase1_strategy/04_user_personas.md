# User Personas
*Version 1.0 — 2026-05-14*

---

## Persona 1 — The Executive Sponsor (CEO)

**Name:** Sarah Chen
**Title:** Group CEO
**Organisation:** FTSE 250 infrastructure services company, 8,000 employees, 14 countries

### Context
Sarah runs a large, decentralised organisation where each regional MD has significant autonomy over vendor decisions. She has no visibility into what the company is spending with vendors until the CFO produces a quarterly report — by which point, bad decisions have already been made. She is preparing for a board meeting where she needs to demonstrate responsible AI governance and procurement hygiene.

### Goals
- See total vendor spend commitment across all departments and regions in one view
- Know immediately if two departments are about to sign contracts with the same vendor at different prices
- Confirm every major vendor decision has a documented, auditable rationale
- Show the board that AI is being used responsibly in procurement

### Frustrations
- "I found out we signed three separate contracts with the same IT vendor last quarter — different prices, different terms. No one told me."
- "When the auditors came, we couldn't find the rationale for a $2M vendor decision from 18 months ago."
- "My regional MDs make vendor decisions in isolation. I have no idea what our total exposure to Vendor X is."

### What She Needs from the Platform
- CEO dashboard with global view: active RFPs, committed spend, vendor concentration, pricing anomalies
- Weekly automated digest email
- One-click drill-down from the summary to the underlying evidence
- Board-ready PDF report generated automatically

### Jobs-to-be-Done
> "When I open my laptop on Monday morning, I need to know what vendor decisions were made last week, what we committed to spend, and whether anything needs my attention — without having to ask anyone."

---

## Persona 2 — The Procurement Manager (Power User)

**Name:** James Okafor
**Title:** Senior Procurement Manager
**Organisation:** UK Local Council, procurement team of 4

### Context
James manages 40–60 RFP evaluations per year across IT, facilities, legal services, and social care. His team is stretched thin — he has two analysts and is expected to keep up with a growing volume of supplier decisions. He has been burned before by a vendor evaluation where a key compliance clause was missed, leading to a failed contract and a procurement tribunal.

### Goals
- Evaluate 3 vendors in parallel in under an hour
- Verify that every compliance claim made by a vendor is backed by an actual document
- Produce a report that will survive scrutiny by the council's external auditors
- Apply a human override when the AI recommendation doesn't match his professional judgement — with a full audit trail

### Frustrations
- "I spent 6 hours reading a 180-page vendor proposal and I still wasn't sure I'd caught everything."
- "The AI tools I've tried before just summarise documents. They don't tell me *where* in the document they found a fact."
- "Every time I override a recommendation I have to write a separate justification email. It disappears into an inbox."

### What He Needs from the Platform
- Upload portal: drag-and-drop multiple vendor PDFs
- Extraction view: see every extracted fact alongside its verbatim source quote
- Override panel: click to override a score or decision, mandatory justification field, audit record created automatically
- PDF report: ready to share with the Department Head and auditors immediately after the run

### Jobs-to-be-Done
> "When I receive 4 vendor proposals, I need to compare them on 12 compliance criteria in under 2 hours, with evidence for every score, so that if an unsuccessful vendor challenges the outcome, I can defend every decision."

---

## Persona 3 — The Department Head (Approver)

**Name:** Dr. Priya Sharma
**Title:** Director of Digital & Technology
**Organisation:** NHS Trust, 500-bed hospital

### Context
Priya runs a department of 80 people and manages a technology vendor budget of $3.2M per year. She is not a procurement expert — she relies on her Procurement Manager to run evaluations. She needs to make approval decisions quickly and confidently, based on a summary she can trust. She is accountable to the Trust Board for every technology vendor decision.

### Goals
- Review a vendor recommendation in under 15 minutes and make an approval decision
- Understand *why* the AI recommended Vendor A over Vendor B without reading 200 pages
- Sign off with confidence that the evaluation is defensible to the board and to NHS procurement standards

### Frustrations
- "The procurement team sends me a 40-page report. I don't have time to read it. I need the key points."
- "I approved a vendor recommendation once that turned out to be wrong. I didn't know the scoring was based on the analyst's interpretation, not the actual document."
- "I have no idea what other departments in the Trust are spending on similar services."

### What She Needs from the Platform
- Executive summary: 1-page view — recommended vendor, score, key differentiators, risk flags
- Evidence confidence: see that every score is grounded in a source quote, not AI opinion
- One-click approval with digital signature
- Notification if her approval is blocking the pipeline

### Jobs-to-be-Done
> "When my Procurement Manager sends me an evaluation, I need to approve or challenge it in under 15 minutes, with enough evidence to justify my decision at the next board meeting."

---

## Persona 4 — The Regional CFO (Financial Gatekeeper)

**Name:** Marcus Weber
**Title:** CFO, EMEA Region
**Organisation:** Global professional services firm, 45 countries

### Context
Marcus oversees vendor spend across 22 countries in EMEA. He approves all contracts over €500K and is responsible for presenting vendor cost optimisation to the group CFO quarterly. He has recently discovered that three offices in EMEA are each paying different rates to the same cloud infrastructure vendor — with no one having negotiated a consolidated deal.

### Goals
- Know immediately when a contract commitment exceeds €500K anywhere in EMEA
- Identify where the company is paying inconsistent prices to the same vendor across regions
- Track savings realised from consolidated vendor negotiations
- Get a clean spend report for the group CFO with no manual aggregation

### Frustrations
- "I have 22 country finance teams. By the time I aggregate their vendor spend into a single number, it's 6 weeks old."
- "We found out we were paying three different prices to the same vendor in France, Germany, and the UK. Nobody flagged it."
- "The approval process for large contracts is an email chain. I can't see who approved what and when."

### What He Needs from the Platform
- EMEA spend dashboard: real-time, filterable by country, department, vendor, spend category
- Pricing anomaly alerts: automated flag when the same vendor is engaged at >15% price variance across regions
- Approval audit trail: immutable record of who approved what, when, and based on what evidence
- Export to board pack format: one click, not one week

### Jobs-to-be-Done
> "When a contract above €500K is about to be signed anywhere in EMEA, I need to know before it happens, see the evaluation evidence, and either approve or challenge it — from my dashboard, not from an email chain."

---

## Persona 5 — The IT Admin (Platform Operator)

**Name:** Liam Tremblay
**Title:** Senior IT Engineer
**Organisation:** Enterprise SaaS customer IT team

### Context
Liam is responsible for onboarding the platform for his company's internal use. He is not an AI engineer — he understands cloud infrastructure, IAM, and API integrations. He needs to configure the platform for his organisation's specific requirements (LLM provider, data residency, RBAC) without touching source code.

### Goals
- Onboard a new department (tenant) in under 30 minutes using only configuration files and the admin UI
- Rotate API keys without downtime
- Ensure vendor data from Department A is completely isolated from Department B
- Configure the platform to use the company's Azure OpenAI deployment instead of OpenAI directly

### Frustrations
- "AI platforms are usually black boxes. I can't tell what data is stored where or how to purge a tenant."
- "Every time we need to add a new department, we have to ask the vendor to do it. We need self-service."
- "We're on Azure — we can't send data to OpenAI directly. The platform has to support our own deployment."

### What He Needs from the Platform
- Admin console: tenant management, user RBAC, API key rotation, data purge
- .env / config-file driven: swap LLM_PROVIDER=azure, no code changes
- Tenant isolation: confirmed by design docs and test results, not just a promise
- Audit log export: pull any tenant's full decision history for compliance requests

### Jobs-to-be-Done
> "When my CISO asks 'where does vendor data go and how do we delete it?', I need to answer that question from documentation and configuration, not by raising a ticket with the vendor."
