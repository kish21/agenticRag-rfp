"use client";

import { useState } from "react";

// ── Injected styles ────────────────────────────────────────────────────────────

const CSS = `
  @import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500&family=IBM+Plex+Sans:wght@400;500;600;700&display=swap');
  @keyframes pulse    { 0%,100%{opacity:1} 50%{opacity:0.25} }
  @keyframes slidein  { from{transform:translateX(100%)} to{transform:translateX(0)} }
  @keyframes fadein   { from{opacity:0} to{opacity:1} }
  * { box-sizing: border-box; }
  ::-webkit-scrollbar { width: 6px; }
  ::-webkit-scrollbar-track { background: transparent; }
  ::-webkit-scrollbar-thumb { background: #7C3AED44; border-radius: 3px; }
`;

// ── Theme ──────────────────────────────────────────────────────────────────────

const PURPLE = "#7C3AED";
const TEAL   = "#00D4AA";
const AMBER  = "#F59E0B";
const RED    = "#EF4444";
const FONT   = "'IBM Plex Sans', ui-sans-serif, system-ui, sans-serif";
const MONO   = "'IBM Plex Mono', ui-monospace, 'Cascadia Code', monospace";

const DARK = {
  bg:       "#0D0F1A",
  surface:  "#16182A",
  elevated: "#1C1F35",
  border:   "#1E2240",
  borderB:  "#2A2E50",
  row:      "#1A1D30",
  text:     { p: "#F8FAFC", s: "#94A3B8", m: "#64748B", d: "#374151" },
  topbar:   "rgba(13,15,26,0.95)",
};

const LIGHT = {
  bg:       "#F5F3FF",
  surface:  "#FFFFFF",
  elevated: "#EDE9FE",
  border:   "#DDD5F7",
  borderB:  "#C4B5FD",
  row:      "#F9F7FF",
  text:     { p: "#1E1B4B", s: "#4C4680", m: "#7C7AAD", d: "#B8B4D8" },
  topbar:   "rgba(245,243,255,0.95)",
};

// ── Types ──────────────────────────────────────────────────────────────────────

interface AgentSlot { colour: string; name: string; evals: number }

interface Company {
  id:          string;
  name:        string;
  plan:        "SaaS Pro" | "SaaS Enterprise" | "On-premise";
  agents:      AgentSlot[];
  evalsToday:  number;
  health:      "healthy" | "warning" | "degraded" | "inactive";
  billing:     "current" | "due_soon" | "overdue" | "trial";
  billingDays?: number;
  since:       string;
  lastEval:    string;
  lastAgent:   string;
  apiUsed:     number;
  apiLimit:    number;
  nextInvoice: string;
}

interface AlertItem {
  id:       string;
  severity: "red" | "amber";
  time:     string;
  company:  string | null;
  message:  string;
  action:   string;
}

// ── Mock data ──────────────────────────────────────────────────────────────────

const COMPANIES: Company[] = [
  {
    id: "meridian", name: "Meridian Financial Services", plan: "SaaS Enterprise",
    agents: [
      { colour: "#00D4AA", name: "IT Procurement",    evals: 12 },
      { colour: "#8B5CF6", name: "People & Culture",  evals: 8  },
      { colour: "#F59E0B", name: "Legal & Compliance",evals: 5  },
    ],
    evalsToday: 25, health: "healthy", billing: "current",
    since: "Jan 2025", lastEval: "14:31 today", lastAgent: "IT Procurement",
    apiUsed: 7400, apiLimit: 10000, nextInvoice: "Jun 1, 2026",
  },
  {
    id: "vantage", name: "Vantage Capital Group", plan: "SaaS Pro",
    agents: [
      { colour: "#00D4AA", name: "IT Procurement", evals: 4 },
      { colour: "#10B981", name: "Finance",         evals: 2 },
    ],
    evalsToday: 6, health: "warning", billing: "due_soon", billingDays: 3,
    since: "Mar 2025", lastEval: "11:02 today", lastAgent: "Finance",
    apiUsed: 3200, apiLimit: 5000, nextInvoice: "May 10, 2026",
  },
  {
    id: "nexus", name: "Nexus Healthcare Systems", plan: "On-premise",
    agents: [
      { colour: "#00D4AA", name: "IT Procurement", evals: 0 },
      { colour: "#F59E0B", name: "Compliance",      evals: 0 },
      { colour: "#3B82F6", name: "Operations",      evals: 0 },
    ],
    evalsToday: 0, health: "inactive", billing: "current",
    since: "Sep 2024", lastEval: "8 days ago", lastAgent: "Compliance",
    apiUsed: 890, apiLimit: 20000, nextInvoice: "Jun 15, 2026",
  },
  {
    id: "brightline", name: "Brightline Logistics", plan: "SaaS Pro",
    agents: [
      { colour: "#00D4AA", name: "IT Procurement", evals: 1 },
    ],
    evalsToday: 38, health: "degraded", billing: "overdue",
    since: "Nov 2024", lastEval: "14:55 today", lastAgent: "IT Procurement",
    apiUsed: 4900, apiLimit: 5000, nextInvoice: "Overdue since May 1",
  },
  {
    id: "summit", name: "Summit Retail Partners", plan: "SaaS Enterprise",
    agents: [
      { colour: "#00D4AA", name: "IT Procurement",   evals: 3 },
      { colour: "#8B5CF6", name: "People & Culture", evals: 7 },
    ],
    evalsToday: 10, health: "healthy", billing: "trial", billingDays: 12,
    since: "Apr 2026", lastEval: "13:10 today", lastAgent: "People & Culture",
    apiUsed: 1100, apiLimit: 10000, nextInvoice: "May 19, 2026",
  },
];

