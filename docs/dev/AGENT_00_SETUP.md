# Agent 00 — Setup Agent
**What it does:** Reads the RFP and any customer-uploaded criteria sheet, extracts evaluation criteria using an LLM, merges everything together, detects gaps, and saves a confirmed EvaluationSetup to the database. This setup is the foundation every other agent reads from.

---

## Process Flow

```
Customer uploads RFP PDF + optional criteria CSV
                │
                ▼
    ┌─────────────────────┐
    │  Step 1             │
    │  Extract RFP text   │
    └─────────────────────┘
                │
                ▼
    ┌─────────────────────┐
    │  Step 2             │
    │  Load org + dept    │
    │  criteria from DB   │
    └─────────────────────┘
                │
                ▼
    ┌─────────────────────┐
    │  Step 3             │  ← only if CSV/Excel/PDF sheet uploaded
    │  Parse customer     │
    │  criteria sheet     │
    └─────────────────────┘
                │
                ▼
    ┌─────────────────────┐
    │  Step 4             │  ← LLM call (GPT-4o)
    │  Extract criteria   │
    │  from RFP text      │
    └─────────────────────┘
                │
                ▼
    ┌─────────────────────┐
    │  Step 5             │
    │  Merge all sources  │
    │  (org + dept + RFP  │
    │  + customer sheet)  │
    └─────────────────────┘
                │
                ▼
    ┌─────────────────────┐
    │  Step 6             │  ← LLM call (GPT-4o) only if gaps found
    │  Gap detection +    │
    │  fill missing score │
    │  guides             │
    └─────────────────────┘
                │
                ▼
    ┌─────────────────────┐
    │  Step 7             │
    │  Save EvaluationSetup│
    │  to PostgreSQL      │
    └─────────────────────┘
                │
                ▼
    ┌─────────────────────┐
    │  Step 8             │
    │  Customer reviews + │  ← UI: Page 4b confirm screen
    │  confirms criteria  │
    └─────────────────────┘
                │
                ▼
        Pipeline starts
```

---

## Tools Used Per Step

### Step 1 — Extract RFP text
| What | Tool | LLM? | Cost |
|---|---|---|---|
| Read PDF pages | **pypdf** (open source) | No | Free |
| Join pages into plain text | Python built-in | No | Free |

**Output:** One large plain text string of the entire RFP.

---

### Step 2 — Load org + department criteria from database
| What | Tool | LLM? | Cost |
|---|---|---|---|
| Query org-level criteria templates | **SQLAlchemy** + **PostgreSQL** | No | Free |
| Query department-level criteria templates | **SQLAlchemy** + **PostgreSQL** | No | Free |

**Output:** Lists of mandatory checks and scoring criteria the customer's organisation has pre-configured.

---

### Step 3 — Parse customer criteria sheet (optional)
| What | Tool | LLM? | Cost |
|---|---|---|---|
| Read CSV or Excel file | **pandas** (open source) | No | Free |
| Match standard column names (name, weight, description) | Pure Python string matching | No | Free |
| If columns don't match → interpret sheet | **GPT-4o** via `call_llm()` | **Yes** | ~$0.001 |
| Extract criteria from PDF/DOCX sheet | **pypdf** / **python-docx** + GPT-4o | **Yes** | ~$0.001 |

**Output:** Customer's own mandatory checks and scoring criteria in a standard format.

---

### Step 4 — Extract criteria from RFP text
| What | Tool | LLM? | Cost |
|---|---|---|---|
| Send RFP text to LLM with extraction prompt | **GPT-4o** via `call_llm()` | **Yes** | ~$0.01 |
| Prompt loaded from | **LangSmith** Hub (fallback: local YAML) | No | Free |
| Parse JSON response | Python `json.loads()` | No | Free |
| Normalise weights to sum to 1.0 | Pure Python | No | Free |

**Output:** Mandatory checks and scoring criteria extracted from the RFP document itself.

---

### Step 5 — Merge all criteria sources
| What | Tool | LLM? | Cost |
|---|---|---|---|
| Deduplicate criteria by normalised name | Pure Python `_normalize_name()` | No | Free |
| Merge org + dept + RFP + customer sheet | Pure Python dict merging | No | Free |
| Resolve conflicts (customer sheet wins over RFP; RFP wins over org defaults) | Pure Python priority rules | No | Free |

