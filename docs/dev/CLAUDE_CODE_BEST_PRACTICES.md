# Claude Code Best Practices — Project Reference Guide

> Authoritative reference for using Claude Code on this project (and as a general engineering practice).
> Each feature: what it is, when to use, when NOT to use, gotchas, project-specific recommendation.

**Last updated:** 2026-05-28 · **Source of truth:** this doc + `docs/dev/PRODUCTION_READINESS_PLAN.md`

---

## Quick reference (one-line answers)

| If you want to… | Use this | Cost |
|---|---|---|
| Catch regressions before push | `/code-review` | 5–15 min, automatic |
| Audit a security-sensitive PR | `/security-review` | 5 min |
| Verify a UI change actually works | `/verify` | varies |
| Apply review fixes to working tree | `/simplify` (= `/code-review --fix`) | 5–10 min |
| Cloud multi-agent deep review | `/code-review ultra [<PR#>]` | 10–20 min, billed |
| Run a recurring task | `/schedule` (cron remote agent) or `/loop` (in-session) | low |
| Query Postgres without scripting | Postgres MCP server | one-time setup |
| Inspect / manage GitHub PRs | GitHub MCP server | one-time setup |
| Work on two independent branches in parallel | `Agent` with `isolation: "worktree"` | none |
| Save lessons for future sessions | Write to `~/.claude/projects/<proj>/memory/` | minimal |
| Auto-run lightweight tests on file edits | `PostToolUse` hook in `.claude/settings.json` | careful (see Hooks section) |
| Migrate Claude API code to newer model | `claude-api` skill | low |
| Start a new project from scratch | `/new-project` | varies |
| Add a custom slash command | Drop a `.md` file in `.claude/commands/` | minimal |
| Add a custom skill | Drop a directory in `.claude/skills/<name>/` with `SKILL.md` | low |
| Build an MCP integration | `mcp-builder` skill | half day |

---

## Settings hierarchy (where things live)

Three levels of settings, merged in this order (later overrides earlier):

```
~/.claude/settings.json                          ← user-global (you)
<repo>/.claude/settings.json                     ← project (commit to git, team-wide)
<repo>/.claude/settings.local.json               ← project-local (NEVER commit; per-machine)
```

**What goes where:**

- **User global** — personal preferences (statusline command, effort level, attribution, marketplaces)
- **Project settings** — team-wide conventions, hooks, custom commands. Commit to git.
- **Project local** — your personal permission allow-list, machine-specific paths. Already gitignored.

Project-specific gotcha: this repo has `.claude/settings.local.json` with ~50 pre-allowlisted commands. Don't accidentally commit it — `.gitignore` already excludes it.

---

## Skills — what they are and when to invoke

A **skill** is a packaged, battle-tested workflow that Claude can run via the `Skill` tool. Skills appear in system reminders at the start of each session. You can also invoke any of them by typing `/<skill-name>`.

### Skills relevant to this project (use them)

| Skill | When to invoke | Why |
|---|---|---|
| `/code-review` | After every phase commit, before push | Catches regressions, suggests cleanups. Multi-agent cloud variant: `/code-review ultra` |
| `/simplify` | After `/code-review` flags simplifications | Auto-applies the review's fix-suggestions to working tree |
| `/security-review` | Before merging Phase 9 (access control), Phase 5 (autonomous ingestion), Phase 8 (delivery) | Independent security audit |
| `/verify` | After UI / endpoint changes (Phase 7 PDF report, Phase 5 dashboard) | Launches the real app + drives the change |
| `/loop <prompt>` | Recurring in-session task (polling, repeated checks) | Lets the model self-pace iterations |
| `/schedule` | Recurring REMOTE task (daily smoke run after Phase 5 ships) | Creates a cron-style routine that runs in the cloud |
| `/fewer-permission-prompts` | Once per project after baseline workflow stabilises | Auto-builds a tight permissions allow-list |
| `claude-api` (via prompt-cache audit) | Before Phase 3 LLM cache | Audits Claude API usage for caching opportunities |

### Skills NOT to invoke on this project

