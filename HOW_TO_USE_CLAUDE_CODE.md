# HOW TO START A CLAUDE CODE SESSION CORRECTLY
# ================================================
# The problem: Claude Code drifts from the skill mid-session.
# The fix: Use the exact prompts below. Every time. No shortcuts.

---

## THE GOLDEN RULE

**Never say:** "Continue building the project"
**Never say:** "Keep going from where we left off"
**Never say:** "Build the next thing"

These vague instructions let Claude Code decide what "next" means.
It will decide based on what seems logical, not what the skill says.

---

## EXACT PROMPT TO START EVERY SESSION

Copy this. Fill in the blanks. Do not paraphrase it.

```
You are working on the Enterprise Agentic AI Platform project.

BEFORE WRITING ANY CODE:
1. Read CLAUDE.md completely
2. Run: python checkpoint_runner.py status
3. Read the output and tell me: what is the last passed checkpoint?

Then tell me ONE sentence: "I will build [FILE] to pass checkpoint [SKILL-CPxx]"

Wait for me to confirm before you start building.
```

---

## AFTER CLAUDE CODE CONFIRMS THE PLAN — Anchor it

Once Claude Code says what it will build, reply with this:

```
Correct. Now build ONLY that file.
After writing it, run: python checkpoint_runner.py [SKILL-CPxx]
Do not touch any other file until that checkpoint passes.
```

---

## WHEN CLAUDE CODE FINISHES A STEP — Keep it anchored

After each file is written and checkpoint passes, use this prompt:

```
Checkpoint [SK0X-CPxx] passed. 
Now read the NEXT step in SKILL_0X.md and tell me what comes next.
Do not start building yet — tell me the plan first.
```

This forces re-reading the skill before every step. Not just at the start.

---

## WHEN YOU SUSPECT DRIFT — Run the detector

If Claude Code seems to be building something not in the current skill:

```
Stop. Do not write any more code.
Run: python drift_detector.py
Read the output to me completely.
```

---

## FULL SESSION SCRIPT — For a clean start

Use this at the beginning of a completely fresh session:

```
New session starting for the Enterprise Agentic AI Platform.

Step 1: Read CLAUDE.md completely. Tell me what the current skill is 
        and what the last passed checkpoint was.

Step 2: Run: python checkpoint_runner.py status
        Read the output. Does it match CLAUDE.md? If not, which is more recent?

Step 3: Run: python drift_detector.py
        Read the output. Are there any errors or warnings?

Step 4: Based on the above, tell me exactly ONE thing you will build 
        in this session and which checkpoint it corresponds to.

Do not start building until I reply "go ahead".
```

---

## KEEPING CLAUDE CODE ON TRACK DURING A LONG SESSION

Every time Claude Code finishes a step, use this re-anchoring prompt:

```
Good. Now before you build the next thing:
- What does SKILL_0X.md say is the NEXT step after the one you just completed?
- What is the checkpoint for that step?
- Is there anything in CLAUDE.md that restricts what you can build now?
```

This 10-second check prevents an entire session of drift.

---

## IF CLAUDE CODE SUGGESTS BUILDING SOMETHING EXTRA

Claude Code will sometimes say "I notice we could also add X" or
"While I'm here I could also build Y".

Reply with this every time:

```
Do not build [X/Y]. 
Add it to BACKLOG.md with today's date.
Continue with the current step only.
```

---

## IF A CHECKPOINT IS FAILING AND CLAUDE CODE WANTS TO MOVE ON

Claude Code sometimes says "this checkpoint is failing but it might work when 
the next component is built". 

Reply with this every time:

```
No. Fix the failing checkpoint before building anything else.
Read the checkpoint error again carefully.
Which specific file is causing the failure?
Fix only that file and re-run the checkpoint.
```

---

## ENDING A SESSION CORRECTLY

Before closing Claude Code, use this prompt:

```
Session is ending. Before we stop:

1. Run: python checkpoint_runner.py status
2. Update CLAUDE.md — set current skill, last passed checkpoint, next action
3. Write one entry in daily_build_log.md
4. Run: python drift_detector.py — confirm no drift

Tell me the results of each step.
```

---

## THE MOST IMPORTANT THING

The skills, checkpoints, and CLAUDE.md only work if you use them
at the start of EVERY session. Not just the first one.

Claude Code has no memory between sessions.
Every session is a fresh start.
The files are the memory. Use them.
