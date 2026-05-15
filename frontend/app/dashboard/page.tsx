"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { AGENT_COLOUR, COMPANY, FONT, SERIF, PALETTE, TOKENS, BG_GRADIENT, TOPBAR_BG, agentColour, detectAgentType } from "@/lib/theme";

// ─── Department pills (mock — replace with /api/v1/agents) ────────────────────
const DEPT_AGENTS = [
  { id: "proc-1",  type: "procurement", name: "IT Procurement",   activeCount: 2, activeLabel: "running"     },
  { id: "hr-1",    type: "hr",          name: "People & Culture",  activeCount: 3, activeLabel: "in progress" },
  { id: "legal-1", type: "legal",       name: "Legal & Compliance", activeCount: 0, activeLabel: "active"     },
];

// FONT, SERIF, AGENT_COLOUR, detectAgentType imported from @/lib/theme

// ─── Data types ───────────────────────────────────────────────────────────────

interface EvalRun {
  run_id: string;
  rfp_title: string;
  department: string;
  status: "running" | "pending_approval" | "complete" | "blocked";
  vendor_count: number;
  shortlisted_count: number;
  rejected_count: number;
  approval_tier?: number;
  approver_role?: string;
  sla_deadline?: string;
  started_at: string;
}

// ─── SVG Icons ────────────────────────────────────────────────────────────────

function IconGrid({ colour = "currentColor" }: { colour?: string }) {
  return (
    <svg width="18" height="18" viewBox="0 0 18 18" fill="none">
      <rect x="1"  y="1"  width="7" height="7" rx="1.5" fill={colour} opacity="0.9" />
      <rect x="10" y="1"  width="7" height="7" rx="1.5" fill={colour} opacity="0.65" />
      <rect x="1"  y="10" width="7" height="7" rx="1.5" fill={colour} opacity="0.65" />
      <rect x="10" y="10" width="7" height="7" rx="1.5" fill={colour} opacity="0.45" />
    </svg>
  );
}

function IconDocumentStack({ colour }: { colour: string }) {
  return (
    <svg width="18" height="18" viewBox="0 0 18 18" fill="none">
      <rect x="2" y="3" width="10" height="1.5" rx="0.75" fill={colour} opacity="0.35" />
      <rect x="1" y="5.5" width="12" height="1.5" rx="0.75" fill={colour} opacity="0.55" />
      <rect x="1" y="8" width="16" height="8" rx="2" fill={colour} opacity="0.85" />
      <path d="M3.5 12h11M3.5 14h6" stroke="#090C12" strokeWidth="1.1" strokeLinecap="round" />
    </svg>
  );
}

function IconPeople({ colour }: { colour: string }) {
  return (
    <svg width="18" height="18" viewBox="0 0 18 18" fill="none">
      <circle cx="6.5" cy="5.5" r="2.5" fill={colour} opacity="0.9" />
      <circle cx="13" cy="6" r="2" fill={colour} opacity="0.5" />
      <path d="M0 16c0-3.314 2.91-6 6.5-6S13 12.686 13 16" fill={colour} opacity="0.85" />
      <path d="M13 10c1.933 0 3.5 1.567 3.5 3.5" stroke={colour} strokeWidth="1.3" strokeLinecap="round" opacity="0.5" />
    </svg>
  );
}

function IconScales({ colour }: { colour: string }) {
  return (
    <svg width="18" height="18" viewBox="0 0 18 18" fill="none">
      <line x1="9" y1="2" x2="9" y2="16" stroke={colour} strokeWidth="1.2" strokeLinecap="round" />
      <line x1="3" y1="16" x2="15" y2="16" stroke={colour} strokeWidth="1.2" strokeLinecap="round" />
      <line x1="4" y1="6.5" x2="14" y2="6.5" stroke={colour} strokeWidth="1" strokeLinecap="round" opacity="0.5" />
      <path d="M4 6.5L2.5 11h3L4 6.5Z" fill={colour} opacity="0.7" />
      <path d="M14 6.5l-1.5 4.5h3L14 6.5Z" fill={colour} opacity="0.5" />
    </svg>
  );
}

