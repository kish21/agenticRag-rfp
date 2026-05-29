"use client";

import { useEffect, useState } from "react";
import { FONT, DISPLAY, MONO } from "@/lib/theme";
import { AGENTS, AGENT_LABELS } from "@/lib/constants";

interface ProgressPageProps {
  agentStatuses: Record<string, { status: string; message: string }>;
  isMobile: boolean;
  onCancel: () => void;
}

function fmtSeconds(s: number): string {
  if (s < 60) return `${s}s`;
  const m = Math.floor(s / 60);
  const r = s % 60;
  return r > 0 ? `${m}m ${r}s` : `${m}m`;
}

export function ProgressPage({ agentStatuses, isMobile, onCancel }: ProgressPageProps) {
  // React 19: `useRef(Date.now())` is impure during render (linter flag).
  // Use useState lazy-initializer instead — runs the impure call exactly
  // once at mount, never on subsequent renders.
  const [startAt] = useState<number>(() => Date.now());
  const [elapsed, setElapsed] = useState(0);

  useEffect(() => {
    const t = setInterval(() => setElapsed(Math.floor((Date.now() - startAt) / 1000)), 1000);
    return () => clearInterval(t);
  }, [startAt]);

  const done  = Object.values(agentStatuses).filter(a => a.status === "done").length;
  const total = AGENTS.length;
  const pct   = total > 0 ? Math.round((done / total) * 100) : 0;

  const avgPerAgent  = done > 0 ? elapsed / done : null;
  const remaining    = avgPerAgent != null ? Math.round(avgPerAgent * (total - done)) : null;

  return (
    <div style={{ maxWidth: 620 }}>
      <div style={{ marginBottom: 32 }}>
        <p style={{
          fontFamily: FONT, fontWeight: 600, fontSize: 11,
          letterSpacing: "0.1em", textTransform: "uppercase",
          color: "var(--color-info)", marginBottom: 8,
        }}>
          Evaluation in progress
        </p>
        <h1 style={{
          fontFamily: DISPLAY, fontWeight: 800,
          fontSize: isMobile ? 24 : 32,
          letterSpacing: "-0.03em", lineHeight: 1.0,
          color: "var(--color-text-primary)", marginBottom: 20,
        }}>
          Analysing vendors…
        </h1>

        <div style={{
          height: 3, backgroundColor: "var(--color-border)",
          borderRadius: 2, overflow: "hidden", marginBottom: 8,
        }}>
          <div style={{
            height: "100%", width: `${pct}%`,
            backgroundColor: "var(--color-info)", borderRadius: 2,
            transition: "width 600ms ease-out",
          }} />
        </div>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
          <p style={{ fontFamily: MONO, fontSize: 11, color: "var(--color-text-muted)" }}>
            {done}/{total} agents complete
          </p>
          <p style={{ fontFamily: MONO, fontSize: 11, color: "var(--color-text-muted)" }}>
            {fmtSeconds(elapsed)} elapsed
            {remaining != null && done > 0 && done < total
              ? ` · ~${fmtSeconds(remaining)} remaining`
              : ""}
          </p>
        </div>
      </div>

      <div style={{
        backgroundColor: "var(--color-surface)",
        borderTop: "1px solid var(--color-border)",
        borderBottom: "1px solid var(--color-border)",
        borderLeft: "1px solid var(--color-border)",
        borderRight: "1px solid var(--color-border)",
        borderRadius: "var(--radius)",
        boxShadow: "var(--shadow-sm)",
        overflow: "hidden",
        marginBottom: 24,
      }}>
        {AGENTS.map((agent, i) => {
          const s = agentStatuses[agent];
          const status    = s?.status ?? "pending";
          const message   = s?.message;
          const isActive  = status === "running";
          const isDone    = status === "done";
          const isBlocked = status === "blocked";
          const isPending = !isActive && !isDone && !isBlocked;

          const statusLabel = isBlocked ? "Blocked"
            : isDone    ? "Complete"
            : isActive  ? "Running"
            : "Not started";

          const statusColor = isBlocked ? "var(--color-error)"
            : isDone   ? "var(--color-success)"
            : isActive ? "var(--color-info)"
            : "var(--color-text-muted)";

          return (
            <div key={agent} style={{
              display: "flex", alignItems: "center", gap: 12,
              padding: "13px 16px",
              borderBottom: i < AGENTS.length - 1 ? "1px solid var(--color-border)" : "none",
              backgroundColor: isActive ? "var(--color-surface-hover)" : "transparent",
              borderLeft: isActive ? "3px solid var(--color-info)"
                : isDone    ? "3px solid var(--color-success)"
                : isBlocked ? "3px solid var(--color-error)"
                : "3px solid transparent",
              transition: "background-color 150ms ease-out",
            }}>
              {/* Icon */}
              <div style={{ width: 18, height: 18, flexShrink: 0, display: "flex", alignItems: "center", justifyContent: "center" }}>
                {isActive && (
                  <div style={{
                    width: 16, height: 16, borderRadius: "50%",
                    borderTop: "2px solid var(--color-info)",
                    borderBottom: "2px solid transparent",
                    borderLeft: "2px solid transparent",
                    borderRight: "2px solid transparent",
                    animation: "meridian-spin 0.7s linear infinite",
                  }} />
                )}
                {isDone && (
                  <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
                    <circle cx="8" cy="8" r="7" fill="var(--color-success)" fillOpacity="0.15" stroke="var(--color-success)" strokeWidth="1.5"/>
                    <path d="M5 8l2 2 4-4" stroke="var(--color-success)" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
                  </svg>
                )}
                {isBlocked && (
                  <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
                    <circle cx="8" cy="8" r="7" fill="var(--color-error)" fillOpacity="0.15" stroke="var(--color-error)" strokeWidth="1.5"/>
                    <path d="M8 5v3.5M8 11h.01" stroke="var(--color-error)" strokeWidth="1.5" strokeLinecap="round"/>
                  </svg>
                )}
                {isPending && (
                  <div style={{
                    width: 8, height: 8, borderRadius: "50%",
                    border: "1.5px solid var(--color-border)",
                    backgroundColor: "transparent",
                  }} />
                )}
              </div>

              {/* Text */}
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 8 }}>
                  <p style={{
                    fontFamily: FONT, fontWeight: isActive ? 700 : 500,
                    fontSize: 13,
                    color: isPending ? "var(--color-text-muted)"
                      : isDone ? "var(--color-text-secondary)"
                      : "var(--color-text-primary)",
                  }}>
                    {AGENT_LABELS[agent] ?? agent}
                  </p>
                  <span style={{
                    fontFamily: MONO, fontSize: 10, letterSpacing: "0.06em", textTransform: "uppercase",
                    fontWeight: isActive ? 700 : 400,
                    color: statusColor,
                    whiteSpace: "nowrap",
                  }}>
                    {statusLabel}
                  </span>
                </div>
                {(isActive || isDone || isBlocked) && message && (
                  <p style={{ fontFamily: FONT, fontSize: 11, color: "var(--color-text-muted)", lineHeight: 1.5, marginTop: 2 }}>
                    {message}
                  </p>
                )}
              </div>
            </div>
          );
        })}
      </div>

      <button
        type="button"
        onClick={onCancel}
        style={{
          background: "none", padding: "8px 0",
          borderTop: "none", borderBottom: "none",
          borderLeft: "none", borderRight: "none",
          cursor: "pointer",
          fontFamily: FONT, fontSize: 13, color: "var(--color-text-muted)",
          transition: "color 150ms ease-out",
        }}
        onMouseEnter={e => { e.currentTarget.style.color = "var(--color-error)"; }}
        onMouseLeave={e => { e.currentTarget.style.color = "var(--color-text-muted)"; }}
      >
        Cancel evaluation
      </button>
    </div>
  );
}
