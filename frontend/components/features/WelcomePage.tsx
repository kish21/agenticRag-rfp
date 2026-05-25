"use client";

import { useState } from "react";
import { FONT, DISPLAY, MONO } from "@/lib/theme";
import { type UserInfo } from "@/lib/api";
import { type EvalRun, type ChatMessage } from "@/lib/types";
import { STATUS_DOT } from "@/lib/constants";
import { fmtDate, greet } from "@/lib/utils";

const inputCss: React.CSSProperties = {
  width: "100%", boxSizing: "border-box",
  padding: "9px 12px",
  backgroundColor: "var(--color-background)",
  borderTop: "1px solid var(--color-border)",
  borderBottom: "1px solid var(--color-border)",
  borderLeft: "1px solid var(--color-border)",
  borderRight: "1px solid var(--color-border)",
  borderRadius: "var(--radius)",
  fontFamily: FONT, fontSize: 13,
  color: "var(--color-text-primary)",
  transition: "border-color 150ms ease-out",
};

interface WelcomePageProps {
  runs: EvalRun[];
  loading: boolean;
  userInfo: UserInfo | null;
  isMobile: boolean;
  chatMessages: ChatMessage[];
  chatLoading: boolean;
  savedCriteria: string[];
  criteriaEditMode: boolean;
  savedConfirm: string | null;
  onStartNewEval: () => void;
  onOpenRun: (run: EvalRun) => void;
  onSaveCriteria: (criteria: string[]) => void;
  onSavedCriteriaChange: (criteria: string[]) => void;
  onCriteriaEditModeChange: (v: boolean) => void;
}