function IconBarChart({ colour }: { colour: string }) {
  return (
    <svg width="18" height="18" viewBox="0 0 18 18" fill="none">
      <rect x="1"  y="12" width="3.5" height="5" rx="1" fill={colour} opacity="0.4" />
      <rect x="7"  y="7"  width="3.5" height="10" rx="1" fill={colour} opacity="0.65" />
      <rect x="13" y="2"  width="3.5" height="15" rx="1" fill={colour} opacity="0.9" />
    </svg>
  );
}

function IconFlowChart({ colour }: { colour: string }) {
  return (
    <svg width="18" height="18" viewBox="0 0 18 18" fill="none">
      <rect x="5" y="1" width="8" height="4.5" rx="1.5" fill={colour} opacity="0.9" />
      <rect x="1" y="12.5" width="6.5" height="4.5" rx="1.5" fill={colour} opacity="0.7" />
      <rect x="10.5" y="12.5" width="6.5" height="4.5" rx="1.5" fill={colour} opacity="0.7" />
      <path d="M9 5.5v3M9 8.5L4.5 12M9 8.5l4.5 3.5" stroke={colour} strokeWidth="1.2" strokeLinecap="round" />
    </svg>
  );
}

function IconSupport({ colour }: { colour: string }) {
  return (
    <svg width="18" height="18" viewBox="0 0 18 18" fill="none">
      <path d="M2 3h14a1.5 1.5 0 0 1 1.5 1.5v7A1.5 1.5 0 0 1 16 13H6l-4 4V4.5A1.5 1.5 0 0 1 3.5 3Z" fill={colour} opacity="0.8" />
      <path d="M5 7.5h8M5 10h4.5" stroke="#090C12" strokeWidth="1.1" strokeLinecap="round" />
    </svg>
  );
}

function IconAdminSettings() {
  return (
    <svg width="17" height="17" viewBox="0 0 17 17" fill="none">
      <rect x="1" y="1" width="6.5" height="6.5" rx="1.5" stroke="currentColor" strokeWidth="1.2" />
      <rect x="9.5" y="1" width="6.5" height="6.5" rx="1.5" stroke="currentColor" strokeWidth="1.2" />
      <rect x="1" y="9.5" width="6.5" height="6.5" rx="1.5" stroke="currentColor" strokeWidth="1.2" />
      <path d="M12.75 9.5v7M9.5 12.75h7" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" />
    </svg>
  );
}

const ICONS: Record<string, (c: string) => React.ReactNode> = {
  procurement: (c) => <IconDocumentStack colour={c} />,
  hr:          (c) => <IconPeople colour={c} />,
  legal:       (c) => <IconScales colour={c} />,
  finance:     (c) => <IconBarChart colour={c} />,
  operations:  (c) => <IconFlowChart colour={c} />,
  support:     (c) => <IconSupport colour={c} />,
};

function LogoMark({ size = 22 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 22 22" fill="none">
      <rect width="22" height="22" rx="5" fill="url(#lgo)" />
      <path d="M6 11l3.5 3.5L17 7" stroke="white" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" />
      <defs>
        <linearGradient id="lgo" x1="0" y1="0" x2="22" y2="22" gradientUnits="userSpaceOnUse">
          <stop stopColor="#00D4AA" />
          <stop offset="1" stopColor="#7C3AED" />
        </linearGradient>
      </defs>
    </svg>
  );
}

// ─── Company Admin Rail ────────────────────────────────────────────────────────