const ALERTS: AlertItem[] = [
  {
    id: "a1", severity: "red", time: "14:23", company: "Brightline Logistics",
    message: "Extraction Agent failing — Vendor Alpha response corrupt",
    action: "Investigate",
  },
  {
    id: "a2", severity: "amber", time: "13:45", company: null,
    message: "Cohere API latency above 3s average (currently 4.1s)",
    action: "Monitor",
  },
  {
    id: "a3", severity: "amber", time: "12:08", company: "Vantage Capital Group",
    message: "Invoice due in 3 days — no payment method on file",
    action: "Contact",
  },
];

const SPARK = [210, 340, 290, 480, 520, 610, 580, 740, 820, 910, 880, 1020];

const LOG_LINES = [
  { level: "ERROR", msg: "ExtractionAgent: failed to parse Vendor Alpha chunk #47 — null body" },
  { level: "ERROR", msg: "ExtractionAgent: retry 1/3 failed — grounding check returned 0 matches" },
  { level: "ERROR", msg: "ExtractionAgent: retry 2/3 failed — LLM returned malformed JSON" },
  { level: "WARN",  msg: "CriticAgent: escalation triggered for run brightline-4491" },
  { level: "WARN",  msg: "CriticAgent: soft failure on ExtractionAgent output (confidence 0.41)" },
  { level: "INFO",  msg: "ExtractionAgent: processing chunk 46 of 58 (vendor: Alpha)" },
  { level: "INFO",  msg: "ExtractionAgent: processing chunk 45 of 58 (vendor: Alpha)" },
  { level: "INFO",  msg: "RetrievalAgent: HyDE query rewritten — 3 chunks retrieved" },
  { level: "INFO",  msg: "PlannerAgent: task DAG created — 5 nodes, 8 edges" },
  { level: "INFO",  msg: "IngestionAgent: 58 chunks indexed for run brightline-4491" },
  { level: "INFO",  msg: "IngestionAgent: dense + sparse vectors written to Qdrant" },
  { level: "INFO",  msg: "IngestionAgent: PDF parsed — 14 pages, 58 chunks" },
];

// ── Sparkline ──────────────────────────────────────────────────────────────────

function Sparkline({ data, colour }: { data: number[]; colour: string }) {
  const W = 72, H = 24;
  const min = Math.min(...data), max = Math.max(...data);
  const pts = data.map((v, i) => {
    const x = (i / (data.length - 1)) * W;
    const y = H - ((v - min) / (max - min || 1)) * H;
    return `${x.toFixed(1)},${y.toFixed(1)}`;
  }).join(" ");
  return (
    <svg width={W} height={H} style={{ display: "block" }}>
      <polyline points={pts} fill="none" stroke={colour} strokeWidth="1.5"
        strokeLinecap="round" strokeLinejoin="round" opacity={0.75} />
    </svg>
  );
}

// ── StatusPill ─────────────────────────────────────────────────────────────────

