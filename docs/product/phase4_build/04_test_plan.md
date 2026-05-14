# Test Plan
*Version 1.0 — 2026-05-14*

---

## Test Levels

| Level | Tool | When |
|---|---|---|
| Unit | pytest | After every file change |
| Integration | pytest + real Qdrant + real PostgreSQL | After every agent change |
| Contract | `contract_tests.py` | Start of every session |
| Checkpoint | `checkpoint_runner.py` | After every build step |
| Drift detection | `drift_detector.py` | End of every session |
| Evaluation (AI quality) | `tests/evaluation/*.py` | See evaluation_framework.md |
| Load / performance | locust | Before pilot customer |
| Security | manual + automated | Before public release |

---

## Unit Tests

### Scope: Individual functions and classes, mocked dependencies

| Module | What is tested | File |
|---|---|---|
| `llm_provider.py` | Provider selection, `get_model_name()`, `call_llm()` with mock client | `tests/unit/test_llm_provider.py` |
| `embedding_provider.py` | Provider selection, dimension lookup | `tests/unit/test_embedding_provider.py` |
| `reranker_provider.py` | Provider selection, reranking logic | `tests/unit/test_reranker_provider.py` |
| `org_settings.py` | Default resolution, cache behaviour, upsert | `tests/unit/test_org_settings.py` |
| `output_models.py` | Pydantic model validation, field validators | `tests/unit/test_output_models.py` |
| `rate_limiter.py` | Backoff behaviour, max retries | `tests/unit/test_rate_limiter.py` |
| `override_mechanism.py` | Override creates AuditOverride, empty justification rejected | `tests/unit/test_override.py` |
| Whitespace normalisation | PDF table cell grounding quote check passes after normalisation | `tests/unit/test_grounding.py` |

---

## Integration Tests

### Scope: Real Qdrant + real PostgreSQL, mocked LLM

| Test | What is verified | Expected |
|---|---|---|
| Ingestion → Qdrant | Chunks stored with correct org_id, vendor_id, dense+sparse vectors | chunk_count > 0, collection named correctly |
| Retrieval isolation | Org A cannot retrieve Org B's chunks (different org_id filters) | Zero results for cross-org query |
| Extraction → PostgreSQL | Facts written with grounding_quote non-empty, source_chunk_id present | Row count > 0, grounding_quote non-empty |
| RLS isolation | PostgreSQL query with wrong org_id returns no rows | Zero rows returned |
| Override audit | Override creates AuditOverride row, empty justification rejected | Row exists, 422 on empty justification |
| Org settings cache | New org inherits product.yaml defaults, DB row overrides cache within 60s | Correct defaults, override visible after TTL |
| Tenant purge | DELETE /admin/orgs/{org_id}/data removes all Qdrant + PostgreSQL rows | Zero rows remaining for org |

---

## Contract Tests (`contract_tests.py`)

These run at the start of every session and verify structural invariants:

| Contract | Check |
|---|---|
| Every agent has a Pydantic output model | Import each agent, verify output model is a BaseModel subclass |
| Every output model has required fields | Verify `grounding_quote`, `confidence`, `org_id` in relevant models |
| Critic check exists for each agent | Verify Critic node is wired in LangGraph after each agent node |
| No direct provider SDK imports in agent files | Grep `app/agents/*.py` for `from openai`, `from anthropic` — expect zero |
| Config fields load without error | Load `product.yaml` and `platform.yaml`, verify all required fields present |

---

## Checkpoint Tests (`checkpoint_runner.py`)

65 checkpoints across 9 skills. Each checkpoint verifies a specific build outcome:

```bash
python checkpoint_runner.py status       # Show all 65 checkpoints and current status
python checkpoint_runner.py run SK04-CP02  # Run specific checkpoint
python checkpoint_runner.py run all      # Run all checkpoints
```

Current status: 65/66 passed (Q09 regression assertion is above threshold).

---

## Multi-Tenancy Isolation Tests

Critical path — zero tolerance for failures:

```bash
python tests/integration/test_tenant_isolation.py --orgs 10 --concurrent-requests 50
```

**What it does:**
1. Creates 10 simulated orgs, each with their own vendor documents ingested
2. Sends 50 concurrent API requests mixing org_ids
3. Verifies every response contains only data for the requesting org
4. Verifies Qdrant returns zero cross-org chunks
5. Verifies PostgreSQL RLS returns zero cross-org rows

**Expected:** Zero cross-tenant data leakage across all 500 request combinations.

---

## Override & Audit Tests

```bash
python tests/integration/test_override_audit.py
```

| Test Case | Expected |
|---|---|
| Override with valid justification | AuditOverride row created, status 200 |
| Override with empty justification | 422 Unprocessable Entity |
| Override with justification = whitespace only | 422 Unprocessable Entity |
| Attempt to UPDATE AuditOverride row directly | PostgreSQL rule blocks → no change |
| Attempt to DELETE AuditOverride row directly | PostgreSQL rule blocks → no change |
| Export audit log via API | JSON with all override records, status 200 |

---

## Load Tests

Run before pilot customer deployment:

```bash
locust -f tests/load/locustfile.py --host http://localhost:8000 --users 20 --spawn-rate 2
```

**Scenarios:**

| Scenario | Users | Duration | Acceptance Criteria |
|---|---|---|---|
| Dashboard reads (CEO) | 20 concurrent | 5 minutes | p95 < 500ms, zero errors |
| Parallel evaluation runs | 5 concurrent | 10 minutes | All complete < 45 min, zero cross-org leaks |
| File upload (50MB PDF) | 3 concurrent | 5 minutes | All ingested < 5 min, zero failures |

---

## Security Tests

| Test | Method | Acceptance |
|---|---|---|
| JWT without org_id claim | Send request with malformed JWT | 401 |
| org_id in request body (bypass attempt) | POST with `{"org_id": "other-org", ...}` | org_id from JWT is used, not body |
| SQL injection in vendor_id | vendor_id = `'; DROP TABLE extracted_facts; --` | Parameterised query — no effect |
| Unauthenticated request | No Authorization header | 401 |
| Cross-tenant override attempt | Override run_id belonging to different org | 403 or zero effect |
| Large file (> 500MB) | Upload 600MB file | 413 Request Entity Too Large |

---

## Test Data

| File | Contents |
|---|---|
| `tests/data/sample_vendor_response.pdf` | Synthetic 50-page vendor response with certifications, insurance, SLAs |
| `tests/data/sample_vendor_response_2.pdf` | Second vendor (for comparison tests) |
| `tests/data/extraction_test_set.json` | 60 criterion-vendor pairs with ground truth annotations |
| `tests/data/red_team_injections.json` | 50 deliberately hallucinated facts for adversarial testing |
| `tests/data/retrieval_test_set.json` | Retrieval test set with annotated correct chunks per criterion |

---

## Regression Tests

Run after any change to `app/agents/extraction.py` or `app/agents/critic.py`:

```bash
python tests/regression/test_whitespace_normalisation.py
python tests/regression/test_grounding_check.py
python tests/regression/test_critic_blocks.py
```

The whitespace normalisation fix (PDF table cells → single-space joining) must pass on every run. Any revert of this fix will cause the grounding check to fail for table-format PDFs — a known previous failure mode.