| Skill | Why skip here |
|---|---|
| `/new-project`, `/init` | Project is well past scaffolding |
| `/anti-ai-ui`, `/frontend-design`, `/frontend-component`, `/new-component` | Frontend work is Phase 7 territory — invoke later when we touch frontend |
| `/theme-factory`, `/web-artifacts-builder` | Not applicable; this is a backend pipeline |
| `/keybindings-help`, `/statusline-setup` | Set up once, don't re-invoke |
| `/mcp-builder` | Only when building a custom MCP server (later, optional) |
| `/skill-creator` | Only when authoring a new skill |
| `/update-config` | When adding/modifying hooks (carefully — see Hooks lessons below) |

### Custom skills you can author

Drop a directory under `.claude/skills/<your-skill-name>/` with a `SKILL.md` file. Examples for this project that would pay off:

- `phase-completion` — orchestrates "run targeted tests + smoke + code-review + commit" as one skill invocation
- `db-snapshot` — captures relevant DB state into a JSON file for regression-baselining

Use the `/skill-creator` skill to scaffold these. The skill's `SKILL.md` includes the description text that shows up in system reminders — make it specific so Claude knows when to use it.

---

## Hooks — power tool, easy to break sessions

**Hook types:**

| Event | Fires when | Common uses | Risk |
|---|---|---|---|
| `SessionStart` | At session start | Set context, run baseline checks | HIGH — can hang session startup |
| `UserPromptSubmit` | After user types a prompt | Inject reminders, validate | Low |
| `PreToolUse` | Before a tool runs | Block dangerous commands, prepare state | Medium |
| `PostToolUse` | After a tool runs | Auto-run tests/lint after edits | Medium — accumulates over many tool uses |
| `Stop` | End of an assistant turn | Final cleanup, status check | Low–Medium |

### Hard-won lessons from this project (avoid these)

❌ **Don't run multi-step Python scripts in `SessionStart`.** This project had:
```bash
python -c "import subprocess; ... subprocess.run([3 commands sequentially]) ..."
```
Each command opened Postgres connections. One slow connect → whole session start froze. **Removed.**

❌ **Don't run DB-touching tests in `PostToolUse` on every edit.** We had `contract_tests.py` (touches DB) firing after every `.py` Edit. With 30 edits per phase, that's 15+ minutes of cumulative test time per phase. Even when it worked, it was wasteful. **Removed.**

❌ **Don't bump timeouts to "fix" hangs.** If a 30s hook is timing out, the underlying command is slow — making it 60s just delays the symptom. Either make the command faster or remove the hook.

### Safer hook patterns

✅ **Fast, opt-in, read-only:**
```jsonc
{
  "hooks": {
    "PostToolUse": [{
      "matcher": "Edit",
      "hooks": [{
        "type": "command",
        // Only when env var set, only pure-Python tests, 10s cap
        "command": "if [ \"$CLAUDE_RUN_FAST_TESTS\" = \"1\" ]; then pytest -x --no-header -q tests/test_pipeline_graph.py tests/test_determinism.py 2>&1 | tail -3; fi",
        "timeout": 10
      }]
    }]
  }
}
```

✅ **`Stop` hook for status-line refresh** (lightweight, no DB):
```jsonc
{
  "hooks": {
    "Stop": [{
      "hooks": [{
        "type": "command",
        "command": "git status --short | head -3",
        "timeout": 5
      }]
    }]
  }
}
```

### Project-specific stance

**Currently: NO hooks** (just `{}` in `.claude/settings.json`). After being burned by hangs, we rely instead on:
- Manual `pytest` runs after meaningful edits (Claude commits to this in memory)
- `/code-review` before push as the quality gate
- Skills (`/verify`, `/security-review`) when their specific concerns apply

Re-introduce hooks ONLY when a specific pain point demands it AND the hook can be proven to run in <2s without external dependencies.

---

## MCP servers — connect Claude to external tools

MCP (Model Context Protocol) servers expose external systems as native tools. Tools become callable inline without `Bash`/`Python` scripting.

### MCP servers worth adding to this project

| Server | Replaces | Effort | Payoff |
|---|---|---|---|
| **Postgres MCP** | `psycopg2` inline scripts | 30 min | Huge for Phase 5 (ingestion_jobs), Phase 6 (versioning), Phase 9 (access verification) |
| **GitHub MCP** | `gh` CLI shelling out | 30 min | PR / issue management without context-switching |
| **Filesystem MCP** | Already partly redundant with Read/Write/Edit | optional | Large-scale refactors only |
| **Slack MCP** | manual notification posting | optional | Useful once Phase 8 delivery channels land — same back-end |
| **Sentry MCP** | shell `curl` to Sentry API | optional | Once we wire observability (Phase 8 era) |