function StatusPill({ colour, label, pulse }: { colour: string; label: string; pulse: boolean }) {
  return (
    <div style={{
      display: "inline-flex", alignItems: "center", gap: 7,
      background: colour + "18", border: `1px solid ${colour}35`,
      borderRadius: 20, padding: "5px 14px",
      fontSize: 12, fontFamily: FONT, fontWeight: 500, color: colour,
    }}>
      <span style={{
        width: 6, height: 6, borderRadius: "50%", background: colour, flexShrink: 0,
        animation: pulse ? "pulse 1.2s ease-in-out infinite" : undefined,
      }} />
      {label}
    </div>
  );
}

// ── PlanBadge ──────────────────────────────────────────────────────────────────

function PlanBadge({ plan }: { plan: Company["plan"] }) {
  const colour = plan === "SaaS Enterprise" ? PURPLE : plan === "SaaS Pro" ? TEAL : AMBER;
  return (
    <span style={{
      fontFamily: FONT, fontSize: 11, fontWeight: 500, color: colour,
      background: colour + "1A", padding: "2px 8px",
      borderRadius: 20, border: `1px solid ${colour}40`, whiteSpace: "nowrap",
    }}>{plan}</span>
  );
}

// ── HealthPill ─────────────────────────────────────────────────────────────────

const HEALTH_CFG = {
  healthy:  { colour: TEAL,      label: "Healthy"  },
  warning:  { colour: AMBER,     label: "Warning"  },
  degraded: { colour: RED,       label: "Degraded" },
  inactive: { colour: "#6B7280", label: "Inactive" },
} as const;

function HealthPill({ health }: { health: Company["health"] }) {
  const { colour, label } = HEALTH_CFG[health];
  return (
    <span style={{ display: "inline-flex", alignItems: "center", gap: 5, fontFamily: FONT, fontSize: 12, color: colour }}>
      <span style={{
        width: 7, height: 7, borderRadius: "50%", background: colour, flexShrink: 0,
        animation: health === "degraded" ? "pulse 1.4s ease-in-out infinite" : undefined,
      }} />
      {label}
    </span>
  );
}

// ── BillingPill ────────────────────────────────────────────────────────────────

function BillingPill({ billing, days }: { billing: Company["billing"]; days?: number }) {
  const map = {
    current:  { colour: TEAL,   label: "Current"                       },
    due_soon: { colour: AMBER,  label: `Due in ${days ?? 3} days`      },
    overdue:  { colour: RED,    label: "Overdue"                        },
    trial:    { colour: PURPLE, label: `Trial · ${days ?? 0} days left` },
  };
  const { colour, label } = map[billing];
  return <span style={{ fontFamily: FONT, fontSize: 12, color: colour, fontWeight: 500 }}>{label}</span>;
}

// ── AgentDots ──────────────────────────────────────────────────────────────────

function AgentDots({ agents }: { agents: AgentSlot[] }) {
  const [tip, setTip] = useState<number | null>(null);
  return (
    <span style={{ display: "inline-flex", gap: 5, position: "relative" }}>
      {agents.map((a, i) => (
        <span key={i} style={{ position: "relative" }}
          onMouseEnter={() => setTip(i)}
          onMouseLeave={() => setTip(null)}
        >
          <span style={{
            width: 10, height: 10, borderRadius: "50%", background: a.colour,
            display: "inline-block", cursor: "default", flexShrink: 0,
          }} />
          {tip === i && (
            <span style={{
              position: "absolute", bottom: 16, left: "50%", transform: "translateX(-50%)",
              background: "#1C1F35", border: "1px solid #2A2E50",
              borderRadius: 6, padding: "4px 8px", whiteSpace: "nowrap",
              fontSize: 11, fontFamily: FONT, color: "#F8FAFC", zIndex: 20,
              pointerEvents: "none",
            }}>
              {a.name} · {a.evals} evals
            </span>
          )}
        </span>
      ))}
    </span>
  );
}

// ── HealthTile ─────────────────────────────────────────────────────────────────

function HealthTile({ isDark, label, metric, metricColour, sub, extra, pulse }: {
  isDark: boolean; label: string; metric: string;
  metricColour?: string; sub: string;
  extra?: React.ReactNode; pulse?: boolean;
}) {
  const T = isDark ? DARK : LIGHT;
  return (
    <div style={{
      background: T.surface, borderRadius: 12,
      border: `1px solid ${T.border}`,
      padding: "18px 20px 16px",
    }}>
      <div style={{
        fontSize: 10, fontWeight: 600, color: T.text.m,
        letterSpacing: "0.07em", textTransform: "uppercase", marginBottom: 12,
      }}>
        {label}
      </div>
      <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: extra ? 8 : 4 }}>
        {pulse && (
          <span style={{
            width: 8, height: 8, borderRadius: "50%", background: RED, flexShrink: 0,
            animation: "pulse 1.2s ease-in-out infinite",
          }} />
        )}
        <span style={{
          fontFamily: MONO, fontSize: 30, fontWeight: 500, letterSpacing: "-0.03em",
          color: metricColour ?? T.text.p, lineHeight: 1,
        }}>
          {metric}
        </span>
      </div>
      {extra && <div style={{ marginBottom: 6 }}>{extra}</div>}
      <div style={{ fontSize: 11, color: T.text.m }}>{sub}</div>
    </div>
  );
}

