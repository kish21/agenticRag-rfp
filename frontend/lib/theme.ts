// ─────────────────────────────────────────────────────────────────────────────
// theme.ts — Single source of truth for all UI tokens
//
// ARCHITECTURE: CSS custom properties on <html> drive all styling.
// applyThemeVars(id) sets vars → browser cascade updates every element instantly.
// Pages use CSS var strings in inline styles: style={{ color: 'var(--color-text-primary)' }}
//
// COMPANY:      Change this block per customer deployment.
// THEMES:       51 professionally-designed themes (Stripe, Linear, Vercel, etc.)
// DEFAULT:      'slate' — Stripe-style, financial institution look, no AI aesthetic.
// ─────────────────────────────────────────────────────────────────────────────

// ── 1. Company branding — swap this per deployment ───────────────────────────

export const COMPANY = {
  name:         "Meridian Financial Services",
  platformName: "Meridian AI Platform",
  shortName:    "Meridian AI",
  logoGradient: { from: "#6366F1", to: "#0A2540" },
} as const;

// ── 2. Agent colour system — platform identity, never changes ─────────────────

export const AGENT_COLOUR: Record<string, string> = {
  procurement: "#6366F1",  // Indigo
  hr:          "#8B5CF6",  // Violet
  legal:       "#F59E0B",  // Amber
  finance:     "#10B981",  // Emerald
  operations:  "#3B82F6",  // Blue
  support:     "#F97316",  // Orange
};

export function agentColour(type: string): string {
  return AGENT_COLOUR[type] ?? AGENT_COLOUR.procurement;
}

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

// ── 3. Typography — CSS variable references, resolved per active theme ────────

export const FONT    = "var(--font-sans)";
export const DISPLAY = "var(--font-display)";
export const SERIF   = "var(--font-display)";  // alias — headings use loaded Inter
export const MONO    = "var(--font-mono)";

// ── 4. Component tokens — sizing, radii, shadows ──────────────────────────────

export const TOKENS = {
  radius: {
    card: 8,
    pill: 20,
    btn:  6,
    icon: 6,
  },
  rail: {
    collapsed: 48,
    expanded:  220,
  },
  topbar: {
    height: 60,
  },
  shadow: {
    card:  "var(--shadow-md)",
    hover: () => "var(--shadow-lg)",
    glow:  () => `0 0 12px var(--color-accent)25`,
  },
} as const;

// ── 5. PALETTE shim — CSS variable strings (pages need zero changes) ──────────
// Both PALETTE and PALETTE_LIGHT return the same CSS var references.
// When applyThemeVars() updates :root vars, all inline styles using var() update automatically.

export const PALETTE = {
  bg: {
    base:     "var(--color-background)",
    surface:  "var(--color-surface)",
    elevated: "var(--color-surface-hover)",
    overlay:  "var(--color-background)",
  },
  border: {
    dim:    "var(--color-border)",
    mid:    "var(--color-border)",
    bright: "var(--color-border-strong)",
  },
  text: {
    primary:   "var(--color-text-primary)",
    secondary: "var(--color-text-secondary)",
    muted:     "var(--color-text-muted)",
    dim:       "var(--color-text-muted)",
    ghost:     "var(--color-border)",
  },
  status: {
    running:  "var(--color-info)",
    pending:  "var(--color-warning)",
    complete: "var(--color-success)",
    blocked:  "var(--color-error)",
    warning:  "var(--color-warning)",
  },
} as const;

export const PALETTE_LIGHT = PALETTE;

// Gradient / topbar — resolved via CSS vars set by applyThemeVars()
export const BG_GRADIENT       = "var(--bg-gradient)";
export const BG_GRADIENT_LIGHT = "var(--bg-gradient)";
export const TOPBAR_BG         = "var(--topbar-bg)";
export const TOPBAR_BG_LIGHT   = "var(--topbar-bg)";

// ── 6. Theme system — 51 professional themes ──────────────────────────────────

export type MotionPersonality = 'calm' | 'energetic' | 'precise';

export type ThemeId =
  | 'frost' | 'crimson' | 'cinema' | 'coral' | 'ocean'
  | 'slate' | 'forest' | 'parchment' | 'midnight' | 'studio'
  | 'obsidian' | 'raycast' | 'spotify' | 'discord' | 'shopify'
  | 'atlassian' | 'dropbox' | 'twitch' | 'framer' | 'webflow'
  | 'arc' | 'craft' | 'pitch' | 'jitter' | 'resend'
  | 'planetscale' | 'railway' | 'supabase' | 'neon' | 'turso'
  | 'clerk' | 'workos' | 'loops' | 'cal' | 'trigger'
  | 'openai' | 'anthropic' | 'perplexity' | 'midjourney' | 'runway'
  | 'elevenlabs' | 'loom' | 'linear' | 'superhuman' | 'dub'
  | 'fly' | 'basement' | 'heights' | 'cron' | 'whiteout'
  | 'procurement';

