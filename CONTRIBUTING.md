# Contributing to Meridian AI Platform

## Prerequisites

- Python 3.11+
- Node.js 20+
- Docker Desktop
- `uv` (recommended) or `pip`

## Local setup

```bash
# 1. Copy environment template
cp .env.example .env
# Fill in API keys in .env

# 2. Start services (PostgreSQL + Qdrant)
docker-compose up -d

# 3. Install Python dependencies
pip install -r requirements.txt

# 4. Run database migrations
alembic upgrade head

# 5. Seed criteria data
python scripts/seed_criteria.py

# 6. Start the backend
uvicorn app.main:app --reload --port 8000

# 7. Start the frontend (separate terminal)
cd frontend && npm install && npm run dev
```

Or run everything at once with Make:

```bash
make dev        # backend (env copy + docker + migrations + seed + uvicorn)
make frontend   # frontend dev server
```

## Daily workflow

```bash
make test       # run pytest (unit + integration)
make lint       # ruff + eslint
make check      # checkpoint runner + drift detector + contract tests
```

## Branch naming

| Type | Pattern |
|------|---------|
| Feature | `feat/<short-description>` |
| Bug fix | `fix/<short-description>` |
| Refactor | `refactor/<short-description>` |
| Docs | `docs/<short-description>` |

## Pull requests

- Target `master`
- PR title: `type: short description` (e.g. `fix: handle empty vendor list in comparator`)
- All CI jobs must pass before merge
- One reviewer approval required

## Architecture constraints — read before coding

See `CLAUDE.md` at the repo root. The key rules:

- Every agent output is a Pydantic model — never raw text
- Every extracted fact must have a `grounding_quote`
- The Critic Agent runs after every agent — never skip it
- No hardcoded hex colours in frontend — use `var(--color-*)` only
- Call `call_llm()` in agent files — never import provider SDKs directly

## Running the full quality suite

```bash
python tools/checkpoint_runner.py status
python tools/drift_detector.py
PYTHONPATH=. python tools/contract_tests.py
python tools/frontend_checkpoint_runner.py run
python tools/frontend_drift_detector.py
```