// ── CompanyRow ─────────────────────────────────────────────────────────────────

function CompanyRow({ company, isDark, isLast, onClick }: {
  company: Company; isDark: boolean; isLast: boolean; onClick: () => void;
}) {
  const [hovered, setHovered] = useState(false);
  const T  = isDark ? DARK : LIGHT;
  const runaway = company.evalsToday > 30;
  return (
    <div onClick={onClick}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      style={{
        display: "grid",
        gridTemplateColumns: "2fr 130px 100px 100px 110px 130px",
        padding: "13px 20px",
        borderBottom: isLast ? "none" : `1px solid ${T.border}`,
        cursor: "pointer",
        background: hovered ? T.elevated : "transparent",
        transition: "background 120ms",
        alignItems: "center",
      }}>
      <span style={{ fontSize: 13, fontWeight: 600, color: T.text.p }}>{company.name}</span>
      <span><PlanBadge plan={company.plan} /></span>
      <span><AgentDots agents={company.agents} /></span>
      <span style={{
        fontFamily: MONO, fontSize: 13,
        color: runaway ? RED : T.text.s,
        fontWeight: runaway ? 600 : 400,
      }}>
        {company.evalsToday}
        {runaway && <span style={{ fontSize: 10, marginLeft: 4 }}>⚠</span>}
      </span>
      <span><HealthPill health={company.health} /></span>
      <span><BillingPill billing={company.billing} days={company.billingDays} /></span>
    </div>
  );
}

// ── AlertRow ───────────────────────────────────────────────────────────────────

function AlertRow({ alert, isDark, isLast, onAction }: {
  alert: AlertItem; isDark: boolean; isLast: boolean; onAction: () => void;
}) {
  const T      = isDark ? DARK : LIGHT;
  const colour = alert.severity === "red" ? RED : AMBER;
  return (
    <div style={{
      display: "grid",
      gridTemplateColumns: "20px 44px 160px 1fr auto",
      gap: 14, alignItems: "center",
      padding: "12px 20px",
      borderBottom: isLast ? "none" : `1px solid ${T.border}`,
    }}>
      <span style={{
        width: 8, height: 8, borderRadius: "50%", background: colour, flexShrink: 0,
        animation: alert.severity === "red" ? "pulse 1.2s ease-in-out infinite" : undefined,
      }} />
      <span style={{ fontFamily: MONO, fontSize: 11, color: T.text.m }}>{alert.time}</span>
      <span style={{
        fontSize: 12, color: colour, fontWeight: 500,
        overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap",
      }}>
        {alert.company ?? "Platform-wide"}
      </span>
      <span style={{ fontSize: 12, color: T.text.s }}>{alert.message}</span>
      <button onClick={e => { e.stopPropagation(); onAction(); }} style={{
        background: "transparent", border: `1px solid ${colour}`,
        borderRadius: 6, padding: "4px 12px", fontSize: 11,
        fontFamily: FONT, color: colour, cursor: "pointer", fontWeight: 500,
        whiteSpace: "nowrap",
      }}>{alert.action}</button>
    </div>
  );
}

// ── Log panel ──────────────────────────────────────────────────────────────────

