# Agent 01 — Planner Agent

## What it does (plain English)

The Planner Agent is the first to run. It takes the evaluation setup — the list of vendors, mandatory checks, and scoring criteria — and produces a structured plan of work. Think of it as writing a project schedule before any actual evaluation begins.

It creates a task for every step that needs to happen: one retrieval task per vendor, one extraction task per vendor, one task per mandatory check, one task per scoring criterion, then compare, decide, and explain. Each task knows what it depends on, so the pipeline can run tasks in the right order.

There are no LLM calls. The plan is built deterministically from the evaluation setup. It then validates its own plan to confirm that every mandatory check and every scoring criterion is covered before handing off to the pipeline.

---

## Where it sits in the pipeline

```
EvaluationSetup + vendor_ids
        ↓
Planner Agent  →  PlannerOutput (task DAG)
        ↓
Pipeline executes tasks in dependency order
```

---

## Task types produced

| Task type | Agent | Depends on |
|-----------|-------|------------|
| `retrieve` | retrieval | nothing (runs first) |
| `extract` | extraction | retrieve (same vendor) |
| `mandatory_check` | evaluation | all extract tasks |
| `scoring` | evaluation | all mandatory_check tasks |
| `compare` | comparator | all scoring tasks |
| `decide` | decision | compare |
| `explain` | explanation | decide |

---

## Plan validation

After building the plan, `validate_plan` checks:
- Every mandatory check from `evaluation_setup` has a corresponding `task-check-{check_id}` task
- Every scoring criterion has a corresponding `task-score-{criterion_id}` task
- No circular dependencies exist in the task graph
- Task count is within a sane range (5 to 500)

If any check fails, the Critic raises a HARD flag and the pipeline is blocked before a single retrieval call is made.

---

## Files

| File | Role |
|------|------|
| `app/agents/planner.py` | Plan generation + validation |
| `app/config/platform.yaml` | `infrastructure.task_duration_estimate_seconds` |

---

## What the Critic checks

| Check | Severity | What it catches |
|-------|----------|----------------|
| `no_vendors` | HARD | Empty vendor list — nothing to evaluate |
| `empty_plan` | HARD | Plan has no tasks — generation failed |
| `plan_validation_error` | HARD | Missing coverage for a check or criterion, or circular dependency |

---

## What was wrong (and fixed in May 2026)

### 1. Critic Agent never called — CRITICAL
**Before:** `run_planner` returned only `PlannerOutput`. Every other agent in the system returns `(output, critic)`. This was the only agent that never ran the Critic, violating CLAUDE.md's rule that "Critic Agent runs after EVERY agent — never skip". A broken plan (missing checks, circular deps) would pass silently into the pipeline.

**Fix:** Return type changed to `tuple[PlannerOutput, CriticOutput]`. `validate_plan` runs after the plan is built and passes any errors to `critic_after_planner`. `critic_after_planner` added to `critic.py`.

### 2. Empty vendor list produced a broken plan silently — MEDIUM
**Before:** If `vendor_ids` was an empty list, the planner would create no retrieve or extract tasks but would still create compare, decide, and explain tasks that depended on non-existent score tasks. `validate_plan` would flag "suspiciously low task count" but still return the broken plan.

**Fix:** If `vendor_ids` is empty, the planner returns immediately with an empty plan and a HARD-blocked critic. The pipeline never starts.

### 3. Task duration estimate was a hardcoded magic number — LOW
**Before:** `estimated_duration_seconds = len(tasks) * 30` — the number 30 was hardcoded directly in the agent file. CLAUDE.md prohibits hardcoded values in agent files.

**Fix:** Reads `settings.platform.infrastructure.task_duration_estimate_seconds` from `platform.yaml`. Default value is 30 seconds, configurable without a code change.
