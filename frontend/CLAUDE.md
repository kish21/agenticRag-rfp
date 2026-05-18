# CLAUDE.md — Frontend Rules (Meridian AI Platform)

> These rules apply to all frontend work inside the `frontend/` directory. For backend rules, see the root `CLAUDE.md`.

---

## Always Do First

- **Invoke the `frontend-design` skill** before writing any frontend code, every session, no exceptions.
- **Invoke the `anti-ai-ui` skill** before finalizing any UI output, to audit for generic/AI-generated aesthetics.

---

## Responsive Design — MANDATORY ON EVERY PAGE

- **Every page** must import and use `useBreakpoint()` from `@/lib/hooks`
- **Breakpoints** (defined in `lib/hooks.ts`):
  - `mobile` → < 640px
  - `tablet` → 640px – 1023px
  - `desktop` → ≥ 1024px
- **Split-panel layouts** (login, signup, any two-column layout) must collapse to single-column on `mobile` and `tablet` — left panel hidden entirely
- **Never** use a fixed pixel width > 360px without a mobile fallback
- **Padding tokens** by breakpoint:
  - desktop: `48px 32px`
  - tablet: `32px 24px`
  - mobile: `24px 20px`
- **Compact logo header** replaces the left brand panel on mobile/tablet — use the inline logo pattern from login/signup

---

## Stack

- **Framework:** Next.js 16 App Router, React 19, Tailwind CSS v4
- **Dev server:** `cd frontend && npm run dev` → http://localhost:3000
- **Theme system:** CSS custom properties on `<html>` via `applyThemeVars()` in `frontend/lib/theme.ts`
- **Font:** Plus Jakarta Sans (loaded via `next/font/google`, weights 300–800, variable `--font-jakarta`). Mono: JetBrains Mono (`--font-mono-loaded`). Constants: `FONT`, `DISPLAY`, `MONO` from `@/lib/theme`
- **51 themes** selectable at runtime — never hardcode a hex colour that should theme

---

## Reference Images

- If a reference image is provided: match layout, spacing, typography, and color **exactly**. Do not improve or add to the design.
- If no reference image: design from scratch using the guardrails below.
- After writing UI code, describe what you expect to see. If a screenshot is taken, compare pixel-by-pixel: spacing, font weight, exact colors, border-radius, alignment. Fix mismatches.
- Do at least **2 comparison rounds**. Stop only when no visible differences remain or user says so.

---

## Brand Assets

- Check `frontend/public/` before designing. Use any logos, icons, or brand images found there.
- Platform name: **"Meridian AI Platform"** · Company: **"Meridian Financial Services"**
- Colors come from the active theme CSS vars — never invent brand colors outside the theme system.

---

## CSS Variable Rules — NEVER BREAK

- **Never write a raw hex colour** in any component (e.g. `"#1A2540"`). Always use `var(--color-*)`.
- **Never write a raw font string** (e.g. `"'IBM Plex Sans', sans-serif"`). Always use `FONT`, `DISPLAY`, or `MONO` from `@/lib/theme`, or `var(--font-sans)` / `var(--font-display)` / `var(--font-mono)`.
- Inline styles that bypass CSS vars cannot respond to theme changes — they will look broken on non-default themes.
- Exception: `AgentSwitcherRail` sidebar is intentionally hardcoded dark — do not change.

---

## Typography Rules

Matching top SaaS products (Linear, Stripe, Vercel):

- **One font family only: Plus Jakarta Sans.** No Inter, Georgia, Times, IBM Plex, or system-ui as primary.
- Headings → `DISPLAY` (`var(--font-display)`), `fontWeight: 800`, `letterSpacing: "-0.03em"`
- Subheadings / section labels → `FONT`, `fontWeight: 600–700`, `letterSpacing: "-0.01em"`
- Body text → `FONT`, `fontWeight: 400–500`, `lineHeight: 1.6`
- Data / timestamps / IDs → `MONO` (`var(--font-mono)`), `fontWeight: 400–500`
- Never use the same weight for a heading and its subtitle — minimum 200 weight difference

---

## Anti-Generic UI Rules (anti-ai-ui skill)

Run this checklist before delivering any UI. Fix every flagged item.

### Pre-Design Commitment

Before writing code, answer these:

1. What is ONE visual concept driving this design? (not just "clean and modern")
2. What single element will make someone stop and notice?
3. What is the layout doing that's unexpected or intentional?

### The 12 AI Tells — Audit Checklist

**Typography**

- [ ] Same font weight for heading and subtitle → minimum 200 weight difference
- [ ] Flat font scale → use dramatic contrast (hero should feel 3–5× body size)
- [ ] Uniform line-height → tight on headings (`1.0–1.1`), generous on body (`1.65–1.8`)
- [ ] No letter-spacing intent → tight tracking on headings (`-0.03em`), open on labels (`0.08em`+)

**Color**

