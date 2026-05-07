// ─────────────────────────────────────────────────────────────────────────────
// theme.ts — Single source of truth for all UI tokens
//
// COMPANY:      Change this block per customer deployment. Nothing else.
// AGENT_COLOUR: Fixed platform identity — never changes per customer.
// PALETTE:      Dark base colours used across all pages.
// TOKENS:       Component sizing, radii, shadows.
// ─────────────────────────────────────────────────────────────────────────────

// ── 1. Company branding — swap this per deployment ───────────────────────────

export const COMPANY = {
  name:          "Meridian Financial Services",
  platformName:  "Meridian AI Platform",
  shortName:     "Meridian AI",
  logoGradient:  { from: "#00D4AA", to: "#7C3AED" },
} as const;

// ── 2. Agent colour system — platform identity, never changes ─────────────────
// Teal = Procurement everywhere. Violet = HR everywhere.
// Never repurpose a colour for a different meaning on any agent's screens.

export const AGENT_COLOUR: Record<string, string> = {
  procurement: "#00D4AA",  // Teal
  hr:          "#8B5CF6",  // Violet
  legal:       "#F59E0B",  // Amber
  finance:     "#10B981",  // Emerald
  operations:  "#3B82F6",  // Blue
  support:     "#F97316",  // Orange
};

/** Safe lookup with fallback to procurement teal */
export function agentColour(type: string): string {
  return AGENT_COLOUR[type] ?? AGENT_COLOUR.procurement;
}

/** Keyword → agent type mapping (for colouring rows by department string) */
export function detectAgentType(department: string): string {
  const d = department.toLowerCase();
  if (d.includes("procurement") || d.includes("vendor") || d.includes("rfp")) return "procurement";
  if (d.includes("hr") || d.includes("people") || d.includes("culture") || d.includes("onboard")) return "hr";
  if (d.includes("legal") || d.includes("compliance") || d.includes("risk")) return "legal";
  if (d.includes("finance") || d.includes("budget") || d.includes("spend")) return "finance";
  if (d.includes("operation") || d.includes("ops") || d.includes("workflow")) return "operations";
  if (d.includes("support") || d.includes("customer")) return "support";
  return "procurement";
}

// ── 3. Typography — system fonts only, no external network requests ───────────

export const FONT  = "ui-sans-serif, system-ui, -apple-system, 'Segoe UI', sans-serif";
export const SERIF = "Georgia, 'Times New Roman', serif";
export const MONO  = "ui-monospace, 'Cascadia Code', 'Consolas', monospace";

// ── 4. Base palette — dark theme ──────────────────────────────────────────────

export const PALETTE = {
  bg: {
    base:     "#090C14",  // page background
    surface:  "#111520",  // card background
    elevated: "#161B2A",  // hover state
    overlay:  "#0D1018",  // rail, section cards
  },
  border: {
    dim:    "#181C28",  // subtle dividers
    mid:    "#1E2438",  // card borders
    bright: "#2A3040",  // hover borders
  },
  text: {
    primary:   "#F8FAFC",
    secondary: "#CBD5E1",
    muted:     "#6B7280",
    dim:       "#374151",
    ghost:     "#2D3344",
  },
  status: {
    running:  "#3B82F6",
    pending:  "#F59E0B",
    complete: "#10B981",
    blocked:  "#EF4444",
    warning:  "#F59E0B",
  },
} as const;

// ── 5. Component tokens — sizing, radii, shadows ──────────────────────────────

export const TOKENS = {
  radius: {
    card: 14,
    pill: 20,
    btn:  8,
    icon: 7,
  },
  rail: {
    collapsed: 48,
    expanded:  220,
  },
  topbar: {
    height: 60,
  },
  shadow: {
    card:  "0 2px 12px rgba(0,0,0,0.4), inset 0 1px 0 rgba(255,255,255,0.03)",
    hover: (colour: string) => `0 8px 32px ${colour}18, 0 2px 8px rgba(0,0,0,0.5)`,
    glow:  (colour: string) => `0 0 12px ${colour}25`,
  },
} as const;

// ── 5b. Light palette — cream/white variant for client deployments ────────────

export const PALETTE_LIGHT = {
  bg: {
    base:     "#fafaf9",  // cream page background
    surface:  "#ffffff",  // white card
    elevated: "#f5f4f1",  // hover
    overlay:  "#f0ede8",  // section backgrounds
  },
  border: {
    dim:    "#e8e4dc",
    mid:    "#ddd9d0",
    bright: "#b8b4aa",
  },
  text: {
    primary:   "#18160f",
    secondary: "#4a4540",
    muted:     "#7a7571",
    dim:       "#aaa69e",
    ghost:     "#c8c4bc",
  },
  status: {
    running:  "#3B82F6",
    pending:  "#F59E0B",
    complete: "#10B981",
    blocked:  "#EF4444",
    warning:  "#F59E0B",
  },
} as const;

// ── 6. Page background gradients ──────────────────────────────────────────────

export const BG_GRADIENT       = "radial-gradient(ellipse 90% 60% at 50% 0%, #111828 0%, #090C14 65%)";
export const BG_GRADIENT_LIGHT = "linear-gradient(160deg, #ede9e0 0%, #fafaf9 55%)";

// ── 7. Topbar backdrops ───────────────────────────────────────────────────────

export const TOPBAR_BG       = "rgba(9,12,20,0.88)";
export const TOPBAR_BG_LIGHT = "rgba(250,250,249,0.92)";
