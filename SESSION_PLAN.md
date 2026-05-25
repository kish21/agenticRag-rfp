# Session Plan — Setup Agent Test Scenarios
**Next session goal:** Run and verify all 4 setup scenarios, then move to Agent 1 (Ingestion)

---

## Context (what was built last session)

- **LangSmith prompt registry** — 4 prompts live at `app/prompts/setup/`, pushed to LangSmith Hub
- **Gap detection** (#116) — LLM generates score guides + mandatory checks when both CSV and RFP are missing them
- **Smart criteria merge** (#115) — RFP score guides enrich CSV criteria; RFP mandatory checks added if missing
- **Criteria review screen** (#117) — ConfirmSetupPage.tsx shows AI-generated items with amber badge + acknowledgment gate
- **Smoke test** mirrors exact UI code path (`POST /api/v1/evaluate/start`)

---

## Session Start (always run first)

```bash
python tools/checkpoint_runner.py status
python tools/drift_detector.py
python tools/contract_tests.py
```

---

## The 4 Test Scenarios

### Scenario 1 — Perfect CSV (everything provided, no LLM gap filling needed)

**What it tests:** CSV has complete scoring criteria with weights, score guide bands, and mandatory checks. RFP may add nothing new. Expect only 1 LLM call (RFP extraction).

**Files:** Existing main documents
```bash
python tools/smoke_test.py --reset

python tools/smoke_test.py --agent rfp \
  --rfp data/documents/RFP_IT_Managed_Services_MFS_2026.pdf \
  --criteria data/documents/Vendor_Selection_Criteria_MFS.csv \
  --vendor-pdf data/documents/Acme_ClearPath_Proposal.pdf \
  --vendor-pdf data/documents/nightbuilb_Apex_Technology_Proposal.pdf
```

**What to verify:**
- [ ] 4 scoring criteria with correct weights (0.35 / 0.30 / 0.20 / 0.15)
- [ ] Score guides shown as `[score guide: YES]` for all 4 criteria
- [ ] Source shown as `user` or `rfp` (not `generated`)
- [ ] No `GAPS DETECTED` section — or if gaps appear, they come from RFP content
- [ ] `run_id` saved to `.smoke_test_state.json`
- [ ] LLM calls: ideally 1 (just RFP extraction), max 2 if RFP adds mandatory checks

---

### Scenario 2 — CSV has weights only, RFP has score guides

**What it tests:** Customer uploaded a CSV with just name + weight + description. No rubric columns. The RFP document contains score guide bands. Merge should enrich CSV criteria with RFP's score guides. Source = `rfp`.

**Files:** New lightweight CSV + main RFP
```bash
python tools/smoke_test.py --reset

python tools/smoke_test.py --agent rfp \
  --rfp data/documents/RFP_IT_Managed_Services_MFS_2026.pdf \
  --criteria data/documents/agent0-setup-s2-rfp-guides/criteria_weights_only.csv \
  --vendor-pdf data/documents/Acme_ClearPath_Proposal.pdf
```

**What to verify:**
- [ ] 3 scoring criteria loaded from CSV
- [ ] Score guides show as `[score guide: YES]` — pulled from RFP
- [ ] Score guide source = `rfp` (check smoke test output says "Score guides added ... from RFP")
- [ ] If RFP has mandatory checks → they appear with source `rfp`
- [ ] If RFP has NO score guides either → `GAPS DETECTED` section appears with `source: generated`
- [ ] LLM calls: 1 (RFP extraction) + possibly 1–2 if gaps remain

---

### Scenario 3 — Both CSV and RFP missing score guides (gap detection)

**What it tests:** Neither the CSV nor the RFP defines score guide bands or mandatory checks. Gap detection fires and LLM generates both. All generated items marked as needing customer review.

**Files:** Existing gap detection folder (already proven working)
```bash
python tools/smoke_test.py --reset

python tools/smoke_test.py --agent rfp \
  --rfp data/documents/agent1-gapdetection/RFP_Cloud_Services_NoGuides.pdf \
  --criteria data/documents/agent1-gapdetection/criteria_no_guides.csv \
  --vendor-pdf data/documents/agent1-gapdetection/Vendor_TechNova_Proposal.pdf
```

**What to verify:**
- [ ] `GAPS DETECTED` section appears
- [ ] Score guides generated for all 3 criteria (`source: generated`)
- [ ] 3–5 mandatory checks suggested (`source: generated`)
- [ ] All items marked `needs customer review`
- [ ] LLM calls: 3 (RFP extraction + Gap 1 score guides + Gap 2 mandatory checks)
- [ ] `gaps_report` saved to state (check `.smoke_test_state.json`)

---

### Scenario 4 — Non-standard CSV headers (LLM sheet interpretation fallback)

**What it tests:** Customer uploaded a CSV with completely different column names (Criterion, Weighting %, Category, etc.). Pandas finds 0 scoring criteria → LLM fallback fires to interpret the sheet. LLM extracts criteria correctly despite non-standard format.

**Files:** New non-standard CSV + existing RFP
```bash
python tools/smoke_test.py --reset

python tools/smoke_test.py --agent rfp \
  --rfp data/documents/RFP_IT_Managed_Services_MFS_2026.pdf \
  --criteria data/documents/agent0-setup-s4-nonstandard/criteria_nonstandard.csv \
  --vendor-pdf data/documents/Acme_ClearPath_Proposal.pdf
```

**What to verify:**
- [ ] Console prints: `trying LLM fallback…` for the criteria sheet
- [ ] 3 scoring criteria extracted despite non-standard headers
- [ ] 1 mandatory check extracted (`Data Residency` — marked MANDATORY in CSV)
- [ ] Weights normalised to sum to 1.0 (40/35/25 → 0.40/0.35/0.25)
- [ ] LLM calls: 1 (RFP extraction) + 1 (sheet interpretation) + possibly 1–2 (gaps)

---

## After All 4 Pass — Move to Agent 1 (Ingestion)

Once all 4 setup scenarios pass, continue the smoke test pipeline with the best run_id:

```bash
# Check which run_id is in state
cat .smoke_test_state.json

# Agent 1 — Ingestion (run for each vendor separately)
python tools/smoke_test.py --agent ingestion --vendor Acme_ClearPath_Proposal
python tools/smoke_test.py --agent ingestion --vendor nightbuilb_Apex_Technology_Proposal

# Agent 2 — Extraction
python tools/smoke_test.py --agent extraction --vendor Acme_ClearPath_Proposal
python tools/smoke_test.py --agent extraction --vendor nightbuilb_Apex_Technology_Proposal
```

---

## Open Issues to Close

| Issue | Status | Action |
|-------|--------|--------|
| #115  | Built ✅ | Close — smart merge working |
| #116  | Built ✅ | Close — gap detection working |
| #117  | Built ✅ | Close — review screen + LangSmith prompts working |
| #118  | Open   | Rename `rubric` → `score guide` in frontend UI |
| #109  | In progress | Continue smoke test through all 9 agents |

---

## Quick Reference — Prompt Registry

```
app/prompts/setup/
  extract_rfp_criteria.yaml      → LangSmith: setup-extract-rfp-criteria
  generate_score_guides.yaml     → LangSmith: setup-generate-score-guides
  suggest_mandatory_checks.yaml  → LangSmith: setup-suggest-mandatory-checks
  interpret_criteria_sheet.yaml  → LangSmith: setup-interpret-criteria-sheet

Push to LangSmith (after editing a YAML):
  python tools/push_prompts.py

View on LangSmith:
  https://smith.langchain.com/prompts
```

---

## Expected LLM Call Count Per Scenario

| Scenario | Call 1 | Call 2 | Call 3 | Call 4 | Total |
|----------|--------|--------|--------|--------|-------|
| S1 Perfect CSV | RFP extract | — | — | — | **1** |
| S2 Weights only | RFP extract | Gap 1 or 2 (if needed) | — | — | **1–3** |
| S3 Gap detection | RFP extract | Gap 1 (score guides) | Gap 2 (mandatory) | — | **3** |
| S4 Non-standard | RFP extract | Sheet interpret | Gap 1 or 2 | — | **2–4** |
