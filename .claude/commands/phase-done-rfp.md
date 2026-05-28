---
description: Phase-completion audit for the Meridian RFP-evaluation pipeline — invokes generic /phase-done then runs project-specific invariant checks (LangGraph topology, deterministic IDs, HARD-block guards, Phase 9 access invariant)
---

# `/phase-done-rfp` — RFP pipeline-specific phase-completion gate

This skill is **specific to the agenticRag-rfp project**. It first runs the
generic 11-category `/phase-done` audit, then layers checks unique to the
LangGraph multi-agent RFP-evaluation architecture this codebase implements.

If you're working on a different project, you want **`/phase-done`** (generic,
user-global) instead.

---

## Phase 0 — Run the generic audit first

Invoke the generic `/phase-done` command and wait for its full **11-category**
report (1–8 = engineering hygiene; 9–11 = pre-push guards added 2026-05-28
after PR #150 surfaced these three bug classes: branch drift causing
merge-time conflicts, CI parity gaps (pytest missing on runner, no PG service
for integration tests), and silent overwrites of existing PR metadata).

**If category 9 (branch freshness) or 10 (pre-push CI parity) BLOCK, do NOT
proceed with the RFP-specific checks below** — fix the blockers first, then
re-run `/phase-done-rfp`. The project-specific invariants are downstream of
"the basics work."

Surface the generic skill's report verbatim. Then continue below with the
RFP-specific extras.

---

## Phase 1 — RFP-pipeline-specific invariant checks

These five checks exist because we've actually been bitten by each of them at
least once on this project (see commit `d58b2fc` and `tests/test_codereview_regressions.py`).

### Check A — LangGraph topology drift

If the diff modified `app/pipeline/graph.py` or `app/pipeline/nodes.py`:

1. Read the compiled graph topology:
   ```bash
   venv/Scripts/python.exe -c "from app.pipeline.graph import evaluation_graph; g = evaluation_graph.get_graph(); print('NODES:'); [print('  '+n) for n in g.nodes]; print('EDGES:'); [print(f'  {e.source} -> {e.target}') for e in g.edges]"
   ```

2. Verify `tests/test_pipeline_graph.py` reflects current topology:
   - `_ALL_GRAPH_NODES` includes every node from step 1
   - `_NODE_PATCH_NAMES` covers every node that any test might monkey-patch
   - `TestGraphTopology` assertions match the current edge set

3. If `decision_output` JSON shape changed (e.g. ExplanationOutput got new
   fields per the Phase 7 plan), prompt the user to regenerate the smoke-test
   golden by deleting prior `tests/smoke_results/*` and re-running
   `tools/smoke_test_graph.py`.

### Check B — Deterministic ID invariant

Phase 1 committed to making criterion / check IDs deterministic via
`_stable_id()`. The `/code-review` we just ran (commit `d58b2fc`) found that
`uuid.uuid4()` still leaks in two places (`query_id`, `explanation_id`).

Grep the pipeline-output construction sites for any new `uuid.uuid4()`:

```bash
venv/Scripts/python.exe -c "import re, pathlib; [print(f'{p}:{n+1}  {l.strip()}') for p in pathlib.Path('app').rglob('*.py') if 'agents' in str(p) or 'pipeline/' in str(p) or 'schemas/' in str(p) for n, l in enumerate(p.read_text(encoding='utf-8').splitlines()) if 'uuid.uuid4' in l]"
```

If new instances exist, prompt: "Should these be `_stable_id(scope, *parts)`?
A future consumer joining on these IDs across runs will see byte-identity
failures."

(Tracked deferral: replace `query_id` and `explanation_id` with stable IDs —
not done yet because no consumer joins on them today.)

### Check C — Per-vendor HARD-block guard invariant

Every `*_per_vendor` node MUST handle a HARD critic verdict by appending to
`failed_vendors`, not silently passing. The Phase 4 commit removed this guard;
commit `d58b2fc` restored it for retrieval + evaluation. Future per-vendor
nodes must preserve this pattern.

Grep:

