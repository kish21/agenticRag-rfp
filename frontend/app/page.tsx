"use client";

import { useState, useEffect, useRef } from "react";
import { useRouter } from "next/navigation";
import { AGENT_COLOUR, COMPANY, DISPLAY, FONT, MONO, SERIF, TOKENS } from "@/lib/theme";
import { useThemeContext } from "@/components/ThemeProvider";
import { ThemePicker } from "@/components/ThemePicker";

type AgentType = keyof typeof AGENT_COLOUR;

interface EvalRun {
  run_id: string; rfp_title: string; department: string;
  status: "running" | "pending_approval" | "complete" | "blocked" | "interrupted";
  vendor_count: number; shortlisted_count: number;
  started_at: string;
}

interface StatusItem {
  label:     string;
  count:     number;
  dotColour: string;
  kind:      "amber" | "teal" | "red" | "grey";
}

interface AgentDef {
  id:           string;
  type:         AgentType;
  name:         string;
  department:   string;
  blurb:        string;
  href:         string;
  lastActivity: string;
  activity24h:  number[];
  suggestions:  string[];
  statuses:     StatusItem[];
}

const MOCK_AGENTS: AgentDef[] = [
  {
    id: "proc-1", type: "procurement",
    name: "IT Procurement", department: COMPANY.name,
    blurb: "contracts · vendors · RFPs",
    href: "/procurement/upload",
    lastActivity: "Comparing 4 vendor responses for Okta renewal",
    activity24h: [3, 5, 4, 7, 5, 8, 6, 9, 5, 7],
    suggestions: [
      "Compare the 4 Okta renewal proposals",
      "What's missing from Brightline's MSA?",
      "Draft evaluation summary for CISO",
    ],
    statuses: [
      { label: "evaluations running",    count: 2, dotColour: "var(--color-warning)", kind: "amber" },
      { label: "result ready to review", count: 1, dotColour: "var(--color-accent)",  kind: "teal"  },
      { label: "awaiting your approval", count: 0, dotColour: "var(--color-border)",  kind: "grey"  },
    ],
  },
  {
    id: "hr-1", type: "hr",
    name: "People & Culture", department: COMPANY.name,
    blurb: "people · policies · onboarding",
    href: "/hr",
    lastActivity: "Drafted update to remote-work policy v3.2",
    activity24h: [5, 8, 6, 9, 7, 5, 8, 6, 7, 9],
    suggestions: [
      "Review remote-work policy v3.2 changes",
      "Summarize onboarding Q&A patterns this week",
      "Flag compliance gaps in new policy draft",
    ],
    statuses: [
      { label: "flagged for review",              count: 1, dotColour: "var(--color-error)",   kind: "red"   },
      { label: "policy reviews in progress",      count: 3, dotColour: "var(--color-warning)", kind: "amber" },
      { label: "onboarding Q&As answered today",  count: 5, dotColour: "#8B5CF6",              kind: "teal"  },
    ],
  },
  {
    id: "legal-1", type: "legal",
    name: "Legal & Compliance", department: COMPANY.name,
    blurb: "contracts · compliance · risk",
    href: "/legal",
    lastActivity: "Flagged 2 clauses in MSA with Brightline Inc.",
    activity24h: [4, 6, 7, 4, 6, 8, 5, 7, 6, 5],
    suggestions: [
      "Identify risk clauses in Brightline MSA",
      "Run compliance check on new vendor contract",
      "Summarize 4 contracts currently under review",
    ],
    statuses: [
      { label: "contracts under review",  count: 4,  dotColour: "var(--color-warning)", kind: "amber" },
      { label: "compliance check passed", count: 12, dotColour: "var(--color-success)", kind: "teal"  },
      { label: "awaiting your approval",  count: 0,  dotColour: "var(--color-border)",  kind: "grey"  },
    ],
  },
];

// ── Icons ─────────────────────────────────────────────────────────────────────