export interface ThemeTokens {
  id: ThemeId;
  name: string;
  description: string;
  isDark: boolean;
  motion: MotionPersonality;
  colors: {
    background: string; surface: string; surfaceHover: string;
    border: string; borderStrong: string;
    accent: string; accentHover: string; accentForeground: string;
    textPrimary: string; textSecondary: string; textMuted: string;
    success: string; warning: string; error: string; info: string;
  };
  font: { sans: string; mono: string };
  radius: string;
  shadow: { sm: string; md: string; lg: string };
}

function mkLight(
  id: ThemeId, name: string, description: string, motion: MotionPersonality,
  bg: string, surface: string, surfaceHover: string, border: string, borderStrong: string,
  accent: string, accentHover: string, accentFg: string,
  textPrimary: string, textSecondary: string, textMuted: string,
  success: string, warning: string, error: string, info: string,
  radius: string,
): ThemeTokens {
  return {
    id, name, description, isDark: false, motion,
    colors: { background: bg, surface, surfaceHover, border, borderStrong, accent, accentHover, accentForeground: accentFg, textPrimary, textSecondary, textMuted, success, warning, error, info },
    font: { sans: "'Inter', system-ui, sans-serif", mono: "'JetBrains Mono', monospace" },
    radius,
    shadow: { sm: '0 1px 3px rgba(0,0,0,0.07)', md: '0 4px 16px rgba(0,0,0,0.10)', lg: '0 16px 40px rgba(0,0,0,0.13)' },
  };
}

function mkDark(
  id: ThemeId, name: string, description: string, motion: MotionPersonality,
  bg: string, surface: string, surfaceHover: string, border: string, borderStrong: string,
  accent: string, accentHover: string, accentFg: string,
  textPrimary: string, textSecondary: string, textMuted: string,
  success: string, warning: string, error: string, info: string,
  radius: string,
): ThemeTokens {
  return {
    id, name, description, isDark: true, motion,
    colors: { background: bg, surface, surfaceHover, border, borderStrong, accent, accentHover, accentForeground: accentFg, textPrimary, textSecondary, textMuted, success, warning, error, info },
    font: { sans: "'Inter', system-ui, sans-serif", mono: "'JetBrains Mono', monospace" },
    radius,
    shadow: { sm: '0 1px 4px rgba(0,0,0,0.4)', md: '0 4px 20px rgba(0,0,0,0.55)', lg: '0 12px 48px rgba(0,0,0,0.7)' },
  };
}

