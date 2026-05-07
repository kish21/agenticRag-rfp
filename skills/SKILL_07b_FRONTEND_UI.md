# SKILL 07b — Frontend UI Redesign
**Sequence:** After SK07 complete. Frontend scaffold exists. Design system in lib/theme.ts.
**Time:** 2-3 days.
**Output:** All 11 pages built to the UI design prompt specifications. Production-quality enterprise UI.

---

## RULES FOR CLAUDE CODE

1. Never hardcode colours — always use theme tokens from lib/theme.ts
2. Never use Tailwind for colours — use inline styles with PALETTE values
3. One primary action button per screen — only one solid coloured button
4. Every AI output shows its source as a formal blockquote with coloured left border
5. No AI jargon in labels — use plain English equivalents (see table below)
6. Build one page at a time — show output and wait for confirmation before next page
7. All pages are "use client" React components
8. API calls use Bearer token from localStorage.getItem("access_token")
9. Never touch app/page.tsx — Page 0 Agent Home is complete

---

## JARGON REPLACEMENT TABLE

| Technical term | Plain English label |
|---|---|
| Compliance gate | Mandatory requirements check |
| Critic Agent flag | Flagged for attention |
| Extraction confidence | Evidence quality |
| Retrieval Agent | (do not mention) |
| Critic verdict | Review status |
| Hard block | Stopped for review |
| Soft flag | Needs attention |
| EvaluationSetup | Evaluation criteria |
| Qdrant | (do not mention) |
| PostgreSQL | (do not mention) |

---

## DESIGN SYSTEM — applies to every page

Import from lib/theme.ts on every page:
```typescript
import {
  AGENT_COLOUR, COMPANY, FONT, SERIF, MONO,
  PALETTE, PALETTE_LIGHT, TOKENS,
  BG_GRADIENT, TOPBAR_BG,
} from "@/lib/theme";
```

