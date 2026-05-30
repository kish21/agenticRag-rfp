# How the Evaluation Works — Plain English

> This document explains exactly what happens inside the system when you click
> "Confirm & Start Evaluation". No jargon. Written for a procurement manager,
> not a software engineer.

---

## The Big Picture

You uploaded an RFP and several vendor proposals. You defined criteria.
The system now needs to read every document, find the evidence, score every
vendor against every criterion, and produce a ranked recommendation.

It does this through 9 specialist workers called **agents**. Each one has a
single job. They hand their work to the next agent in line, like a relay race.
A 10th worker — the **Critic** — watches every agent and checks their work
before it moves on.

---

## Two ways an evaluation starts

There are two ways the documents get in front of the agents. Either way, the
9-agent pipeline below is identical — only the timing differs.

1. **Upload everything at once (manual mode).** You upload the RFP and all
   vendor proposals together, set your criteria, and click Evaluate. The system
   reads and processes everything on the spot. This is the original flow.

2. **Vendors submit over a deadline window (background mode).** You create the
   RFP, invite vendors, and set a submission deadline. Vendors drop their files
   in over days or weeks. The system quietly stores each file as it arrives but
   does no scoring yet. When the deadline passes, it processes every vendor in
   the background against the same criteria. By the time you click Evaluate, the
   facts are already extracted — so the result comes back in about 30 seconds
   instead of several minutes.

Background mode has three settings: stop after extracting facts and wait for you
to click Evaluate (`auto_to_evaluate`, the default), or — once the PDF report
feature ships — go all the way to a finished report automatically
(`auto_to_report`). `manual` keeps the upload-everything-at-once behaviour.

---

## Step 1 — The Planner Agent

**What it does:**
Before anything starts, the Planner reads your criteria list and draws up a
work plan. It decides what needs to be extracted from the documents, in what
order, and which agents will handle which parts.

**Why it matters:**
Without a plan, every agent would have to figure out the job from scratch.
The Planner makes the whole pipeline efficient and consistent.

**Real world analogy:**
A project manager reading a brief and writing the team's task list before
the work begins.

---

## Step 2 — The Ingestion Agent

**What it does:**
Takes every document you uploaded (the RFP and all vendor proposals) and
breaks them into small, overlapping chunks — roughly paragraph-sized pieces.
Each chunk is stored with a label so the system always knows which document
and which page it came from.

It also creates two types of "fingerprints" for every chunk:
- A **meaning fingerprint** — captures what the text is about conceptually
- A **keyword fingerprint** — captures the exact words used

Both fingerprints are stored in a search database (Qdrant).

**Why it matters:**
You can't ask an AI to read a 200-page PDF in one go. Chunking lets the
system find the right paragraph out of thousands in milliseconds.

**Real world analogy:**
A librarian cutting every book into individual pages, labelling each one,
and filing them in a way that lets you find any page by topic OR by keyword.

---

## Step 3 — The Retrieval Agent

**What it does:**
For each criterion (e.g. "Service Level Commitments"), it searches the
chunk database using both fingerprint types at the same time. It gets back
a list of candidate chunks from each vendor's document.

It then runs those candidates through a **re-ranker** — a second AI model
that re-reads each chunk and scores how genuinely relevant it is to the
criterion. The top-ranked chunks (usually 5–10 per vendor per criterion)
are kept.

It also uses a technique called **HyDE**: before searching, it generates
a hypothetical ideal answer to the criterion, then searches for chunks
that look like that ideal answer. This finds relevant content even when
the vendor uses completely different wording.

**Why it matters:**
A basic keyword search would miss a vendor who calls it "uptime guarantee"
instead of "service level commitment". The meaning fingerprint + HyDE
combination catches that. The re-ranker removes noise.

**Real world analogy:**
A researcher who searches the library by topic AND by keyword, reads the
top results, throws away the ones that are only superficially related, and
hands you the most genuinely useful pages.

---

## Step 4 — The Extraction Agent

**What it does:**
Takes the relevant chunks found in Step 3 and pulls out specific, structured
facts. For each vendor it extracts things like:

- Certifications held (ISO 27001, Cyber Essentials, etc.)
- Insurance amounts (e.g. £5M professional indemnity)
- SLA commitments (e.g. 99.9% uptime, 4-hour response time)
- Project references (past contracts, sectors, values)
- Pricing structures

Every fact is saved with a **direct quote** from the original document —
the exact sentence it came from. If it can't find a quote, it does not
invent one.

All extracted facts are stored in a structured database table (PostgreSQL),
not in the search database. This is important: from this point on, the
evaluation reads from structured facts, not from raw document text.

**Why it matters:**
Scoring based on raw text is unreliable. Scoring based on structured facts
(vendor X stated 99.9% uptime on page 4, quoted verbatim) is auditable and
defensible.

**Real world analogy:**
A paralegal reading every proposal and filling in a standardised fact sheet
for each vendor — with page references for every entry.

