# Capacity Planning
*Version 1.0 — 2026-05-14*

---

## Assumptions

| Variable | Pilot (Q3 2026) | 10 Customers (Q1 2027) | 100 Customers (2027) |
|---|---|---|---|
| Customers (orgs) | 1 | 10 | 100 |
| RFPs/org/month | 10 | 10 | 10 |
| Vendors/RFP | 3 | 3 | 3 |
| Pages/vendor doc | 100 | 100 | 100 |
| Concurrent pipeline runs | 2 | 10 | 50 |
| Dashboard active users | 5 | 50 | 500 |

---

## Qdrant (Vector Store)

### Vector Count Growth

| Stage | Chunks per doc | Docs per RFP | RFPs/month | Vectors/month | Total (12 months) |
|---|---|---|---|---|---|
| Pilot | ~400 | 3 | 10 | 12,000 | 144,000 |
| 10 Customers | ~400 | 3 | 100 | 120,000 | 1,440,000 |
| 100 Customers | ~400 | 3 | 1,000 | 1,200,000 | 14,400,000 |

**Qdrant memory requirement:**
- 1 vector = 3072 floats × 4 bytes = ~12KB (dense) + ~1KB (sparse metadata)
- 14.4M vectors × 13KB ≈ **187GB RAM** at full scale
- Qdrant Cloud: 3 nodes × 64GB = 192GB — adequate at 100 customers with compression

### Recommendation

| Stage | Qdrant Setup | Estimated Cost |
|---|---|---|
| Pilot | Qdrant Cloud Starter (4GB RAM) | ~£25/month |
| 10 Customers | Qdrant Cloud Business (16GB RAM) | ~£200/month |
| 100 Customers | Qdrant Cloud Enterprise (3 × 64GB nodes) | ~£2,000/month |

---

## PostgreSQL (Structured Facts)

### Row Count Growth

| Table | Rows per RFP | RFPs/month | Rows/month (10 customers) | Rows/year |
|---|---|---|---|---|
| extracted_certifications | ~5 | 100 | 500 | 6,000 |
| extracted_insurance | ~3 | 100 | 300 | 3,600 |
| extracted_slas | ~4 | 100 | 400 | 4,800 |
| extracted_pricing | ~6 | 100 | 600 | 7,200 |
| extracted_projects | ~5 | 100 | 500 | 6,000 |
| evaluation_scores | ~36 (3 vendors × 12 criteria) | 100 | 3,600 | 43,200 |
| audit_overrides | ~2 (average) | 100 | 200 | 2,400 |

**Total at 10 customers, 12 months: ~73,200 rows** — trivially small for PostgreSQL.
**At 100 customers: ~730,000 rows/year** — still trivially small. PostgreSQL scales to billions.

### Recommendation

| Stage | PostgreSQL Setup | Estimated Cost |
|---|---|---|
| Pilot | Supabase Free (500MB) | £0/month |
| 10 Customers | Supabase Pro (8GB) | ~£25/month |
| 100 Customers | RDS PostgreSQL Multi-AZ (db.r6g.large, 100GB) | ~£300/month |

---

## Modal (GPU Compute)

### LLM Inference (A100-80GB, Qwen 2.5 72B)

| Stage | RFPs/month | LLM calls/RFP | LLM calls/month | Avg call time | GPU-hours/month |
|---|---|---|---|---|---|
| Pilot | 10 | ~50 | 500 | 15s | ~2 GPU-hours |
| 10 Customers | 100 | ~50 | 5,000 | 15s | ~21 GPU-hours |
| 100 Customers | 1,000 | ~50 | 50,000 | 15s | ~208 GPU-hours |

**Modal A100 rate:** ~£3–4/GPU-hour
**Cost at 100 customers:** ~£600–830/month for LLM inference

### Embedding (A10G, BGE batch)

| Stage | Chunks/month | Batch time | GPU-hours/month |
|---|---|---|---|
| 10 Customers | 1,200,000 | 200ms/200 chunks | ~0.3 GPU-hours |
| 100 Customers | 12,000,000 | 200ms/200 chunks | ~3.3 GPU-hours |

**Embedding cost:** Negligible at these scales (~£10–15/month).

### Cold Start Strategy

| Stage | Strategy | Cold start cost |
|---|---|---|
| Pilot | On-demand (no min_containers) | 5–10 min cold start, accepted |
| 10 Customers | `min_containers=1` (1 warm A100) | ~£2,400/month (always-on) |
| 100 Customers | `min_containers=2` (2 warm A100s) | ~£4,800/month (always-on) |

**Decision at 10 customers:** Weigh £2,400/month always-on vs. customer experience of 10-minute cold starts. First paying customer likely requires always-on.

---

## API (FastAPI)

| Stage | Concurrent users | Req/sec (peak) | Setup |
|---|---|---|---|
| Pilot | 5 | 2 | 1 × Cloud Run instance (512MB, 1 CPU) |
| 10 Customers | 50 | 20 | 2 × Cloud Run instances (1GB, 2 CPU) |
| 100 Customers | 500 | 200 | Auto-scaling Cloud Run (max 10 instances) |

**Cost at 100 customers:** ~£200–400/month (Cloud Run, pay-per-request).

---

## Total Cost Summary

| Stage | Qdrant | PostgreSQL | Modal LLM | API | Observability | **Total/month** |
|---|---|---|---|---|---|---|
| Pilot | £25 | £0 | ~£25 | ~£10 | £50 | **~£110** |
| 10 Customers | £200 | £25 | ~£2,500 | ~£50 | £100 | **~£2,875** |
| 100 Customers | £2,000 | £300 | ~£5,000 | ~£400 | £300 | **~£8,000** |

At 100 customers paying £30K/year (£2,500/month), platform gross margin is ~**68%**.
At £60K/year pricing, gross margin is ~**84%**.

---

## Scaling Bottlenecks

| Bottleneck | Threshold | Solution |
|---|---|---|
| Qdrant RAM | >10M vectors per node | Add nodes, enable quantisation |
| PostgreSQL connections | >100 concurrent | PgBouncer connection pooling |
| Modal cold start | >1 concurrent customer | `min_containers=1` (always-on) |
| FastAPI throughput | >100 req/sec | Horizontal scaling (Cloud Run auto-scale) |
| LLM rate limits (OpenAI) | >200 req/min | Switch `LLM_PROVIDER=modal` for burst |