function IconDocumentStack({ colour }: { colour: string }) {
  return (
    <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
      <rect x="2" y="3" width="12" height="2" rx="1" fill={colour} opacity="0.35" />
      <rect x="1" y="6" width="14" height="2" rx="1" fill={colour} opacity="0.55" />
      <rect x="1" y="9" width="18" height="9" rx="2" fill={colour} opacity="0.9" />
      <path d="M4 13h12M4 15.5h7" stroke="var(--color-background)" strokeWidth="1.3" strokeLinecap="round" />
    </svg>
  );
}
function IconPeople({ colour }: { colour: string }) {
  return (
    <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
      <circle cx="7.5" cy="6.5" r="3" fill={colour} opacity="0.9" />
      <circle cx="15" cy="7.5" r="2.2" fill={colour} opacity="0.5" />
      <path d="M0.5 18c0-3.866 3.134-7 7-7s7 3.134 7 7" fill={colour} opacity="0.85" />
      <path d="M15 12c2.21 0 4 1.79 4 4" stroke={colour} strokeWidth="1.4" strokeLinecap="round" opacity="0.5" />
    </svg>
  );
}
function IconScales({ colour }: { colour: string }) {
  return (
    <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
      <line x1="10" y1="2" x2="10" y2="18" stroke={colour} strokeWidth="1.4" strokeLinecap="round" />
      <line x1="4" y1="18" x2="16" y2="18" stroke={colour} strokeWidth="1.4" strokeLinecap="round" />
      <line x1="4.5" y1="7" x2="15.5" y2="7" stroke={colour} strokeWidth="1.1" strokeLinecap="round" opacity="0.5" />
      <path d="M4.5 7L2.5 12h4l-2-5Z" fill={colour} opacity="0.75" />
      <path d="M15.5 7l-2 5h4l-2-5Z" fill={colour} opacity="0.5" />
    </svg>
  );
}
function IconSettings() {
  return (
    <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
      <circle cx="8" cy="8" r="2" stroke="currentColor" strokeWidth="1.2" />
      <path d="M8 1v1.5M8 13.5V15M1 8h1.5M13.5 8H15M2.9 2.9l1.06 1.06M12.04 12.04l1.06 1.06M2.9 13.1l1.06-1.06M12.04 3.96l1.06-1.06" stroke="currentColor" strokeWidth="1.1" strokeLinecap="round" />
    </svg>
  );
}
function IconSend() {
  return (
    <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
      <path d="M12 7H2M8 3l4 4-4 4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

const ICONS: Record<AgentType, (c: string) => React.ReactNode> = {
  procurement: (c) => <IconDocumentStack colour={c} />,
  hr:          (c) => <IconPeople colour={c} />,
  legal:       (c) => <IconScales colour={c} />,
  finance:     (c) => <IconDocumentStack colour={c} />,
  operations:  (c) => <IconDocumentStack colour={c} />,
  support:     (c) => <IconPeople colour={c} />,
};

// ── Sparkline ─────────────────────────────────────────────────────────────────

function Sparkline({ values, colour, height = 28 }: { values: number[]; colour: string; height?: number }) {
  const max = Math.max(...values, 1);
  return (
    <div style={{ display: "flex", alignItems: "flex-end", gap: 2, height }}>
      {values.map((v, i) => (
        <div key={i} style={{
          width: 4,
          height: `${Math.max(18, (v / max) * 100)}%`,
          backgroundColor: colour,
          borderRadius: 2,
          opacity: 0.25 + (i / (values.length - 1)) * 0.75,
          transition: "height 400ms ease",
        }} />
      ))}
    </div>
  );
}

// ── Sidebar rail — always dark (intentional: sidebar contrast) ────────────────

function AgentSwitcherRail({ agents, activeId, onSelect, userName }: {
  agents:    AgentDef[];
  activeId:  string | null;
  onSelect:  (a: AgentDef) => void;
  userName?: string;
}) {
  const [expanded, setExpanded]   = useState(false);
  const [hoveredId, setHoveredId] = useState<string | null>(null);

  return (
    <div
      style={{
        position: "fixed", left: 0, top: 0, bottom: 0,
        width: expanded ? 220 : 48,
        backgroundColor: "#080A10",
        borderRight: "1px solid #181C28",
        transition: "width 180ms cubic-bezier(0.4,0,0.2,1)",
        display: "flex", flexDirection: "column", alignItems: "center",
        zIndex: 50, overflow: "hidden",
      }}
      onMouseEnter={() => setExpanded(true)}
      onMouseLeave={() => { setExpanded(false); setHoveredId(null); }}
    >
      <div style={{
        height: 60, width: "100%", flexShrink: 0,
        display: "flex", alignItems: "center",
        padding: expanded ? "0 16px" : "0",
        justifyContent: expanded ? "flex-start" : "center",
        borderBottom: "1px solid #181C28", gap: 12,
      }}>
        <div style={{ width: 22, height: 22, borderRadius: 5, background: "linear-gradient(135deg, var(--color-accent), var(--color-info))", display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0 }}>
          <svg width="12" height="12" viewBox="0 0 12 12" fill="none">
            <circle cx="6" cy="6" r="2.2" fill="white" opacity="0.95" />
            <circle cx="6" cy="6" r="5" stroke="white" strokeWidth="0.85" opacity="0.35" />
          </svg>
        </div>
        {expanded && (
          <span style={{ fontSize: 12, fontWeight: 700, color: "#CBD5E1", fontFamily: FONT, letterSpacing: "0.08em", textTransform: "uppercase", whiteSpace: "nowrap" }}>
            {COMPANY.shortName}
          </span>
        )}
      </div>

      <div style={{ flex: 1, width: "100%", paddingTop: 6, overflowY: "auto" }}>
        {agents.map((agent) => {
          const colour   = AGENT_COLOUR[agent.type];
          const isActive = agent.id === activeId;
          const isHov    = hoveredId === agent.id;
          const hasAttn  = agent.statuses.some(s => s.count > 0);
          const lit      = isActive || isHov;
          return (
            <div
              key={agent.id}
              onClick={() => onSelect(agent)}
              onMouseEnter={() => setHoveredId(agent.id)}
              onMouseLeave={() => setHoveredId(null)}
              style={{
                position: "relative", height: 44, width: "100%",
                display: "flex", alignItems: "center",
                padding: expanded ? "0 14px" : "0",
                justifyContent: expanded ? "flex-start" : "center",
                cursor: "pointer", gap: 12,
                borderLeft: isActive ? `2px solid ${colour}` : "2px solid transparent",
                backgroundColor: isHov && !isActive ? "#111520" : "transparent",
                transition: "background-color 120ms",
              }}
            >
              <div style={{
                width: 30, height: 30, borderRadius: 7, flexShrink: 0,
                display: "flex", alignItems: "center", justifyContent: "center",
                backgroundColor: lit ? `${colour}18` : "transparent",
                border: lit ? `1px solid ${colour}30` : "1px solid transparent",
                transition: "all 140ms",
              }}>
                {ICONS[agent.type](lit ? colour : "#4B5563")}
              </div>
              {expanded && (
                <span style={{ fontSize: 12.5, fontFamily: FONT, fontWeight: isActive ? 600 : 400, color: isActive ? colour : isHov ? "#E2E8F0" : "#6B7280", whiteSpace: "nowrap", transition: "color 120ms" }}>
                  {agent.name}
                </span>
              )}
              {hasAttn && (
                <span style={{ position: "absolute", top: 9, right: expanded ? 12 : 8, width: 5, height: 5, borderRadius: "50%", backgroundColor: "#F59E0B", boxShadow: "0 0 4px #F59E0BAA" }} />
              )}
              {!expanded && isHov && (
                <div style={{ position: "absolute", left: 54, backgroundColor: "#1A1F2E", border: "1px solid #2A3040", borderRadius: 7, padding: "5px 11px", fontSize: 12, color: "#E2E8F0", whiteSpace: "nowrap", zIndex: 200, pointerEvents: "none", fontFamily: FONT, boxShadow: "0 4px 12px rgba(0,0,0,0.4)" }}>
                  {agent.name}
                </div>
              )}
            </div>
          );
        })}
      </div>

      <div style={{ borderTop: "1px solid #181C28", paddingTop: 4, paddingBottom: 8, width: "100%" }}>
        <div style={{ height: 44, width: "100%", display: "flex", alignItems: "center", justifyContent: expanded ? "flex-start" : "center", padding: expanded ? "0 16px" : 0, gap: 12, cursor: "pointer", color: "#4B5563" }}>
          <IconSettings />
          {expanded && <span style={{ fontSize: 12, color: "#4B5563", fontFamily: FONT }}>Settings</span>}
        </div>
        <div style={{ height: 44, width: "100%", display: "flex", alignItems: "center", justifyContent: expanded ? "flex-start" : "center", padding: expanded ? "0 14px" : 0, gap: 12, cursor: "pointer" }}>
          <div style={{ width: 28, height: 28, borderRadius: "50%", background: "linear-gradient(135deg, var(--color-surface) 0%, var(--color-surface-hover) 100%)", border: "1.5px solid var(--color-border-strong)", display: "flex", alignItems: "center", justifyContent: "center", fontSize: 9, fontWeight: 700, color: "var(--color-accent)", flexShrink: 0, fontFamily: FONT }}>SJ</div>
          {expanded && <span style={{ fontSize: 12, color: "#6B7280", fontFamily: FONT, whiteSpace: "nowrap" }}>{userName}</span>}
        </div>
      </div>
    </div>
  );
}

// ── Composer ──────────────────────────────────────────────────────────────────

function Composer({ agents, onNavigate }: {
  agents:     AgentDef[];
  onNavigate: (agent: AgentDef, query?: string) => void;
}) {
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [text, setText]             = useState("");
  const inputRef                    = useRef<HTMLInputElement>(null);

  const activeAgent = agents.find(a => a.id === selectedId) ?? agents[0];
  const colour      = AGENT_COLOUR[activeAgent.type];

  function handleSubmit(query?: string) {
    onNavigate(activeAgent, (query ?? text) || undefined);
  }

  return (
    <div style={{
      backgroundColor: "var(--color-surface)",
      border:          "1px solid var(--color-border)",
      borderRadius:    16,
      padding:         "20px 24px 16px",
      marginBottom:    32,
      boxShadow:       "var(--shadow-md)",
    }}>
      <p style={{ fontSize: 13, fontWeight: 600, color: "var(--color-text-secondary)", fontFamily: FONT, margin: "0 0 14px", letterSpacing: "0.01em" }}>
        What can your agents help with today?
      </p>

      <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginBottom: 14 }}>
        {agents.map(a => {
          const ac     = AGENT_COLOUR[a.type];
          const isChip = a.id === selectedId;
          return (
            <button key={a.id} onClick={() => setSelectedId(isChip ? null : a.id)} style={{
              display: "inline-flex", alignItems: "center", gap: 6,
              height: 28, padding: "0 12px", borderRadius: 20,
              border:          `1px solid ${isChip ? ac : "var(--color-border)"}`,
              backgroundColor: isChip ? `${ac}20` : "var(--color-background)",
              color:           isChip ? ac : "var(--color-text-muted)",
              fontSize: 11.5, fontWeight: isChip ? 600 : 400,
              fontFamily: FONT, cursor: "pointer", transition: "all 120ms",
            }}>
              <span style={{ width: 6, height: 6, borderRadius: "50%", backgroundColor: isChip ? ac : "var(--color-border-strong)", flexShrink: 0 }} />
              {a.name}
            </button>
          );
        })}
      </div>

      <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
        <div style={{
          flex: 1, display: "flex", alignItems: "center", gap: 10,
          height: 40, padding: "0 14px", borderRadius: 10,
          border: "1px solid var(--color-border)",
          backgroundColor: "var(--color-background)",
        }}>
          <span style={{ fontSize: 11, fontFamily: MONO, color: "var(--color-text-muted)", flexShrink: 0 }}>
            {activeAgent.name.split(" ")[0].toLowerCase()}&gt;
          </span>
          <input
            ref={inputRef}
            value={text}
            onChange={e => setText(e.target.value)}
            onKeyDown={e => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); handleSubmit(); } }}
            placeholder={`Ask ${activeAgent.name} anything…`}
            suppressHydrationWarning
            style={{ flex: 1, background: "transparent", border: "none", outline: "none", fontSize: 13, fontFamily: FONT, color: "var(--color-text-primary)" }}
          />
        </div>
        <button onClick={() => handleSubmit()} style={{
          width: 40, height: 40, borderRadius: 10, border: "none",
          backgroundColor: colour, color: "#fff",
          display: "flex", alignItems: "center", justifyContent: "center",
          cursor: "pointer", flexShrink: 0,
          boxShadow: `0 0 14px ${colour}55`,
        }}>
          <IconSend />
        </button>
      </div>

      <div style={{ marginTop: 12, display: "flex", gap: 8, flexWrap: "wrap" }}>
        <span style={{ fontSize: 10.5, color: "var(--color-text-muted)", fontFamily: FONT, alignSelf: "center", marginRight: 2 }}>Try:</span>
        {activeAgent.suggestions.map((s, i) => (
          <button key={i} onClick={() => handleSubmit(s)} style={{
            display: "inline-flex", alignItems: "center", gap: 5,
            height: 26, padding: "0 10px", borderRadius: 6,
            border: "1px solid var(--color-border)",
            backgroundColor: "transparent",
            color: "var(--color-text-muted)",
            fontSize: 11, fontFamily: FONT, cursor: "pointer",
            transition: "border-color var(--transition), color var(--transition)",
          }}
          onMouseEnter={e => { (e.currentTarget as HTMLButtonElement).style.borderColor = colour; (e.currentTarget as HTMLButtonElement).style.color = colour; }}
          onMouseLeave={e => { (e.currentTarget as HTMLButtonElement).style.borderColor = "var(--color-border)"; (e.currentTarget as HTMLButtonElement).style.color = "var(--color-text-muted)"; }}
          >
            {s}
            <svg width="9" height="9" viewBox="0 0 9 9" fill="none" style={{ opacity: 0.5 }}>
              <path d="M2 7L7 2M7 2H3M7 2v4" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round" />
            </svg>
          </button>
        ))}
      </div>
    </div>
  );
}

