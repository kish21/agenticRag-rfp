# START HERE
# Read this before opening Claude Code.

---

## What is in this package

```
agentic-platform/
├── START_HERE.md              ← You are reading this
├── CLAUDE.md                  ← Claude Code reads this automatically every session
├── QUICK_REFERENCE.md         ← Keep open during every coding session
├── HOW_TO_USE_CLAUDE_CODE.md  ← Exact prompts to keep Claude Code on track
├── checkpoint_runner.py       ← 59 checkpoints across 10 skills
├── drift_detector.py          ← Detects when Claude Code goes off track
├── contract_tests.py          ← Verifies interfaces between components
├── build_state.json           ← Auto-managed progress tracker
├── daily_build_log.md         ← One entry per session
├── BACKLOG.md                 ← Ideas noticed during coding — do not build yet
└── skills/
    ├── SKILL_01_FOUNDATION.md           ← START HERE — setup, API keys, Qdrant, PostgreSQL
    ├── SKILL_02_PLANNER_AND_CRITIC.md   ← Planner Agent, Critic Agent, rate limiter
    ├── SKILL_03_INGESTION_AGENT.md      ← LlamaIndex, Qdrant, ZIP handler, fact store
    ├── SKILL_03b_RAG_QUALITY.md         ← Retrieval Agent, Cohere Rerank, HyDE, compression
    └── SKILL_04_TO_09_REFERENCE.md      ← Extraction→Evaluation→Comparator→Decision→Explanation→Platform
```

---

## What you are building

Enterprise Agentic AI Platform — Nine-agent system for RFP evaluation (first agent).

Nine agents: Planner → Ingestion → Retrieval → Extraction → Evaluation → Comparator → Decision → Explanation → Critic

Two storage layers: Qdrant (vector store) + PostgreSQL (structured facts)

Tech stack: LangGraph · LlamaIndex · Qdrant · Cohere Rerank · ColBERT · GPT-4o · FastAPI · Modal · LangSmith · LangFuse · Next.js

---

## The skill sequence — 10 steps, 59 checkpoints

```
SKILL_01   Foundation                       9 checkpoints  ← start here
SKILL_02   Planner Agent + Critic Agent     8 checkpoints
SKILL_03   Ingestion Agent                  5 checkpoints
SKILL_03b  RAG Quality Enhancement          4 checkpoints
SKILL_04   Extraction Agent                 6 checkpoints
SKILL_05   Evaluation + Comparator          7 checkpoints
SKILL_06   Decision + Explanation           6 checkpoints
SKILL_07   Output + Frontend + Regression   5 checkpoints
SKILL_08   Monitoring + Jobs                3 checkpoints
SKILL_09   Platform Expansion               6 checkpoints
                                   Total:  59 checkpoints
```

Skills 04-09 are all in SKILL_04_TO_09_REFERENCE.md — one file with patterns, code skeletons, and checkpoints for each skill.

---

## Setup

```bash
mkdir agentic-platform
cd agentic-platform
# Copy all package files here
# Open Claude Code in this folder
```

**First prompt every session:**
```
Read CLAUDE.md.
Run: python checkpoint_runner.py status
Tell me the last passed checkpoint and what the next step is.
Do not write any code until I confirm the plan.
```

**Three commands every session start:**
```bash
python checkpoint_runner.py status
python drift_detector.py
python contract_tests.py
```
