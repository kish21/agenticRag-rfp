# Incident Response Plan
*Version 1.0 — 2026-05-14*

---

## Severity Levels

| Severity | Definition | Response Time | Examples |
|---|---|---|---|
| P0 — Critical | Platform completely down or data breach | Immediate | All evaluations failing, cross-tenant data leak, database unreachable |
| P1 — High | Key feature broken, workaround exists | 1 hour | Pipeline HARD blocking all runs, LLM provider down, approval workflow broken |
| P2 — Medium | Degraded performance or partial failure | 4 hours | Slow evaluations (>45 min), single agent consistently failing, Modal cold start >15 min |
| P3 — Low | Minor issue, cosmetic, or future risk | Next business day | Dashboard metric slow to update, soft Critic flag rate elevated |

---

## Incident Playbooks

---

### INC-01: All Evaluation Pipelines Failing (P0)

**Symptoms:** No `pipeline_complete` events in LangFuse for >30 minutes. Multiple HARD blocks reported.

**Diagnosis:**
```bash
# Step 1: Check API health
curl https://<api-host>/health

# Step 2: Check Qdrant
curl <QDRANT_URL>/collections

# Step 3: Check PostgreSQL
psql $DATABASE_URL -c "SELECT 1"

# Step 4: Check LLM provider
python scripts/test_llm_call.py

# Step 5: Check Modal (if LLM_PROVIDER=modal)
modal logs --env rag
```

**Recovery:**
- If Qdrant unreachable → restart Qdrant container / check Qdrant Cloud status
- If PostgreSQL unreachable → failover to read replica, restore from last backup
- If LLM provider down → switch `LLM_PROVIDER` to fallback: `openai → openrouter` or `openai → modal`
- If Modal LLM down → switch `LLM_PROVIDER=openai`, restart API

**Communication:** Notify all active customers (procurement managers with in-flight evaluations) within 15 minutes of P0 declaration.

---

### INC-02: Suspected Cross-Tenant Data Leak (P0)

**Symptoms:** A customer reports seeing data from another organisation. Any internal test shows cross-org data returned.

**Immediate actions (first 10 minutes):**
1. Take the API offline immediately (`systemctl stop rfp-api` / scale ECS to 0)
2. Preserve all application logs from the last 24 hours
3. Notify Data Protection Officer
4. Do NOT delete any logs or data until DPO advises

**Investigation:**
```bash
# Identify affected org_ids
python scripts/audit_cross_org_access.py --hours 24

# Check RLS policies are active
python scripts/verify_rls.py

# Check Qdrant queries in LangSmith — look for queries without org_id filter
```

**Root cause categories:**
1. RLS policy disabled on a table (migration gone wrong)
2. org_id filter missing from a Qdrant query (new code path)
3. JWT org_id injection bypassed (API route missing auth dependency)

**Recovery:**
1. Fix the root cause
2. Re-enable platform for unaffected orgs only
3. Full GDPR breach notification process if personal data was exposed (72-hour window)
4. Affected org receives individual notification with details of what was exposed

---

### INC-03: LLM Rate Limit — Pipeline Blocked Mid-Run (P1)

**Symptoms:** `rate_limit_hit` events appearing in LangFuse. Evaluations stuck at a single agent.

**The system is designed for this:** `rate_limiter.py` applies exponential backoff up to 5 retries automatically. This incident only applies if all 5 retries fail.

**Manual recovery:**
```bash
# Option A: Switch to a different provider (no restart required)
# Edit .env: LLM_PROVIDER=openrouter (or modal)
# Restart API: systemctl restart rfp-api (or rolling deploy)

# Option B: Wait for rate limit window to reset (usually 60 seconds for OpenAI)
# Monitor: tail LangFuse logs for rate_limit_hit frequency

# Option C: Resume stuck pipeline from last checkpoint (if LangGraph checkpoint enabled)
python scripts/resume_pipeline.py --run-id <run_id>
```

**Prevention:** Rate monitor job alerts at 80% of limit — switch provider before hitting 100%.

---

### INC-04: Critic Agent HARD Block — Incorrect Block (P2)

**Symptoms:** A Procurement Manager reports the pipeline blocked on a valid document. Override mechanism invoked but customer frustrated.

**This is expected behaviour** — the Critic is strict. But if it's blocking correct content:

**Investigation:**
```bash
# Get the critic output for the blocked run
python scripts/inspect_run.py --run-id <run_id> --agent critic
```

**Common causes:**
1. PDF table parsing issue — cells on separate lines, whitespace normalisation not applied
2. Grounding quote truncated in extraction
3. Retrieval Critic confidence floor too high for this document type

**Fix options:**
1. Procurement Manager applies human override (correct path — creates audit record)
2. If systematic: lower `extraction_critic_confidence_floor` in `platform.yaml` (requires re-test)
3. If PDF format issue: check whitespace normalisation is applied in `_hallucination_risk()`

---

### INC-05: Modal GPU Cold Start > 15 Minutes (P2)

**Symptoms:** Pipeline waiting at LLM call for >10 minutes. Modal logs show container still initialising.

**Context:** Qwen 2.5 72B AWQ cold start on A100 takes 5–10 minutes normally. >15 minutes indicates a problem.

**Recovery:**
```bash
# Check Modal container status
modal app status --env rag

# If container stuck: restart
modal app stop --env rag
modal deploy app_modal.py --env rag

# Short-term: switch to OpenAI while Modal restarts
# Edit .env: LLM_PROVIDER=openai
# Restart API
```

**Prevention:** Set `min_containers=1` in `serve_llm_on_modal` to keep one container warm (Modal billing applies even when idle — cost vs. cold start tradeoff).

---

### INC-06: Database Full / Disk Space Warning (P2)

**Symptoms:** PostgreSQL logs show disk warning. API errors on write operations.

```bash
# Check table sizes
psql $DATABASE_URL -c "
  SELECT schemaname, tablename, pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename))
  FROM pg_tables WHERE schemaname = 'public' ORDER BY pg_total_relation_size(schemaname||'.'||tablename) DESC;
"

# Immediate: run cleanup job manually
python app/jobs/cleanup.py --dry-run   # Check what would be deleted
python app/jobs/cleanup.py             # Run for real

# If still tight: increase disk on cloud provider
```

---

## Post-Incident Review Template

After every P0 or P1:

```markdown
## Incident Review — [Date] [INC-ID]

**What happened:** 
**Duration:** 
**Customers affected:** 
**Root cause:** 
**Timeline:**
  - HH:MM — First alert
  - HH:MM — Diagnosis
  - HH:MM — Fix applied
  - HH:MM — Platform restored

**What worked well:**
**What should improve:**
**Action items (owner, due date):**
```