export const THEMES: Record<ThemeId, ThemeTokens> = {
  // ── ORIGINAL 10 ────────────────────────────────────────────────────────────
  frost: {
    id: 'frost', name: 'Frost', description: 'Cool white & Blue — Apple',
    isDark: false, motion: 'calm',
    colors: { background:'#F5F5F7', surface:'#FFFFFF', surfaceHover:'#EBEBED', border:'#D2D2D7', borderStrong:'#BBBBBE', accent:'#0066CC', accentHover:'#0055AA', accentForeground:'#FFFFFF', textPrimary:'#1D1D1F', textSecondary:'#6E6E73', textMuted:'#AEAEB2', success:'#34C759', warning:'#FF9500', error:'#FF3B30', info:'#007AFF' },
    font: { sans:"'SF Pro Display', 'Inter', system-ui, sans-serif", mono:"'SF Mono', 'JetBrains Mono', monospace" },
    radius: '0.75rem', shadow: { sm:'0 1px 3px rgba(0,0,0,0.06)', md:'0 4px 16px rgba(0,0,0,0.08)', lg:'0 16px 40px rgba(0,0,0,0.12)' },
  },
  crimson: {
    id: 'crimson', name: 'Crimson', description: 'White & Red — YouTube',
    isDark: false, motion: 'energetic',
    colors: { background:'#FFFFFF', surface:'#F9F9F9', surfaceHover:'#F0F0F0', border:'#E5E5E5', borderStrong:'#CCCCCC', accent:'#FF0033', accentHover:'#CC0028', accentForeground:'#FFFFFF', textPrimary:'#212121', textSecondary:'#606060', textMuted:'#909090', success:'#1A8A1A', warning:'#F5A623', error:'#D93025', info:'#3EA6FF' },
    font: { sans:"'Inter', system-ui, sans-serif", mono:"'JetBrains Mono', monospace" },
    radius: '0.5rem', shadow: { sm:'0 1px 3px rgba(0,0,0,0.08)', md:'0 4px 12px rgba(0,0,0,0.10)', lg:'0 8px 32px rgba(0,0,0,0.12)' },
  },
  cinema: {
    id: 'cinema', name: 'Cinema', description: 'Black & Red — Netflix',
    isDark: true, motion: 'energetic',
    colors: { background:'#000000', surface:'#141414', surfaceHover:'#1F1F1F', border:'#2A2A2A', borderStrong:'#3D3D3D', accent:'#E50914', accentHover:'#B8070F', accentForeground:'#FFFFFF', textPrimary:'#FFFFFF', textSecondary:'#B3B3B3', textMuted:'#808080', success:'#46D369', warning:'#F5A623', error:'#E50914', info:'#3498DB' },
    font: { sans:"'Inter', system-ui, sans-serif", mono:"'JetBrains Mono', monospace" },
    radius: '0.375rem', shadow: { sm:'0 1px 4px rgba(0,0,0,0.5)', md:'0 4px 16px rgba(0,0,0,0.6)', lg:'0 12px 40px rgba(0,0,0,0.7)' },
  },
  coral: {
    id: 'coral', name: 'Coral', description: 'White & Coral — Airbnb',
    isDark: false, motion: 'energetic',
    colors: { background:'#FFFFFF', surface:'#F7F7F7', surfaceHover:'#EFEFEF', border:'#DDDDDD', borderStrong:'#C0C0C0', accent:'#FF385C', accentHover:'#D93A56', accentForeground:'#FFFFFF', textPrimary:'#484848', textSecondary:'#717171', textMuted:'#9B9B9B', success:'#00A699', warning:'#FC642D', error:'#C13515', info:'#428BCA' },
    font: { sans:"'Inter', system-ui, sans-serif", mono:"'JetBrains Mono', monospace" },
    radius: '0.75rem', shadow: { sm:'0 1px 4px rgba(0,0,0,0.06)', md:'0 6px 20px rgba(0,0,0,0.08)', lg:'0 16px 48px rgba(0,0,0,0.12)' },
  },
  ocean: {
    id: 'ocean', name: 'Ocean', description: 'Black & Blue — Vercel',
    isDark: true, motion: 'precise',
    colors: { background:'#000000', surface:'#111111', surfaceHover:'#1A1A1A', border:'#333333', borderStrong:'#444444', accent:'#0070F3', accentHover:'#0057C2', accentForeground:'#FFFFFF', textPrimary:'#FFFFFF', textSecondary:'#888888', textMuted:'#555555', success:'#50E3C2', warning:'#F5A623', error:'#FF0000', info:'#79B8FF' },
    font: { sans:"'Inter', system-ui, sans-serif", mono:"'JetBrains Mono', monospace" },
    radius: '0.375rem', shadow: { sm:'0 0 0 1px rgba(255,255,255,0.06)', md:'0 4px 20px rgba(0,0,0,0.8)', lg:'0 12px 48px rgba(0,0,0,0.9)' },
  },
  slate: {
    id: 'slate', name: 'Slate', description: 'Off-white & Navy — Stripe',
    isDark: false, motion: 'precise',
    colors: { background:'#F6F9FC', surface:'#FFFFFF', surfaceHover:'#EEF3F8', border:'#E0E8F0', borderStrong:'#C7D5E0', accent:'#0A2540', accentHover:'#061A2F', accentForeground:'#FFFFFF', textPrimary:'#0A2540', textSecondary:'#425466', textMuted:'#8898AA', success:'#09B383', warning:'#F5A623', error:'#CD3D64', info:'#5469D4' },
    font: { sans:"'Inter', system-ui, sans-serif", mono:"'JetBrains Mono', monospace" },
    radius: '0.5rem', shadow: { sm:'0 1px 3px rgba(10,37,64,0.08)', md:'0 4px 16px rgba(10,37,64,0.12)', lg:'0 16px 40px rgba(10,37,64,0.18)' },
  },
  forest: {
    id: 'forest', name: 'Forest', description: 'White & Green — GitHub',
    isDark: false, motion: 'precise',
    colors: { background:'#FFFFFF', surface:'#F6F8FA', surfaceHover:'#EAEEF2', border:'#D0D7DE', borderStrong:'#B1BAC4', accent:'#0FBF3E', accentHover:'#0A9932', accentForeground:'#FFFFFF', textPrimary:'#24292E', textSecondary:'#57606A', textMuted:'#8C959F', success:'#0FBF3E', warning:'#9A6700', error:'#CF222E', info:'#0969DA' },
    font: { sans:"'Inter', system-ui, sans-serif", mono:"'JetBrains Mono', monospace" },
    radius: '0.375rem', shadow: { sm:'0 1px 3px rgba(0,0,0,0.07)', md:'0 3px 12px rgba(0,0,0,0.10)', lg:'0 8px 28px rgba(0,0,0,0.12)' },
  },
  parchment: {
    id: 'parchment', name: 'Parchment', description: 'Warm white & Black — Notion',
    isDark: false, motion: 'calm',
    colors: { background:'#F7F6F3', surface:'#FFFFFF', surfaceHover:'#EEECEA', border:'#E9E8E5', borderStrong:'#D0CEC9', accent:'#000000', accentHover:'#333333', accentForeground:'#FFFFFF', textPrimary:'#37352F', textSecondary:'#6B6966', textMuted:'#9B9A97', success:'#0F7B55', warning:'#D9730D', error:'#E03E3E', info:'#0B6E99' },
    font: { sans:"'Inter', system-ui, sans-serif", mono:"'JetBrains Mono', monospace" },
    radius: '0.25rem', shadow: { sm:'0 1px 2px rgba(55,53,47,0.06)', md:'0 3px 12px rgba(55,53,47,0.08)', lg:'0 8px 30px rgba(55,53,47,0.10)' },
  },
  midnight: {
    id: 'midnight', name: 'Midnight', description: 'Near-black & Soft blue — Linear',
    isDark: true, motion: 'precise',
    colors: { background:'#0F0F1A', surface:'#1B1B2E', surfaceHover:'#252540', border:'#2D2D3E', borderStrong:'#3D3D55', accent:'#5E6AD2', accentHover:'#4A55C2', accentForeground:'#FFFFFF', textPrimary:'#FFFFFF', textSecondary:'#8A8A9A', textMuted:'#5A5A6A', success:'#4CAF88', warning:'#E8A045', error:'#E05C5C', info:'#5E6AD2' },
    font: { sans:"'Inter', system-ui, sans-serif", mono:"'JetBrains Mono', monospace" },
    radius: '0.5rem', shadow: { sm:'0 1px 4px rgba(0,0,0,0.4)', md:'0 4px 20px rgba(0,0,0,0.5)', lg:'0 12px 48px rgba(0,0,0,0.6)' },
  },
  studio: {
    id: 'studio', name: 'Studio', description: 'White & Mint — Figma',
    isDark: false, motion: 'energetic',
    colors: { background:'#FFFFFF', surface:'#F5F5F5', surfaceHover:'#EBEBEB', border:'#E0E0E0', borderStrong:'#C4C4C4', accent:'#0ACF83', accentHover:'#08A868', accentForeground:'#FFFFFF', textPrimary:'#1E1E1E', textSecondary:'#5C5C5C', textMuted:'#8C8C8C', success:'#0ACF83', warning:'#F24E1E', error:'#FF4D4D', info:'#1ABCFE' },
    font: { sans:"'Inter', system-ui, sans-serif", mono:"'JetBrains Mono', monospace" },
    radius: '0.5rem', shadow: { sm:'0 1px 3px rgba(0,0,0,0.06)', md:'0 4px 14px rgba(0,0,0,0.09)', lg:'0 10px 36px rgba(0,0,0,0.12)' },
  },

  // ── NEW 40 ──────────────────────────────────────────────────────────────────
  obsidian:    mkDark('obsidian','Obsidian','Deep black & Amber — Raycast dark','energetic','#070A0B','#151515','#1E1E1E','#2A2A2A','#3A3A3A','#FF6363','#E04F4F','#FFFFFF','#F0F0F0','#A0A0A0','#606060','#22D3A5','#FF9F0A','#FF6363','#60A5FA','0.5rem'),
  raycast:     mkDark('raycast','Raycast','Dark charcoal & Hot coral — Raycast','energetic','#131214','#1E1C1F','#2A2830','#36343C','#484550','#FF5F57','#E04A44','#FFFFFF','#ECECF0','#9090A0','#606070','#30D158','#FFD60A','#FF5F57','#64D2FF','0.625rem'),
  spotify:     mkDark('spotify','Spotify','Rich black & Neon green — Spotify','energetic','#191414','#282828','#3E3E3E','#535353','#767676','#1DB954','#169C42','#000000','#FFFFFF','#B3B3B3','#727272','#1DB954','#FFC864','#F15E6C','#3D91F4','0.5rem'),
  discord:     mkDark('discord','Discord','Greyple & Blurple — Discord','calm','#36393F','#2F3136','#40444B','#202225','#4F545C','#5865F2','#4752C4','#FFFFFF','#DCDDDE','#8E9297','#72767D','#57F287','#FEE75C','#ED4245','#5865F2','0.5rem'),
  shopify:     mkLight('shopify','Shopify','White & Deep green — Shopify','calm','#FFFFFF','#F6F6F6','#EDEDED','#E1E3E5','#C9CCCF','#008060','#006E52','#FFFFFF','#202223','#6D7175','#8C9196','#008060','#FFC453','#D72C0D','#0091FF','0.5rem'),
  atlassian:   mkLight('atlassian','Atlassian','Cloud white & Cobalt — Atlassian','calm','#FAFBFC','#FFFFFF','#F4F5F7','#DFE1E6','#C1C7D0','#0052CC','#0747A6','#FFFFFF','#172B4D','#6B778C','#97A0AF','#36B37E','#FF8B00','#DE350B','#0052CC','0.25rem'),
  dropbox:     mkLight('dropbox','Dropbox','Clean white & Electric blue — Dropbox','precise','#FFFFFF','#F7F7F7','#EEEEEE','#E2E2E2','#C8C8C8','#0061FF','#004ECC','#FFFFFF','#1F1F1F','#637282','#9BAAB8','#26B825','#FAA11B','#E01E30','#0061FF','0.5rem'),
  twitch:      mkDark('twitch','Twitch','Dark & Vivid purple — Twitch','energetic','#0E0E10','#18181B','#1F1F23','#2C2C30','#3D3D42','#9146FF','#772CE8','#FFFFFF','#EFEFF1','#ADADB8','#6C6C7A','#00DB84','#FAA61A','#EB0400','#9146FF','0.5rem'),
  framer:      mkLight('framer','Framer','White & Vivid teal — Framer','energetic','#FFFFFF','#F5FDFB','#E6FAF5','#CCEBE2','#99D6C5','#0EA5E9','#0284C7','#FFFFFF','#0C1C1A','#2C6B5E','#5A9E8F','#00B37D','#F59E0B','#EF4444','#0EA5E9','0.75rem'),
  webflow:     mkLight('webflow','Webflow','White & Blueprint blue — Webflow','energetic','#FFFFFF','#F3F4F6','#E5E7EB','#D1D5DB','#9CA3AF','#4353FF','#2B3EE8','#FFFFFF','#111827','#374151','#6B7280','#10B981','#F59E0B','#EF4444','#4353FF','0.5rem'),
  arc:         mkLight('arc','Arc','Soft cream & Sky blue — Arc Browser','calm','#F8F7F5','#FFFFFF','#F0EEE9','#E2DED7','#C8C3BB','#0080FF','#0068D6','#FFFFFF','#1A1915','#5A5750','#9A9692','#34C759','#FF9F0A','#FF453A','#0080FF','1rem'),
  craft:       mkLight('craft','Craft','Warm cream & Rich gold — Craft','calm','#FFFBF5','#FFFFFF','#F7F3EB','#EDE6D8','#D4C8B0','#C2922A','#A87820','#FFFFFF','#1A130A','#6B5540','#9E8870','#2D9653','#C2922A','#D9534F','#3B82F6','0.625rem'),
  pitch:       mkDark('pitch','Pitch','Deep navy & Electric indigo — Pitch','precise','#0F1419','#161D27','#1E2733','#2A3340','#374050','#5B7FFF','#4268F5','#FFFFFF','#E2E8F0','#8A9AB0','#526070','#4ADE80','#FB923C','#F87171','#5B7FFF','0.5rem'),
  jitter:      mkLight('jitter','Jitter','White & Vibrant orange — Jitter','energetic','#FFFFFF','#FFF8F3','#FFF0E6','#FFD9C0','#FFB899','#FF6B2B','#E55A1C','#FFFFFF','#1A0A00','#7C3E1E','#B87448','#22C55E','#FF6B2B','#EF4444','#3B82F6','0.75rem'),
  resend:      mkLight('resend','Resend','Off-white & Forest teal — Resend','calm','#F9FAFB','#FFFFFF','#F3F4F6','#E5E7EB','#D1D5DB','#000000','#333333','#FFFFFF','#111827','#374151','#9CA3AF','#10B981','#F59E0B','#EF4444','#3B82F6','0.375rem'),
  planetscale: mkDark('planetscale','PlanetScale','Jet black & Cyan glow — PlanetScale','precise','#000000','#0A0A0A','#141414','#1E1E1E','#2A2A2A','#00D9FF','#00AACC','#000000','#FFFFFF','#A0A0A0','#606060','#00D9FF','#FFB347','#FF4D4D','#00D9FF','0.375rem'),
  railway:     mkLight('railway','Railway','White & Deep ocean navy — Railway','precise','#FFFFFF','#F1F5F9','#E2E8F0','#CBD5E1','#94A3B8','#0B3D91','#082E6E','#FFFFFF','#0F172A','#334155','#64748B','#16A34A','#D97706','#DC2626','#0B3D91','0.5rem'),
  supabase:    mkLight('supabase','Supabase','White & Jungle green — Supabase','precise','#F8FAF9','#FFFFFF','#EBF5F0','#D1E7DC','#A8D0BC','#3ECF8E','#2EAF74','#FFFFFF','#1A3D30','#2E6B52','#5A9E80','#3ECF8E','#F59E0B','#EF4444','#3B82F6','0.5rem'),
  neon:        mkDark('neon','Neon','Jet black & Vivid lime — Neon DB','energetic','#000000','#0D0D0D','#1A1A1A','#262626','#333333','#00D084','#00A86B','#000000','#E0E0E0','#909090','#555555','#00D084','#FFD700','#FF4444','#00D084','0.375rem'),
  turso:       mkLight('turso','Turso','Cool white & Deep indigo — Turso','precise','#F8F9FF','#FFFFFF','#EEF0FF','#D9DDFF','#B8BFFF','#4F46E5','#3730A3','#FFFFFF','#1E1B4B','#3730A3','#6366F1','#16A34A','#D97706','#DC2626','#4F46E5','0.5rem'),
  clerk:       mkLight('clerk','Clerk','White & Deep violet — Clerk','precise','#FAFAFA','#FFFFFF','#F4F1FF','#E4DAFF','#C9B8FF','#6B21A8','#521A82','#FFFFFF','#1F1F2E','#4A4A6A','#8080A0','#16A34A','#D97706','#DC2626','#6B21A8','0.5rem'),
  workos:      mkLight('workos','WorkOS','White & Sunset orange — WorkOS','energetic','#FFFAF7','#FFFFFF','#FFF3E8','#FFD9B5','#FFB870','#EA580C','#C2470A','#FFFFFF','#1C0A00','#7C3A10','#B87040','#16A34A','#EA580C','#DC2626','#3B82F6','0.5rem'),
  loops:       mkLight('loops','Loops','White & Hot rose — Loops','energetic','#FFF5F8','#FFFFFF','#FFE8EF','#FFB3CA','#FF80A8','#EC4899','#D03689','#FFFFFF','#2D0018','#8B2252','#C05080','#16A34A','#D97706','#EC4899','#3B82F6','0.625rem'),
  cal:         mkDark('cal','Cal.com','Pure black & White — Cal.com','calm','#111111','#1A1A1A','#222222','#2E2E2E','#3D3D3D','#FFFFFF','#E0E0E0','#000000','#FFFFFF','#A0A0A0','#606060','#4ADE80','#FB923C','#F87171','#60A5FA','0.5rem'),
  trigger:     mkLight('trigger','Trigger.dev','Off-white & Warm amber — Trigger.dev','energetic','#FFFDF5','#FFFFFF','#FFFAEB','#FDE68A','#FBBF24','#D97706','#B45309','#FFFFFF','#1C1407','#786028','#A88040','#16A34A','#D97706','#DC2626','#3B82F6','0.375rem'),
  openai:      mkLight('openai','OpenAI','White & Black — OpenAI','calm','#FFFFFF','#F9F9F9','#F3F3F3','#E6E6E6','#D0D0D0','#10A37F','#0D8A6C','#FFFFFF','#0D0D0D','#353740','#6E6E80','#10A37F','#F5A623','#EF4444','#10A37F','0.5rem'),
  anthropic:   mkLight('anthropic','Anthropic','Warm cream & Terracotta — Anthropic','calm','#FBF8F3','#FFFFFF','#F5EDDF','#E8D9C0','#D4BFA0','#C96442','#A84F30','#FFFFFF','#1A1008','#5C3820','#9C7050','#2D9653','#D97706','#C96442','#3B82F6','0.5rem'),
  perplexity:  mkLight('perplexity','Perplexity','White & Teal — Perplexity AI','calm','#FFFFFF','#F0FDFA','#CCFBF1','#99F6E4','#5EEAD4','#0D9488','#0F766E','#FFFFFF','#042F2E','#115E59','#0F766E','#16A34A','#D97706','#DC2626','#0D9488','0.5rem'),
  midjourney:  mkDark('midjourney','Midjourney','Deep indigo & Sky blue — Midjourney','calm','#060520','#0F0D2A','#181540','#222055','#2E2B6A','#60A5FA','#3B82F6','#FFFFFF','#CAD5E2','#7890B0','#4A6080','#4ADE80','#FB923C','#F87171','#60A5FA','0.5rem'),
  runway:      mkLight('runway','Runway','White & Deep crimson — Runway ML','precise','#FEFEFE','#FFFFFF','#FEF2F2','#FECACA','#F87171','#DC2626','#B91C1C','#FFFFFF','#1F0505','#7F1D1D','#B45454','#16A34A','#D97706','#DC2626','#3B82F6','0.5rem'),
  elevenlabs:  mkLight('elevenlabs','ElevenLabs','White & Royal blue — ElevenLabs','energetic','#FFFFFF','#F8FAFF','#EFF4FF','#DBEAFE','#BFDBFE','#2563EB','#1D4ED8','#FFFFFF','#0F172A','#1E3A5F','#4A7AB5','#16A34A','#D97706','#DC2626','#2563EB','0.5rem'),
  loom:        mkLight('loom','Loom','White & Soft violet — Loom','energetic','#FAFAFA','#FFFFFF','#F5F3FF','#EDE9FE','#DDD6FE','#7C3AED','#6D28D9','#FFFFFF','#1E1B28','#4C3D6E','#7A6EA0','#16A34A','#D97706','#DC2626','#7C3AED','0.5rem'),
  linear:      mkLight('linear','Linear','Ice white & Indigo — Linear App','precise','#FAFAFA','#FFFFFF','#F0F1FF','#E0E2FF','#C0C4FF','#5E6AD2','#4A56C2','#FFFFFF','#1A1A2E','#4A4A6E','#8080A8','#16A34A','#D97706','#DC2626','#5E6AD2','0.5rem'),
  superhuman:  mkLight('superhuman','Superhuman','White & Cobalt — Superhuman','precise','#FFFFFF','#F8FAFC','#F0F4F8','#DDE6F0','#B8CCE0','#0053A0','#003D7A','#FFFFFF','#0A1929','#2B4A6F','#6080A8','#16A34A','#D97706','#DC2626','#0053A0','0.5rem'),
  dub:         mkLight('dub','Dub.co','White & Rich violet — Dub.co','energetic','#FDFCFF','#FFFFFF','#F5EEFF','#E8D8FF','#D0AAFF','#8B5CF6','#7C3AED','#FFFFFF','#1A0040','#5B2B9E','#9060C8','#16A34A','#D97706','#DC2626','#8B5CF6','0.5rem'),
  fly:         mkLight('fly','Fly.io','White & Vivid pink — Fly.io','energetic','#FFF0F5','#FFFFFF','#FFE0ED','#FFB3CF','#FF80AF','#E11D74','#C0185F','#FFFFFF','#2D0018','#8B1048','#C04080','#16A34A','#D97706','#E11D74','#3B82F6','0.5rem'),
  basement:    mkDark('basement','Basement','Pitch black & Neon green — Basement','energetic','#0A0A0A','#121212','#1A1A1A','#242424','#303030','#00FF7F','#00CC66','#000000','#F0F0F0','#A0A0A0','#606060','#00FF7F','#FFD700','#FF4444','#00CCFF','0.375rem'),
  heights:     mkLight('heights','Heights','Pale lavender & Deep violet — Heights','calm','#F8F5FF','#FFFFFF','#F0E8FF','#DDD0FF','#C0A8FF','#7C3AED','#6025CB','#FFFFFF','#1A0A40','#4A2080','#8050B8','#16A34A','#D97706','#DC2626','#7C3AED','0.75rem'),
  cron:        mkLight('cron','Cron','White & Emerald — Cron / Notion Calendar','calm','#F8FFFE','#FFFFFF','#ECFDF5','#D1FAE5','#A7F3D0','#059669','#047857','#FFFFFF','#022C22','#065F46','#10B981','#059669','#D97706','#DC2626','#0D9488','0.5rem'),
  whiteout:    mkLight('whiteout','Whiteout','Pure white & Graphite — Minimal','calm','#FFFFFF','#FAFAFA','#F4F4F4','#E8E8E8','#D0D0D0','#111111','#333333','#FFFFFF','#111111','#555555','#999999','#22C55E','#F59E0B','#EF4444','#3B82F6','0.25rem'),

  // ── ENTERPRISE ──────────────────────────────────────────────────────────────
  procurement: mkDark('procurement','Procurement','Deep navy & Indigo — Enterprise CFO/CEO','precise','#0F172A','#1A2540','#1E2D4E','#253558','#2E4070','#6366F1','#4F52E8','#FFFFFF','#E8EEFF','#94A3C8','#576280','#22C55E','#F59E0B','#EF4444','#818CF8','0.375rem'),
};