### How to add an MCP server

```bash
claude mcp add postgres --command "npx @modelcontextprotocol/server-postgres postgresql://user:pass@localhost/agenticplatform"
# or via Claude Code config UI
```

Servers persist across sessions. They appear as `mcp__<server>__<tool>` in the deferred tools list — invoke via `ToolSearch` then call.

### Authoring your own MCP server

Use the `mcp-builder` skill. Best for:
- Internal APIs your team uses (Linear, Notion, custom service)
- DB ops where you want a custom domain interface (e.g. `query_vendor_facts(vendor_id, rfp_id)` is friendlier than raw SQL)

---

## Subagents — delegate to specialised workers

The `Agent` tool spawns a subagent. Subagent types available on this project:

| Type | What it does | When to use |
|---|---|---|
| `Explore` | Read-only search agent | Locating code, finding references, "where is X defined" |
| `Plan` | Architect agent for implementation design | Design before code; the Plan agent helps validate approach |
| `general-purpose` | Catch-all multi-step worker | Tasks not matching a more specific type |
| `claude-code-guide` | Q&A about Claude Code itself | "Can Claude do X?" without disrupting main session |
| `statusline-setup` | One-shot statusline configuration | Use once via `/statusline-setup` |

### When subagents help most

- **Open-ended exploration** — "find all callers of X across the codebase" → `Explore` is faster than my own grep iteration
- **Independent work** — two subagents in parallel on independent files (worktrees!)
- **Protecting main context** — if you'd otherwise read 50 files, delegate the read+summarise to a subagent

### Worktree isolation — parallel branch work

Pass `isolation: "worktree"` to the `Agent` tool. The subagent works in a fresh git worktree on a temp branch. Useful for:

- Two phases that don't touch each other (e.g., Phase 5 backend ingestion + Phase 7 PDF report)
- Trying two designs in parallel to compare

Worktree auto-cleans up if the agent makes no changes. Otherwise it returns a path + branch name you can merge.

### When NOT to subagent

- Single targeted lookup — `Glob` / `Grep` is faster
- Code that needs to be reviewed line-by-line — agents summarise, you'd lose detail
- Sequential work — overhead exceeds the work itself

---

## Memory system — persistence across sessions

