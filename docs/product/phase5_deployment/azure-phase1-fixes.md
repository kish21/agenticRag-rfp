# Azure phase 1 — six readiness fixes

These fixes prepare the app for its first deploy to Azure Container Apps.
The runbook is `05_multi_cloud_deployment_guide.md` (Profile 2 — Azure).

---

## 1. EU region: Sweden Central

**What was wrong:** The runbook created every Azure resource in `uksouth` (UK South). The UK is not in the EU.

**The change:** Every region in the Azure section is now `swedencentral`. Sweden Central is an EU region where Azure OpenAI models are available. A note now says the model versions in the runbook are from 2024 and must be checked against what Sweden Central offers on deploy day.

**Interview line:** "I picked the region from two constraints together — EU data residency and where the AI models are actually available — and I check model versions at deploy time, because they change faster than runbooks."

---

## 2. Re-ranker chosen on purpose

**What was wrong:** A re-ranker re-orders search results so the best evidence comes first. The runbook chose the local BGE re-ranker, but its library is not in the production Docker image. On Azure every re-rank call would fail, and search would quietly fall back to a weaker order.

**The change:** The code already supports Cohere's hosted re-rank API, which needs no local library. The Azure runbook now sets `RERANKER_PROVIDER=cohere` and lists the key it needs, `COHERE_API_KEY`. At startup the app now prints a clear warning if re-ranking is off (`none`) or if Cohere is chosen without a key.

**Decision for you:** Cohere runs outside Azure, so query text and short document snippets go to Cohere. If a client needs everything inside Azure, set `RERANKER_PROVIDER=none` for phase 1. The startup warning will then say re-ranking is off.

**Interview line:** "A fallback that fails silently is a hidden quality bug, so I made the re-ranker an explicit deployment choice and made the app say out loud when it is running degraded."

---

## 3. Database migrations command

**What was wrong:** The runbook ran `python scripts/migrate.py`. That file does not exist. The repo uses Alembic, a tool that applies database schema changes in order.

**The change:** The step now runs `alembic upgrade head` from the repo root. It passes the `POSTGRES_*` settings, because Alembic reads those (not `DATABASE_URL`). The app also runs this on startup, so the manual step just makes the first deploy predictable.

**Interview line:** "Schema changes are versioned and applied by one standard tool, so every environment reaches the same database state the same way."

---

## 4. Unique image tag per build

**What was wrong:** Images were tagged `latest`. `latest` moves with every build, so you cannot tell which code is running or roll back to an exact version.

**The change:** Each build is tagged with the git short commit ID (`$(git rev-parse --short HEAD)`). The Container App is created and updated with that exact tag. `latest` is no longer used in the Azure deploy path.

**Interview line:** "Every running container maps to one exact commit, which makes deploys traceable and rollbacks a one-line change."

---

## 5. BM25 keyword model inside the image

**What was wrong:** Hybrid search uses a BM25 keyword model (`Qdrant/bm25`, loaded by the `fastembed` library). It was downloaded into a temp folder the first time a document was ingested. A new container could stall, or fail without internet, at that moment.

**The change:** The Dockerfile now downloads the model during the image build into `/opt/fastembed_cache`. The `FASTEMBED_CACHE_PATH` setting points the library at that folder, so the running app finds it without a download.

**Interview line:** "I bake model files into the image at build time so containers start ready, behave the same everywhere, and don't depend on the internet at runtime."

---

## 6. Server logs back on

**What was wrong:** On startup the app runs Alembic. Alembic loads its logging settings from `alembic.ini`, and by default that switches off every logger that already exists — including uvicorn's (the web server) and the app's. So there was no "startup complete" message and no request logs.

**The change:** One line in `alembic/env.py`: the logging setup now passes `disable_existing_loggers=False`. Alembic still gets its own logging, and the server's loggers stay on. A quick local check confirmed the uvicorn logger stays enabled with this flag.

**Interview line:** "A library's default logging setup silently muted our server; I changed it so tools can add logging without switching off anyone else's, because observability is the first thing you need on a new deploy."