```bash
venv/Scripts/python.exe -c "
import re, pathlib
src = pathlib.Path('app/pipeline/nodes.py').read_text(encoding='utf-8')
# Find every async def *_per_vendor function body
funcs = re.findall(r'async def (\w+_per_vendor)\b.*?(?=^async def|\Z)', src, re.DOTALL | re.MULTILINE)
for body in funcs:
    name = body.split('(')[0].strip()
    has_hard_block = 'CriticVerdict.BLOCKED' in body and 'failed_vendors' in body
    print(f'  {name}: HARD-block guard present = {has_hard_block}')
"
```

Any `*_per_vendor` showing `False` is a Phase 4 / Phase 2 regression. Flag it.

### Check D — Phase 9 access-inheritance invariant

The Phase 9 plan guarantees that autonomous code paths (agents, jobs,
pipeline, retrieval) NEVER write to access tables (`user_departments`,
`rfp_collaborators`, `approval_assignments`). Re-run the static-analysis
test to make sure nothing slipped in:

```bash
venv/Scripts/python.exe -m pytest tests/test_access_invariant.py -v --no-header
```

All 3 tests must pass. If any fails, the diff introduced an autonomous write
path to the access tables — surface immediately as a security finding.

### Check E — Determinism stability (functional regression)

Run the smoke test once and capture grounding_completeness + nodes-executed.
If the diff touched anything that affects scoring, retrieval, or LLM calls,
prompt the user to run a second consecutive smoke and compare:

```bash
# Verify per-vendor grounding stays high (Phase 1 commitment: ≥ 0.95)
venv/Scripts/python.exe -c "
import json, pathlib
latest = sorted(pathlib.Path('tests/smoke_results').glob('2*'))[-1]
s = json.load(open(latest / 'summary.json'))
print(f'Latest smoke: status={s[\"status\"]}, nodes={len(s.get(\"nodes_executed\", []))}')
"
```

Flag any regression:
- `status` != `complete`
- `nodes_executed` count shrank
- `grounding_completeness` < 0.95 (from node_diffs/08_explanation.json)

---

## Phase 2 — RFP-specific architectural reminders

For the upcoming phases listed in `docs/dev/PRODUCTION_READINESS_PLAN.md`,
recommend specific Claude Code features:

| Upcoming phase | Recommended Claude Code feature |
|---|---|
| **Phase 5** (background ingestion, deadline scheduler) | `/schedule` to prototype the cron pattern; `/security-review` because watcher + admin-attribution endpoints touch access |
| **Phase 6** (incremental re-eval, LangGraph checkpointers) | `/code-review ultra` (cloud multi-agent) — subtle state-resume correctness deserves it |
| **Phase 7** (PDF report) | `/frontend-design` then `/anti-ai-ui` for the report's HTML/CSS template |
| **Phase 8** (delivery channels) | `mcp-builder` if you want to expose Slack/Teams as MCP tools rather than direct webhook calls |
| **Phase 3** (LLM response cache) | `claude-api` skill — audit prompt caching opportunities at the same time |
| **Phase 10** (architecture rationale doc) | Subagent with `Explore` to gather concrete code references for each claim |

---

## Phase 3 — Aggregate report

Combine the generic `/phase-done` 8-category report with the RFP-specific
checks above. Final output should clearly separate:

- Generic findings (from `/phase-done`)
- RFP-specific findings (this skill's extras)
- Recommended next features per upcoming phase

Conclude with `READY TO PUSH` / `FIX FIRST` / `REVIEW WARNINGS` exactly as
the generic skill does — RFP-specific checks failing should escalate to
`FIX FIRST`.

---

## Footnote — when to extend this

Add a new check whenever:
- A `/code-review` finding ships that could have been prevented by a static check
- A regression is found in production that a grep-able rule would have caught
- A new architectural invariant is established (e.g. Phase 5 might add "every
  ingestion_job has a content_hash uniqueness guard" — that's a Check F worth adding)

Date created: 2026-05-28 (after commit `d58b2fc`).

The 5 checks above each have an actual scar in the git history:
- Check A — `/code-review` finding from session 2026-05-28
- Check B — `/code-review` finding #7 (commit `d58b2fc`)
- Check C — `/code-review` findings #2 + #3 (commit `d58b2fc`)
- Check D — Phase 9 invariant (commit `c25aea1`)
- Check E — Phase 1 functional-determinism contract (commit `7374fa9`)
