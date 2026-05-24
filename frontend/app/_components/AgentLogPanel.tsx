"use client";

import React, { useRef, useEffect } from "react";
import { FONT, MONO } from "@/lib/theme";
import { type AgentEvent } from "@/lib/types";
import { AGENT_LABELS } from "@/lib/constants";
import { DevLogPanel, type DevLogEntry } from "@/components/features/DevLogPanel";

export type { DevLogEntry };

type ShellState = "idle" | "running" | "completed";

interface AgentLogPanelProps {
  rightExpanded: boolean;
  rightTab: "agent" | "dev";
  shellState: ShellState;
  agentEvents: AgentEvent[];
  devLogEntries: DevLogEntry[];
  devLogConnected: boolean;
  isDevRole: boolean;
  onSetExpanded: (expanded: boolean) => void;
  onTabChange: (tab: "agent" | "dev") => void;
}

function agentStatusColor(status: string): string {
  if (status === "done")    return "var(--color-success)";
  if (status === "blocked") return "var(--color-error)";
  if (status === "running") return "var(--color-info)";
  return "var(--color-border)";
}

export function AgentLogPanel({
  rightExpanded, rightTab, shellState, agentEvents,
  devLogEntries, devLogConnected, isDevRole,
  onSetExpanded, onTabChange,
}: AgentLogPanelProps) {
  const logEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    logEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [agentEvents]);

  return (
    <aside style={{
      width: rightExpanded ? 320 : 40, flexShrink: 0,
      display: "flex", flexDirection: "column",
      backgroundColor: "var(--color-surface)",
      borderLeft: "1px solid var(--color-border)",
      overflow: "hidden",
      transition: "width 250ms ease-out",
    }}>
      {rightExpanded ? (
        <div style={{ display: "flex", flexDirection: "column", height: "100%" }}>
          <div style={{
            display: "flex", alignItems: "center", justifyContent: "space-between",
            padding: "10px 12px",
            borderBottom: "1px solid var(--color-border)",
            flexShrink: 0, gap: 8,
          }}>
            <div style={{ display: "flex", gap: 2 }}>
              {(["agent", ...(isDevRole ? ["dev"] : [])] as ("agent" | "dev")[]).map(tab => (
                <button
                  key={tab} type="button" onClick={() => onTabChange(tab)}
                  style={{
                    fontFamily: FONT, fontWeight: 600, fontSize: 10,
                    letterSpacing: "0.08em", textTransform: "uppercase",
                    padding: "3px 8px", borderRadius: "var(--radius)",
                    border: "none", cursor: "pointer",
                    backgroundColor: rightTab === tab ? "var(--color-surface-hover)" : "transparent",
                    color: rightTab === tab ? "var(--color-text-primary)" : "var(--color-text-muted)",
                    transition: "opacity 150ms ease-out",
                  }}
                >
                  {tab === "agent" ? "Agent Log" : "Dev Log"}
                </button>
              ))}
              {shellState === "running" && (
                <div style={{ display: "flex", alignItems: "center", gap: 4, marginLeft: 4 }}>
                  <div style={{
                    width: 5, height: 5, borderRadius: "50%",
                    backgroundColor: "var(--color-info)",
                    animation: "meridian-dot-pulse 1.5s ease-in-out infinite",
                  }} />
                  <p style={{ fontFamily: MONO, fontSize: 10, color: "var(--color-info)" }}>Live</p>
                </div>
              )}
            </div>
            <button
              type="button" onClick={() => onSetExpanded(false)} aria-label="Collapse agent log"
              style={{
                background: "none", border: "none", cursor: "pointer",
                color: "var(--color-text-muted)", padding: 4, fontSize: 14,
                transition: "color 150ms ease-out",
              }}
              onMouseEnter={e => { e.currentTarget.style.color = "var(--color-text-primary)"; }}
              onMouseLeave={e => { e.currentTarget.style.color = "var(--color-text-muted)"; }}
            >→</button>
          </div>

          {rightTab === "agent" && (
            <div style={{ flex: 1, overflowY: "auto", padding: "12px" }}>
              {agentEvents.length === 0 && (
                <p style={{ fontFamily: FONT, fontSize: 12, color: "var(--color-text-muted)", lineHeight: 1.6 }}>
                  {shellState === "running" ? "Waiting for first agent event…" : "No events recorded."}
                </p>
              )}
              {agentEvents.map((ev, i) => (
                <div key={i} style={{ marginBottom: 12 }}>
                  <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 3 }}>
                    <div style={{
                      width: 5, height: 5, borderRadius: "50%", flexShrink: 0,
                      backgroundColor: agentStatusColor(ev.status),
                    }} />
                    <p style={{ fontFamily: MONO, fontSize: 10, fontWeight: 600, color: "var(--color-text-secondary)", letterSpacing: "0.04em" }}>
                      {AGENT_LABELS[ev.agent] ?? ev.agent}
                    </p>
                    <p style={{ fontFamily: MONO, fontSize: 10, color: "var(--color-text-muted)", marginLeft: "auto" }}>
                      {ev.status}
                    </p>
                  </div>
                  <p style={{ fontFamily: FONT, fontSize: 11, color: "var(--color-text-muted)", lineHeight: 1.5, paddingLeft: 11 }}>
                    {ev.message}
                  </p>
                </div>
              ))}
              <div ref={logEndRef} />
            </div>
          )}

          {rightTab === "dev" && isDevRole && (
            <DevLogPanel entries={devLogEntries} connected={devLogConnected} />
          )}
        </div>
      ) : (
        <div
          onClick={() => onSetExpanded(true)}
          role="button" tabIndex={0}
          onKeyDown={e => { if (e.key === "Enter" || e.key === " ") onSetExpanded(true); }}
          aria-label="Expand agent log"
          style={{
            flex: 1, display: "flex", flexDirection: "column",
            alignItems: "center", justifyContent: "center",
            cursor: "pointer", gap: 10,
            transition: "background-color 150ms ease-out",
          }}
          onMouseEnter={e => { (e.currentTarget as HTMLElement).style.backgroundColor = "var(--color-surface-hover)"; }}
          onMouseLeave={e => { (e.currentTarget as HTMLElement).style.backgroundColor = "transparent"; }}
        >
          <span style={{
            fontFamily: FONT, fontWeight: 600, fontSize: 10,
            letterSpacing: "0.12em", textTransform: "uppercase",
            color: shellState === "running" ? "var(--color-info)" : "var(--color-text-muted)",
            writingMode: "vertical-rl", textOrientation: "mixed",
            transform: "rotate(180deg)", userSelect: "none",
            transition: "color 150ms ease-out",
          }}>
            Agent Log
          </span>
          {shellState === "running" && (
            <div style={{
              width: 6, height: 6, borderRadius: "50%",
              backgroundColor: "var(--color-info)",
              animation: "meridian-dot-pulse 1.5s ease-in-out infinite",
            }} />
          )}
        </div>
      )}
    </aside>
  );
}