Location: `C:\Users\kishore\.claude\projects\c--Users-kishore-Downloads-agenticRag-rfp\memory\`

### Memory types

| Type | What goes here | Example |
|---|---|---|
| `user` | Who the user is, their role, expertise | "Kishore is an engineer optimising for product quality; no demo pressure right now" |
| `feedback` | Corrections / confirmations on approach | "Always run /code-review after each phase commit" |
| `project` | Time-bounded facts about current work | "Phase 5 is deadline-based not arrival-based; design committed in 9b41fa0" |
| `reference` | Pointers to external systems | "PRs tracked at github.com/kish21/agenticRag-rfp" |

### Patterns from this session that should be in memory

I've saved:
- `feedback_proactive_claude_code_tooling.md` — recommend Claude Code tools proactively, not on demand

Should be saved (didn't yet):
- "Anthropic SDK silently drops temperature param — always pass it explicitly" (Phase 1 bug)
- "uuid.uuid4() in setup code breaks cross-run reproducibility — use SHA-derived stable IDs"
- "LangGraph Send + dict fields require Annotated[dict, _merge_dicts] reducer or last-writer-wins silently"
- "passlib bcrypt version-detection warning is non-fatal — verify_password still works"

### When to write memory

- After every non-obvious bug fix → save the cause + fix as `feedback_*`
- After every architectural decision → save as `project_*` (with date)
- When the user provides any explicit "from now on..." instruction → save as `feedback_*`

Memory is loaded into context next session, so future-Claude knows what current-Claude learned.

---

## Plan mode — design before code

Trigger: type `/plan` or describe an ambitious task and Claude enters plan mode.

### Phases (enforced by the harness)

1. **Phase 1 — Initial Understanding** — read code, ask clarifying questions
2. **Phase 2 — Design** — Plan agent designs the approach (subagent type)
3. **Phase 3 — Review** — review Plan agent's output
4. **Phase 4 — Final Plan** — write to plan file (only file Claude can edit)
5. **Phase 5 — ExitPlanMode** — user approves; Claude exits plan mode and starts coding

### When to use plan mode

- ✅ Multi-phase features (everything in `PRODUCTION_READINESS_PLAN.md`)
- ✅ Architectural decisions with ≥3 viable approaches
- ✅ Cross-cutting refactors that touch multiple subsystems
- ❌ Single-file bug fixes
- ❌ "Just add a print statement"
- ❌ Exploratory questions ("what would happen if...?")

### Plan mode gotchas

- ONLY the designated plan file can be edited inside plan mode — everything else is read-only
- `ExitPlanMode` is the approval signal; the user can reject it and continue iterating
- After plan approval, Claude returns to normal mode and starts implementation

---

## Slash commands — quick invocations

Built-in commands available in this project:

| Command | Effect |
|---|---|
| `/clear` | Start a new conversation; clears context |
| `/compact` | Compress conversation history (manual; auto happens too) |
| `/help` | Built-in help |
| `/config` | Edit settings via UI |
| `/init` | Generate CLAUDE.md for the current repo |
| `/loop <prompt>` | Run a prompt on a recurring interval |
| `/schedule` | Cron-style scheduled remote agent |
| `/verify` | Run the app and confirm a change works |
| `/code-review` | Multi-agent review of current diff |
| `/security-review` | Security audit of branch |
| `/simplify` | Apply `/code-review --fix` |
| `/run` | Launch and drive the project's app |
| `/fewer-permission-prompts` | Auto-build a permissions allow-list |

### Custom slash commands

Drop a `.md` file in `.claude/commands/<command-name>.md`. The file body is the prompt Claude runs when the command is invoked. Project has these already:

- `.claude/commands/` (directory exists; inspect contents to see what's there)

Useful custom commands for this project would be:
- `/phase-commit` — runs targeted tests, generates commit message in our standard format, commits
- `/smoke` — runs the standard fixture smoke test and reports pass/fail
- `/seed-personas` — invokes `tools/seed_visibility_personas.py`

---

## Statusline — persistent awareness

Configured in `~/.claude/settings.json`:
```jsonc
{
  "statusLine": {
    "type": "command",
    "command": "bash ~/.claude/statusline-command.sh"
  }
}
```

The script output appears at the bottom of the Claude Code UI. Useful items:
- Current git branch
- Number of unpushed commits
- Last test run pass/fail
- Token usage estimate
- Active worktree (if any)

Use `/statusline-setup` skill once to scaffold a fresh statusline.

---

## Permissions model

Two layers:

1. **`permissionMode`** in settings — `default` (prompt on dangerous), `acceptEdits` (auto-allow edits), etc.
2. **`permissions.allow` / `permissions.deny`** in `.claude/settings.local.json` — explicit allow-list

This project's `settings.local.json` has 50+ pre-allowlisted commands. Add new ones via the popup when Claude is blocked, OR run `/fewer-permission-prompts` to auto-batch.

### Best practice
- Pre-allowlist *read-only* commands generously (git status, git log, ls, cat)
- Pre-allowlist *destructive* commands narrowly (git push only to specific remotes)
- Never allow `rm -rf` or unbounded `Bash(*)` wildcards

---

## Plugins / marketplaces

Extensions live in `~/.claude/plugins/`. Sources include:

```jsonc
"extraKnownMarketplaces": {
  "claude-plugins-official": {
    "source": { "source": "github", "repo": "anthropics/claude-plugins-official" }
  }
}
```

Browse via `/plugin` or `/marketplace`. Plugins can add:
- New skills
- New MCP servers
- Statusline themes
- Custom commands

For this project, the official Anthropic marketplace is the safest source. Check for plugins related to: LangGraph, LangSmith, Qdrant, FastAPI — they may add purpose-built MCP servers or skills.

---

## Background tasks & monitoring

Tools we've used heavily this session:

- `Bash(... run_in_background: true)` — fire-and-forget shell commands. Returns a task ID; Claude is auto-notified when it completes.
- `Agent(... run_in_background: true)` — spawn a subagent in the background.
- `Monitor` (deferred tool) — stream events from a running background task without polling.
- `TaskOutput` / `TaskStop` (deferred tools) — read output / kill a background task.

### Best practice

- Use `run_in_background` for ANY operation expected to take >30s (LLM batch jobs, smoke runs, builds, deploys)
- Use `ScheduleWakeup` only in `/loop` dynamic mode — never to poll background tasks (they auto-notify)
- For "wait until done" semantics, use foreground Bash with `timeout`

### Project specific

The 5-minute smoke test should ALWAYS run `run_in_background: true`. We did this consistently; keep doing it.

---

## Cloud / billed features

These cost credits but are sometimes worth it:

| Feature | Cost | When worth it |
|---|---|---|
| `/code-review ultra` | Per-run | High-stakes PRs (Phase 9 multi-tenant, Phase 5 autonomous ingestion). Multi-agent deep review in the cloud. |
| `/schedule` recurring agent | Per-run | Daily smoke test, weekly drift check |
| Cloud subagents (`subagent_type=general-purpose` with heavy work) | Tokens | Long codebase audits, large refactor planning |
| `Fast mode` for Claude Code | Faster output, same model | Set via `/fast` — useful when you're in a hurry |

---

## Settings cheat-sheet for this project

```jsonc
// ~/.claude/settings.json (user global)
{
  "statusLine": { "type": "command", "command": "bash ~/.claude/statusline-command.sh" },
  "effortLevel": "medium",                  // "low" / "medium" / "high" — controls auto-reasoning depth
  "attribution": { "commit": "", "pr": "" }, // no Co-Authored-By trailer (per project memory)
  "extraKnownMarketplaces": { "claude-plugins-official": { ... } }
}