function CompanyAdminRail({ activeSection, onNavigate }: {
  activeSection: "overview" | string;
  onNavigate: (section: "overview" | string, href: string) => void;
}) {
  const [expanded, setExpanded] = useState(false);
  const [hoveredId, setHoveredId] = useState<string | null>(null);

  const overviewActive = activeSection === "overview";

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
      {/* Logo */}
      <div style={{ height: 60, width: "100%", flexShrink: 0, display: "flex", alignItems: "center", padding: expanded ? "0 16px" : "0", justifyContent: expanded ? "flex-start" : "center", borderBottom: "1px solid #181C28", gap: 12 }}>
        <LogoMark size={22} />
        {expanded && <span style={{ fontSize: 12, fontWeight: 700, color: "#CBD5E1", fontFamily: FONT, letterSpacing: "0.08em", textTransform: "uppercase", whiteSpace: "nowrap" }}>{COMPANY.shortName}</span>}
      </div>

      <div style={{ flex: 1, width: "100%", overflowY: "auto" }}>

        {/* Company overview — top item, default for CFO */}
        <div
          onClick={() => onNavigate("overview", "/dashboard")}
          onMouseEnter={() => setHoveredId("overview")}
          onMouseLeave={() => setHoveredId(null)}
          style={{
            position: "relative", height: 48, width: "100%", display: "flex",
            alignItems: "center", padding: expanded ? "0 14px" : "0",
            justifyContent: expanded ? "flex-start" : "center",
            cursor: "pointer", gap: 12,
            borderLeft: overviewActive ? "2px solid #CBD5E1" : "2px solid transparent",
            backgroundColor: overviewActive ? "#111828" : hoveredId === "overview" ? "#0F1420" : "transparent",
            marginTop: 6,
          }}
        >
          <div style={{
            width: 30, height: 30, borderRadius: 7, flexShrink: 0,
            display: "flex", alignItems: "center", justifyContent: "center",
            backgroundColor: overviewActive || hoveredId === "overview" ? "#FFFFFF14" : "transparent",
            border: overviewActive || hoveredId === "overview" ? "1px solid #FFFFFF25" : "1px solid transparent",
          }}>
            <IconGrid colour={overviewActive ? "#E2E8F0" : hoveredId === "overview" ? "#94A3B8" : "#4B5563"} />
          </div>
          {expanded && (
            <span style={{ fontSize: 12.5, fontWeight: overviewActive ? 700 : 400, color: overviewActive ? "#E2E8F0" : hoveredId === "overview" ? "#CBD5E1" : "#6B7280", fontFamily: FONT, whiteSpace: "nowrap" }}>
              Company overview
            </span>
          )}
          {!expanded && hoveredId === "overview" && (
            <div style={{ position: "absolute", left: 54, backgroundColor: "#1A1F2E", border: "1px solid #2A3040", borderRadius: 7, padding: "5px 11px", fontSize: 12, color: "#E2E8F0", whiteSpace: "nowrap", zIndex: 200, pointerEvents: "none", fontFamily: FONT, boxShadow: "0 4px 12px rgba(0,0,0,0.4)" }}>
              Company overview
            </div>
          )}
        </div>

        {/* Thin divider before agent icons */}
        <div style={{ height: 1, backgroundColor: "#181C28", margin: "6px 12px" }} />

        {/* Individual agent icons */}
        {DEPT_AGENTS.map((agent) => {
          const colour = AGENT_COLOUR[agent.type];
          const isActive = activeSection === agent.id;
          const isHov = hoveredId === agent.id;
          const lit = isActive || isHov;

          return (
            <div
              key={agent.id}
              onClick={() => onNavigate(agent.id, `/procurement/upload`)}
              onMouseEnter={() => setHoveredId(agent.id)}
              onMouseLeave={() => setHoveredId(null)}
              style={{
                position: "relative", height: 44, width: "100%", display: "flex",
                alignItems: "center", padding: expanded ? "0 14px" : "0",
                justifyContent: expanded ? "flex-start" : "center",
                cursor: "pointer", gap: 12,
                borderLeft: isActive ? `2px solid ${colour}` : "2px solid transparent",
                backgroundColor: isHov && !isActive ? "#111520" : "transparent",
                transition: "background-color 120ms",
              }}
            >
              <div style={{ width: 30, height: 30, borderRadius: 7, flexShrink: 0, display: "flex", alignItems: "center", justifyContent: "center", backgroundColor: lit ? `${colour}18` : "transparent", border: lit ? `1px solid ${colour}30` : "1px solid transparent", transition: "all 140ms" }}>
                {ICONS[agent.type]?.(lit ? colour : "#4B5563")}
              </div>
              {expanded && (
                <span style={{ fontSize: 12, fontFamily: FONT, fontWeight: isActive ? 600 : 400, color: isActive ? colour : isHov ? "#E2E8F0" : "#6B7280", whiteSpace: "nowrap", transition: "color 120ms" }}>
                  {agent.name}
                </span>
              )}
              {agent.activeCount > 0 && (
                <span style={{ position: "absolute", top: 9, right: expanded ? 12 : 8, width: 5, height: 5, borderRadius: "50%", backgroundColor: colour, boxShadow: `0 0 4px ${colour}AA` }} />
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

      {/* Bottom: Admin settings (company admin only) */}
      <div style={{ borderTop: "1px solid #181C28", paddingTop: 4, paddingBottom: 8, width: "100%" }}>
        <div
          onMouseEnter={() => setHoveredId("admin")}
          onMouseLeave={() => setHoveredId(null)}
          style={{ height: 44, width: "100%", display: "flex", alignItems: "center", justifyContent: expanded ? "flex-start" : "center", padding: expanded ? "0 14px" : 0, gap: 12, cursor: "pointer", color: hoveredId === "admin" ? "#94A3B8" : "#374151", transition: "color 120ms" }}
        >
          <IconAdminSettings />
          {expanded && <span style={{ fontSize: 12, fontFamily: FONT }}>Admin settings</span>}
        </div>
        <div style={{ height: 44, width: "100%", display: "flex", alignItems: "center", justifyContent: expanded ? "flex-start" : "center", padding: expanded ? "0 14px" : 0, gap: 12, cursor: "pointer" }}>
          <div style={{ width: 28, height: 28, borderRadius: "50%", background: "linear-gradient(135deg, #312E81, #4C1D95)", border: "1.5px solid #4338CA", display: "flex", alignItems: "center", justifyContent: "center", fontSize: 9, fontWeight: 700, color: "#C4B5FD", flexShrink: 0, fontFamily: FONT }}>
            MF
          </div>
          {expanded && <span style={{ fontSize: 12, color: "#6B7280", fontFamily: FONT, whiteSpace: "nowrap" }}>CFO · M. Fisher</span>}
        </div>
      </div>
    </div>
  );
}

// ─── Department pill strip ────────────────────────────────────────────────────

function DepartmentPillStrip({ onDrillDown }: { onDrillDown: (agentId: string) => void }) {
  const [hoveredId, setHoveredId] = useState<string | null>(null);

  return (
    <div>
      <p style={{ fontSize: 10, fontWeight: 700, color: "#2D3344", letterSpacing: "0.18em", textTransform: "uppercase", margin: "0 0 14px", fontFamily: FONT }}>
        Your departments
      </p>
      <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
        {DEPT_AGENTS.map((agent) => {
          const colour = AGENT_COLOUR[agent.type];
          const hov = hoveredId === agent.id;
          return (
            <button
              key={agent.id}
              onClick={() => onDrillDown(agent.id)}
              onMouseEnter={() => setHoveredId(agent.id)}
              onMouseLeave={() => setHoveredId(null)}
              style={{
                display: "inline-flex", alignItems: "center", gap: 8,
                padding: "7px 14px",
                backgroundColor: hov ? `${colour}22` : `${colour}12`,
                border: `1px solid ${hov ? colour + "80" : colour + "40"}`,
                borderRadius: 20,
                cursor: "pointer",
                fontFamily: FONT,
                transition: "all 140ms ease",
                boxShadow: hov ? `0 0 12px ${colour}20` : "none",
              }}
            >
              <span style={{ width: 7, height: 7, borderRadius: "50%", backgroundColor: colour, display: "inline-block", boxShadow: `0 0 6px ${colour}99`, flexShrink: 0 }} />
              <span style={{ fontSize: 12.5, fontWeight: 600, color: hov ? colour : "#94A3B8", whiteSpace: "nowrap", transition: "color 140ms" }}>
                {agent.name}
              </span>
              {agent.activeCount > 0 && (
                <span style={{ fontSize: 11, color: hov ? colour + "CC" : "#4B5563", fontFamily: FONT }}>
                  {agent.activeCount} {agent.activeLabel}
                </span>
              )}
            </button>
          );
        })}
      </div>
    </div>
  );
}

// ─── SLA countdown ────────────────────────────────────────────────────────────

function SlaCountdown({ deadline }: { deadline: string }) {
  const [remaining, setRemaining] = useState("");

  useEffect(() => {
    function calc() {
      const diff = new Date(deadline).getTime() - Date.now();
      if (diff <= 0) { setRemaining("OVERDUE"); return; }
      const h = Math.floor(diff / 3_600_000);
      const m = Math.floor((diff % 3_600_000) / 60_000);
      setRemaining(`${h}h ${m}m`);
    }
    calc();
    const t = setInterval(calc, 60_000);
    return () => clearInterval(t);
  }, [deadline]);

  const overdue = remaining === "OVERDUE";
  return (
    <span style={{ fontSize: 11, fontFamily: "var(--font-mono)", fontWeight: 700, color: overdue ? "#EF4444" : "#F59E0B", letterSpacing: "0.04em" }}>
      {overdue ? "⚠ OVERDUE" : `⏱ ${remaining}`}
    </span>
  );
}

// ─── KPI Card ─────────────────────────────────────────────────────────────────

function KpiCard({ label, value, accent }: { label: string; value: number; accent: string }) {
  return (
    <div style={{ backgroundColor: "var(--color-surface)", borderLeft: "1px solid var(--color-border)", borderRight: "1px solid var(--color-border)", borderBottom: "1px solid var(--color-border)", borderTop: `2px solid ${accent}`, borderRadius: 12, padding: "20px 24px", boxShadow: "var(--shadow-sm)" }}>
      <p style={{ fontSize: 11, color: "var(--color-text-muted)", fontFamily: FONT, margin: "0 0 10px", letterSpacing: "0.07em", textTransform: "uppercase" }}>{label}</p>
      <p style={{ fontSize: 36, fontWeight: 700, color: accent, fontFamily: FONT, margin: 0, lineHeight: 1 }}>{value}</p>
    </div>
  );
}

// ─── Approval row ─────────────────────────────────────────────────────────────

function ApprovalRow({ run, onClick }: { run: EvalRun; onClick: () => void }) {
  const [hovered, setHovered] = useState(false);
  const agentType = detectAgentType(run.department);
  const agentColour = AGENT_COLOUR[agentType];

  return (
    <div
      onClick={onClick}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      style={{
        display: "flex", alignItems: "center", gap: 14,
        padding: "14px 16px",
        backgroundColor: hovered ? "var(--color-surface-hover)" : "var(--color-surface)",
        border: `1px solid var(--color-border)`,
        borderLeft: `3px solid ${agentColour}`,
        borderRadius: 10, cursor: "pointer",
        transition: "all 140ms ease",
        boxShadow: hovered ? `0 4px 16px ${agentColour}15` : "none",
      }}
    >
      {/* Agent identity dot */}
      <div style={{ flexShrink: 0, display: "flex", flexDirection: "column", alignItems: "center", gap: 4 }}>
        <div style={{ width: 8, height: 8, borderRadius: "50%", backgroundColor: agentColour, boxShadow: `0 0 6px ${agentColour}BB` }} />
      </div>

      {/* Main info */}
      <div style={{ flex: 1, minWidth: 0 }}>
        <p style={{ fontSize: 13, fontWeight: 600, color: "var(--color-text-primary)", fontFamily: FONT, margin: "0 0 4px", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
          {run.rfp_title}
        </p>
        <p style={{ fontSize: 11, color: "var(--color-text-muted)", fontFamily: FONT, margin: 0 }}>
          <span style={{ color: agentColour, fontWeight: 500 }}>{run.department}</span>
          {" · "}Tier {run.approval_tier}
          {run.approver_role && ` — ${run.approver_role.replace(/_/g, " ")}`}
        </p>
      </div>

      {/* Right side */}
      <div style={{ textAlign: "right", flexShrink: 0 }}>
        {run.sla_deadline && <SlaCountdown deadline={run.sla_deadline} />}
        <p style={{ fontSize: 11, color: "var(--color-text-muted)", fontFamily: FONT, margin: "4px 0 0" }}>
          {run.shortlisted_count} shortlisted
        </p>
      </div>

      {/* Arrow */}
      <svg width="14" height="14" viewBox="0 0 14 14" fill="none" style={{ color: hovered ? "#6B7280" : "#2D3344", flexShrink: 0 }}>
        <path d="M3 7h8M8.5 4.5L11 7l-2.5 2.5" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
    </div>
  );
}

// ─── Run row (active / all) ───────────────────────────────────────────────────

function RunRow({ run, onClick }: { run: EvalRun; onClick: () => void }) {
  const [hovered, setHovered] = useState(false);
  const agentColour = AGENT_COLOUR[detectAgentType(run.department)];

  const STATUS_COLOUR: Record<EvalRun["status"], string> = {
    running:          "var(--color-info)",
    pending_approval: "var(--color-warning)",
    complete:         "var(--color-success)",
    blocked:          "var(--color-error)",
  };
  const sc = STATUS_COLOUR[run.status];

  return (
    <div
      onClick={onClick}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      style={{
        display: "flex", alignItems: "center", gap: 14, padding: "12px 16px",
        backgroundColor: hovered ? "var(--color-surface-hover)" : "transparent",
        border: "1px solid transparent",
        borderBottom: "1px solid var(--color-border)",
        cursor: "pointer", transition: "background-color 120ms",
      }}
    >
      <div style={{ width: 6, height: 6, borderRadius: "50%", backgroundColor: agentColour, flexShrink: 0 }} />
      <div style={{ flex: 1, minWidth: 0 }}>
        <p style={{ fontSize: 13, fontWeight: 500, color: "var(--color-text-primary)", fontFamily: FONT, margin: "0 0 3px", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{run.rfp_title}</p>
        <p style={{ fontSize: 11, color: "var(--color-text-muted)", fontFamily: FONT, margin: 0 }}>{run.department} · {run.vendor_count} vendors</p>
      </div>
      <div style={{ display: "flex", alignItems: "center", gap: 6, flexShrink: 0 }}>
        {run.status === "running" && (
          <span style={{ width: 6, height: 6, borderRadius: "50%", backgroundColor: sc, display: "inline-block", animation: "pulse 2s infinite" }} />
        )}
        <span style={{ fontSize: 11, fontWeight: 600, color: sc, fontFamily: FONT, letterSpacing: "0.02em" }}>
          {run.status.replace(/_/g, " ")}
        </span>
      </div>
    </div>
  );
}

// ─── Section card wrapper ─────────────────────────────────────────────────────

function SectionCard({ title, accent, children }: { title: React.ReactNode; accent: string; children: React.ReactNode }) {
  return (
    <div style={{ backgroundColor: "var(--color-surface)", border: "1px solid var(--color-border)", borderTop: `2px solid ${accent}`, borderRadius: 14, overflow: "hidden", boxShadow: "var(--shadow-sm)" }}>
      <div style={{ padding: "14px 20px 12px", borderBottom: "1px solid var(--color-border)" }}>
        <p style={{ margin: 0, fontSize: 12, fontWeight: 600, color: "var(--color-text-secondary)", fontFamily: FONT, display: "flex", alignItems: "center", gap: 8 }}>
          {title}
        </p>
      </div>
      <div style={{ padding: "4px 0 8px" }}>
        {children}
      </div>
    </div>
  );
}

// ─── Page ─────────────────────────────────────────────────────────────────────

export default function DashboardPage() {
  const router = useRouter();
  const [runs, setRuns] = useState<EvalRun[]>([]);
  const [loading, setLoading] = useState(true);
  const [activeSection, setActiveSection] = useState<"overview" | string>("overview");
  const [pageOpacity, setPageOpacity] = useState(0);

  useEffect(() => {
    const t = setTimeout(() => setPageOpacity(1), 40);
    return () => clearTimeout(t);
  }, []);

  useEffect(() => {
    const token = localStorage.getItem("access_token");
    fetch("/api/v1/evaluate/list", {
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    })
      .then((r) => r.json())
      .then((d) => { setRuns(d.runs ?? []); setLoading(false); })
      .catch(() => setLoading(false));
  }, []);

  const pending = runs.filter(r => r.status === "pending_approval");
  const active  = runs.filter(r => r.status === "running");
  const rest    = runs.filter(r => r.status !== "pending_approval" && r.status !== "running");

  function handleRailNavigate(section: "overview" | string, href: string) {
    setActiveSection(section);
    if (section !== "overview") {
      setTimeout(() => router.push(href + "?from=overview"), 200);
    }
  }

  function handleDrillDown(agentId: string) {
    const agent = DEPT_AGENTS.find(a => a.id === agentId);
    const dept = agent ? encodeURIComponent(agent.name) : agentId;
    router.push(`/dashboard/department/${dept}`);
  }

  const drilledAgent = activeSection !== "overview"
    ? DEPT_AGENTS.find(a => a.id === activeSection)
    : null;

  return (
    <div style={{ minHeight: "100vh", background: BG_GRADIENT, fontFamily: FONT, opacity: pageOpacity, transition: "opacity 220ms ease" }}>

      <CompanyAdminRail activeSection={activeSection} onNavigate={handleRailNavigate} />

      <div style={{ marginLeft: 48, display: "flex", flexDirection: "column", minHeight: "100vh" }}>

        {/* Top bar */}
        <header style={{
          height: 60, position: "sticky", top: 0, zIndex: 40,
          backgroundColor: TOPBAR_BG, backdropFilter: "blur(12px)",
          borderBottom: "1px solid var(--topbar-border)",
          display: "flex", alignItems: "center", justifyContent: "space-between",
          padding: "0 36px", flexShrink: 0, gap: 16,
        }}>
          <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
            <span style={{ fontSize: 11, fontWeight: 700, color: "var(--color-text-muted)", letterSpacing: "0.14em", textTransform: "uppercase", fontFamily: FONT }}>
              {COMPANY.platformName}
            </span>
            {drilledAgent && (
              <>
                <span style={{ color: "var(--color-text-muted)", fontSize: 13 }}>›</span>
                <span style={{ fontSize: 12, color: AGENT_COLOUR[drilledAgent.type], fontWeight: 600, fontFamily: FONT }}>
                  {drilledAgent.name}
                </span>
                <button
                  onClick={() => setActiveSection("overview")}
                  style={{ marginLeft: 8, fontSize: 11, color: "var(--color-text-muted)", fontFamily: FONT, background: "none", border: "1px solid var(--color-border)", borderRadius: 6, padding: "3px 10px", cursor: "pointer" }}
                >
                  ← Back
                </button>
              </>
            )}
          </div>

          <div style={{ display: "flex", alignItems: "center", gap: 16 }}>
            <button
              onClick={() => router.push("/procurement/upload")}
              style={{ fontSize: 12, fontWeight: 600, color: "var(--color-accent)", fontFamily: FONT, background: "none", border: "1px solid var(--color-border-strong)", borderRadius: 8, padding: "7px 16px", cursor: "pointer", letterSpacing: "0.02em", transition: "background var(--transition), border-color var(--transition)" }}
            >
              + New Evaluation
            </button>
            <div style={{ textAlign: "right" }}>
              <div style={{ fontSize: 13, color: "var(--color-text-secondary)", fontWeight: 600, lineHeight: 1.3 }}>M. Fisher</div>
              <div style={{ fontSize: 11, color: "var(--color-text-muted)", lineHeight: 1.3 }}>CFO · {COMPANY.shortName}</div>
            </div>
            <div style={{ width: 34, height: 34, borderRadius: "50%", background: "linear-gradient(135deg, #312E81, #4C1D95)", border: "1.5px solid #4338CA", display: "flex", alignItems: "center", justifyContent: "center", fontSize: 11, fontWeight: 700, color: "#C4B5FD", flexShrink: 0, fontFamily: FONT }}>
              MF
            </div>
          </div>
        </header>

        {/* Main content */}
        <main style={{ flex: 1, width: "100%", maxWidth: 1040, margin: "0 auto", padding: "52px 36px 80px" }}>

          {/* Page heading */}
          <div style={{ marginBottom: 40 }}>
            <p style={{ fontSize: 11, fontWeight: 600, color: "var(--color-text-muted)", letterSpacing: "0.16em", textTransform: "uppercase", margin: "0 0 10px", fontFamily: FONT }}>
              Company overview
            </p>
            <h1 style={{ fontSize: 38, fontWeight: 800, color: "var(--color-text-primary)", fontFamily: FONT, margin: 0, letterSpacing: "-0.03em", lineHeight: 1 }}>
              {COMPANY.name}
            </h1>
          </div>

          {/* ── Department pill strip ── */}
          <div style={{ marginBottom: 36, padding: "22px 24px", backgroundColor: "var(--color-surface)", border: "1px solid var(--color-border)", borderRadius: 14, boxShadow: "var(--shadow-sm)" }}>
            <DepartmentPillStrip onDrillDown={handleDrillDown} />
          </div>

          {/* Thin rule */}
          <div style={{ height: 1, background: "linear-gradient(90deg, var(--color-border) 0%, transparent 100%)", marginBottom: 36 }} />

          {/* ── KPI tiles ── */}
          <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 16, marginBottom: 36 }}>
            <KpiCard label="Active evaluations" value={active.length}  accent="var(--color-info)" />
            <KpiCard label="Pending approval"   value={pending.length} accent="var(--color-warning)" />
            <KpiCard label="Total runs"         value={runs.length}    accent="var(--color-accent)" />
          </div>

          {/* ── Pending approvals — cross-agent ── */}
          {(pending.length > 0 || !loading) && (
            <div style={{ marginBottom: 24 }}>
              <SectionCard
                accent="var(--color-warning)"
                title={
                  <>
                    <span style={{ width: 7, height: 7, borderRadius: "50%", backgroundColor: "var(--color-warning)", display: "inline-block" }} />
                    Pending approval
                    {pending.length > 0 && <span style={{ fontSize: 11, color: "var(--color-text-muted)", fontWeight: 400 }}>— {pending.length} across all agents</span>}
                  </>
                }
              >
                {pending.length === 0 ? (
                  <p style={{ fontSize: 12, color: "var(--color-text-muted)", fontFamily: FONT, padding: "16px 20px", margin: 0 }}>No approvals pending.</p>
                ) : (
                  <div style={{ padding: "8px 12px", display: "flex", flexDirection: "column", gap: 8 }}>
                    {pending.map(run => (
                      <ApprovalRow key={run.run_id} run={run} onClick={() => router.push(`/${run.run_id}/results`)} />
                    ))}
                  </div>
                )}
              </SectionCard>
            </div>
          )}

          {/* ── Active runs ── */}
          {active.length > 0 && (
            <div style={{ marginBottom: 24 }}>
              <SectionCard accent="var(--color-info)" title={<><span style={{ width: 7, height: 7, borderRadius: "50%", backgroundColor: "var(--color-info)", display: "inline-block" }} />Active runs</>}>
                {active.map(run => (
                  <RunRow key={run.run_id} run={run} onClick={() => router.push(`/${run.run_id}/progress`)} />
                ))}
              </SectionCard>
            </div>
          )}

          {/* ── All runs ── */}
          {!loading && rest.length > 0 && (
            <SectionCard accent="var(--color-border-strong)" title="All runs">
              {rest.map(run => (
                <RunRow key={run.run_id} run={run} onClick={() => router.push(`/${run.run_id}/results`)} />
              ))}
            </SectionCard>
          )}

          {loading && (
            <p style={{ textAlign: "center", color: "var(--color-text-muted)", fontSize: 13, fontFamily: FONT, marginTop: 40 }}>Loading…</p>
          )}
          {!loading && runs.length === 0 && (
            <div style={{ textAlign: "center", padding: "64px 0" }}>
              <p style={{ fontSize: 15, color: "var(--color-text-secondary)", fontFamily: FONT, marginBottom: 8 }}>No evaluation runs yet.</p>
              <p style={{ fontSize: 12, color: "var(--color-text-muted)", fontFamily: FONT }}>Start one with &ldquo;New Evaluation&rdquo; above.</p>
            </div>
          )}

        </main>
      </div>
    </div>
  );
}