export function WelcomePage({
  runs, loading, userInfo, isMobile,
  chatMessages, chatLoading,
  savedCriteria, criteriaEditMode, savedConfirm,
  onStartNewEval, onOpenRun,
  onSaveCriteria, onSavedCriteriaChange, onCriteriaEditModeChange,
}: WelcomePageProps) {
  const [searchQ,      setSearchQ]      = useState("");
  const [statusFilter, setStatusFilter] = useState<string>("all");

  const total     = runs.length;
  const running   = runs.filter(r => r.status === "running").length;
  const completed = runs.filter(r => r.status === "completed" || r.status === "complete").length;
  const hasChatMessages = chatMessages.length > 0;

  const normalise  = (s: string) => s.toLowerCase().replace(/[-_]/g, " ");
  const STATUS_GROUPS: Record<string, string[]> = {
    all:       [],
    running:   ["running"],
    complete:  ["completed", "complete"],
    pending:   ["pending_confirm"],
    failed:    ["failed", "interrupted"],
  };
  const filteredRuns = runs.filter(r => {
    const q = normalise(searchQ);
    const matchesSearch = !q
      || normalise(r.rfp_title || "").includes(q)
      || normalise(r.status).includes(q);
    const allowed = STATUS_GROUPS[statusFilter];
    const matchesStatus = !allowed?.length || allowed.includes(r.status);
    return matchesSearch && matchesStatus;
  });

  return (
    <div style={{ maxWidth: 680 }}>
      {!hasChatMessages && (<>
        {/* Hero greeting */}
        <div style={{ marginBottom: 48 }}>
          <h1 style={{
            fontFamily: DISPLAY, fontWeight: 800,
            fontSize: isMobile ? 36 : 56,
            lineHeight: 1.0, letterSpacing: "-0.04em",
            color: "var(--color-text-primary)", marginBottom: 12,
          }}>
            {userInfo ? greet(userInfo.email) : "Welcome back."}
          </h1>
          <p style={{
            fontFamily: FONT, fontSize: 15, fontWeight: 400,
            color: "var(--color-text-secondary)", lineHeight: 1.65,
          }}>
            Evaluate vendor proposals against RFP criteria using multi-agent AI analysis.
          </p>
        </div>

        {/* Stats */}
        {total > 0 && (
          <div style={{
            display: "grid",
            gridTemplateColumns: isMobile ? "1fr 1fr" : "1fr 1fr 2fr",
            gap: 12, marginBottom: 40,
          }}>
            {[
              { label: "Total", value: total },
              { label: "Running", value: running },
              { label: "Complete", value: completed },
            ].map(({ label, value }) => (
              <div key={label} style={{
                padding: "16px 20px",
                backgroundColor: "var(--color-surface)",
                borderTop: "1px solid var(--color-border)",
                borderBottom: "1px solid var(--color-border)",
                borderLeft: "1px solid var(--color-border)",
                borderRight: "1px solid var(--color-border)",
                borderRadius: "var(--radius)",
                boxShadow: "var(--shadow-sm)",
              }}>
                <p style={{
                  fontFamily: MONO, fontWeight: 700, fontSize: 32,
                  color: "var(--color-text-primary)", lineHeight: 1,
                  marginBottom: 4, fontVariantNumeric: "tabular-nums",
                }}>{value}</p>
                <p style={{
                  fontFamily: FONT, fontWeight: 500, fontSize: 10,
                  letterSpacing: "0.1em", textTransform: "uppercase",
                  color: "var(--color-text-muted)",
                }}>{label}</p>
              </div>
            ))}
          </div>
        )}

        {/* CTA */}
        <button
          type="button"
          onClick={onStartNewEval}
          style={{
            display: "inline-flex", alignItems: "center", gap: 8,
            padding: "11px 24px",
            backgroundColor: "var(--color-accent)",
            color: "var(--color-accent-foreground)",
            borderTop: "none", borderBottom: "none",
            borderLeft: "none", borderRight: "none",
            borderRadius: "var(--radius)",
            fontFamily: FONT, fontWeight: 600, fontSize: 14,
            cursor: "pointer", boxShadow: "var(--shadow-sm)",
            transition: "opacity 150ms ease-out, transform 150ms ease-out",
            marginBottom: 40,
          }}
          onMouseEnter={e => { e.currentTarget.style.opacity = "0.88"; e.currentTarget.style.transform = "translateY(-1px)"; }}
          onMouseLeave={e => { e.currentTarget.style.opacity = "1"; e.currentTarget.style.transform = "translateY(0)"; }}
        >
          <span style={{ fontSize: 18, fontWeight: 300, lineHeight: 1 }}>+</span>
          Start new evaluation
        </button>

        {/* Saved success criteria */}
        {savedCriteria.length > 0 && (
          <div style={{ marginBottom: 40 }}>
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 10 }}>
              <p style={{
                fontFamily: FONT, fontWeight: 600, fontSize: 10,
                letterSpacing: "0.1em", textTransform: "uppercase",
                color: "var(--color-text-muted)",
              }}>Your success criteria</p>
              <button
                type="button"
                onClick={() => onCriteriaEditModeChange(!criteriaEditMode)}
                style={{
                  background: "none", border: "none", cursor: "pointer",
                  fontFamily: FONT, fontSize: 11, color: "var(--color-text-muted)",
                  padding: "2px 8px",
                  borderRadius: "var(--radius)",
                  transition: "color 150ms ease-out",
                }}
                onMouseEnter={e => { e.currentTarget.style.color = "var(--color-accent)"; }}
                onMouseLeave={e => { e.currentTarget.style.color = "var(--color-text-muted)"; }}
              >
                {criteriaEditMode ? "Done" : "Edit"}
              </button>
            </div>
            {criteriaEditMode ? (
              <div style={{
                backgroundColor: "var(--color-surface)",
                borderTop: "1px solid var(--color-border)",
                borderBottom: "1px solid var(--color-border)",
                borderLeft: "1px solid var(--color-border)",
                borderRight: "1px solid var(--color-border)",
                borderRadius: "var(--radius)",
                padding: "12px 16px",
                boxShadow: "var(--shadow-sm)",
              }}>
                {savedCriteria.map((c, i) => (
                  <div key={i} style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 8 }}>
                    <input
                      type="text"
                      value={c}
                      onChange={e => {
                        const next = [...savedCriteria];
                        next[i] = e.target.value;
                        onSavedCriteriaChange(next);
                      }}
                      style={{ ...inputCss, flex: 1, fontSize: 13 }}
                    />
                    <button
                      type="button"
                      onClick={() => onSavedCriteriaChange(savedCriteria.filter((_, j) => j !== i))}
                      aria-label="Remove criterion"
                      style={{
                        background: "none", border: "none", cursor: "pointer",
                        color: "var(--color-error)", fontSize: 16, padding: "0 4px",
                        flexShrink: 0,
                      }}
                    >×</button>
                  </div>
                ))}
                <div style={{ display: "flex", gap: 8, marginTop: 8 }}>
                  <button
                    type="button"
                    onClick={() => onSavedCriteriaChange([...savedCriteria, ""])}
                    style={{
                      background: "none", border: "none", cursor: "pointer",
                      fontFamily: FONT, fontSize: 12, color: "var(--color-accent)",
                      padding: 0,
                    }}
                  >+ Add criterion</button>
                  <button
                    type="button"
                    onClick={() => { onSaveCriteria(savedCriteria); onCriteriaEditModeChange(false); }}
                    style={{
                      marginLeft: "auto",
                      padding: "6px 16px",
                      backgroundColor: "var(--color-accent)",
                      color: "var(--color-accent-foreground)",
                      border: "none", borderRadius: "var(--radius)",
                      fontFamily: FONT, fontWeight: 600, fontSize: 12,
                      cursor: "pointer",
                    }}
                  >Save changes</button>
                </div>
              </div>
            ) : (
              <ul style={{ listStyle: "none", padding: 0, margin: 0 }}>
                {savedCriteria.map((c, i) => (
                  <li key={i} style={{
                    display: "flex", alignItems: "flex-start", gap: 8,
                    fontFamily: FONT, fontSize: 13, color: "var(--color-text-secondary)",
                    lineHeight: 1.6, marginBottom: 4,
                  }}>
                    <span style={{ color: "var(--color-accent)", flexShrink: 0, marginTop: 1 }}>•</span>
                    {c}
                  </li>
                ))}
              </ul>
            )}
            {savedConfirm && (
              <p style={{
                fontFamily: FONT, fontSize: 11, color: "var(--color-success)",
                marginTop: 6,
              }}>{savedConfirm} ✓</p>
            )}
          </div>
        )}
      </>)}

      {/* Chat thread */}
      {chatMessages.length > 0 && (
        <div style={{ marginBottom: 32 }}>
          <p style={{
            fontFamily: FONT, fontWeight: 600, fontSize: 10,
            letterSpacing: "0.1em", textTransform: "uppercase",
            color: "var(--color-text-muted)", marginBottom: 12,
          }}>Chat history</p>
          <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
            {chatMessages.map((msg, i) => (
              <div key={i} style={{
                display: "flex",
                justifyContent: msg.role === "user" ? "flex-end" : "flex-start",
              }}>
                <div style={{
                  maxWidth: "80%",
                  padding: "10px 14px",
                  backgroundColor: msg.role === "user" ? "var(--color-accent)" : "var(--color-surface)",
                  color: msg.role === "user" ? "var(--color-accent-foreground)" : "var(--color-text-primary)",
                  borderRadius: msg.role === "user" ? "12px 12px 4px 12px" : "4px 12px 12px 12px",
                  borderTop: msg.role === "assistant" ? "1px solid var(--color-border)" : "none",
                  borderBottom: msg.role === "assistant" ? "1px solid var(--color-border)" : "none",
                  borderLeft: msg.role === "assistant" ? "1px solid var(--color-border)" : "none",
                  borderRight: msg.role === "assistant" ? "1px solid var(--color-border)" : "none",
                  boxShadow: msg.role === "assistant" ? "var(--shadow-sm)" : "none",
                  fontFamily: FONT, fontSize: 13, lineHeight: 1.65,
                }}>
                  <p style={{ whiteSpace: "pre-wrap", margin: 0 }}>{msg.text}</p>
                  {msg.role === "assistant" && msg.suggestedCriteria && msg.suggestedCriteria.length > 0 && (
                    <div style={{ marginTop: 10, paddingTop: 10, borderTop: "1px solid var(--color-border)" }}>
                      <p style={{
                        fontFamily: FONT, fontWeight: 600, fontSize: 10,
                        letterSpacing: "0.08em", textTransform: "uppercase",
                        color: "var(--color-text-muted)", marginBottom: 6,
                      }}>Suggested criteria</p>
                      <ul style={{ listStyle: "none", padding: 0, margin: "0 0 10px 0" }}>
                        {msg.suggestedCriteria.map((c, j) => (
                          <li key={j} style={{
                            fontFamily: FONT, fontSize: 12,
                            color: "var(--color-text-secondary)",
                            lineHeight: 1.6, paddingLeft: 12,
                            position: "relative",
                          }}>
                            <span style={{ position: "absolute", left: 0, color: "var(--color-accent)" }}>•</span>
                            {c}
                          </li>
                        ))}
                      </ul>
                      <button
                        type="button"
                        onClick={() => onSaveCriteria(msg.suggestedCriteria!)}
                        style={{
                          padding: "5px 12px",
                          backgroundColor: "var(--color-accent)",
                          color: "var(--color-accent-foreground)",
                          border: "none", borderRadius: "var(--radius)",
                          fontFamily: FONT, fontWeight: 600, fontSize: 11,
                          cursor: "pointer",
                        }}
                      >Save as my criteria</button>
                    </div>
                  )}
                </div>
              </div>
            ))}
            {chatLoading && (
              <div style={{ display: "flex", justifyContent: "flex-start" }}>
                <div style={{
                  padding: "10px 14px",
                  backgroundColor: "var(--color-surface)",
                  borderTop: "1px solid var(--color-border)",
                  borderBottom: "1px solid var(--color-border)",
                  borderLeft: "1px solid var(--color-border)",
                  borderRight: "1px solid var(--color-border)",
                  borderRadius: "4px 12px 12px 12px",
                  boxShadow: "var(--shadow-sm)",
                  display: "flex", gap: 4, alignItems: "center",
                }}>
                  {[0, 1, 2].map(j => (
                    <span key={j} style={{
                      width: 6, height: 6, borderRadius: "50%",
                      backgroundColor: "var(--color-text-muted)",
                      animation: "meridian-dot-pulse 1.2s ease-in-out infinite",
                      animationDelay: `${j * 200}ms`,
                      display: "inline-block",
                    }} />
                  ))}
                </div>
              </div>
            )}
          </div>
        </div>
      )}

      {!hasChatMessages && (<>
        {/* Recent evaluations */}
        {total > 0 && (
          <>
            {/* Search + filter bar */}
            <div style={{ display: "flex", gap: 8, marginBottom: 10, alignItems: "center" }}>
              <label htmlFor="run-search" style={{ position: "absolute", width: 1, height: 1, overflow: "hidden", clip: "rect(0,0,0,0)" }}>
                Search evaluations
              </label>
              <input
                id="run-search"
                type="search"
                value={searchQ}
                onChange={e => setSearchQ(e.target.value)}
                placeholder="Search…"
                style={{
                  flex: 1, minWidth: 0,
                  padding: "7px 10px",
                  backgroundColor: "var(--color-background)",
                  borderTop: "1px solid var(--color-border)",
                  borderBottom: "1px solid var(--color-border)",
                  borderLeft: "1px solid var(--color-border)",
                  borderRight: "1px solid var(--color-border)",
                  borderRadius: "var(--radius)",
                  fontFamily: FONT, fontSize: 12,
                  color: "var(--color-text-primary)",
                  outline: "none",
                  transition: "border-color 150ms ease-out",
                }}
                onFocus={e => { e.currentTarget.style.borderColor = "var(--color-accent)"; }}
                onBlur={e => { e.currentTarget.style.borderColor = "var(--color-border)"; }}
              />
              <label htmlFor="run-status-filter" style={{ position: "absolute", width: 1, height: 1, overflow: "hidden", clip: "rect(0,0,0,0)" }}>
                Filter by status
              </label>
              <select
                id="run-status-filter"
                value={statusFilter}
                onChange={e => setStatusFilter(e.target.value)}
                style={{
                  padding: "7px 10px",
                  backgroundColor: "var(--color-background)",
                  borderTop: "1px solid var(--color-border)",
                  borderBottom: "1px solid var(--color-border)",
                  borderLeft: "1px solid var(--color-border)",
                  borderRight: "1px solid var(--color-border)",
                  borderRadius: "var(--radius)",
                  fontFamily: FONT, fontSize: 12,
                  color: "var(--color-text-primary)",
                  cursor: "pointer",
                  outline: "none",
                  flexShrink: 0,
                }}
              >
                <option value="all">All</option>
                <option value="complete">Complete</option>
                <option value="running">Running</option>
                <option value="pending">Pending</option>
                <option value="failed">Failed</option>
              </select>
            </div>

            {filteredRuns.length > 0 ? (
              <div style={{
                backgroundColor: "var(--color-surface)",
                borderTop: "1px solid var(--color-border)",
                borderBottom: "1px solid var(--color-border)",
                borderLeft: "1px solid var(--color-border)",
                borderRight: "1px solid var(--color-border)",
                borderRadius: "var(--radius)",
                boxShadow: "var(--shadow-sm)",
                overflow: "hidden",
              }}>
                {filteredRuns.map((run, i) => (
                  <div
                    key={run.run_id}
                    onClick={() => onOpenRun(run)}
                    role="button"
                    tabIndex={0}
                    onKeyDown={e => { if (e.key === "Enter") onOpenRun(run); }}
                    style={{
                      display: "flex", alignItems: "center", justifyContent: "space-between",
                      padding: "12px 16px",
                      borderBottom: i < filteredRuns.length - 1 ? "1px solid var(--color-border)" : "none",
                      cursor: "pointer",
                      transition: "background-color 150ms ease-out",
                    }}
                    onMouseEnter={e => { (e.currentTarget as HTMLElement).style.backgroundColor = "var(--color-surface-hover)"; }}
                    onMouseLeave={e => { (e.currentTarget as HTMLElement).style.backgroundColor = "transparent"; }}
                  >
                    <div>
                      <p style={{ fontFamily: FONT, fontWeight: 500, fontSize: 13, color: "var(--color-text-primary)" }}>
                        {run.rfp_title || "Untitled RFP"}
                      </p>
                      <p style={{ fontFamily: MONO, fontSize: 11, color: "var(--color-text-muted)", marginTop: 2 }}>
                        {(run.started_at || run.created_at) ? fmtDate(run.started_at || run.created_at) : ""}
                        {" · "}
                        {run.vendor_count ?? 0} vendor{run.vendor_count !== 1 ? "s" : ""}
                        {run.total_cost_usd != null ? ` · $${run.total_cost_usd.toFixed(3)}` : ""}
                      </p>
                    </div>
                    <div style={{ display: "flex", alignItems: "center", gap: 6, flexShrink: 0 }}>
                      <div style={{
                        width: 6, height: 6, borderRadius: "50%",
                        backgroundColor: STATUS_DOT[run.status] ?? "var(--color-text-muted)",
                      }} />
                      <span style={{ fontFamily: FONT, fontSize: 12, color: "var(--color-text-secondary)" }}>
                        {run.status.charAt(0).toUpperCase() + run.status.slice(1)}
                      </span>
                      <span style={{ color: "var(--color-text-muted)", fontSize: 14, marginLeft: 4 }}>→</span>
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <p style={{ fontFamily: FONT, fontSize: 13, color: "var(--color-text-muted)", padding: "16px 0" }}>
                No evaluations match your search.
              </p>
            )}
          </>
        )}

        {/* Empty state */}
        {total === 0 && !loading && (
          <div style={{
            padding: "48px 32px", textAlign: "center",
            backgroundColor: "var(--color-surface)",
            borderTop: "1px solid var(--color-border)",
            borderBottom: "1px solid var(--color-border)",
            borderLeft: "1px solid var(--color-border)",
            borderRight: "1px solid var(--color-border)",
            borderRadius: "var(--radius)",
            boxShadow: "var(--shadow-sm)",
          }}>
            <p style={{ fontFamily: MONO, fontSize: 40, color: "var(--color-text-muted)", marginBottom: 16, lineHeight: 1 }}>◻</p>
            <p style={{ fontFamily: DISPLAY, fontWeight: 700, fontSize: 20, color: "var(--color-text-primary)", marginBottom: 8 }}>
              No evaluations yet
            </p>
            <p style={{ fontFamily: FONT, fontSize: 14, color: "var(--color-text-muted)", lineHeight: 1.65 }}>
              Upload your first RFP to start evaluating vendors.
            </p>
          </div>
        )}
      </>)}
    </div>
  );
}