// .claude/settings.json (project, commit to git)
{}    // <-- currently empty. Add hooks ONLY if proven needed + fast + read-only.

// .claude/settings.local.json (gitignored, machine-specific)
{ "permissions": { "allow": [ ... ~50 entries ... ] } }
```

---

## Anti-patterns we've hit on this project

| Anti-pattern | Why it bites | Better |
|---|---|---|
| Running DB-touching tests in `PostToolUse` hook | Multiplies cost by number of edits; hangs on DB slowness | Run targeted tests manually after a meaningful edit batch |
| 3 sequential `SessionStart` commands with no parallelism | One slow command freezes session start | Run them on-demand, or rewrite as one fast pre-flight check |
| Increasing hook timeouts to "fix" hangs | Treats symptom not cause | Diagnose what's slow; fix that |
| Reaching for `Bash` to query Postgres 30× per session | Slow, verbose, brittle escape syntax on Windows | Install Postgres MCP once |
| Committing `.claude/settings.local.json` | Leaks personal allow-list to the repo | Already gitignored; double-check before push |
| Deep multi-step `python -c "..."` inline scripts | Windows `cmd.exe` quoting hell, no syntax highlighting | Put it in a real `.py` file under `tools/` |

---

## What I (Claude) commit to on this project — going forward

1. **At session start** — read CLAUDE.md, summarise current state, identify which Claude Code features apply to the planned work
2. **After every phase commit** — recommend `/code-review` against the diff
3. **Before any auth/access/schema PR** — recommend `/security-review`
4. **For repetitive ops** — recommend MCP servers
5. **For parallelisable work** — recommend worktree subagents
6. **As I discover non-obvious patterns** — save them to memory immediately
7. **For UI work** — invoke `/frontend-design`, `/frontend-component`, `/anti-ai-ui` in order (per existing memory)
8. **For commits** — never add `Co-Authored-By` trailer (per existing memory)
9. **Default: NO hooks** — re-introduce only after a proven need + cost analysis

---

## Useful references

- Plan + exit criteria for upcoming phases: [PRODUCTION_READINESS_PLAN.md](PRODUCTION_READINESS_PLAN.md)
- Measured metrics + customer-facing claims: [PERFORMANCE_AND_QUALITY_METRICS.md](PERFORMANCE_AND_QUALITY_METRICS.md)
- Project conventions + constraints: [../../CLAUDE.md](../../CLAUDE.md)

---

## TL;DR — three commands every Claude Code session should know about

1. `/code-review` — before every push
2. `/security-review` — before auth/access PRs
3. `/verify` — before saying "the UI works"

Everything else is enhancement. These three are the floor.
