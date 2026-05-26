"use client";

import React from "react";
import Link from "next/link";
import { FONT } from "@/lib/theme";
import { type EvalRun, type ChatSession } from "@/lib/types";
import { type UserInfo } from "@/lib/api";
import { STATUS_DOT } from "@/lib/constants";

type ShellState = "idle" | "running" | "completed";

interface AppSidebarProps {
  userInfo: UserInfo | null;
  runs: EvalRun[];
  loading: boolean;
  chatSessions: ChatSession[];
  activeRunId: string | null;
  chatSessionId: string | null;
  shellState: ShellState;
  hoveredRunId: string | null;
  deletingRunId: string | null;
  isNarrow: boolean;
  sidebarOpen: boolean;
  onStartNewEval: () => void;
  onNewChatSession: () => void;
  onLoadChatSession: (session: ChatSession) => void;
  onOpenRun: (run: EvalRun) => void;
  onDeleteRun: (e: React.MouseEvent, runId: string) => void;
  onGoHome: () => void;
  onSignOut: () => void;
  onSetHoveredRunId: (id: string | null) => void;
  onCloseSidebar: () => void;
}

export function AppSidebar({
  userInfo, runs, loading, chatSessions, activeRunId, chatSessionId,
  hoveredRunId, deletingRunId, isNarrow, sidebarOpen,
  onStartNewEval, onNewChatSession, onLoadChatSession, onOpenRun,
  onDeleteRun, onGoHome, onSignOut, onSetHoveredRunId, onCloseSidebar,
}: AppSidebarProps) {
  return (
    <>
      {(!isNarrow || sidebarOpen) && (
        <aside style={{
          width: 240, flexShrink: 0,
          display: "flex", flexDirection: "column",
          backgroundColor: "var(--color-surface)",
          borderRight: "1px solid var(--color-border)",
          overflowY: "auto",
          ...(isNarrow ? {
            position: "absolute", top: 0, left: 0, bottom: 0,
            zIndex: 30, boxShadow: "var(--shadow-lg)",
          } : {}),
        }}>
          <div style={{ padding: "14px 12px 8px" }}>
            <button
              type="button" onClick={onStartNewEval}
              style={{
                width: "100%", display: "flex", alignItems: "center", gap: 8,
                padding: "9px 12px",
                backgroundColor: "var(--color-accent)",
                color: "var(--color-accent-foreground)",
                borderTop: "none", borderBottom: "none",
                borderLeft: "none", borderRight: "none",
                borderRadius: "var(--radius)",
                fontFamily: FONT, fontWeight: 600, fontSize: 13,
                cursor: "pointer", transition: "opacity 150ms ease-out",
              }}
              onMouseEnter={e => { e.currentTarget.style.opacity = "0.88"; }}
              onMouseLeave={e => { e.currentTarget.style.opacity = "1"; }}
            >
              <span style={{ fontSize: 16, fontWeight: 300, lineHeight: 1 }}>+</span>
              New evaluation
            </button>
          </div>

          {/* Personal chats */}
          <div style={{ padding: "8px 16px 4px", display: "flex", alignItems: "center", justifyContent: "space-between" }}>
            <p style={{
              fontFamily: FONT, fontWeight: 600, fontSize: 10,
              letterSpacing: "0.1em", textTransform: "uppercase",
              color: "var(--color-text-muted)",
            }}>Personal</p>
            <button
              type="button" onClick={onNewChatSession} title="New chat"
              style={{
                background: "none",
                borderTop: "none", borderBottom: "none", borderLeft: "none", borderRight: "none",
                cursor: "pointer", padding: "2px 4px", borderRadius: "var(--radius)",
                fontFamily: FONT, fontSize: 11, color: "var(--color-text-muted)",
                transition: "color 150ms ease-out", lineHeight: 1,
              }}
              onMouseEnter={e => { e.currentTarget.style.color = "var(--color-accent)"; }}
              onMouseLeave={e => { e.currentTarget.style.color = "var(--color-text-muted)"; }}
            >+ new</button>
          </div>

          <div style={{ padding: "0 8px 4px" }}>
            {chatSessions.length === 0 && (
              <p style={{ fontFamily: FONT, fontSize: 11, color: "var(--color-text-muted)", padding: "4px 8px", lineHeight: 1.5 }}>
                No chats yet. Ask a question below.
              </p>
            )}
            {chatSessions.slice(0, 8).map(session => {
              const isActive = session.id === chatSessionId;
              return (
                <button
                  key={session.id} type="button"
                  onClick={() => onLoadChatSession(session)}
                  style={{
                    width: "100%", textAlign: "left",
                    display: "flex", alignItems: "center", gap: 8,
                    padding: "6px 8px",
                    backgroundColor: isActive ? "var(--color-surface-hover)" : "transparent",
                    borderTop: "none", borderBottom: "none", borderRight: "none",
                    borderLeft: isActive ? "2px solid var(--color-accent)" : "2px solid transparent",
                    borderRadius: "0 var(--radius) var(--radius) 0",
                    cursor: "pointer", transition: "background-color 150ms ease-out",
                  }}
                  onMouseEnter={e => { if (!isActive) e.currentTarget.style.backgroundColor = "var(--color-surface-hover)"; }}
                  onMouseLeave={e => { if (!isActive) e.currentTarget.style.backgroundColor = "transparent"; }}
                >
                  <span style={{ fontSize: 9, color: "var(--color-text-muted)", flexShrink: 0 }}>💬</span>
                  <span style={{
                    fontFamily: FONT, fontSize: 11,
                    fontWeight: isActive ? 600 : 400,
                    color: isActive ? "var(--color-text-primary)" : "var(--color-text-secondary)",
                    overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", flex: 1,
                  }}>
                    {session.title}
                  </span>
                </button>
              );
            })}
          </div>

          <div style={{ height: 1, backgroundColor: "var(--color-border)", margin: "4px 0" }} />

          {/* RFP Evaluations */}
          <div style={{ padding: "8px 16px 4px" }}>
            <p style={{
              fontFamily: FONT, fontWeight: 600, fontSize: 10,
              letterSpacing: "0.1em", textTransform: "uppercase",
              color: "var(--color-text-muted)",
            }}>RFP Evaluations</p>
          </div>

          <div style={{ flex: 1, padding: "0 8px" }}>
            {loading && (
              <p style={{ fontFamily: FONT, fontSize: 12, color: "var(--color-text-muted)", padding: "8px 8px" }}>Loading…</p>
            )}
            {!loading && runs.length === 0 && (
              <p style={{ fontFamily: FONT, fontSize: 12, color: "var(--color-text-muted)", padding: "8px 8px", lineHeight: 1.6 }}>
                No evaluations yet.
              </p>
            )}
            {!loading && runs.slice(0, 10).map(run => {
              const isActive    = run.run_id === activeRunId;
              const isRunning   = run.status === "running";
              const isCompleted = run.status === "completed";
              const canDelete   = !isCompleted && !isRunning;
              const isHovered   = hoveredRunId === run.run_id;
              const isDeleting  = deletingRunId === run.run_id;
              return (
                <div
                  key={run.run_id}
                  style={{ position: "relative" }}
                  onMouseEnter={() => onSetHoveredRunId(run.run_id)}
                  onMouseLeave={() => onSetHoveredRunId(null)}
                >
                  <button
                    type="button" onClick={() => onOpenRun(run)}
                    style={{
                      width: "100%", textAlign: "left",
                      display: "flex", alignItems: "center", gap: 8,
                      padding: "7px 8px",
                      paddingRight: canDelete ? 28 : 8,
                      backgroundColor: isActive ? "var(--color-surface-hover)" : "transparent",
                      borderTop: "none", borderBottom: "none", borderRight: "none",
                      borderLeft: isActive ? "2px solid var(--color-accent)" : "2px solid transparent",
                      borderRadius: "0 var(--radius) var(--radius) 0",
                      cursor: "pointer", transition: "background-color 150ms ease-out",
                      ...(isRunning ? { animation: "meridian-pulse-border 2.5s ease-in-out infinite" } : {}),
                    }}
                    onMouseEnter={e => { if (!isActive) e.currentTarget.style.backgroundColor = "var(--color-surface-hover)"; }}
                    onMouseLeave={e => { if (!isActive) e.currentTarget.style.backgroundColor = "transparent"; }}
                  >
                    <div style={{
                      width: 6, height: 6, borderRadius: "50%", flexShrink: 0,
                      backgroundColor: STATUS_DOT[run.status] ?? "var(--color-text-muted)",
                      ...(isRunning ? { animation: "meridian-dot-pulse 2s ease-in-out infinite" } : {}),
                    }} />
                    <span style={{
                      fontFamily: FONT, fontSize: 12,
                      fontWeight: isActive ? 600 : 400,
                      color: isActive ? "var(--color-text-primary)" : "var(--color-text-secondary)",
                      overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", flex: 1,
                    }}>
                      {run.rfp_title || "Untitled RFP"}
                    </span>
                  </button>

                  {canDelete && (
                    <button
                      type="button"
                      onClick={e => onDeleteRun(e, run.run_id)}
                      title="Delete run"
                      style={{
                        position: "absolute", right: 6, top: "50%",
                        transform: "translateY(-50%)",
                        opacity: isHovered && !isDeleting ? 1 : 0,
                        pointerEvents: isHovered ? "auto" : "none",
                        background: "none",
                        borderTop: "none", borderBottom: "none", borderLeft: "none", borderRight: "none",
                        cursor: "pointer", padding: "2px 4px",
                        color: "var(--color-text-muted)",
                        fontSize: 13, lineHeight: 1,
                        transition: "opacity 150ms ease-out, color 150ms ease-out",
                      }}
                      onMouseEnter={e => { e.currentTarget.style.color = "var(--color-error)"; }}
                      onMouseLeave={e => { e.currentTarget.style.color = "var(--color-text-muted)"; }}
                    >
                      {isDeleting ? "…" : "×"}
                    </button>
                  )}
                </div>
              );
            })}
          </div>

          {/* Bottom nav */}
          <div style={{ borderTop: "1px solid var(--color-border)", padding: "8px" }}>
            <button
              type="button" onClick={onGoHome}
              style={{
                width: "100%", textAlign: "left",
                display: "flex", alignItems: "center", gap: 8,
                padding: "7px 8px", background: "none",
                borderTop: "none", borderBottom: "none",
                borderLeft: "none", borderRight: "none",
                cursor: "pointer", borderRadius: "var(--radius)",
                fontFamily: FONT, fontSize: 12, color: "var(--color-text-muted)",
                transition: "color 150ms ease-out, background-color 150ms ease-out",
              }}
              onMouseEnter={e => { e.currentTarget.style.color = "var(--color-text-primary)"; e.currentTarget.style.backgroundColor = "var(--color-surface-hover)"; }}
              onMouseLeave={e => { e.currentTarget.style.color = "var(--color-text-muted)"; e.currentTarget.style.backgroundColor = "transparent"; }}
            >
              <span style={{ width: 16, textAlign: "center", fontSize: 13 }}>⌂</span>
              Home
            </button>

            {userInfo?.role === "org_admin" && (
              <Link
                href="/admin/settings"
                style={{
                  display: "flex", alignItems: "center", gap: 8,
                  padding: "7px 8px", borderRadius: "var(--radius)",
                  fontFamily: FONT, fontSize: 12, color: "var(--color-text-muted)",
                  textDecoration: "none",
                  transition: "color 150ms ease-out, background-color 150ms ease-out",
                }}
                onMouseEnter={e => { e.currentTarget.style.color = "var(--color-text-primary)"; e.currentTarget.style.backgroundColor = "var(--color-surface-hover)"; }}
                onMouseLeave={e => { e.currentTarget.style.color = "var(--color-text-muted)"; e.currentTarget.style.backgroundColor = "transparent"; }}
              >
                <span style={{ width: 16, textAlign: "center", fontSize: 13 }}>⚙</span>
                Org Settings
              </Link>
            )}

            <Link
              href="/settings"
              style={{
                display: "flex", alignItems: "center", gap: 8,
                padding: "7px 8px", borderRadius: "var(--radius)",
                fontFamily: FONT, fontSize: 12, color: "var(--color-text-muted)",
                textDecoration: "none",
                transition: "color 150ms ease-out, background-color 150ms ease-out",
              }}
              onMouseEnter={e => { e.currentTarget.style.color = "var(--color-text-primary)"; e.currentTarget.style.backgroundColor = "var(--color-surface-hover)"; }}
              onMouseLeave={e => { e.currentTarget.style.color = "var(--color-text-muted)"; e.currentTarget.style.backgroundColor = "transparent"; }}
            >
              <span style={{ width: 16, textAlign: "center", fontSize: 13 }}>◎</span>
              My Settings
            </Link>

            <button
              type="button" onClick={onSignOut}
              style={{
                width: "100%", textAlign: "left",
                display: "flex", alignItems: "center", gap: 8,
                padding: "7px 8px", background: "none",
                borderTop: "none", borderBottom: "none",
                borderLeft: "none", borderRight: "none",
                cursor: "pointer", borderRadius: "var(--radius)",
                fontFamily: FONT, fontSize: 12, color: "var(--color-text-muted)",
                transition: "color 150ms ease-out, background-color 150ms ease-out",
              }}
              onMouseEnter={e => { e.currentTarget.style.color = "var(--color-error)"; e.currentTarget.style.backgroundColor = "var(--color-surface-hover)"; }}
              onMouseLeave={e => { e.currentTarget.style.color = "var(--color-text-muted)"; e.currentTarget.style.backgroundColor = "transparent"; }}
            >
              <span style={{ width: 16, textAlign: "center", fontSize: 13 }}>→</span>
              Sign out
            </button>
          </div>
        </aside>
      )}

      {/* Mobile overlay backdrop */}
      {isNarrow && sidebarOpen && (
        <div
          onClick={onCloseSidebar}
          style={{
            position: "absolute", inset: 0, zIndex: 20,
            backgroundColor: "rgba(0,0,0,0.4)",
          }}
        />
      )}
    </>
  );
}