function LogPanel({ isDark, onClose }: { isDark: boolean; onClose: () => void }) {
  const T = isDark ? DARK : LIGHT;
  return (
    <>
      <div onClick={onClose} style={{
        position: "fixed", inset: 0, background: "rgba(0,0,0,0.45)",
        zIndex: 40, animation: "fadein 160ms ease",
      }} />
      <div style={{
        position: "fixed", top: 0, right: 0, bottom: 0, width: 520,
        background: T.surface, borderLeft: `1px solid ${T.border}`,
        borderTop: `3px solid ${RED}`,
        zIndex: 50, overflowY: "auto", fontFamily: FONT,
        animation: "slidein 220ms cubic-bezier(0.22,1,0.36,1)",
      }}>
        <div style={{
          padding: "18px 24px", borderBottom: `1px solid ${T.border}`,
          display: "flex", justifyContent: "space-between", alignItems: "center",
        }}>
          <div>
            <div style={{ fontSize: 14, fontWeight: 600, color: T.text.p }}>Agent logs</div>
            <div style={{ fontSize: 11, color: T.text.m, marginTop: 2 }}>
              Last 12 entries · Brightline Logistics · run brightline-4491
            </div>
          </div>
          <button onClick={onClose} style={{
            background: "none", border: "none", cursor: "pointer",
            color: T.text.m, fontSize: 18, padding: 4,
          }}>✕</button>
        </div>
        <div style={{ padding: "16px 24px", display: "flex", flexDirection: "column", gap: 10 }}>
          {LOG_LINES.map((l, i) => {
            const time = `14:${String(23 - i).padStart(2, "0")}`;
            const lc   = l.level === "ERROR" ? RED : l.level === "WARN" ? AMBER : T.text.m;
            return (
              <div key={i} style={{
                display: "grid", gridTemplateColumns: "40px 46px 1fr", gap: 10,
                alignItems: "baseline",
              }}>
                <span style={{ fontFamily: MONO, fontSize: 11, color: T.text.d }}>{time}</span>
                <span style={{ fontFamily: MONO, fontSize: 11, fontWeight: 600, color: lc }}>{l.level}</span>
                <span style={{ fontFamily: MONO, fontSize: 11, color: T.text.s, lineHeight: 1.5 }}>{l.msg}</span>
              </div>
            );
          })}
        </div>
      </div>
    </>
  );
}

// ── Detail panel ───────────────────────────────────────────────────────────────