export const DEFAULT_THEME: ThemeId = 'slate';

// Theme groupings for the picker UI
export const THEME_GROUPS: { label: string; ids: ThemeId[] }[] = [
  { label: 'Enterprise & Financial', ids: ['procurement','slate','ocean','midnight','pitch','superhuman','atlassian','dropbox','railway','linear'] },
  { label: 'Light & Clean',          ids: ['frost','parchment','whiteout','forest','studio','supabase','openai','anthropic','perplexity','cron'] },
  { label: 'Dark',                   ids: ['cinema','obsidian','raycast','spotify','discord','twitch','cal','basement','neon','midjourney'] },
  { label: 'Colourful',              ids: ['coral','crimson','framer','jitter','loops','fly','workos','runway','dub','arc','craft'] },
  { label: 'Developer Tools',        ids: ['resend','planetscale','turso','clerk','trigger','elevenlabs','loom','heights','webflow'] },
];

// ── 7. Apply theme — sets CSS custom properties on <html> ─────────────────────

export function applyThemeVars(id: ThemeId): void {
  if (typeof document === 'undefined') return;
  const t = THEMES[id];
  if (!t) return;
  const root = document.documentElement;
  root.setAttribute('data-theme', id);
  root.setAttribute('data-motion', t.motion);

  const c = t.colors;
  root.style.setProperty('--color-background',        c.background);
  root.style.setProperty('--color-surface',           c.surface);
  root.style.setProperty('--color-surface-hover',     c.surfaceHover);
  root.style.setProperty('--color-border',            c.border);
  root.style.setProperty('--color-border-strong',     c.borderStrong);
  root.style.setProperty('--color-accent',            c.accent);
  root.style.setProperty('--color-accent-hover',      c.accentHover);
  root.style.setProperty('--color-accent-foreground', c.accentForeground);
  root.style.setProperty('--color-text-primary',      c.textPrimary);
  root.style.setProperty('--color-text-secondary',    c.textSecondary);
  root.style.setProperty('--color-text-muted',        c.textMuted);
  root.style.setProperty('--color-success',           c.success);
  root.style.setProperty('--color-warning',           c.warning);
  root.style.setProperty('--color-error',             c.error);
  root.style.setProperty('--color-info',              c.info);
  root.style.setProperty('--font-sans',    "var(--font-jakarta), 'Plus Jakarta Sans', system-ui, -apple-system, sans-serif");
  root.style.setProperty('--font-display', "var(--font-jakarta), 'Plus Jakarta Sans', system-ui, -apple-system, sans-serif");
  root.style.setProperty('--font-mono',     t.font.mono);
  root.style.setProperty('--radius',                  t.radius);
  root.style.setProperty('--shadow-sm',               t.shadow.sm);
  root.style.setProperty('--shadow-md',               t.shadow.md);
  root.style.setProperty('--shadow-lg',               t.shadow.lg);

  const dur = t.motion === 'precise' ? '150ms' : t.motion === 'calm' ? '280ms' : '200ms';
  root.style.setProperty('--transition', `${dur} ease-out`);

  if (t.isDark) {
    root.style.setProperty('--bg-gradient', `radial-gradient(ellipse 90% 60% at 50% 0%, ${c.surface} 0%, ${c.background} 65%)`);
    root.style.setProperty('--topbar-bg',   c.background + 'E0');
    root.style.setProperty('--topbar-border', 'rgba(255,255,255,0.08)');
  } else {
    root.style.setProperty('--bg-gradient', `linear-gradient(160deg, ${c.surfaceHover} 0%, ${c.background} 55%)`);
    root.style.setProperty('--topbar-bg',   c.background + 'EC');
    root.style.setProperty('--topbar-border', 'rgba(0,0,0,0.07)');
  }

  // Also set directly on body so all CSS cascade consumers see it immediately
  document.body.style.background = c.background;
  document.body.style.color = c.textPrimary;
}