// ── Agent Card ─────────────────────────────────────────────────────────────────

function AgentCard({ agent, index, onOpen, isClicking, isDark }: {
  agent: AgentDef; index: number; onOpen: (a: AgentDef) => void;
  isClicking: boolean; isDark: boolean;
}) {
  const [visible, setVisible] = useState(false);
  const [hovered, setHovered] = useState(false);
  const colour  = AGENT_COLOUR[agent.type];
  const sorted  = [...agent.statuses].sort((a, b) => (b.count > 0 ? 1 : 0) - (a.count > 0 ? 1 : 0) || b.count - a.count);
  const hasAttn = agent.statuses.some(s => s.count > 0);

  useEffect(() => {
    const t = setTimeout(() => setVisible(true), index * 90);
    return () => clearTimeout(t);
  }, [index]);

  const lit = hovered || isClicking;

  if (!isDark) {
    // Light layout: horizontal row
    return (
      <div
        style={{
          display: "flex",
          backgroundColor: lit ? "var(--color-surface-hover)" : "var(--color-surface)",
          borderRadius: 12,
          border: `1px solid ${lit ? colour + "40" : "var(--color-border)"}`,
          overflow: "hidden", cursor: "pointer",
          transform: visible ? "translateX(0)" : "translateX(-12px)",
          opacity: visible ? 1 : 0,
          transition: "transform 280ms cubic-bezier(0.34,1.56,0.64,1), opacity 240ms ease, border-color 160ms, background-color 160ms, box-shadow 160ms",
          boxShadow: lit ? `0 4px 20px ${colour}14, var(--shadow-sm)` : "var(--shadow-sm)",
        }}
        onMouseEnter={() => setHovered(true)}
        onMouseLeave={() => setHovered(false)}
        onClick={() => onOpen(agent)}
      >
        <div style={{ width: 5, backgroundColor: colour, flexShrink: 0, opacity: lit ? 1 : 0.7 }} />
        <div style={{ flex: 1, padding: "14px 20px", display: "grid", gridTemplateColumns: "2fr 2.2fr 1.4fr auto", gap: 20, alignItems: "center" }}>
          <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
            <div style={{ width: 40, height: 40, borderRadius: 9, flexShrink: 0, backgroundColor: `${colour}14`, border: `1px solid ${colour}28`, display: "flex", alignItems: "center", justifyContent: "center" }}>
              {ICONS[agent.type](colour)}
            </div>
            <div>
              <div style={{ fontSize: 14, fontWeight: 700, color: "var(--color-text-primary)", fontFamily: FONT, letterSpacing: "-0.01em" }}>{agent.name}</div>
              <div style={{ fontSize: 10.5, color: "var(--color-text-muted)", fontFamily: MONO, textTransform: "uppercase", letterSpacing: "0.05em", marginTop: 2 }}>{agent.blurb}</div>
            </div>
          </div>
          <div style={{ display: "flex", flexDirection: "column", gap: 5 }}>
            {sorted.map((s, i) => {
              const active = s.count > 0;
              return (
                <div key={i} style={{ display: "flex", alignItems: "center", gap: 8 }}>
                  <span style={{ fontSize: 13, fontWeight: 700, fontFamily: FONT, minWidth: 22, color: active ? s.dotColour : "var(--color-border-strong)", textAlign: "right", lineHeight: 1 }}>{s.count}</span>
                  <div style={{ width: 3, height: 3, borderRadius: "50%", backgroundColor: active ? s.dotColour : "var(--color-border-strong)", flexShrink: 0 }} />
                  <span style={{ fontSize: 11, fontFamily: FONT, color: active ? "var(--color-text-secondary)" : "var(--color-text-muted)" }}>{s.label}</span>
                </div>
              );
            })}
          </div>
          <div>
            <div style={{ fontSize: 9, fontFamily: MONO, color: "var(--color-text-muted)", textTransform: "uppercase", letterSpacing: "0.08em", marginBottom: 6 }}>24h activity</div>
            <Sparkline values={agent.activity24h} colour={colour} height={26} />
            <div style={{ fontSize: 10.5, color: "var(--color-text-muted)", marginTop: 6, lineHeight: 1.4, fontFamily: FONT }}>
              <i>{agent.lastActivity.substring(0, 45)}{agent.lastActivity.length > 45 ? "…" : ""}</i>
            </div>
          </div>
          <div>
            <div style={{ height: 32, padding: "0 16px", borderRadius: 8, border: `1.5px solid ${colour}`, backgroundColor: lit ? `${colour}18` : "transparent", color: colour, fontSize: 12, fontWeight: 700, fontFamily: FONT, display: "inline-flex", alignItems: "center", gap: 7, cursor: "pointer", whiteSpace: "nowrap" }}>
              Open
              <svg width="11" height="11" viewBox="0 0 11 11" fill="none"><path d="M2 5.5h7M6.5 3l2.5 2.5L6.5 8" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round" /></svg>
            </div>
          </div>
        </div>
      </div>
    );
  }

  // Dark layout: grid card
  return (
    <div
      style={{
        backgroundColor: lit ? "var(--color-surface-hover)" : "var(--color-surface)",
        borderRadius: 14,
        borderLeft:   `1px solid ${lit ? colour + "55" : "var(--color-border)"}`,
        borderRight:  `1px solid ${lit ? colour + "55" : "var(--color-border)"}`,
        borderBottom: `1px solid ${lit ? colour + "55" : "var(--color-border)"}`,
        borderTop:    `1px solid ${lit ? colour + "80" : "var(--color-border-strong)"}`,
        cursor: "pointer",
        transform: isClicking ? "scale(1.025)" : visible ? "translateY(0) scale(1)" : "translateY(20px) scale(0.98)",
        opacity: visible ? 1 : 0,
        transition: isClicking
          ? "transform 80ms ease"
          : "transform 280ms cubic-bezier(0.34,1.56,0.64,1), opacity 240ms ease, border-color 160ms ease, background-color 160ms ease, box-shadow 160ms ease",
        boxShadow: lit
          ? `0 0 0 1px ${colour}20, 0 8px 32px ${colour}18, var(--shadow-md)`
          : "var(--shadow-sm)",
        position: "relative", display: "flex", flexDirection: "column", overflow: "hidden",
      }}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      onClick={() => onOpen(agent)}
    >
      <div style={{ position: "absolute", top: 0, left: 0, right: 0, height: 90, background: `linear-gradient(160deg, ${colour}12 0%, transparent 100%)`, pointerEvents: "none" }} />
      {hasAttn && <div style={{ position: "absolute", top: 12, right: 12, width: 7, height: 7, borderRadius: "50%", backgroundColor: "var(--color-warning)", boxShadow: "0 0 7px var(--color-warning)" }} />}

      <div style={{ padding: "18px 18px 12px", display: "flex", alignItems: "flex-start", gap: 13, flexShrink: 0, position: "relative" }}>
        <div style={{ width: 38, height: 38, borderRadius: 9, flexShrink: 0, backgroundColor: `${colour}18`, border: `1px solid ${colour}35`, display: "flex", alignItems: "center", justifyContent: "center", boxShadow: lit ? `0 0 12px ${colour}25` : "none", transition: "box-shadow 160ms" }}>
          {ICONS[agent.type](colour)}
        </div>
        <div style={{ minWidth: 0, paddingTop: 2 }}>
          <div style={{ fontSize: 14.5, fontWeight: 700, color: "var(--color-text-primary)", fontFamily: FONT, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis", letterSpacing: "-0.01em" }}>{agent.name}</div>
          <div style={{ fontSize: 10.5, color: "var(--color-text-muted)", marginTop: 3, fontFamily: FONT, letterSpacing: "0.03em" }}>{agent.blurb}</div>
        </div>
      </div>

      <div style={{ height: 1, backgroundColor: "var(--color-border)", margin: "0 18px", flexShrink: 0 }} />

      <div style={{ flex: 1, padding: "12px 18px", display: "flex", flexDirection: "column", justifyContent: "center", gap: 7 }}>
        {sorted.slice(0, 3).map((s, i) => {
          const active = s.count > 0;
          return (
            <div key={i} style={{ display: "flex", alignItems: "center", gap: 9 }}>
              <span style={{ fontSize: 14, fontWeight: 700, fontFamily: FONT, minWidth: 20, color: active ? s.dotColour : "var(--color-border-strong)", textAlign: "right", lineHeight: 1 }}>{s.count}</span>
              <div style={{ width: 3.5, height: 3.5, borderRadius: "50%", backgroundColor: active ? s.dotColour : "var(--color-border-strong)", flexShrink: 0 }} />
              <span style={{ fontSize: 11, fontFamily: FONT, color: active ? "var(--color-text-secondary)" : "var(--color-text-muted)", lineHeight: 1 }}>{s.label}</span>
            </div>
          );
        })}
      </div>

      <div style={{ padding: "8px 18px 10px", display: "flex", alignItems: "center", justifyContent: "space-between", borderTop: "1px solid var(--color-border)" }}>
        <div>
          <div style={{ fontSize: 9, fontFamily: MONO, color: "var(--color-text-muted)", textTransform: "uppercase", letterSpacing: "0.08em", marginBottom: 4 }}>24h activity</div>
          <Sparkline values={agent.activity24h} colour={colour} height={22} />
        </div>
        <div style={{ fontSize: 10, fontFamily: FONT, color: "var(--color-text-muted)", maxWidth: 130, lineHeight: 1.4, textAlign: "right" }}>
          <i>{agent.lastActivity.substring(0, 50)}{agent.lastActivity.length > 50 ? "…" : ""}</i>
        </div>
      </div>

      <div style={{ padding: "0 12px 12px", flexShrink: 0 }}>
        <button
          onClick={(e) => { e.stopPropagation(); onOpen(agent); }}
          style={{ width: "100%", height: 34, border: `1px solid ${colour}55`, borderRadius: 8, backgroundColor: lit ? `${colour}28` : `${colour}14`, color: colour, fontSize: 12, fontWeight: 600, fontFamily: FONT, cursor: "pointer", transition: "background-color 140ms", display: "flex", alignItems: "center", justifyContent: "center", gap: 6 }}
        >
          Open {agent.name}
          <svg width="11" height="11" viewBox="0 0 11 11" fill="none"><path d="M2 5.5h7M6.5 3l2.5 2.5L6.5 8" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round" /></svg>
        </button>
      </div>
    </div>
  );
}

// ── Page ──────────────────────────────────────────────────────────────────────

export default function Home() {
  const router = useRouter();
  const { isDark } = useThemeContext();

  const [pageOpacity, setPageOpacity] = useState(0);
  const [clickingId, setClickingId]   = useState<string | null>(null);
  const [runs,    setRuns]    = useState<EvalRun[]>([]);
  const [userName, setUserName] = useState("You");

  useEffect(() => {
    const t = setTimeout(() => setPageOpacity(1), 40);
    const token = localStorage.getItem("access_token");
    if (!token) { router.replace("/login"); return; }
    try {
      const payload = JSON.parse(atob(token.split(".")[1]));
      const email: string = payload.sub ?? "";
      setUserName(email.split("@")[0].replace(/[._]/g, " ").replace(/\b\w/g, c => c.toUpperCase()));
    } catch { /* ignore */ }
    fetch("/api/v1/evaluate/list", { headers: { Authorization: `Bearer ${token}` } })
      .then(r => r.json())
      .then(d => setRuns(d.runs ?? []))
      .catch(() => {});
    return () => clearTimeout(t);
  }, []);

  const runningRuns  = runs.filter(r => r.status === "running");
  const pendingRuns  = runs.filter(r => r.status === "pending_approval");
  const completeRuns = runs.filter(r => r.status === "complete");
  const lastRun      = runs[0];

  const procAgent: AgentDef = {
    ...MOCK_AGENTS[0],
    lastActivity: lastRun ? `${lastRun.rfp_title || lastRun.run_id.slice(0, 16)} — ${lastRun.status}` : MOCK_AGENTS[0].lastActivity,
    statuses: [
      { label: "evaluations running",     count: runningRuns.length,  dotColour: "var(--color-warning)", kind: "amber" },
      { label: "results ready to review", count: completeRuns.length, dotColour: "var(--color-accent)",  kind: "teal"  },
      { label: "awaiting your approval",  count: pendingRuns.length,  dotColour: pendingRuns.length > 0 ? "var(--color-error)" : "var(--color-border)", kind: pendingRuns.length > 0 ? "red" : "grey" },
    ],
  };

  const agents      = [procAgent, ...MOCK_AGENTS.slice(1)];
  const urgentCount = agents.filter(a => a.statuses.some(s => s.kind === "red")).length;

  function handleOpenAgent(agent: AgentDef, query?: string) {
    if (clickingId) return;
    setClickingId(agent.id);
    setTimeout(() => setPageOpacity(0), 200);
    const deptParam = `department=${encodeURIComponent(agent.name)}`;
    const url = query ? `${agent.href}?${deptParam}&q=${encodeURIComponent(query)}` : `${agent.href}?${deptParam}`;
    setTimeout(() => router.push(url), 400);
  }

  return (
    <div style={{
      minHeight: "100vh",
      background: "var(--bg-gradient)",
      fontFamily: FONT,
      opacity: pageOpacity,
      transition: "opacity 220ms ease",
    }}>
      <AgentSwitcherRail agents={agents} activeId={null} onSelect={handleOpenAgent} userName={userName} />

      <div style={{ marginLeft: 48, display: "flex", flexDirection: "column", minHeight: "100vh" }}>

        {/* Top bar */}
        <header style={{
          height: 60, position: "sticky", top: 0, zIndex: 40,
          backgroundColor: "var(--topbar-bg)",
          backdropFilter: "blur(12px)", WebkitBackdropFilter: "blur(12px)",
          borderBottom: "1px solid var(--topbar-border)",
          display: "flex", alignItems: "center", justifyContent: "space-between",
          padding: "0 36px", flexShrink: 0,
        }}>
          <span style={{ fontSize: 11, fontWeight: 700, color: "var(--color-text-muted)", letterSpacing: "0.14em", fontFamily: FONT, textTransform: "uppercase" }}>
            {COMPANY.platformName}
          </span>

          <div style={{ display: "flex", alignItems: "center", gap: 16 }}>
            <ThemePicker />
            <div style={{ width: 1, height: 20, backgroundColor: "var(--color-border)" }} />
            <div style={{ textAlign: "right" }}>
              <div style={{ fontSize: 13, color: "var(--color-text-secondary)", fontWeight: 600, lineHeight: 1.3 }}>{userName}</div>
              <div style={{ fontSize: 11, color: "var(--color-text-muted)", lineHeight: 1.3 }}>{COMPANY.name}</div>
            </div>
            <div style={{ width: 34, height: 34, borderRadius: "50%", background: "linear-gradient(135deg, var(--color-surface), var(--color-surface-hover))", border: "1.5px solid var(--color-border-strong)", display: "flex", alignItems: "center", justifyContent: "center", fontSize: 11, fontWeight: 700, color: "var(--color-accent)", flexShrink: 0, fontFamily: FONT }}>
              SJ
            </div>
          </div>
        </header>

        {/* Main */}
        <main style={{ flex: 1, width: "100%", maxWidth: 980, margin: "0 auto", padding: "56px 36px 80px" }}>

          <div style={{ marginBottom: 40 }}>
            <p style={{ fontSize: 11, fontWeight: 600, color: "var(--color-text-muted)", letterSpacing: "0.16em", textTransform: "uppercase", margin: "0 0 8px", fontFamily: FONT }}>
              Good morning
            </p>
            <h1 style={{ fontSize: 44, fontWeight: 800, color: "var(--color-text-primary)", fontFamily: DISPLAY, margin: "0 0 18px", letterSpacing: "-0.03em", lineHeight: 1.05 }}>
              {userName}.
            </h1>
            <div style={{ display: "flex", alignItems: "center", gap: 12, flexWrap: "wrap" }}>
              <span style={{ fontSize: 14, color: "var(--color-text-muted)", fontFamily: FONT }}>
                You have access to{" "}
                <span style={{ color: "var(--color-text-secondary)", fontWeight: 600 }}>{agents.length} agents</span>
                {" "}·{" "}
                <span style={{ color: "var(--color-text-secondary)", fontWeight: 600 }}>{runs.length} evaluations</span>
              </span>
              {urgentCount > 0 && (
                <span style={{ display: "inline-flex", alignItems: "center", gap: 6, fontSize: 12, fontFamily: FONT, backgroundColor: "var(--color-surface)", border: "1px solid var(--color-warning)", color: "var(--color-warning)", borderRadius: 20, padding: "4px 12px", fontWeight: 500 }}>
                  <span style={{ width: 5, height: 5, borderRadius: "50%", backgroundColor: "var(--color-warning)", display: "inline-block" }} />
                  {urgentCount} {urgentCount === 1 ? "item needs" : "items need"} attention
                </span>
              )}
            </div>
          </div>

          <Composer agents={agents} onNavigate={handleOpenAgent} />

          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 16 }}>
            <p style={{ fontSize: 10, fontWeight: 700, color: "var(--color-text-muted)", letterSpacing: "0.18em", textTransform: "uppercase", margin: 0, fontFamily: FONT }}>
              Your agents
            </p>
            <div style={{ display: "flex", gap: 20 }}>
              {[
                { label: "active tasks",     value: agents.reduce((s, a) => s + a.statuses.reduce((x, c) => x + c.count, 0), 0) },
                { label: "ready for review", value: agents.reduce((s, a) => s + a.statuses.filter(c => c.kind === "teal").reduce((x, c) => x + c.count, 0), 0) },
              ].map(stat => (
                <div key={stat.label} style={{ textAlign: "right" }}>
                  <div style={{ fontSize: 18, fontWeight: 700, fontFamily: SERIF, color: "var(--color-text-primary)", lineHeight: 1 }}>{stat.value}</div>
                  <div style={{ fontSize: 9, fontFamily: MONO, color: "var(--color-text-muted)", textTransform: "uppercase", letterSpacing: "0.08em", marginTop: 2 }}>{stat.label}</div>
                </div>
              ))}
            </div>
          </div>

          <div style={{ height: 1, background: "linear-gradient(90deg, var(--color-border) 0%, transparent 100%)", marginBottom: 20 }} />

          {isDark ? (
            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(295px, 1fr))", gap: 16 }}>
              {agents.map((agent, i) => (
                <AgentCard key={agent.id} agent={agent} index={i} onOpen={handleOpenAgent} isClicking={clickingId === agent.id} isDark={isDark} />
              ))}
            </div>
          ) : (
            <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
              {agents.map((agent, i) => (
                <AgentCard key={agent.id} agent={agent} index={i} onOpen={handleOpenAgent} isClicking={clickingId === agent.id} isDark={isDark} />
              ))}
            </div>
          )}

          {runs.length > 0 && (
            <div style={{ marginTop: 40 }}>
              <p style={{ fontSize: 11, fontWeight: 600, color: "var(--color-text-muted)", letterSpacing: "0.14em", textTransform: "uppercase", margin: "0 0 14px", fontFamily: FONT }}>
                Recent evaluations
              </p>
              <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                {runs.slice(0, 8).map(run => {
                  const statusColour =
                    run.status === "complete"         ? "var(--color-success)" :
                    run.status === "running"          ? "var(--color-info)"    :
                    run.status === "pending_approval" ? "var(--color-warning)" :
                    run.status === "interrupted"      ? "var(--color-text-muted)" : "var(--color-error)";
                  const statusLabel = run.status === "interrupted" ? "interrupted" : run.status.replace(/_/g, " ");
                  const href = run.status === "running" ? `/${run.run_id}/progress` : run.status === "interrupted" ? "#" : `/${run.run_id}/results`;
                  return (
                    <div key={run.run_id}
                      onClick={() => href !== "#" && router.push(href)}
                      className="hoverable"
                      style={{
                        display: "flex", alignItems: "center", gap: 14,
                        padding: "11px 16px", borderRadius: 10,
                        cursor: href === "#" ? "default" : "pointer",
                        opacity: run.status === "interrupted" ? 0.55 : 1,
                        background: "var(--color-surface)",
                        border: "1px solid var(--color-border)",
                        transition: "background var(--transition)",
                      }}
                    >
                      <span style={{ width: 8, height: 8, borderRadius: "50%", background: statusColour, flexShrink: 0 }} />
                      <span style={{ flex: 1, fontSize: 13, color: "var(--color-text-secondary)", fontFamily: FONT, fontWeight: 500, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                        {run.rfp_title || run.run_id.slice(0, 20)}
                      </span>
                      <span style={{ fontSize: 11, color: "var(--color-text-muted)", fontFamily: FONT }}>{run.department}</span>
                      <span style={{ fontSize: 11, fontWeight: 600, color: statusColour, fontFamily: FONT, flexShrink: 0 }}>{statusLabel}</span>
                      <span style={{ fontSize: 11, color: "var(--color-text-muted)", fontFamily: FONT, flexShrink: 0 }}>→</span>
                    </div>
                  );
                })}
              </div>
            </div>
          )}
        </main>
      </div>
    </div>
  );
}