function DetailPanel({ company, isDark, onClose }: {
  company: Company; isDark: boolean; onClose: () => void;
}) {
  const T      = isDark ? DARK : LIGHT;
  const usePct = Math.round((company.apiUsed / company.apiLimit) * 100);
  const barCol = usePct > 90 ? RED : usePct > 70 ? AMBER : TEAL;
  const [confirmSuspend, setConfirmSuspend] = useState(false);

  return (
    <>
      <div onClick={onClose} style={{
        position: "fixed", inset: 0, background: "rgba(0,0,0,0.45)",
        zIndex: 40, animation: "fadein 160ms ease",
      }} />
      <div style={{
        position: "fixed", top: 0, right: 0, bottom: 0, width: 480,
        background: T.surface, borderLeft: `1px solid ${T.border}`,
        zIndex: 50, overflowY: "auto", display: "flex", flexDirection: "column",
        animation: "slidein 220ms cubic-bezier(0.22,1,0.36,1)",
        fontFamily: FONT,
      }}>
        {/* Panel header */}
        <div style={{
          borderTop: `3px solid ${PURPLE}`,
          padding: "20px 24px 16px",
          borderBottom: `1px solid ${T.border}`,
          display: "flex", alignItems: "flex-start", justifyContent: "space-between",
          flexShrink: 0,
        }}>
          <div>
            <div style={{ fontSize: 15, fontWeight: 600, color: T.text.p, marginBottom: 8 }}>
              {company.name}
            </div>
            <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
              <PlanBadge plan={company.plan} />
              <span style={{ fontSize: 11, color: T.text.m }}>Since {company.since}</span>
            </div>
          </div>
          <button onClick={onClose} style={{
            background: "none", border: "none", cursor: "pointer",
            color: T.text.m, fontSize: 20, padding: 4, lineHeight: 1,
          }}>✕</button>
        </div>

        {/* Panel body */}
        <div style={{ padding: "20px 24px", flex: 1, display: "flex", flexDirection: "column", gap: 22, overflowY: "auto" }}>

          {/* Agents */}
          <section>
            <Label>Active agents</Label>
            <div style={{ display: "flex", flexDirection: "column", gap: 9 }}>
              {company.agents.map((a, i) => (
                <div key={i} style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
                  <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                    <span style={{ width: 8, height: 8, borderRadius: "50%", background: a.colour, flexShrink: 0 }} />
                    <span style={{ fontSize: 13, color: T.text.s }}>{a.name}</span>
                  </div>
                  <span style={{ fontFamily: MONO, fontSize: 12, color: T.text.m }}>{a.evals} evals today</span>
                </div>
              ))}
            </div>
          </section>

          {/* Last eval */}
          <section>
            <Label>Last evaluation</Label>
            <div style={{ fontSize: 13, color: T.text.s }}>
              {company.lastEval}
              {" · "}
              <span style={{ color: T.text.p }}>{company.lastAgent}</span>
            </div>
          </section>

          {/* API usage */}
          <section>
            <Label>API usage this month</Label>
            <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 8 }}>
              <span style={{ fontFamily: MONO, fontSize: 14, color: T.text.p, fontWeight: 500 }}>
                {company.apiUsed.toLocaleString()}
              </span>
              <span style={{ fontFamily: MONO, fontSize: 12, color: T.text.m }}>
                / {company.apiLimit.toLocaleString()} calls
              </span>
            </div>
            <div style={{
              height: 6, borderRadius: 3,
              background: isDark ? "#1E2240" : "#E0D9F7",
              overflow: "hidden",
            }}>
              <div style={{
                height: "100%", width: `${Math.min(usePct, 100)}%`, borderRadius: 3,
                background: barCol, transition: "width 400ms ease",
              }} />
            </div>
            <div style={{ fontSize: 11, color: usePct > 90 ? RED : T.text.m, marginTop: 4 }}>
              {usePct}% used
            </div>
          </section>

          {/* Billing */}
          <section>
            <Label>Billing</Label>
            <div style={{ display: "flex", flexDirection: "column", gap: 5 }}>
              <BillingPill billing={company.billing} days={company.billingDays} />
              <div style={{ fontSize: 12, color: T.text.m }}>Next invoice: {company.nextInvoice}</div>
            </div>
          </section>

          {/* Logs link */}
          <div>
            <a href="#" onClick={e => e.preventDefault()} style={{
              fontSize: 13, color: PURPLE, textDecoration: "none", fontWeight: 500,
            }}>
              View full company logs →
            </a>
          </div>

          {/* Admin actions */}
          <div style={{
            borderTop: `1px solid ${T.border}`,
            paddingTop: 20, marginTop: "auto",
            display: "flex", flexDirection: "column", gap: 10,
          }}>
            <div style={{
              fontSize: 10, fontWeight: 600, color: PURPLE,
              letterSpacing: "0.07em", textTransform: "uppercase", marginBottom: 4,
            }}>
              Admin actions
            </div>
            <button style={{
              background: PURPLE, color: "#fff", border: "none", borderRadius: 8,
              padding: "10px 16px", fontSize: 13, fontFamily: FONT, fontWeight: 500,
              cursor: "pointer", textAlign: "left",
            }}>
              + Add agent to this company
            </button>
            <button style={{
              background: "transparent", color: T.text.s,
              border: `1px solid ${T.border}`,
              borderRadius: 8, padding: "10px 16px", fontSize: 13,
              fontFamily: FONT, fontWeight: 500, cursor: "pointer", textAlign: "left",
            }}>
              Download usage report
            </button>
            {!confirmSuspend ? (
              <button onClick={() => setConfirmSuspend(true)} style={{
                background: "transparent", color: RED,
                border: `1px solid ${RED}`,
                borderRadius: 8, padding: "10px 16px", fontSize: 13,
                fontFamily: FONT, fontWeight: 500, cursor: "pointer", textAlign: "left",
                marginTop: 4,
              }}>
                Suspend company
              </button>
            ) : (
              <div style={{
                border: `1px solid ${RED}`, borderRadius: 8, padding: "12px 16px",
                background: RED + "10",
              }}>
                <div style={{ fontSize: 12, color: RED, fontWeight: 600, marginBottom: 8 }}>
                  Confirm suspension?
                </div>
                <div style={{ fontSize: 12, color: T.text.m, marginBottom: 12 }}>
                  All evaluations will be paused. This action is logged.
                </div>
                <div style={{ display: "flex", gap: 8 }}>
                  <button style={{
                    background: RED, color: "#fff", border: "none",
                    borderRadius: 6, padding: "6px 14px", fontSize: 12,
                    fontFamily: FONT, fontWeight: 600, cursor: "pointer",
                  }}>
                    Confirm suspend
                  </button>
                  <button onClick={() => setConfirmSuspend(false)} style={{
                    background: "transparent", color: T.text.m,
                    border: `1px solid ${T.border}`, borderRadius: 6,
                    padding: "6px 14px", fontSize: 12, fontFamily: FONT, cursor: "pointer",
                  }}>
                    Cancel
                  </button>
                </div>
              </div>
            )}
          </div>
        </div>
      </div>
    </>
  );
}

