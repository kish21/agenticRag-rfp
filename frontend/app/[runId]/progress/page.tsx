"use client";

import { useEffect, useRef, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { TopBar } from "@/components/TopBar";
import { useThemeContext } from "@/components/ThemeProvider";
import { PALETTE, PALETTE_LIGHT, FONT, MONO, TOKENS, AGENT_COLOUR } from "@/lib/theme";

const API     = process.env.NEXT_PUBLIC_API_URL ?? "";
const API_SSE = process.env.NEXT_PUBLIC_API_SSE_URL ?? "http://localhost:8000";
function getToken() { return typeof window !== "undefined" ? (localStorage.getItem("access_token") ?? "") : ""; }

// ── Agent definitions ──────────────────────────────────────────────────────────

const AGENTS = [
  { id: "planner",     label: "Planner",     desc: "Decomposes RFP into typed evaluation tasks", colour: AGENT_COLOUR.procurement },
  { id: "ingestion",   label: "Ingestion",   desc: "Parses vendor PDFs → Qdrant vector index",   colour: AGENT_COLOUR.hr         },
  { id: "retrieval",   label: "Retrieval",   desc: "Hybrid search + Cohere rerank + HyDE",        colour: AGENT_COLOUR.legal      },
  { id: "extraction",  label: "Extraction",  desc: "Extracts structured facts → PostgreSQL",      colour: AGENT_COLOUR.finance    },
  { id: "evaluation",  label: "Evaluation",  desc: "Scores vendors against criteria",             colour: AGENT_COLOUR.operations },
  { id: "comparator",  label: "Comparator",  desc: "Cross-vendor ranking, rank stability check",  colour: "var(--color-info)"    },
  { id: "decision",    label: "Decision",    desc: "Governance routing, approval tier selection", colour: "var(--color-success)"  },
  { id: "explanation", label: "Explanation", desc: "Grounded report — every claim cited",         colour: "var(--color-warning)"  },
  { id: "critic",      label: "Critic",      desc: "Validates every agent output for quality",    colour: "var(--color-accent)"   },
] as const;

type AgentStatus = "pending" | "running" | "done" | "blocked" | "warned";

interface AgentEvent { agent: string; status: AgentStatus; message?: string; log_msg?: string; }
interface LogEntry   { ts: string; agent: string; status: AgentStatus; message: string; }

const STATUS_COLOUR: Record<AgentStatus, string> = {
  pending: "var(--color-text-muted)",
  running: "var(--color-info)",
  done:    "var(--color-success)",
  blocked: "var(--color-error)",
  warned:  "var(--color-warning)",
};
const STATUS_ICON: Record<AgentStatus, string> = {
  pending: "○", running: "◉", done: "✓", blocked: "✗", warned: "⚠",
};

// ── Spinner ────────────────────────────────────────────────────────────────────

function Spinner({ colour }: { colour: string }) {
  return (
    <svg width="16" height="16" viewBox="0 0 16 16" style={{ animation: "spin 1s linear infinite" }}>
      <circle cx="8" cy="8" r="6" stroke={colour} strokeWidth="2" strokeDasharray="20 18" fill="none" strokeLinecap="round" />
      <style>{`@keyframes spin { to { transform: rotate(360deg); transform-origin: 8px 8px; } }`}</style>
    </svg>
  );
}

// ── Page ───────────────────────────────────────────────────────────────────────

export default function ProgressPage() {
  const { runId }          = useParams<{ runId: string }>();
  const router             = useRouter();
  const { isDark } = useThemeContext();
  const P          = isDark ? PALETTE : PALETTE_LIGHT;

  const [statuses, setStatuses] = useState<Record<string, AgentStatus>>(
    Object.fromEntries(AGENTS.map(a => [a.id, "pending"]))
  );
  const [messages,  setMessages]  = useState<Record<string, string>>({});
  const [durations, setDurations] = useState<Record<string, number>>({});
  const [startTimes, setStartTimes] = useState<Record<string, number>>({});
  const [elapsed,   setElapsed]   = useState(0);
  const [done,      setDone]      = useState(false);
  const [blocked,   setBlocked]   = useState("");
  const [now,       setNow]       = useState(Date.now());
  const [logEntries, setLogEntries] = useState<LogEntry[]>([]);
  const logRef = useRef<HTMLDivElement>(null);

  const BG = "var(--bg-gradient)";

  // Save runId so user can reload without losing progress
  useEffect(() => {
    localStorage.setItem("meridian-last-run", runId);
  }, [runId]);

  // Tick for elapsed display
  useEffect(() => {
    const t0 = Date.now();
    const iv = setInterval(() => {
      setElapsed(Math.floor((Date.now() - t0) / 1000));
      setNow(Date.now());
    }, 1000);
    return () => clearInterval(iv);
  }, []);

  // SSE stream
  useEffect(() => {
    const token = getToken();
    // SSE must connect directly to FastAPI — Next.js rewrites buffer responses and break streaming
    const url   = `${API_SSE}/api/v1/evaluate/${runId}/stream${token ? `?token=${encodeURIComponent(token)}` : ""}`;
    const es    = new EventSource(url);

    es.onmessage = e => {
      try {
        const ev: AgentEvent = JSON.parse(e.data);
        if (!ev.agent) return; // heartbeat
        setStatuses(s => ({ ...s, [ev.agent]: ev.status }));
        if (ev.message) setMessages(m => ({ ...m, [ev.agent]: ev.message! }));
        if (ev.status === "running") setStartTimes(t => ({ ...t, [ev.agent]: Date.now() }));
        if (ev.status === "done" || ev.status === "blocked" || ev.status === "warned") {
          setDurations(d => ({
            ...d,
            [ev.agent]: Math.round((Date.now() - (startTimes[ev.agent] ?? Date.now())) / 1000),
          }));
        }
        // Accumulate plain-English log entries
        const logText = ev.log_msg || ev.message;
        if (logText && (ev.status === "running" || ev.status === "done" || ev.status === "blocked")) {
          setLogEntries(prev => [...prev, {
            ts:      new Date().toISOString(),
            agent:   ev.agent,
            status:  ev.status,
            message: logText,
          }]);
          setTimeout(() => logRef.current?.scrollTo({ top: logRef.current.scrollHeight, behavior: "smooth" }), 50);
        }
        if (ev.agent === "explanation" && ev.status === "done") { setDone(true); es.close(); }
        if (ev.status === "blocked") { setBlocked(`${ev.agent}: ${ev.message ?? ""}`); es.close(); }
      } catch { /* ignore */ }
    };
    es.onerror = () => {
      setBlocked("Connection lost. Your evaluation is still running — results will be ready when complete.");
      es.close();
    };
    return () => es.close();
  }, [runId]); // eslint-disable-line react-hooks/exhaustive-deps

  const doneCount    = AGENTS.filter(a => statuses[a.id] === "done").length;
  const progress     = Math.round((doneCount / AGENTS.length) * 100);
  const fmtTime      = (s: number) => s < 60 ? `${s}s` : `${Math.floor(s / 60)}m ${s % 60}s`;

  const CARD = { background: P.bg.surface, borderRadius: TOKENS.radius.card, border: `1px solid ${P.border.mid}` };

  return (
    <div style={{ minHeight: "100vh", background: BG, fontFamily: FONT }}>
      <TopBar
        crumbs={[
          { label: "Procurement", href: "/" },
          { label: runId.slice(0, 8) + "…", href: `/${runId}/confirm` },
          { label: "Progress" },
        ]} />

      <main style={{ maxWidth: 720, margin: "0 auto", padding: "36px 28px 80px", display: "flex", flexDirection: "column", gap: 18 }}>

        {/* Header */}
        <div style={{ ...CARD, padding: "20px 22px" }}>
          <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", marginBottom: 14 }}>
            <div>
              <h1 style={{ fontSize: 18, fontWeight: 700, color: P.text.primary, margin: "0 0 4px", fontFamily: FONT }}>
                Evaluation in progress
              </h1>
              <div style={{ fontSize: 11, color: P.text.muted, fontFamily: MONO }}>
                {runId} · {fmtTime(elapsed)} elapsed
              </div>
            </div>
            <div style={{
              background: "var(--color-accent)18", border: "1px solid var(--color-accent)40",
              borderRadius: 20, padding: "4px 12px",
              fontSize: 11, color: "var(--color-accent)", fontWeight: 600, fontFamily: FONT,
            }}>
              ● Progress saved — reload safely
            </div>
          </div>

          {/* Overall progress bar */}
          <div style={{ marginBottom: 6 }}>
            <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 5 }}>
              <span style={{ fontSize: 12, color: P.text.secondary, fontFamily: FONT }}>{doneCount} of {AGENTS.length} agents complete</span>
              <span style={{ fontFamily: MONO, fontSize: 12, color: "var(--color-accent)", fontWeight: 600 }}>{progress}%</span>
            </div>
            <div style={{ height: 6, borderRadius: 3, background: P.border.dim, overflow: "hidden" }}>
              <div style={{ height: "100%", width: `${progress}%`, background: "var(--color-accent)", borderRadius: 3, transition: "width 500ms ease" }} />
            </div>
          </div>
        </div>

        {/* Agent list */}
        <div style={CARD}>
          {AGENTS.map((agent, i) => {
            const status  = statuses[agent.id] ?? "pending";
            const colour  = status === "pending" ? P.text.muted : STATUS_COLOUR[status];
            const msg     = messages[agent.id];
            const dur     = durations[agent.id];
            const isLast  = i === AGENTS.length - 1;
            const running = status === "running";
            return (
              <div key={agent.id} style={{
                display: "flex", alignItems: "center", gap: 14,
                padding: "13px 20px",
                borderBottom: isLast ? "none" : `1px solid ${P.border.dim}`,
                background: running ? "var(--color-surface-hover)" : "transparent",
                transition: "background 200ms",
              }}>
                {/* Status icon */}
                <div style={{
                  width: 28, height: 28, borderRadius: "50%", flexShrink: 0,
                  background: colour + "18", border: `1.5px solid ${colour}`,
                  display: "flex", alignItems: "center", justifyContent: "center",
                }}>
                  {running
                    ? <Spinner colour={colour} />
                    : <span style={{ fontSize: 13, color: colour, fontWeight: 700 }}>{STATUS_ICON[status]}</span>
                  }
                </div>

                {/* Agent info */}
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 2 }}>
                    <span style={{ width: 6, height: 6, borderRadius: "50%", background: agent.colour, flexShrink: 0 }} />
                    <span style={{ fontSize: 13, fontWeight: 600, color: P.text.primary, fontFamily: FONT }}>{agent.label} Agent</span>
                  </div>
                  <div style={{ fontSize: 11, color: P.text.muted, fontFamily: FONT, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                    {msg ?? agent.desc}
                  </div>
                </div>

                {/* Status pill + duration */}
                <div style={{ display: "flex", flexDirection: "column", alignItems: "flex-end", gap: 3, flexShrink: 0 }}>
                  <span style={{
                    fontSize: 11, fontWeight: 600, color: colour,
                    background: colour + "18", padding: "2px 8px", borderRadius: 12,
                    fontFamily: FONT,
                  }}>{status}</span>
                  {dur !== undefined && (
                    <span style={{ fontFamily: MONO, fontSize: 10, color: P.text.muted }}>{fmtTime(dur)}</span>
                  )}
                </div>
              </div>
            );
          })}
        </div>

        {/* Activity log */}
        {logEntries.length > 0 && (
          <div style={{ ...CARD, overflow: "hidden" }}>
            <div style={{ padding: "14px 20px 10px", borderBottom: `1px solid ${P.border.dim}` }}>
              <span style={{ fontSize: 11, fontWeight: 700, color: P.text.secondary, letterSpacing: "0.1em", textTransform: "uppercase", fontFamily: FONT }}>
                Activity log
              </span>
            </div>
            <div ref={logRef} style={{ maxHeight: 260, overflowY: "auto", padding: "8px 0" }}>
              {logEntries.map((entry, i) => {
                const dotColour = entry.status === "done" ? "var(--color-success)" : entry.status === "blocked" ? "var(--color-error)" : "var(--color-info)";
                const time = new Date(entry.ts).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
                return (
                  <div key={i} style={{ display: "flex", gap: 12, padding: "7px 20px", alignItems: "flex-start" }}>
                    <span style={{ fontSize: 10, color: P.text.muted, fontFamily: MONO, flexShrink: 0, marginTop: 2, minWidth: 70 }}>{time}</span>
                    <span style={{ width: 6, height: 6, borderRadius: "50%", background: dotColour, flexShrink: 0, marginTop: 5 }} />
                    <span style={{ fontSize: 13, color: P.text.primary, fontFamily: FONT, lineHeight: 1.5 }}>{entry.message}</span>
                  </div>
                );
              })}
            </div>
          </div>
        )}

        {/* Blocked error */}
        {blocked && (
          <div style={{
            background: "var(--color-error)14", border: "1px solid var(--color-error)",
            borderRadius: TOKENS.radius.card, padding: "14px 18px",
            fontSize: 13, color: "var(--color-error)", fontFamily: FONT,
          }}>
            <strong>Pipeline blocked:</strong> {blocked}
          </div>
        )}

        {/* Done CTA */}
        {done && (
          <button onClick={() => router.push(`/${runId}/results`)} style={{
            background: "var(--color-accent)", color: "var(--color-accent-foreground)", border: "none",
            borderRadius: TOKENS.radius.btn, padding: "13px",
            fontSize: 14, fontFamily: FONT, fontWeight: 700, cursor: "pointer",
            width: "100%",
          }}>
            View results →
          </button>
        )}
      </main>
    </div>
  );
}