- [ ] Raw hex or Tailwind palette name → always `var(--color-*)`, never `blue-600` etc.
- [ ] Equal-weight colors → 60/30/10 rule: dominant / accent / neutral
- [ ] Plain white background → use `var(--color-background)` with gradient via `var(--bg-gradient)`

**Depth & Shadow**

- [ ] Flat single shadow → layer 2–3 shadows using `var(--shadow-sm/md/lg)`
- [ ] All elements on same z-plane → base (`--color-background`) → elevated (`--color-surface`) → floating (`--shadow-lg` + border)

**Spacing & Layout**

- [ ] Uniform padding everywhere → use intentional spacing tokens: 4, 8, 12, 16, 20, 24, 32, 40, 48
- [ ] Everything centered → break the grid at least once; use asymmetry, offset, or overlap intentionally

**Motion & Interaction**

- [ ] `transition: all` anywhere → animate only `transform` and `opacity`, use `var(--transition)`
- [ ] Missing interactive states → every clickable element needs hover + focus-visible + active

**Visual Texture**

- [ ] Solid flat backgrounds → add depth via `var(--bg-gradient)`, subtle border, or layered surface

### Self-Review Before Delivering

- Could any other AI prompt have produced this? If yes, change something.
- Is there at least one "wait, that's interesting" design moment?
- Would a design-savvy person call this "template-y"? If yes, find and fix the offending element.

### The One Rule

> If the design is only describable as "clean and modern" — it's generic. Every design should be describable by what makes it _that specific thing_.

---

## Hard Rules

- Do **not** mix `border` shorthand with `borderTop` / `borderLeft` in React inline styles — use all four sides explicitly.
- Do **not** use `transition-all` or `transition: all` anywhere.
- Do **not** hardcode dark/light mode per-component. Use `isDark` from `useThemeContext()`.
- Do **not** load additional Google Fonts via `@import url(...)`. Plus Jakarta Sans and JetBrains Mono are already loaded globally via `next/font`.
- Do **not** add sections or content not in the reference image.
- Do **not** "improve" a reference design — match it exactly.
- Do **not** use `var(--color-accent)` directly as a background on large surfaces — it's an accent, not a base color.

---

## Status Colors — Always Semantic

| Use case            | Variable               |
| ------------------- | ---------------------- |
| Success / positive  | `var(--color-success)` |
| Warning / caution   | `var(--color-warning)` |
| Error / destructive | `var(--color-error)`   |
| Informational       | `var(--color-info)`    |

Never use raw green/red/yellow for status states.

---

## Page Delivery Checklist — MUST PASS BEFORE MARKING ANY PAGE DONE

Run this before committing every page. Every box must be ticked.

```
□ frontend-design skill invoked before writing code
□ anti-ai-ui audit passed (all 12 checklist items clean)
□ useBreakpoint imported and used from @/lib/hooks
□ mobile layout tested at 375px — no overflow, no cramped content
□ tablet layout tested at 768px — correct collapse behaviour
□ all <input> elements have an associated <label> with htmlFor
□ error states rendered with role="alert" and var(--color-error)
□ loading state shown for every async fetch (spinner or "Loading…")
□ auth guard present on protected pages (redirect to /login if no token)
□ no raw hex colours outside intentional hardcoded dark panels
□ no Tailwind palette names (blue-600, indigo-500, etc.)
□ no transition:all — only transform/opacity animated
□ python frontend_drift_detector.py exits 0 on this file
□ python frontend_checkpoint_runner.py run ROUTES passes for this page
```

---

## Checkpoint & Drift Detection

Two automated quality tools mirror the backend checkpoint system:

```bash
python frontend_drift_detector.py              # scan all files for violations
python frontend_checkpoint_runner.py status    # show all 40 checkpoint states
python frontend_checkpoint_runner.py run       # run all checks
python frontend_checkpoint_runner.py run AUTH  # run a single category
```

**Categories:** BUILD · ROUTES · THEME · RESPONSIVE · AUTH · FORMS · A11Y · DOMAIN · SECURITY · PERF

Run both after every page delivery and before every git commit.

---

## User Roles — Enterprise RFP Governance

Three roles exist in the JWT payload. The UI must respect them:

| Role | Display name | Access |
|---|---|---|
| `procurement_manager` | Procurement | Full workflow — upload, evaluate, approve, override |
| `executive` | Executive | Read-only — results, compare, reports only |
| `org_admin` | Admin | Org settings, user management, no evaluation workflow |

### Rules
- **TopBar** must show the current user's email and role badge
- **Executive** visiting `/procurement/upload` → redirect to `/` with an info message
- **Admin-only routes** (`/admin/*`) must check `role === "org_admin"` before rendering content
- JWT payload structure: `{ sub: email, role: "procurement_manager"|"executive"|"org_admin", org_id: "..." }`
- Parse role from token: `JSON.parse(atob(token.split('.')[1])).role`

### Phase — implement role guards after all core pages are built