**Base colours:**
- Page background: PALETTE.bg.base (#090C14)
- Card background: PALETTE.bg.surface (#111520)
- Card border: PALETTE.border.mid (#1E2438)
- Primary text: PALETTE.text.primary (#F8FAFC)
- Secondary text: PALETTE.text.secondary (#CBD5E1)
- Muted text: PALETTE.text.muted (#6B7280)

**Evidence quote box — used on every page that shows AI output:**
```typescript
const quoteBoxStyle = {
  backgroundColor: "#2A2D3E",
  borderLeft: "4px solid ACCENT_COLOUR",
  borderRadius: "0 8px 8px 0",
  padding: "12px 16px",
  margin: "8px 0",
};
// Opening quotation mark: large decorative character in accent colour
// Quote text: white, 17px
// Source line below: grey mono, small
```

**Confidence display — never show numbers:**
- High confidence: small green dot + "High confidence"
- Medium confidence: small amber dot + "Attention needed"
- Low confidence: small red dot + "Flagged for review"

---

## STEP 1 — Extract shared component

Before building any page, extract AgentSwitcherRail from app/page.tsx
into components/AgentSwitcherRail.tsx.

Do not change app/page.tsx functionality.
Export the component and import it back into app/page.tsx.

Verify app/page.tsx still renders correctly after extraction.

---

## STEP 2 — Update layout.tsx

Update app/layout.tsx:
- Title: COMPANY.platformName from theme.ts
- Add all Google Fonts as CSS variables at layout level:
  IBM Plex Sans, IBM Plex Mono, Sora, Space Grotesk, Inter,
  Outfit, Lora, Raleway, Nunito, DM Sans

```typescript
import {
  IBM_Plex_Sans, IBM_Plex_Mono, Sora, Space_Grotesk,
  Inter, Outfit, Lora, Raleway, Nunito, DM_Sans
} from "next/font/google";
```

---

## PAGE 1 — Department Head Dashboard
**File:** app/dashboard/page.tsx (replace existing)
**Font:** IBM Plex Sans
**Accent:** #00D4AA (teal)

### Layout — three zones

**Zone 1: Sticky status bar (56px)**
- Left: platform wordmark white
- Centre: three pills — pulsing amber dot + running count | teal dot + ready count | grey dot + attention count
- Right: user avatar + department label
- Sticky — follows user on scroll

**Zone 2: Three action cards (120px each, horizontal row)**
- Card A: New Evaluation — plus icon, label, arrow
- Card B: Review Results — teal count badge, label
- Card C: Pending Approvals — grey count badge, label
- Visual rule: card with non-zero badge gets 3px teal left border
- Zero count cards get dim #2A2D3E border

**Zone 3: Recent evaluations table**
- Columns: Name | Vendors | Status | Started | Action
- Status pills (colour-coded, never plain text):
  - Running: amber pill + animated dot + current agent in plain English: 'Scoring — 6 of 18 done'
  - Ready: teal pill 'Results ready'
  - Pending approval: amber pill 'Awaiting CFO approval'
  - Complete: grey pill 'Complete · date'
  - Failed: red pill 'Failed' — hover shows reason
- Action button changes by status:
  - Running → 'View progress' (ghost)
  - Ready → 'Review results' (solid teal)
  - Complete → 'View report' (ghost)
  - Failed → 'See what happened' (ghost red)
- Clicking running row expands inline: 5-step pipeline
  - Steps: Ingestion > Retrieval > Compliance > Scoring > Report
  - Complete: teal | Active: amber pulse | Waiting: grey
  - Each step shows elapsed time

**Empty state:**
- Document stack SVG (not generic clipart)
- 'No evaluations yet.' large text
- One button: 'Start evaluation' in teal
- Nothing else

**API:**
```
GET /api/v1/dashboard
Returns: evaluation_runs[] with run_id, rfp_title, department,
status, vendor_count, shortlisted_count, rejected_count, started_at
```

### Architect rules
1. Status bar answers 'what needs my attention?' before the user scrolls
2. Running evaluations show current agent name in plain English inside status pill
3. Action card with non-zero count is visually louder through border colour only — not font size
4. Empty state has exactly one action — one button, nothing else

---

## PAGE 2 — CEO/CFO Executive Dashboard
**File:** app/dashboard/cfo/page.tsx (new file)
**Font:** Playfair Display for numbers only, DM Sans for everything else
**Accent:** #F59E0B (amber) for all financial figures

### Rules
- Zero AI jargon — replace every technical term
- No upload buttons, no configuration — reporting and approval surface only
- No navigation sidebar on this page

### Layout

**Row 1: Four KPI tiles (25% each, 140px tall)**
- Active evaluations: number in Playfair Display 48px
- Contract pipeline value: £ figure amber 48px Playfair, sub-label
- Pending approval: number, red pulse animation if >0, '72-hour SLA applies'
- Completed this month: teal
- Each tile: sparkline bottom-right in dim grey

**Row 2: Approvals required (HIDDEN when empty — never show empty state)**
- Amber-bordered card, shown ONLY if pending count >0
- Each item: dept badge | evaluation name | recommended vendor + score | contract value amber bold | SLA countdown (red <24h) | 'Review and approve' button amber solid

**Row 3: Two columns**
- Left 58%: all active evaluations table
  - Columns: Dept | Evaluation | Vendors | Contract value | Status | Days
  - Contract value always amber
  - Clicking row: 480px slide-in panel (no navigation)
    - Panel: recommendation, top 3 scores, contract value, requestor, days
    - One button: 'Open full report' (new tab)
- Right 42%: department activity
  - recharts horizontal bar chart
  - One bar per department, amber fill, grey track
  - Clicking bar filters left table

**Bottom:** Dim timestamp + refresh only. Nothing else.

**API:**
```
GET /api/v1/dashboard/executive
Returns: kpis{}, pending_approvals[], active_evaluations[], dept_activity[]
```

### Architect rules
1. Contract value is always amber and always the largest number visible
2. Approvals section completely hidden when empty — CFO never sees empty state
3. Slide-in panel keeps CFO in context — no navigation away
4. Zero AI terminology on this page

---

## PAGE 3 — New Evaluation Upload
**File:** app/procurement/upload/page.tsx (replace existing)
**Font:** Sora
**Accent:** #818CF8 (soft indigo)

### Step progress tracker (horizontal, full width)
- 3 steps: Upload RFP | Add vendors | Review and start
- Completed: solid indigo circle + white tick + indigo label
- Active: indigo ring, bold white label
- Future: grey ring, grey label
- Connecting lines: solid indigo (done), dashed grey (pending)

### Step 1 — Upload RFP
- Drop zone: 220px tall, 1px dashed indigo border, 12px border-radius
- Custom SVG: document with arrow (NOT a cloud icon)
- Headline: 'Drop your RFP document here'
- Sub-label: 'PDF or Word document · Maximum 50MB'
- 'or browse files' link in indigo
- Collapsible '? What is an RFP document' section
- After upload: animated green check (CSS stroke animation 300ms)
  + file name left, file size right, Remove link
- Primary button: 'Continue to vendors →' appears after file added

### Step 2 — Add vendors
- Header: 'Add vendor submissions' + live count badge
- Repeating vendor entry component:
  - Vendor name input (auto-focused first load)
  - 60px compact file drop zone
  - Accepted formats as small grey pills: PDF, DOCX, ZIP
  - After upload: compact file card (name + size + remove)
  - Remove vendor: × top-right, hover only
- ZIP FILE HANDLING (critical):
  - When ZIP dropped: expanding preview
  - 'Found X files inside this archive:'
  - Each file: name — will be processed ✓ (or: skipped, amber not red)
- 'Add another vendor' button: secondary indigo border
- Minimum 1 vendor: button disabled with tooltip

### Step 3 — Review and start
- Summary card: RFP filename + vendor count + vendor names list
- Estimated duration: ~3 minutes per vendor
- 'You can close this window after starting' — prominent, not footnote
- Start evaluation button (indigo, full width)
- After click: spinner then navigate to /[runId]/confirm

**API:**
```
POST /api/v1/documents/upload (FormData: rfp file + vendor files)
POST /api/v1/evaluations/start {rfp_doc_id, vendor_doc_ids}
Returns {run_id}
```

### Architect rules
1. Accepted file formats shown as pills inside drop zone BEFORE user tries anything
2. ZIP file preview is non-negotiable — enterprise submissions are often ZIP archives
3. Estimated duration shown before user clicks Start
4. 'You can close this window' message must be in Step 3 confirmation

---

## PAGE 4 — RFP Identity Confirmation
**File:** app/[runId]/confirm/page.tsx (replace existing)
**Font:** DM Sans
**Accent:** #F59E0B (amber) for warnings

### Layout
- Centred card, max-width 600px
- Card background: #1A1D27
- Border: 1px #2A2D3E
- Border-radius: 16px
- Page background: #0F1117

### Card header
- Custom SVG: document with magnifying glass overlay (NOT a warning triangle)
- Headline: 'We found this RFP' — 28px white DM Sans bold
- Sub-headline: 'Please confirm this is the correct document before we begin.'
- Separator line

### Identity table (6 rows, staggered animation 80ms per row)
| Row | Label | Value |
|---|---|---|
| 1 | Reference number | extracted text |
| 2 | Issuer | extracted text |
| 3 | Document title | extracted text |
| 4 | Submission deadline | date or amber 'Not found in document' |
| 5 | Mandatory requirements | '3 found: ...' preview |
| 6 | Scoring criteria | '4 found: ...' preview |

- Value pills: #2A2D3E background, white text, 6px border-radius
- 'Not found': amber text, no pill
- Labels: grey #6B7280 — values must be MORE prominent

### Confidence line
- Green dot: 'We are confident in these details'
- Amber dot: 'Some details could not be confirmed'
- If any 'Not found': amber info banner above buttons

### Two buttons (full width, stacked, no close X)
- Primary (48px, indigo #6366F1): 'Yes, this is the correct RFP — start evaluation'
- Secondary (text link only): 'No, go back and upload a different document'

### Animation sequence
1. Card fades from bottom (200ms ease-out)
2. Header immediately
3. Table rows stagger 80ms apart
4. Buttons fade in after last row (100ms delay)
Total: under 700ms

**API:**
```
GET /api/v1/evaluations/{runId}/rfp-identity
Returns {reference, issuer, title, deadline, mandatory_count,
mandatory_preview, scoring_count, scoring_preview, confidence}
POST /api/v1/evaluations/{runId}/confirm-rfp
```

### Architect rules
1. Values visually dominant over labels — white value, grey label
2. 'Not found' appears amber, never red — it is not a failure
3. Two buttons only, no close X — user must actively choose
4. Staggered animation is functional — draws eye to each field in sequence

---

## PAGE 5 — Live Evaluation Progress
**File:** app/[runId]/progress/page.tsx (replace existing)
**Font:** Space Grotesk
**Accent:** #00D4AA (teal) complete, #F59E0B (amber) active

### Sticky top bar (60px)
- Left: evaluation name white bold
- Centre: 'Running...' + animated amber dot (2s pulse cycle)
- Right: 'Safe to close this window — evaluation continues in the background'
  - White text, teal info icon — MUST be visible without scrolling

### Two-column layout

**Left 38% — Pipeline status**
- Heading: 'Agent pipeline'
- 9 circular nodes vertically:
  1 Planner | 2 Ingestion | 3 Retrieval | 4 Extraction | 5 Compliance
  6 Scoring | 7 Comparison | 8 Decision | 9 Report
- Complete: solid teal circle + white tick + elapsed time mono grey below
- Active: amber ring 1.5s pulse + current action amber text (plain English)
  Example: 'Checking security certification · Vendor Alpha'
- Waiting: dim #3A3D50 ring
- Progress bar below nodes: '[count] of [total] vendors complete'
- Estimated time remaining (updates dynamically)

**Right 62% — Live activity feed**
- Heading: 'What is happening'
- Auto-scroll log newest at top
- Pauses on manual scroll + 'Jump to latest' button appears
- Each entry:
  - HH:MM:SS timestamp (mono, dim grey, right-aligned)
  - Agent badge: colour-coded pill
  - Message: plain English only, no technical terms, no IDs
  - Vendor name in grey after message
- Entry left border: 2px teal (confirmed/passed) | 2px red (rejected) | none (progress)

**Below log — Vendor status grid:**
- One cell per vendor, real-time updates
- Complete: teal border + vendor name + tick
- Running: amber border + current agent name
- Failed: red border + × icon

**SSE:**
```
GET /api/v1/evaluations/{runId}/stream
Events: agent_update | vendor_update | log_message | complete | error
```

### Architect rules
1. 'Safe to close this window' visible in sticky bar without scrolling
2. Log messages in plain English — 'Compliance check — security certification · Vendor Alpha'
3. Vendor grid gives instant status at 20-vendor scale
4. Failed vendor processing does not show as full pipeline failure

---

## PAGE 6+7 — Compliance Results + Scoring
**File:** app/[runId]/results/page.tsx (replace existing)

Two tabs: 'Compliance ✓' | 'Scoring' (violet underline active)

---

### COMPLIANCE TAB (Page 6)
**Font:** Inter
**Accent:** red rejected, teal passed

**Sticky header:**
- Breadcrumb: Dashboard > [dept] RFP > Compliance
- Summary: 'X vendors evaluated · X passed · X rejected' (large clear numbers)

**Section A: Rejected vendors FIRST (red-tinted header)**
- Sub-label: 'These vendors will not proceed to scoring.'
- Each card expandable:

  **Collapsed:**
  - Vendor name bold | RED PILL 'REJECTED' | failed check pills (dim)
  - Expand chevron

  **Expanded per failed check:**
  - Check name bold + clause reference (small grey pill)
  - What was required (one plain English sentence)
  - Evidence quote box:
    - #2A2D3E background
    - 4px indigo left border
    - Large indigo opening quotation mark
    - Exact vendor sentence in white
    - Source: 'Page X · Section X · Vendor name submission'
  - Why this fails (one sentence)
  - Confidence: 'High confidence' (teal) or 'Attention needed' (amber)

  **Buttons:**
  - 'Download rejection notice' (secondary)
  - 'Dispute this decision' (ghost red border)

  **Dispute side panel (480px, slides from right, no navigation away):**
  - Shows: AI decision + evidence (read-only, locked appearance)
  - Text area: 'Why do you believe this decision should be changed?' (min 50 chars)
  - Live character counter
  - Submit: 'Record dispute for review' (amber)
  - After submit: 'Recorded.' message, panel auto-closes 3s

**Section B: Passed vendors (quieter visual treatment)**
- White section header (not red-tinted)
- Same card structure but teal accent
- Smaller font in collapsed state, less contrast

---

### SCORING TAB (Page 7)
**Font:** Outfit
**Accent:** #A78BFA (violet), gold top vendor, silver second, bronze third

**Summary:** '14 vendors scored · Ranked by weighted criteria'

**Three-panel layout:**

**Left panel (260px sticky):** Ranked vendor list
- Rank number: 32px bold, gold/silver/bronze/grey
- Vendor name: white bold
- Thin score bar: violet fill on grey track
- Score number: right-aligned violet
- Active vendor: violet left border + #1E1B4B background

**Centre panel (flexible):** Selected vendor detail
- Rank badge + vendor name (24px) + total score (violet 32px)
- Confidence line: green/amber dot
- If two vendors within 3 points: amber info bar on BOTH
- Per criterion block (one per criterion):
  - Name + weight right
  - Score bar: full width violet, animated (0 → value, 600ms on load)
  - Score fraction: '9 / 10' violet Outfit bold
  - Rubric band pill: '9-10 band: [description]'
  - Evidence quote box (3px violet left border)
  - Soft flag: amber ⚠ icon with hover tooltip

**Right panel (220px sticky):** Compare vendors
- Dropdown: select vendor to compare
- When selected: centre splits into two columns
- Higher score per criterion highlighted violet background

**API:**
```
GET /api/v1/evaluations/{runId}/results
Returns shortlisted_vendors, rejected_vendors with full evidence and quotes
```

### Architect rules
1. Evidence quote is most important element — formal blockquote style
2. Rejected vendors appear BEFORE passed vendors
3. Confidence always plain English alongside evidence
4. Dispute panel does not navigate away

---

## PAGE 8 — Evaluation Report
**File:** app/[runId]/report/page.tsx (new file)
**Font:** Lora (serif) for headings, DM Sans for body
**Accent:** #00D4AA (teal)

### Page header (not sticky)
- Evaluation title: 40px Lora serif white
- Sub-line: dept · organisation · date
- Evaluator line: 'AI-assisted evaluation · Reviewed by [name]'
- Teal separator line

### TWO DOWNLOAD BUTTONS — above the fold, side by side, always visible
- 'Download PDF report' — teal solid (left)
- 'Download Excel scoring matrix' — ghost (right)
- Never hide these in a menu

### Approval status banner (full width, impossible to miss)
- Pending: amber background — '⏳ Awaiting CFO approval · X hours remaining'
- Approved: teal background — '✓ Approved by [name] · date'
- Rejected: red background — '✗ Returned for revision · See comments'

### Executive summary card
- Three KPI numbers: X evaluated | X rejected | X shortlisted
- Recommendation sentence (22px Lora): 'Vendor X is recommended based on...'
- Sub-text: contract value + approval status

### Shortlisted vendors (expandable cards)
- Rank badge (gold/silver/bronze) + vendor name + score + 'Recommended' badge for rank 1
- Collapsed: header row only
- Expanded: per-criterion score bars + evidence quotes
- 'View full scoring detail →' link (opens scoring tab)

### Rejected vendors (compact, below shortlist)
- Vendor name | REJECTED badge | reason (one sentence) | evidence excerpt
- 'Download formal rejection notice' per vendor

### Audit trail (bottom, grey smaller text)
- 'Every decision is traced to source documents.'
- Evaluation ID + 'View detailed audit log' link

**API:**
```
GET /api/v1/evaluations/{runId}/report
POST /api/v1/evaluations/{runId}/report/download?format=pdf|excel
```

### Architect rules
1. Download buttons above the fold always — user opened this page to download
2. Approval status banner impossible to miss
3. PDF must pass 'board paper test' — professional enough for board appendix
4. Audit trail note at bottom adds institutional trust at low cost

---

## PAGE 9 — Approval Screen
**File:** app/[runId]/approve/page.tsx (new file)
**Must work as standalone URL from Slack or email link**
**Font:** Raleway for headings, DM Sans for body
**Accent:** #F59E0B (amber)

### Layout
- Single column, max-width 760px, centred
- No sidebar, no navigation rail

### Top banner (full width)
- Default: amber — '⚡ Your approval is required · X hours remaining'
- Under 24h: red — '🔴 Urgent: X hours remaining'
- Expired: grey — 'This approval request has expired. Contact procurement.'

### Context card: 'What you are approving'
- Evaluation name large white
- 'Requested by [name], [department]'
- ONE SENTENCE plain English why approval needed:
  'The recommended contract value (£X) exceeds the £X threshold that
  requires CFO sign-off under company procurement policy.'

### Recommendation card (gold-tinted border)
- 'Recommended vendor: [name]'
- Score: large violet
- Contract value: VERY LARGE amber Raleway bold (largest number on page)
- One-sentence rationale (plain English, no agent names)

### Evidence accordion (open by default)
- Heading: 'Why we recommend this vendor'
- Per criterion: label | score bar | one plain English sentence
- Link: 'See full scoring and evidence →' (new tab)

### Rejected vendors (compact list)
- '× Vendor name — reason' per rejected vendor
- Link: 'View compliance report →' (new tab)

### Decision section
- Heading: 'Your decision'
- Sub-text: 'Your response will be logged with timestamp and your name.'
- Text input: 'type APPROVE to confirm' (prevents accidental mobile tap)
- APPROVE button: large amber, disabled until input matches exactly
- 'Return for revision' ghost red button + optional comments textarea

### After approve
- Green confirmation, timestamp, 'This cannot be undone' message

### After return
- Amber confirmation with comment stored

**API:**
```
GET /api/v1/evaluations/{runId}/approval
POST /api/v1/evaluations/{runId}/approve
Body: {decision: "approved"|"returned", comment?: string}
```

### Architect rules
1. SLA countdown in top banner must be red under 24h
2. 'type APPROVE to confirm' pattern prevents accidental mobile approvals
3. Contract value is the largest number on the page, in amber
4. Page must work as standalone URL with no prior platform knowledge

---

## PAGE 10A — Override Side Panel
**Component:** components/OverridePanel.tsx (used inside results page)
**Font:** DM Sans
**Accent:** #F97316 (orange — distinct from teal, amber, red)

### Panel spec
- 480px wide, slides in from right
- Overlay main page — no navigation away
- Orange 4px left border on entire panel edge

### Panel header
- Title: 'Override AI decision' white bold
- Sub-title: 'This is logged permanently and cannot be undone.' amber

### Context block (read-only, locked appearance)
- Heading: 'The AI decision you are changing'
- Decision type + vendor name
- AI decision: RED PILL 'REJECTED'
- AI evidence: original quote in #2A2D3E box
- AI confidence shown plain English
- Grey border, no hover state — visually locked

### Override form
- 'Your decision' heading
- Radio buttons (large touch targets):
  - ○ Change decision to PASS
  - ○ Keep as FAIL but flag for manual review
- Required text area: 'Reason for your override'
- Placeholder: 'Explain why you believe this decision should be changed...'
- Character counter: '0 / 50 minimum'
  - Orange at 30/50, green at 50+
- Submit disabled until 50 characters
- Name: pre-filled from auth, read-only
- Date/time: auto-filled, read-only
- Submit: 'Record this override' orange full width
- 'Cancel' grey text below

### After submit
- Do NOT close immediately
- Show inline: green checkmark (draws in 300ms) + confirmation messages
- Panel auto-closes after 3s with slide-out animation
- Results page behind updates vendor status

---

## PAGE 10B — Department Agent Configuration
**File:** app/config/page.tsx (new file)
**Font:** Nunito (rounded, friendly)
**Accent:** #8B5CF6 (violet)

### Layout
- Left nav 200px fixed + Right content area flexible

### Left navigation
- 4 sections with completion indicators:
  - 1 ● Mandatory requirements (green tick when complete)
  - 2 ● Scoring criteria (green tick when weights = 100%)
  - 3 ○ Approval thresholds (grey = incomplete)
  - 4 ○ Output settings (grey = optional)
- Active section: violet left border, lighter background
- Clicking section scrolls right panel to that section

### Section 1 — Mandatory requirements
- Tooltip: 'Vendors that fail any of these will be automatically rejected before scoring.'
- Each requirement row: ON/OFF toggle | name | edit icon | delete icon
- Toggle off: greys row but keeps it
- Clicking name: inline edit (no modal)
- 'Add a requirement' expands inline form (NO modal):
  - Input: 'Requirement name (e.g. ISO 27001 Certification)'
  - Input: 'What must the vendor provide?'
  - Input: 'What does a passing response look like?'
  - Save | Cancel inline

### Section 2 — Scoring criteria
- Tooltip: 'Weights must sum to 100%.'
- WEIGHT TOTAL BAR (full width, live updating):
  - Segmented bar, one segment per criterion, colour-coded
  - '[total]% of 100% allocated'
  - Amber if under 100%: 'X% unallocated — scoring will be incomplete'
  - Red if over 100%: '-X% over — reduce a criterion weight'
- Each criterion row expandable:
  - Name | weight input (1-100 with % suffix) | expand arrow
  - Expanded: RUBRIC EDITOR
    - 4 bands: 9-10 | 6-8 | 3-5 | 0-2
    - Each: text input with grey italic placeholder example
    - 9-10 placeholder: '3 or more named comparable projects with outcomes'
    - 6-8 placeholder: '1-2 projects with good outcomes'
    - 3-5 placeholder: 'Some relevant experience mentioned'
    - 0-2 placeholder: 'No relevant experience provided'
- Zero JSON visible. Zero technical field names.

### Section 3 — Approval thresholds
- Tier rows: contract value range | approver role | SLA hours
- Add tier button
- Plain English labels only

### Section 4 — Output settings
- Report format: PDF / Excel / Both (radio)
- Include audit trail: toggle (on by default)
- Rejection notice template: text area

### Save configuration button
- Violet, full width, sticky at bottom of right content area

**API:**
```
GET /api/v1/config/{agent_type}
PUT /api/v1/config/{agent_type}
```

### Architect rules
1. Override minimum 50 characters — UI encourages richer reasons
2. Override panel never navigates away
3. Rubric editor placeholder examples are as important as the editor
4. Configuration shows zero JSON, zero technical terms

---

## CHECKPOINT — After all pages built

```bash
cd frontend && npm run build
```

All TypeScript errors must be resolved. Build must succeed with zero errors.

Then verify routes exist:
- / — Page 0 Agent Home
- /dashboard — Department Head Dashboard
- /dashboard/cfo — CFO Dashboard
- /procurement/upload — New Evaluation
- /[runId]/confirm — RFP Confirmation
- /[runId]/progress — Live Progress
- /[runId]/results — Results (Compliance + Scoring tabs)
- /[runId]/report — Evaluation Report
- /[runId]/approve — Approval Screen
- /config — Agent Configuration

```bash
python checkpoint_runner.py SK07-CP03
```

Next.js build checkpoint must pass.

---

## SKILL 07b COMPLETE

All 11 pages built to design specification.
Design system applied consistently.
No AI jargon visible to users.
One primary action per screen on every page.
Evidence quotes styled as formal blockquotes on every page showing AI output.
Build succeeds with zero TypeScript errors.
