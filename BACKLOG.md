# BACKLOG
# Items noticed during this conversation that belong in future development.
# Do not build any of these during Skills 01-06.
# Review before starting work after first customer is live.

---

## OPEN ITEMS — Prioritised

| Date | What | Relevant to | Priority | Notes |
|---|---|---|---|---|
| 2026-04 | Self-consistency voting — run same compliance check 3 times, take majority | After SK04 | High | Reduces hallucination risk on borderline decisions. Only for checks above approval threshold. |
| 2026-04 | Verification step — second LLM call after synthesis checks every claim against retrieved context | After SK05 | High | Catches hallucinations before PDF report. Add as optional guardrail node. |
| 2026-04 | Human feedback capture — when evaluator overrides AI score, capture correction | After first customer | High | Requires a feedback UI in the frontend. Corrections flow back into few-shot examples. |
| 2026-04 | Score drift detection in production — alert when average confidence drops week-over-week | After SK05 | High | LangSmith has the data. Needs a monitoring rule and Slack alert. |
| 2026-04 | Prompt versioning — track which prompt version produced which result | After SK04 | Medium | Cannot identify cause of accuracy changes without this. Store prompt_version in decisions table. |
| 2026-04 | Pydantic validation on synthesizer output | After SK03b | Medium | ComplianceCheckResult and ScoringCriterionResult are done. SynthesisResult needed. |
| 2026-04 | OCR for scanned PDFs — Tesseract integration | After first customer | Medium | pypdf returns empty text for scanned documents. Many real vendor submissions are scanned. |
| 2026-04 | Document versioning — track what was evaluated at what version | After SK05 | Medium | Resubmission currently deletes all previous data. Needed for audit trail completeness. |
| 2026-04 | Confidence calibration — empirical calibration of GPT-4o confidence scores | After first customer | Medium | Requires ground truth dataset. 0.8 confidence may not mean 80% accurate on your documents. |
| 2026-04 | Context compression — extract only relevant sentences from chunks before sending to LLM | After SK03b | Medium | LangChain ContextualCompressionRetriever. Reduces noise in context window. |
| 2026-04 | Lost-in-the-middle handling — place most important chunks first and last | After SK03b | Medium | LLMs attend less to content in middle of long context. Sort chunks by importance. |
| 2026-04 | Contextual chunk headers — prepend each chunk with parent section summary | After SK03b | Low | Gives LLM context of where chunk sits in document. Additional LLM call per chunk. |
| 2026-04 | A/B testing prompts — run two prompt versions on same evaluation, compare accuracy | After first customer | Low | Requires evaluation dataset for comparison. Cannot do this without ground truth. |
| 2026-04 | Evaluation ground truth dataset — collect correct evaluations for accuracy measurement | After first customer | Low | Need real customer data to build this. Ask first customer to manually evaluate 20 vendors as ground truth. |
| 2026-04 | Chunk overlap strategy — sentence-boundary overlap instead of fixed token overlap | After SK03b if score not good enough | Low | Only needed if retrieval quality test still fails specific boundary cases. |
| 2026-04 | Retrieval quality monitoring in production | After SK05 | Low | 80% threshold test runs in dev. Need scheduled job that runs same test on production collections weekly. |
| 2026-04 | Hierarchical chunking — summary chunk + detail chunks per section | After SK03b if needed | Low | Higher complexity. Only add if standard chunking still struggles with very long sections. |
| 2026-04 | SaaS billing system — usage metering per org | After SK06 | Low | Current platform has no billing. Need Stripe integration and usage tracking before selling to second customer. |
| 2026-04 | Executive dashboard — CEO/CFO view of all active evaluations | After SK06 | Low | Described in the platform vision. Not needed until multiple departments active at one company. |
| 2026-04 | Approval SLA checker background job — flags overdue approvals | After SK05 | Low | Modal scheduled function that runs hourly. Sends Slack reminder when approval is overdue. |

---

## COMPLETED ITEMS

| Date | What was built | Built in skill | Notes |
|---|---|---|---|
| | | | |

---

## REJECTED ITEMS

| Date | What was considered | Reason rejected |
|---|---|---|
| 2026-04 | Fine-tuning models | Too expensive and slow for v1. Few-shot prompting achieves comparable results on this use case. Revisit after 1000+ evaluations. |
| 2026-04 | Image/audio document ingestion | Out of scope for RFP evaluation. Vendor responses are text documents. |
| 2026-04 | Multi-language support | English only for v1. Add after first non-English customer requests it. |
