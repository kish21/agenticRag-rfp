# Observability Plan
*Version 1.0 — 2026-05-14*

---

## Observability Stack

| Tool | Role | Provider Config |
|---|---|---|
| LangSmith | Passive LLM call tracing — every `call_llm()` call | Always active when `LANGCHAIN_API_KEY` is set |
| LangFuse | Active agent run logging — Critic flags, pipeline events | `OBSERVABILITY_PROVIDER=langfuse` |
| stdout JSON | Dev / air-gapped fallback | `OBSERVABILITY_PROVIDER=stdout` |
| Rate monitor job | LLM usage rate vs. limits, runs every 30 min | `app/jobs/rate_monitor.py` (Modal scheduled) |
| Cleanup job | Expired data purge, runs daily | `app/jobs/cleanup.py` (Modal scheduled) |

---

## What Is Traced

### LangSmith (Passive — every LLM call)

Every call to `call_llm()` is decorated with `@traceable(run_type="llm", name="call_llm")`:

| Field | Value |
|---|---|
| run_id | Unique per evaluation run |
| agent_name | Name of the calling agent |
| prompt | Full messages array |
| response | LLM text response |
| latency | Wall clock time |
| model | Model name (from `get_model_name()`) |
| provider | `LLM_PROVIDER` value |

### LangFuse (Active — agent events)

The observability provider logs these event types:

```python
log_event(
    run_id=run_id,
    event_type="critic_flag",       # critic_flag | agent_complete | pipeline_start | pipeline_complete | pipeline_error
    agent_name="extraction",
    flag_type="HARD",               # HARD | SOFT | LOG | ESCALATE
    reason="grounding_quote is empty",
    metadata={"fact_type": "certification", "vendor_id": vendor_id}
)
```

| Event Type | When Logged |
|---|---|
| `pipeline_start` | First agent begins |
| `agent_complete` | Each agent finishes successfully |
| `critic_flag` | Critic issues any flag (HARD / SOFT / LOG / ESCALATE) |
| `pipeline_complete` | Explanation agent finishes, report generated |
| `pipeline_error` | Unhandled exception in any agent |
| `rate_limit_hit` | LLM returns 429, backoff triggered |
| `human_override` | Procurement Manager applies an override |

---

## Dashboards

### LangSmith Dashboard
- View: All `call_llm` traces filtered by `run_id`
- Use for: Debugging extraction failures, slow LLM calls, prompt/response inspection
- URL: `https://smith.langchain.com` → Project: `rfp-eval-prod`

### LangFuse Dashboard
- View: Pipeline runs timeline, Critic flag frequency, agent latency breakdown
- Use for: Production monitoring, flag trend analysis, SLA tracking
- URL: `https://cloud.langfuse.com` → Project: your project

### Key Metrics to Monitor (Weekly)

| Metric | Source | Alert Threshold |
|---|---|---|
| Pipeline success rate | LangFuse `pipeline_complete` / (`pipeline_complete` + `pipeline_error`) | < 99% |
| HARD block rate | LangFuse `critic_flag` where `flag_type=HARD` / total runs | > 5% |
| Average end-to-end latency | LangFuse `pipeline_start` → `pipeline_complete` | > 45 min |
| LLM error rate | LangSmith failed traces | > 1% |
| Rate limit frequency | LangFuse `rate_limit_hit` events | > 10/day |

---

## Rate Monitor Job (`app/jobs/rate_monitor.py`)

Runs every 30 minutes via Modal scheduled function.

**What it checks:**
- LLM requests in last 30 minutes vs. configured daily limit
- Alerts if usage exceeds 80% of limit (early warning)
- Alerts if usage exceeds 100% of limit (action required)

**Alert output:**
```json
{
  "timestamp": "2026-05-14T10:30:00Z",
  "provider": "openai",
  "requests_last_30min": 45,
  "daily_limit": 1000,
  "daily_used_so_far": 820,
  "alert_level": "WARNING",
  "message": "82% of daily limit used — consider throttling or switching to modal"
}
```

Logged to observability provider (LangFuse trace or stdout JSON).

---

## Cleanup Job (`app/jobs/cleanup.py`)

Runs daily via Modal scheduled function.

**What it cleans:**
- `evaluation_runs` older than retention period (product.yaml: 7 years default)
- Qdrant collections for deleted orgs
- Temporary Modal files from completed PDF extraction jobs

**What it never deletes:**
- `audit_overrides` (permanent)
- `org_settings_audit` (permanent)
- Any row within the 7-year retention window

**Output:**
```json
{
  "timestamp": "2026-05-14T00:00:00Z",
  "runs_deleted": 0,
  "collections_deleted": 0,
  "modal_temp_files_deleted": 12,
  "errors": []
}
```

---

## Air-Gapped Observability

When `OBSERVABILITY_PROVIDER=stdout`, all events are logged as structured JSON to stdout:

```json
{"ts": "2026-05-14T10:31:00Z", "event": "critic_flag", "run_id": "abc123", "agent": "extraction", "flag": "SOFT", "reason": "confidence below threshold: 0.68 < 0.70"}
```

This can be piped to any log aggregator (CloudWatch, Splunk, ELK) without code changes.

---

## Incident Detection

### How to detect a production issue

1. **LangFuse:** High HARD block rate → check which agent is blocking
2. **LangSmith:** High LLM error rate → check rate limit or provider outage
3. **Rate monitor:** Alert → switch `LLM_PROVIDER` to fallback (e.g., `modal` instead of `openai`)
4. **Pipeline stuck:** No `pipeline_complete` event after 60 minutes → check Modal GPU cold start

### First 3 steps when something is wrong

```bash
# 1. Check last 10 pipeline runs in LangFuse
# 2. Check LangSmith for the failing run_id
python scripts/debug_run.py --run-id <run_id>
# 3. Check Modal logs
modal logs --env rag
```
