# Issue #212 — Reranker air-gapped default (`.env` is the single source of truth)

*Status: built 2026-06-04 · branch `212-reranker-airgapped-default`*

## Problem

A brand-new org (no `org_settings` row) resolved its reranker backend from the
`product.yaml` quality preset, which **hardcoded `reranker_provider: "bge"`**.
Because [retrieval.py](../../app/agents/retrieval.py) passes the org's value to
`rerank(provider=...)` and `provider=` wins over `.env`, that preset value
**overrode the operator's `.env` `RERANKER_PROVIDER`**. `bge` runs a local model
and downloads ~2.3 GB from HuggingFace on first use. In an **air-gapped VPC**
(no HF egress) that download fails and retrieval **silently degrades to
vector-score order** — worse precision, no operator signal. The operator's
deliberate `.env` choice (e.g. `=modal`, which keeps the box off HuggingFace, or
`=none`) was dead config.

## Decision (signed off)

1. **Backend choice is sourced from `.env`** (honour the operator). The preset
   keeps deciding *whether* to rerank (`use_reranking`); *which* backend serves
   it (`bge`/`modal`/`cohere`/`colbert`/`none`) is a **deployment** concern read
   from `RERANKER_PROVIDER`. This makes `.env` the single source of truth for any
   org that has not *explicitly* chosen its own backend.
2. **Fail-open but LOUD** on an unavailable reranker — keep producing a report
   (vector-order fallback) but surface the degradation so it is never silent.

Per-tenant correctness: an org with its **own** `org_settings` row keeps its
explicit choice (a global `.env` flip must not override one customer's deliberate
setting). The backend is no longer pinned in the preset, so a **tier change no
longer silently resets** an org's reranker.

## Changes

| Surface | Change |
|---|---|
| [product.yaml](../../app/config/product.yaml) | Removed `reranker_provider` from the `&unified_config` preset anchor (with a pointer comment). |
| [org_settings.py `_defaults_for`](../../app/domain/org_settings.py) | After the preset overlay, set `reranker_provider = settings.reranker_provider` (the `.env` value) — the single authoritative default surface. |
| [schema.sql](../../app/db/schema.sql) + [alembic 0014](../../alembic/versions/0014_reranker_default_bge.py) | Aligned the stale column `DEFAULT 'cohere'` → `'bge'` (a manual column-omitted INSERT would otherwise default to the **paid** Cohere API with no key). Never hit by app code; safety-net only. |
| [reranker.py `rerank()`](../../app/providers/reranker.py) | New optional `warnings: list` param. On a non-`none` provider failing/unknown → appends an operator-facing "Reranking degraded … fell back to vector-score order" message. `none` is intentional, never reported. |
| [schema_ingestion_retrieval.py](../../app/schemas/schema_ingestion_retrieval.py) | `RetrievalOutput.reranking_degraded: bool = False`. |
| [retrieval.py](../../app/agents/retrieval.py) | Threads the warnings list into `rerank()`, sets `reranking_degraded`, and applies a **config-driven** confidence penalty on degrade. |
| [nodes.py `retrieval_per_vendor`](../../app/pipeline/nodes.py) | The **live graph path** merges per-query retrievals into one `combined` output; it now aggregates `reranking_degraded` + de-duped warnings and applies the penalty there too. Without this the signal was dropped before the critic/downstream saw it (caught in self-review). |
| [critic.py `critic_after_retrieval`](../../app/agents/critic.py) | Emits a **SOFT** `reranking_degraded` flag (visible to operators; does not HARD-block — fail-open). Suppresses the generic `low_retrieval_confidence` flag when degraded, so the lowered confidence isn't misattributed to "vendor doesn't address the criterion". |
| [platform.yaml](../../app/config/platform.yaml) + [loader.py](../../app/config/loader.py) | `retrieval.rerank_degraded_confidence_factor: 0.8` (no hardcoding). |

## Exit criteria — verified

- [x] A defaulted org resolves `reranker_provider` from `.env`, for every provider value (`test_defaulted_org_follows_env_provider`).
- [x] The preset no longer pins `reranker_provider`; tier change can't reset it (`test_preset_does_not_pin_reranker_backend`).
- [x] An unavailable real reranker fails open to vector order **and** surfaces a degradation warning (`test_unavailable_reranker_reports_degradation`).
- [x] `none` is never reported as degraded (`test_none_provider_is_not_reported_as_degraded`).
- [x] The critic raises a SOFT (not HARD) `reranking_degraded` flag (`test_critic_flags_reranking_degraded_soft`).
- [x] The confidence penalty is config-driven (`test_degraded_confidence_factor_is_config_driven`).
- [x] The **live graph path** propagates the degradation into the combined output (`test_live_node_propagates_degradation_into_combined_output`) — guards the self-review regression.

## Not in scope

- The reranker.py provider fallback is already `none` (correct) — this was **not**
  touched; the fix is the config default, not the fallback.
- Changing the documented product default away from BGE (ADR-004 stands — BGE is
  the air-gapped-friendly open-source default *when pre-cached*; `modal` runs the
  same open-source model on a GPU with no local HF egress).