---

## Step 5 — The Evaluation Agent

**What it does:**
Goes through every vendor × every criterion combination and produces a score.

For a **Required criterion**: returns Pass or Fail, with the evidence.

For a **Scoring criterion**: returns a score from 0 to 10, a written
justification, and the direct quote from the vendor's document that the
score is based on.

It reads from the structured fact sheets (from Step 4), not from the raw
documents. This means every score is grounded in something the vendor
actually wrote.

**Why it matters:**
This is the core of the evaluation. Every score has a reason and a source.
Nothing is made up.

**Real world analogy:**
A subject matter expert sitting down with the fact sheets and scoring each
vendor on each question — writing their reasoning next to every score.

---

## Step 6 — The Comparator Agent

**What it does:**
Takes all the scores from Step 5 and calculates each vendor's final weighted
total. It applies your criterion weights (the percentages you set on the
confirm page) to turn individual scores into a single comparable number.

It also runs a **stability check**: it slightly varies the weights within
a small range and checks whether the ranking changes. If one vendor is only
ahead because of a 0.1% weight difference, that is flagged as an unstable
result.

Finally it produces a ranked list: Vendor A: 78%, Vendor B: 64%, etc.

**Why it matters:**
Without weighting, a vendor who is excellent at one thing would look the
same as a vendor who is consistently good at everything. The weights reflect
your organisation's actual priorities.

**Real world analogy:**
A scorekeeper who multiplies each judge's score by its agreed importance,
adds them up, and checks whether the final positions would change if the
importance weights shifted slightly.

---

## Step 7 — The Decision Agent

**What it does:**
Takes the ranked list and applies your organisation's governance rules.

- Any vendor who failed a Required criterion is marked **Rejected** at
  this stage, regardless of their scoring total.
- The remaining vendors are **Shortlisted** in rank order.
- Based on the contract value you entered, it determines the **approval
  tier** — who needs to sign this off (e.g. department head vs. board).
- It sets a deadline for that approval.

**Why it matters:**
Scores alone are not a decision. The Decision Agent turns scores into an
actionable recommendation that fits your procurement governance framework.

**Real world analogy:**
A procurement director reviewing the scoring sheet, removing anyone who
failed a mandatory check, and writing the approval memo with the right
signatory based on the contract value.

---

## Step 8 — The Explanation Agent

**What it does:**
Writes the final report in plain English. For every claim in the report —
every score, every rejection reason, every recommendation — it includes a
citation back to the exact passage in the vendor's document.

The report covers:
- Overall recommendation and rationale
- Each vendor's strengths and weaknesses per criterion
- Why each rejected vendor was eliminated
- Who needs to approve, and by when

**Why it matters:**
A decision without explanation is not auditable. If a losing vendor
challenges the outcome, every line of the report can be traced back to what
they actually wrote — or failed to write.

**Real world analogy:**
A barrister writing a closing argument — every statement backed by
evidence, every conclusion explained, no assertion without a source.

---

## Step 9 — The Critic Agent (runs after every step)

**What it does:**
After every single agent finishes its work, the Critic inspects the output
before it is passed on. It checks for:

- **Hard failures** — e.g. a score was invented with no quote. Pipeline stops.
- **Soft warnings** — e.g. a quote was found but is only loosely relevant.
  Logged, pipeline continues.
- **Escalations** — patterns that suggest something is systematically wrong.
  Flagged for human review.

If the Critic blocks a step, the run is marked as needing human review
rather than silently producing a wrong result.

**Why it matters:**
AI models can hallucinate — produce confident-sounding but incorrect output.
The Critic is the quality control layer that catches this before it affects
a real procurement decision.

**Real world analogy:**
A senior reviewer who checks every piece of work before it leaves the team —
not to redo it, but to catch anything that looks wrong before it reaches
the client.

---

## What the System Does NOT Do

- It does not guess. If evidence is not in the document, the score reflects
  that gap rather than filling it in.
- It does not override your criteria. It evaluates exactly what you told it
  to evaluate, with exactly the weights you set.
- It does not make the final decision. It makes a recommendation. A human
  approves it.

---

## Cost and Time

| Phase | Approx. time | AI cost (typical) |
|---|---|---|
| Document reading + chunking | 30–60 sec | None (no AI) |
| Retrieval per criterion | 5–10 sec | None (search only) |
| Extraction (per vendor) | 15–30 sec | ~£0.01–0.03 |
| Evaluation (per vendor × criterion) | 20–40 sec | ~£0.02–0.05 |
| Decision + report | 10–20 sec | ~£0.01–0.02 |
| **Total (3 vendors, 10 criteria)** | **3–6 minutes** | **~£0.10–0.30** |

Cost scales with number of vendors and number of criteria. A large evaluation
(10 vendors, 20 criteria) would be approximately £1–3.

---

*Document version: May 2026*
