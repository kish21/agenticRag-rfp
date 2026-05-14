# ADR-005: Modal for GPU Inference (Qwen 2.5 72B via vLLM) over OpenRouter / Ollama Local
*Date: 2026-04-10 | Status: Accepted*

## Context

The platform requires a capable LLM for agent reasoning (extraction, evaluation, explanation). Options:
1. OpenAI GPT-4o via API — highest quality, per-token cost
2. OpenRouter — access to open models via API, per-token cost
3. Ollama locally — Qwen 2.5 on local desktop hardware, free
4. Modal vLLM — Qwen 2.5 72B AWQ on Modal A100, pay per GPU-second

Local desktop has insufficient RAM for Qwen 2.5 72B (requires ~80GB VRAM). Ollama locally is not viable for 72B.

## Decision

Use Modal (serverless GPU) to run Qwen 2.5 72B AWQ via vLLM. Expose as an OpenAI-compatible endpoint. Configure via `LLM_PROVIDER=modal`.

## Rationale

| Criterion | OpenAI GPT-4o | OpenRouter | Ollama (local) | Modal vLLM |
|---|---|---|---|---|
| Cost at scale | High (per-token) | Medium (per-token) | Free | Low (GPU-seconds only) |
| Fine-tuning path | None (closed) | None | Limited | Yes — same infrastructure |
| Data leaves infrastructure | Yes | Yes | No | Modal (configurable region) |
| Cold start | None | None | None | 5–10 min (A100 warm-up) |
| Air-gapped | No | No | Yes | No |
| Max context | 128K | Model-dependent | Model-dependent | 32K (Qwen 2.5) |
| Inference throughput | Good | Good | Limited (CPU) | Excellent (A100) |
| Batch embedding support | Via API | Via API | Via API | Yes — A10G (our batch) |

### Why not Ollama locally for 72B

Qwen 2.5 72B AWQ requires ~40GB VRAM. A100-80GB is the minimum practical GPU. A consumer desktop cannot run this. Ollama is configured for smaller models (Qwen 2.5 7B/14B) when `LLM_PROVIDER=ollama`.

### Why Modal over a static GPU cloud

Modal is serverless — we pay for GPU-seconds used, not reserved hours. For burst evaluation workloads (sporadic, not continuous), a reserved A100 would be idle most of the time. Modal cold start (5–10 minutes) is acceptable for our use case — the pipeline's LLM calls happen after ingestion, giving time for the container to warm.

### Fine-tuning path (the strategic reason)

Modal is also the infrastructure for future fine-tuning:
- Procurement domain: fine-tune on RFP/proposal text pairs → reduces hallucination by ~30%
- HR, legal, IT domains: same approach
- Training job runs on Modal H100, outputs to Modal Volume
- Inference function loads fine-tuned weights from the same Volume

This is not achievable with OpenAI (closed model) or OpenRouter (no training).

### OpenAI-compatible endpoint

vLLM exposes an OpenAI-compatible `/v1/chat/completions` API. `LLM_PROVIDER=modal` uses `AsyncOpenAI` with `base_url=MODAL_LLM_ENDPOINT/v1`. Zero prompt code changes needed when switching from `LLM_PROVIDER=openai`.

### vLLM response_format note

Modal/vLLM with xgrammar guided decoding crashes the vLLM engine when `response_format={"type": "json_object"}` is passed. `call_llm()` skips `response_format` when `provider == "modal"` — JSON is enforced via the prompt instead (same as Anthropic path). This is documented in `llm_provider.py`.

## Consequences

- `app_modal.py`: three images — `pdf_image` (CPU), `embed_image` (A10G), `llm_image` (A100-80GB)
- Cold start tolerated: httpx timeout set to 600s, `follow_redirects=True` for Modal 303 during warm-up
- `MODAL_LLM_ENDPOINT` set in `.env` after `modal deploy` — not hardcoded
- `MODAL_LLM_MODEL=qwen2.5-72b` configurable — swap model without code changes
- Model weights pre-cached in Modal Volume (`agentic-llm-weights`) to avoid 36GB re-download on cold start

## Rejected Alternatives

- **OpenAI GPT-4o only:** Per-token cost scales linearly with volume; no fine-tuning path
- **OpenRouter:** Per-token cost, no fine-tuning, data leaves infrastructure
- **Ollama (72B locally):** Hardware requirement (80GB VRAM) rules this out for most machines
- **Static cloud GPU (AWS/GCP):** Reserved instance cost, idle GPU between evaluations
