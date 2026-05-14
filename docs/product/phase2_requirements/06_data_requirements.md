# Data Requirements
*Version 1.0 — 2026-05-14*

---

## 1. Input Data

### 1.1 Vendor Response Documents

| Attribute | Requirement |
|---|---|
| Formats accepted | PDF (primary), DOCX (secondary) |
| Max file size | 500MB per file |
| Page range | 1–500 pages (>50 pages → Modal burst CPU for extraction) |
| Language | English (primary); multilingual support planned Q4 2026 |
| Document types | Vendor proposals, RFP responses, compliance certifications, financial statements, insurance certificates |
| Scanned PDFs | Supported via OCR on Modal (CPU burst) |
| Password-protected PDFs | Not supported — vendor must submit unlocked copy |

### 1.2 RFP / Evaluation Criteria

| Attribute | Requirement |
|---|---|
| Source | Customer-configured criteria loaded from org_settings + product.yaml |
| Format | YAML (platform config) or JSON (via admin API) |
| Per-criterion fields | criterion_name, what_passes (threshold rule), weight, section_type |
| Customisable per org | Yes — via admin API, changes stored in org_settings table |

### 1.3 Customer Configuration Data

| Attribute | Requirement |
|---|---|
| Source | .env file + product.yaml + platform.yaml |
| Sensitive fields | API keys, DB credentials — env vars only, never in YAML |
| Per-org settings | org_settings table in PostgreSQL, TTL-cached (60 seconds) |

---

## 2. Stored Data

### 2.1 Vector Store (Qdrant)

| Field | Type | Notes |
|---|---|---|
| org_id | string (filter) | Tenant isolation — all queries must include |
| vendor_id | string (filter) | Evaluation isolation within a tenant |
| run_id | string (filter) | Links chunk to a specific evaluation run |
| section_type | string (filter) | e.g. certifications / sla / pricing / general |
| priority | string (filter) | high / medium / low |
| dense vector | float[3072] | text-embedding-3-large (or 1024 for BGE local) |
| sparse vector | BM25 sparse | 100K hash bins |
| chunk_text | string (payload) | Original chunk text |
| source_page | int (payload) | Page number in source document |
| chunk_index | int (payload) | Position in document |

**Collection naming:** `{org_id}__{vendor_id}` — enforced in `qdrant_client.py`

### 2.2 Structured Facts (PostgreSQL)

#### extracted_certifications
| Column | Type | Notes |
|---|---|---|
| id | UUID | Primary key |
| org_id | text | Tenant isolation (RLS enforced) |
| vendor_id | text | Evaluation scope |
| run_id | text | Links to pipeline run |
| cert_type | text | e.g. ISO_27001, Cyber_Essentials |
| cert_number | text | Certificate identifier |
| issuer | text | Certifying body |
| valid_until | date | Expiry date |
| grounding_quote | text | Verbatim text from source document |
| source_chunk_id | text | Qdrant chunk ID |
| created_at | timestamp | |

#### extracted_insurance
| Column | Type | Notes |
|---|---|---|
| insurance_type | text | e.g. Professional_Indemnity, Public_Liability |
| coverage_amount | numeric | In source currency |
| currency | text | GBP / USD / EUR |
| provider | text | Insurance company name |
| policy_number | text | Policy identifier |
| grounding_quote | text | Verbatim |
| source_chunk_id | text | |

#### extracted_slas
| Column | Type | Notes |
|---|---|---|
| sla_type | text | e.g. uptime, response_time, resolution_time |
| value | text | e.g. "99.9%", "4 hours" |
| measurement_period | text | e.g. monthly, annual |
| grounding_quote | text | Verbatim |
| source_chunk_id | text | |

#### extracted_pricing
| Column | Type | Notes |
|---|---|---|
| item_description | text | What is being priced |
| unit_price | numeric | |
| currency | text | |
| pricing_model | text | e.g. per_seat, per_transaction, fixed |
| grounding_quote | text | Verbatim |
| source_chunk_id | text | |

#### extracted_projects
| Column | Type | Notes |
|---|---|---|
| project_name | text | Reference project name |
| client | text | Reference client (may be anonymised) |
| value | numeric | Contract value if disclosed |
| duration_months | int | |
| sector | text | e.g. NHS, local_government, financial_services |
| grounding_quote | text | Verbatim |
| source_chunk_id | text | |

#### extracted_facts (generic)
| Column | Type | Notes |
|---|---|---|
| fact_type | text | Free-form category |
| fact_value | text | Extracted value |
| key_identifier | text | Certificate number, date, amount — whatever is relevant |
| grounding_quote | text | Verbatim |
| source_chunk_id | text | |

### 2.3 Evaluation & Decision Data

| Table | Purpose |
|---|---|
| evaluation_runs | One row per pipeline run — status, timestamps, vendor list |
| evaluation_scores | Per-criterion scores per vendor per run |
| evaluation_comparisons | Comparator output — cross-vendor ranking |
| evaluation_decisions | Decision agent output — recommended vendor, approval tier |
| org_settings | Per-org configuration (quality tier, output language, etc.) |
| org_settings_audit | Immutable log of org_settings changes |
| audit_overrides | Immutable human override records |
| rfp_confirmations | RFP identity confirmation records |

---

## 3. Data Lineage

```
Source PDF
  → LlamaIndex chunker (chunks with metadata)
  → Qdrant (dense + sparse vectors, org_id scoped)
  → Retrieval agent (top-k chunks per criterion)
  → Extraction agent (structured facts → PostgreSQL)
  → Evaluation agent (reads PostgreSQL facts → scores)
  → Comparator agent (SQL join cross-vendor → ranking)
  → Decision agent (routing → approval record)
  → Explanation agent (report ← PostgreSQL + Qdrant)
  → PDF report + CEO dashboard
```

Every step preserves the `source_chunk_id` link back to the original chunk.
Every fact preserves the `grounding_quote` back to the original text.

---

## 4. Data Retention

| Data Type | Retention Period | Enforcement |
|---|---|---|
| Vendor documents (raw) | Duration of contract + 7 years | Cleanup job (daily) |
| Extracted facts (PostgreSQL) | 7 years from evaluation date | product.yaml `audit.retain_decisions_years: 7` |
| Audit overrides | 7 years (immutable) | Insert-only table policy |
| Vector embeddings (Qdrant) | Duration of org tenancy | Admin purge API |
| LLM call traces (LangSmith) | LangSmith retention policy (configurable) | LangSmith project settings |
| Observability logs (LangFuse) | LangFuse retention policy (configurable) | LangFuse project settings |

---

## 5. Data Privacy

| Requirement | Implementation |
|---|---|
| Vendor PII (contact names in documents) | Extracted only as part of structured facts — not stored separately |
| Cross-tenant isolation | org_id RLS in PostgreSQL + filter in Qdrant — verified by automated tests |
| GDPR right to erasure | Admin API: `DELETE /admin/orgs/{org_id}/data` — purges Qdrant collection + PostgreSQL rows |
| Data residency | Cloud region configured via infrastructure provider settings — not cross-region by default |
| LLM data handling | Data sent to OpenAI/Anthropic per their API data policies; Azure OpenAI keeps data in-region |
