# Stakeholder Map
*Version 1.0 — 2026-05-14*

---

## Stakeholder Overview

| Stakeholder | Role | Primary Need | Access Level |
|---|---|---|---|
| CEO | Executive sponsor | Global spend visibility, vendor risk, board reporting | Full — all departments, all regions |
| CFO | Budget authority | Cost commitments, savings realised, pricing anomalies | Full financial view |
| Regional Director | Regional P&L owner | Their region's RFPs, vendor decisions, budget impact | Region-scoped |
| Department Head | Evaluation initiator | Their department's active RFPs, vendor recommendations | Department-scoped |
| Procurement Manager | Day-to-day operator | Run evaluations, review agent output, apply overrides | Full pipeline access |
| Legal Reviewer | Compliance gatekeeper | Contract clauses, liability, SLA terms | Read-only on relevant evaluations |
| IT Admin | Platform operator | Tenant onboarding, API key rotation, data purge | Admin — no vendor data |
| Vendor | RFP respondent | Submit documents, receive decision notification | Submission portal only |
| External Auditor | Compliance reviewer | Audit trail, override log, decision evidence | Read-only audit log |

---

## Stakeholder Detail

### CEO
- **What they see**: Global dashboard — active RFPs by department/region, total committed spend, duplicate vendor alerts, pricing anomaly flags, vendor concentration risk
- **What they care about**: "Are we paying too much? Are we too reliant on one vendor? Are all decisions documented?"
- **Decision authority**: Can escalate any evaluation for board review
- **Engagement cadence**: Weekly automated digest, real-time dashboard access

### CFO
- **What they see**: Spend dashboard — committed vs. budgeted, savings vs. prior period, contract value by department
- **What they care about**: "What is the total vendor spend commitment this quarter? Where are we overpaying?"
- **Decision authority**: Approves contracts above £500K
- **Engagement cadence**: Monthly board pack, real-time dashboard access

### Regional Director
- **What they see**: Region-filtered view — all RFPs in their geography, local vendor decisions, regional spend
- **What they care about**: "What vendors are we choosing in my region and are we getting the right price?"
- **Decision authority**: Approves contracts £100K–£500K within their region
- **Engagement cadence**: On-demand dashboard access

### Department Head
- **What they see**: Department-filtered view — their active and historical RFPs, vendor scores, recommendations
- **What they care about**: "Is the evaluation complete? Which vendor does the AI recommend and why?"
- **Decision authority**: Approves contracts under £100K; escalates above
- **Engagement cadence**: Triggered notifications at each pipeline milestone

### Procurement Manager
- **What they see**: Full pipeline — upload documents, trigger evaluation, review extraction results, apply human overrides with justification
- **What they care about**: "Is the AI right? Where do I need to intervene? Is the output good enough to share with the Department Head?"
- **Decision authority**: Can apply overrides (all overrides create an immutable audit record)
- **Engagement cadence**: Active user during every evaluation run

### Legal Reviewer
- **What they see**: Evaluation reports — contract clause extractions, SLA terms, liability caps, insurance requirements
- **What they care about**: "Has the AI correctly extracted the liability clause? Is the vendor's PI insurance adequate?"
- **Decision authority**: Can flag an evaluation for re-review; cannot override scores
- **Engagement cadence**: Invited into specific evaluations by Procurement Manager

### IT Admin
- **What they see**: Admin console — tenant list, user management, API key status, data retention settings
- **What they care about**: "Is the platform healthy? Can I onboard a new department without touching code?"
- **Decision authority**: Platform configuration only; no access to vendor evaluation data
- **Engagement cadence**: On-demand

### Vendor
- **What they see**: Submission portal — upload their response documents, receive acknowledgement, receive outcome notification
- **What they care about**: "Was my submission received? When will I hear the outcome?"
- **Decision authority**: None — receives notification only
- **Engagement cadence**: At submission and at decision

### External Auditor
- **What they see**: Read-only audit log — all decisions, all overrides, all agent critic flags, timestamps, user IDs
- **What they care about**: "Is every decision traceable? Were human overrides justified? Is the 7-year retention intact?"
- **Decision authority**: None — observer only
- **Engagement cadence**: Annual audit cycle or on-demand

---

## Influence / Interest Matrix

```
HIGH INTEREST
    │
    │  Legal Reviewer        CEO / CFO
    │  Dept Head             Regional Director
    │  Procurement Mgr
    │
    │  IT Admin              External Auditor
    │  Vendor
    │
LOW INTEREST
    └─────────────────────────────────────────
      LOW INFLUENCE          HIGH INFLUENCE
```

**Keep satisfied:** CEO, CFO, Regional Director — high influence, give them the best dashboard
**Manage closely:** Procurement Manager — high interest, daily user, must trust the output
**Keep informed:** Legal Reviewer, External Auditor — periodic engagement at key milestones
**Monitor:** Vendor — low influence but failure to communicate damages brand

---

## Escalation Path

```
Procurement Manager → Department Head → Regional Director → CFO → CEO → Board
                   ↑
              AI Critic Agent (hard block → auto-escalates to Procurement Manager)
```