// ── Tiny helper ────────────────────────────────────────────────────────────────

function Label({ children }: { children: React.ReactNode }) {
  return (
    <div style={{
      fontSize: 10, fontWeight: 600, color: "#7C7AAD",
      letterSpacing: "0.07em", textTransform: "uppercase", marginBottom: 10,
    }}>
      {children}
    </div>
  );
}

// ── Page ───────────────────────────────────────────────────────────────────────

export default function AdminPage() {
  const [isDark,   setIsDark]   = useState(true);
  const [selected, setSelected] = useState<Company | null>(null);
  const [logOpen,  setLogOpen]  = useState(false);

  const T = isDark ? DARK : LIGHT;

  const saasCount    = COMPANIES.filter(c => c.plan !== "On-premise").length;
  const onPremCount  = COMPANIES.filter(c => c.plan === "On-premise").length;
  const activeEvals  = COMPANIES.reduce((s, c) => s + c.evalsToday, 0);
  const evalCos      = COMPANIES.filter(c => c.evalsToday > 0).length;
  const alertCount   = ALERTS.length;
  const apiToday     = SPARK[SPARK.length - 1];

  const sysStatus =
    COMPANIES.some(c => c.health === "degraded") ? "degraded" :
    COMPANIES.some(c => c.health === "warning")  ? "warning"  : "ok";

  return (
    <div style={{ minHeight: "100vh", background: T.bg, fontFamily: FONT }}>
      <style suppressHydrationWarning>{CSS}</style>

      {/* ── Top bar ──────────────────────────────────────────────────────────── */}
      <header style={{
        position: "sticky", top: 0, zIndex: 30,
        background: T.topbar, backdropFilter: "blur(14px)",
        borderBottom: `1px solid ${T.border}`,
        borderTop: `3px solid ${PURPLE}`,
        height: 56, display: "flex", alignItems: "center", padding: "0 28px",
      }}>
        {/* Left: logo + label */}
        <div style={{ display: "flex", alignItems: "center", gap: 10, flex: 1 }}>
          <div style={{
            width: 28, height: 28, borderRadius: 7, flexShrink: 0,
            background: `linear-gradient(135deg, ${TEAL}, ${PURPLE})`,
            display: "flex", alignItems: "center", justifyContent: "center",
          }}>
            <svg width="13" height="13" viewBox="0 0 13 13" fill="none">
              <circle cx="6.5" cy="6.5" r="2.5" fill="white" opacity="0.95" />
              <circle cx="6.5" cy="6.5" r="5.5" stroke="white" strokeWidth="0.9" opacity="0.35" />
            </svg>
          </div>
          <div>
            <div style={{ fontSize: 13, fontWeight: 600, color: T.text.p, lineHeight: 1.15 }}>
              Platform AI
            </div>
            <div style={{ fontSize: 10, color: PURPLE, fontWeight: 600, letterSpacing: "0.05em", lineHeight: 1 }}>
              Admin console
            </div>
          </div>
        </div>

        {/* Centre: system status */}
        <div style={{ flex: 1, display: "flex", justifyContent: "center" }}>
          {sysStatus === "ok"       && <StatusPill colour={TEAL}  label="All systems operational" pulse={false} />}
          {sysStatus === "warning"  && <StatusPill colour={AMBER} label="1 service degraded"      pulse />}
          {sysStatus === "degraded" && <StatusPill colour={RED}   label="Critical alert"           pulse />}
        </div>

        {/* Right: theme toggle + operator */}
        <div style={{ flex: 1, display: "flex", justifyContent: "flex-end", alignItems: "center", gap: 14 }}>
          <button onClick={() => setIsDark(d => !d)} style={{
            background: isDark ? "#1C1F35" : "#EDE9FE",
            border: `1px solid ${T.border}`, borderRadius: 7,
            padding: "5px 11px", fontSize: 11, fontFamily: FONT,
            color: T.text.s, cursor: "pointer",
          }}>
            {isDark ? "☀ Light" : "☾ Dark"}
          </button>
          <div style={{ display: "flex", alignItems: "center", gap: 9 }}>
            <div style={{
              width: 28, height: 28, borderRadius: "50%",
              background: PURPLE + "28", border: `1px solid ${PURPLE}50`,
              display: "flex", alignItems: "center", justifyContent: "center",
              fontSize: 11, fontWeight: 700, color: PURPLE,
            }}>K</div>
            <div>
              <div style={{ fontSize: 12, fontWeight: 500, color: T.text.p, lineHeight: 1.2 }}>Kishore V</div>
              <div style={{ fontSize: 10, color: PURPLE, fontWeight: 600, letterSpacing: "0.04em" }}>Admin</div>
            </div>
          </div>
        </div>
      </header>

      {/* ── Main content ─────────────────────────────────────────────────────── */}
      <main style={{ maxWidth: 1300, margin: "0 auto", padding: "28px 28px 72px" }}>

        {/* Row 1: Health tiles */}
        <div style={{
          display: "grid", gridTemplateColumns: "repeat(4, 1fr)",
          gap: 16, marginBottom: 28,
        }}>
          <HealthTile
            isDark={isDark}
            label="Active companies"
            metric={String(COMPANIES.length)}
            sub={`${saasCount} SaaS · ${onPremCount} on-premise`}
          />
          <HealthTile
            isDark={isDark}
            label="Active evaluations"
            metric={String(activeEvals)}
            sub={`across ${evalCos} compan${evalCos === 1 ? "y" : "ies"}`}
          />
          <HealthTile
            isDark={isDark}
            label="API calls today"
            metric={apiToday.toLocaleString()}
            sub="past 12 hours"
            extra={<Sparkline data={SPARK} colour={PURPLE} />}
          />
          <HealthTile
            isDark={isDark}
            label="Alerts"
            metric={String(alertCount)}
            metricColour={alertCount > 0 ? RED : TEAL}
            sub={alertCount > 0 ? "requiring attention" : "no active alerts"}
            pulse={alertCount > 0}
          />
        </div>

        {/* Row 2: Company roster */}
        <section style={{ marginBottom: 28 }}>
          <div style={{
            fontSize: 12, fontWeight: 600, color: T.text.p,
            marginBottom: 12, letterSpacing: "0.02em",
          }}>
            Companies
          </div>
          <div style={{
            background: T.surface, borderRadius: 12,
            border: `1px solid ${T.border}`, overflow: "hidden",
          }}>
            {/* Table header */}
            <div style={{
              display: "grid",
              gridTemplateColumns: "2fr 130px 100px 100px 110px 130px",
              padding: "10px 20px",
              borderBottom: `1px solid ${T.border}`,
              fontSize: 10, fontWeight: 600, color: T.text.m,
              letterSpacing: "0.06em", textTransform: "uppercase",
            }}>
              <span>Company</span>
              <span>Plan</span>
              <span>Agents</span>
              <span>Evals today</span>
              <span>Health</span>
              <span>Billing</span>
            </div>

            {COMPANIES.map((co, i) => (
              <CompanyRow
                key={co.id}
                company={co}
                isDark={isDark}
                isLast={i === COMPANIES.length - 1}
                onClick={() => setSelected(co)}
              />
            ))}
          </div>
        </section>

        {/* Row 3: Alerts (conditional) */}
        {ALERTS.length > 0 && (
          <section style={{ marginBottom: 28 }}>
            <div style={{
              fontSize: 12, fontWeight: 600, color: T.text.p,
              marginBottom: 12, letterSpacing: "0.02em",
            }}>
              System alerts
            </div>
            <div style={{
              background: T.surface, borderRadius: 12,
              border: `1px solid ${T.border}`, overflow: "hidden",
            }}>
              {ALERTS.map((alert, i) => (
                <AlertRow
                  key={alert.id}
                  alert={alert}
                  isDark={isDark}
                  isLast={i === ALERTS.length - 1}
                  onAction={() => setLogOpen(true)}
                />
              ))}
            </div>
          </section>
        )}

        {/* Export */}
        <button style={{
          background: "transparent", border: `1px solid ${T.border}`,
          borderRadius: 8, padding: "9px 18px",
          fontSize: 12, fontFamily: FONT, fontWeight: 500, color: T.text.s,
          cursor: "pointer", display: "inline-flex", alignItems: "center", gap: 8,
        }}>
          <svg width="13" height="13" viewBox="0 0 13 13" fill="none">
            <path d="M6.5 1v7.5M4 6l2.5 2.5L9 6M1.5 10.5h10"
              stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
          Export platform report (CSV)
        </button>
      </main>

      {/* Overlays */}
      {selected && (
        <DetailPanel company={selected} isDark={isDark} onClose={() => setSelected(null)} />
      )}
      {logOpen && (
        <LogPanel isDark={isDark} onClose={() => setLogOpen(false)} />
      )}
    </div>
  );
}