**Output:** One unified set of mandatory checks + scoring criteria + extraction targets.

> ℹ️ **Note on extraction targets (verified 2026-06-01).** `_build_targets()` currently emits every
> target with `fact_type="custom"`, so downstream extraction stores all facts in the generic
> `extracted_facts` table and the five typed tables stay empty. Categories are still customer-driven
> (via each target's name/description); "custom" just means generic storage. See
> AGENT_04_EXTRACTION.md for the full explanation. Whether to add typed storage is a parked decision.

---

### Step 6 — Gap detection and fill
| What | Tool | LLM? | Cost |
|---|---|---|---|
| Check if any scoring criterion is missing a score guide (rubric) | Pure Python | No | Free |
| Check if any mandatory checks are missing | Pure Python | No | Free |
| If gaps found → generate missing score guides | **GPT-4o** via `call_llm()` | **Yes** | ~$0.005 |
| Flag generated items as amber (needs customer review) | Pure Python | No | Free |

**Output:** Complete EvaluationSetup with all score guides filled. Gap report indicating which items were AI-generated vs customer-defined.

---

### Step 7 — Save to database
| What | Tool | LLM? | Cost |
|---|---|---|---|
| Save EvaluationSetup as JSONB blob | **SQLAlchemy** + **PostgreSQL** `evaluation_setups` table | No | Free |
| Save evaluation run record | **SQLAlchemy** + **PostgreSQL** `evaluation_runs` table | No | Free |
| Save vendor document records with file_bytes | **SQLAlchemy** + **PostgreSQL** `vendor_documents` table | No | Free |
| Write audit log entry | **SQLAlchemy** + **PostgreSQL** `audit_log` table | No | Free |

**Output:** Persisted run with `run_id`, `setup_id`, `rfp_id` returned to the frontend.

---

### Step 8 — Customer confirms criteria (UI)
| What | Tool | LLM? | Cost |
|---|---|---|---|
| Display criteria on review screen | **Next.js** frontend | No | Free |
| Amber badge on AI-generated items | Frontend UI logic | No | Free |
| Customer edits/accepts/rejects | `PUT /api/v1/evaluate/{runId}/setup` | No | Free |
| Customer confirms → pipeline starts | `POST /api/v1/evaluate/{runId}/confirm` | No | Free |

**Output:** `rfp_confirmed = true` on EvaluationSetup. Pipeline is triggered.

---

## LLM Call Summary

| Step | Prompt | When called | Approx cost |
|---|---|---|---|
| Step 3 | `setup/interpret_criteria_sheet` | Only if CSV columns non-standard | ~$0.001 |
| Step 4 | `setup/extract_criteria_from_rfp` | Every run | ~$0.010 |
| Step 6 | `setup/detect_and_fill_gaps` | Only if score guides missing | ~$0.005 |

**Total per run:** ~$0.01–$0.016. Under 2 cents.

---

## Data Saved to Database

| Table | What is saved |
|---|---|
| `evaluation_setups` | Full EvaluationSetup JSON — criteria, weights, score guides, extraction targets |
| `evaluation_runs` | run_id, rfp_id, setup_id, rfp_filename, rfp_bytes, vendor list, contract value |
| `vendor_documents` | doc_id, vendor_id, filename, file_bytes, content_hash per vendor |
| `audit_log` | run.created event with actor, timestamp, vendor count |

---

## Key Files

| File | Role |
|---|---|
| `app/api/evaluation_routes.py` | API endpoint — `POST /evaluate/start` |
| `app/domain/criteria.py` | All criteria extraction, merging, gap detection logic |
| `app/prompts/registry.py` | Loads prompts from LangSmith or local YAML fallback |
| `app/db/fact_store.py` | `save_evaluation_setup()` — persists to PostgreSQL |
| `tools/smoke_test.py` | `run_rfp()` — developer test that mirrors the API exactly |

---

## Known Limitations

| # | Issue | Backlog item |
|---|---|---|
| 1 | Criteria source cannot be selected per run (always merges all sources) | PF-001 |
| 2 | Score guides generated by LLM are not verified against industry standards | AI-003 |
| 3 | No re-extraction if customer edits criteria after confirming | — |
