# QUICK REFERENCE
# Keep this open in a separate window during every coding session.

---

## START OF EVERY SESSION — These 3 commands. Always. No exceptions.

```bash
python checkpoint_runner.py status    # Where am I?
python drift_detector.py              # Is anything wrong?
python contract_tests.py              # Are interfaces intact?
```

---

## THE PROMPT TO START EVERY SESSION

```
Read CLAUDE.md.
Run: python checkpoint_runner.py status
Tell me the last passed checkpoint and what the next step is.
Do not write any code until I confirm the plan.
```

---

## AFTER CLAUDE CODE WRITES EACH FILE

```bash
python checkpoint_runner.py SK0X-CPxx
```
✓ PASS → say "good, what is the next step?"  
✗ FAIL → say "fix only that file and re-run the checkpoint"

---

## EVERY 20 MINUTES IN A LONG SESSION

```bash
python drift_detector.py
```

---

## WHEN CLAUDE CODE SUGGESTS BUILDING SOMETHING EXTRA

Say this every time:
```
Do not build that now.
Add it to BACKLOG.md with today's date.
Continue with the current step.
```

---

## WHEN A CHECKPOINT KEEPS FAILING

Say this:
```
Stop trying different things.
Read the checkpoint error message carefully.
Tell me exactly which line in which file is causing the failure.
Fix only that line.
```

---

## END OF EVERY SESSION

```bash
python checkpoint_runner.py status
python drift_detector.py
```

Then say to Claude Code:
```
Update CLAUDE.md — set current skill, last checkpoint, next action.
Add one line to daily_build_log.md.
```

---

## CHECKPOINT QUICK REFERENCE

| Command | What it does |
|---|---|
| `python checkpoint_runner.py status` | Show full build state |
| `python checkpoint_runner.py SK01` | All Skill 01 checkpoints |
| `python checkpoint_runner.py SK01-CP03` | One specific checkpoint |
| `python checkpoint_runner.py all` | Full regression on all passed |
| `python drift_detector.py` | Detect off-track code |
| `python contract_tests.py` | Verify component interfaces |

---

## SKILL PROGRESS TRACKER

```
□ SKILL 01 — Foundation          (8 checkpoints)
□ SKILL 02 — Agent Engine        (11 checkpoints)
□ SKILL 03 — Document Processing  (6 checkpoints)
□ SKILL 04 — Procurement Agent    (7 checkpoints)
□ SKILL 05 — Output & Deploy      (5 checkpoints)
□ SKILL 06 — Platform Expansion   (6 checkpoints)
                         Total: 43 checkpoints
```

Tick a skill when ALL its checkpoints pass AND drift_detector shows clean.
