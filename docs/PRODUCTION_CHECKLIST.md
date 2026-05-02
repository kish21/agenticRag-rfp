# Production Deployment Checklist
# Last updated: 2026-05-02
# Work through this top to bottom before going live.

---

## 1. Infrastructure — Migrate off localhost

These services run on Docker locally and are unreachable from Modal or any cloud deployment.

| Service | Current | Action needed |
|---|---|---|
| PostgreSQL | `localhost:5432` (Docker) | Provision cloud PostgreSQL — Neon / Supabase / Railway |
| Qdrant | `localhost:6333` (Docker) | Provision Qdrant Cloud (qdrant.io) — free tier available |

**After migrating:**
- Run `app/db/schema.sql` against the new cloud PostgreSQL to create all tables
- Update `.env`: `POSTGRES_HOST`, `POSTGRES_PORT`, `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB`
- Update `.env`: `QDRANT_HOST`, `QDRANT_PORT`, add `QDRANT_API_KEY`
- Update Modal secret in `rag` environment:
  ```bash
  modal secret create agentic-platform-secrets \
    POSTGRES_HOST=<cloud-host> QDRANT_HOST=<cloud-host> ... --env rag
  ```

---

## 2. Modal Scheduled Jobs — Re-enable after cloud DB is live

Both functions are commented out in `app_modal.py` because they require cloud PostgreSQL.

**File:** `app_modal.py` — lines 79–109

Steps:
1. Uncomment `daily_cleanup` and `rate_monitor` functions
2. Remove the `# PRODUCTION TODO` comment block
3. Redeploy: `modal deploy app_modal.py --env rag`

---

## 3. Secrets — Replace all REPLACE_ME values

All placeholder values must be replaced before production. Check `.env`:

| Variable | Status | Where to get it |
|---|---|---|
| `OPENAI_API_KEY` | ✅ Set | — |
| `ANTHROPIC_API_KEY` | ❌ `REPLACE_ME` | console.anthropic.com → API Keys |
| `OPENROUTER_API_KEY` | ❌ `REPLACE_ME` | openrouter.ai → Keys (only if using OpenRouter) |
| `LANGCHAIN_API_KEY` | ❌ `REPLACE_ME` | smith.langchain.com → Settings → API Keys |
| `COHERE_API_KEY` | ✅ Set | — |
| `LANGFUSE_PUBLIC_KEY` | ✅ Set | — |
| `LANGFUSE_SECRET_KEY` | ✅ Set | — |
| `SLACK_BOT_TOKEN` | ❌ `REPLACE_ME` | api.slack.com → OAuth & Permissions |
| `SLACK_CHANNEL_ID` | ❌ `REPLACE_ME` | Slack channel settings |
| `APP_API_KEY` | ❌ `REPLACE_ME` | Generate: `python -c "import secrets; print(secrets.token_hex(32))"` |

---

## 4. Security — Harden before go-live

### 4a. JWT Secret Key
The `.env` has a real key but `app/config.py` has a hardcoded fallback `"change-me-in-production"`.
Ensure `JWT_SECRET_KEY` is always set in the environment — never rely on the default.
Rotate it if it has been shared or committed anywhere.

### 4b. Dev user — disable in production
`app/api/auth_routes.py` seeds a dev user (`dev@platform.local` / `devpassword2026`) at startup.
This must be disabled before production:
- Set `DEV_USER_ENABLED=false` in `.env` (add the config field)
- Or remove the `_init_dev_user()` call in `auth_routes.py` for the production build

### 4c. PostgreSQL password
`POSTGRES_PASSWORD=platformpass2026` is a weak dev password.
Use a strong randomly generated password for the cloud database.

### 4d. CORS origins
`app/main.py` sets `allow_origins=["*"]` when `APP_API_KEY` is set.
For production, replace `"*"` with the actual frontend domain:
```python
allow_origins=["https://your-production-domain.com"]
```

### 4e. HTTPS
Ensure FastAPI is served behind a reverse proxy (nginx / Caddy / cloud load balancer) with TLS.
Never expose port 8000 directly in production.

---

## 5. Frontend — Production build

```bash
cd frontend
npm run build          # verify no TypeScript or build errors
```

Update `frontend/.env.production` (create if missing):
```
NEXT_PUBLIC_API_URL=https://your-api-domain.com
```

The frontend currently proxies `/api/v1/*` — ensure the Next.js config points to the production FastAPI URL, not `localhost:8000`.

---

## 6. Evaluation Routes — Wire up before frontend is useful

`app/api/evaluation_routes.py` does not exist yet.
The frontend calls these endpoints which are currently unimplemented:

| Endpoint | Used by |
|---|---|
| `POST /api/v1/evaluate/start` | Upload page — starts an evaluation run |
| `GET /api/v1/evaluate/list` | Dashboard — lists all runs |
| `GET /api/v1/evaluate/{runId}/status` | Progress page — SSE agent status stream |
| `GET /api/v1/evaluate/{runId}/results` | Results page — shortlist + rejections |
| `GET /api/v1/evaluate/{runId}/decision` | Override page — current vendor decision |
| `POST /api/v1/evaluate/{runId}/override` | Override page — submit human override |

Build this file before any end-to-end testing.

---

## 7. Modal — Final production deploy checklist

Run these in order after all of the above is complete:

```bash
# 1. Verify rag environment is active
modal environment list

# 2. Update secrets with production values
modal secret create agentic-platform-secrets \
  OPENAI_API_KEY=... POSTGRES_HOST=... QDRANT_HOST=... ... \
  --env rag

# 3. Deploy
modal deploy app_modal.py --env rag

# 4. Verify function is live
modal app list --env rag
```

---

## 8. Smoke tests — Run after every production deploy

```bash
# All checkpoints still green
python checkpoint_runner.py all

# Contracts intact
python contract_tests.py

# Regression above threshold
python tests/regression/run_regression.py

# Drift clean
python drift_detector.py
```

Expected: 66/66 checkpoints, 14/14 contracts, 18+/20 regression, no drift.

---

## Status tracker

| Section | Owner | Done |
|---|---|---|
| 1. Cloud PostgreSQL | | ☐ |
| 1. Cloud Qdrant | | ☐ |
| 2. Re-enable Modal scheduled jobs | | ☐ |
| 3. Replace REPLACE_ME secrets | | ☐ |
| 4a. JWT secret hardened | | ☐ |
| 4b. Dev user disabled | | ☐ |
| 4c. Postgres password rotated | | ☐ |
| 4d. CORS locked to domain | | ☐ |
| 4e. HTTPS / TLS | | ☐ |
| 5. Frontend production build | | ☐ |
| 6. evaluation_routes.py built | | ☐ |
| 7. Modal production deploy | | ☐ |
| 8. Smoke tests pass | | ☐ |
