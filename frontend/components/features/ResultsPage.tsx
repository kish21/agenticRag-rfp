"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { FONT, DISPLAY, MONO } from "@/lib/theme";
import { api } from "@/lib/api";
import { type EvalResults } from "@/lib/types";

interface ResultsPageProps {
  results: EvalResults | null;
  activeRunId: string | null;
  isMobile: boolean;
  onStartNewEval: () => void;
}

interface AgentCost {
  calls: number;
  tokens: number;
  cost_usd: number;
  latency_ms: number;
}

interface CostData {
  total_cost_usd: number | null;
  total_tokens: number | null;
  by_agent: Record<string, AgentCost>;
  source: string;
}

function CostBreakdown({ runId }: { runId: string }) {
  const [cost, setCost]       = useState<CostData | null>(null);
  const [open, setOpen]       = useState(false);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    // Trigger-based fetch on dropdown open. setLoading(true) fires
    // synchronously before the async fetch so the spinner shows; the
    // remaining setState calls run inside promise resolution (after the
    // effect commits) so React 19 strict-mode is satisfied — the
    // setLoading(true) line is the only one the linter flags.
    if (!open || cost) return;
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setLoading(true);
    api.get<CostData>(`/api/v1/evaluate/${runId}/cost`)
      .then(setCost)
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [open, runId, cost]);

  const agents = cost ? Object.entries(cost.by_agent).sort((a, b) => b[1].cost_usd - a[1].cost_usd) : [];
  const hasCost = cost && (cost.total_cost_usd !== null && cost.total_cost_usd !== undefined);

  return (
    <div style={{
      marginTop: 32,
      backgroundColor: "var(--color-surface)",
      borderTop: "1px solid var(--color-border)",
      borderBottom: "1px solid var(--color-border)",
      borderLeft: "1px solid var(--color-border)",
      borderRight: "1px solid var(--color-border)",
      borderRadius: "var(--radius)",
      boxShadow: "var(--shadow-sm)",
      overflow: "hidden",
    }}>
      <button
        type="button"
        onClick={() => setOpen(o => !o)}
        style={{
          width: "100%", display: "flex", alignItems: "center",
          justifyContent: "space-between",
          padding: "12px 16px", background: "none", border: "none",
          cursor: "pointer",
          transition: "background-color 150ms ease-out",
        }}
        onMouseEnter={e => { e.currentTarget.style.backgroundColor = "var(--color-surface-hover)"; }}
        onMouseLeave={e => { e.currentTarget.style.backgroundColor = "transparent"; }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <span style={{
            fontFamily: FONT, fontWeight: 600, fontSize: 10,
            letterSpacing: "0.08em", textTransform: "uppercase",
            color: "var(--color-text-muted)",
          }}>LLM Cost</span>
          {hasCost && (
            <span style={{
              fontFamily: MONO, fontWeight: 700, fontSize: 12,
              color: "var(--color-text-primary)", fontVariantNumeric: "tabular-nums",
            }}>
              ${cost!.total_cost_usd!.toFixed(4)}
            </span>
          )}
        </div>
        <span style={{
          fontFamily: MONO, fontSize: 10, color: "var(--color-text-muted)",
          transform: open ? "rotate(180deg)" : "none",
          transition: "transform 150ms ease-out",
          display: "inline-block",
        }}>▾</span>
      </button>

      {open && (
        <div style={{ borderTop: "1px solid var(--color-border)" }}>
          {loading && (
            <div style={{ padding: "16px", display: "flex", alignItems: "center", gap: 8 }}>
              <div style={{
                width: 12, height: 12,
                borderTop: "2px solid var(--color-info)",
                borderBottom: "2px solid transparent",
                borderLeft: "2px solid transparent",
                borderRight: "2px solid transparent",
                borderRadius: "50%",
                animation: "meridian-spin 0.7s linear infinite",
              }} />
              <span style={{ fontFamily: FONT, fontSize: 12, color: "var(--color-text-muted)" }}>Loading…</span>
            </div>
          )}
          {!loading && cost && (
            <>
              {agents.length > 0 ? (
                <table style={{
                  width: "100%", borderCollapse: "collapse",
                  fontFamily: FONT, fontSize: 12,
                }}>
                  <thead>
                    <tr style={{ borderBottom: "1px solid var(--color-border)" }}>
                      {["Agent", "Calls", "Tokens", "Cost (USD)", "Latency"].map(h => (
                        <th key={h} style={{
                          padding: "8px 16px", textAlign: "left",
                          fontFamily: FONT, fontWeight: 600, fontSize: 10,
                          letterSpacing: "0.08em", textTransform: "uppercase",
                          color: "var(--color-text-muted)",
                        }}>{h}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {agents.map(([agent, a]) => (
                      <tr key={agent} style={{ borderBottom: "1px solid var(--color-border)" }}>
                        <td style={{ padding: "9px 16px", color: "var(--color-text-primary)", fontWeight: 500 }}>
                          {agent}
                        </td>
                        <td style={{ padding: "9px 16px", fontFamily: MONO, color: "var(--color-text-secondary)", fontVariantNumeric: "tabular-nums" }}>
                          {a.calls}
                        </td>
                        <td style={{ padding: "9px 16px", fontFamily: MONO, color: "var(--color-text-secondary)", fontVariantNumeric: "tabular-nums" }}>
                          {a.tokens.toLocaleString()}
                        </td>
                        <td style={{ padding: "9px 16px", fontFamily: MONO, fontWeight: 600, color: "var(--color-text-primary)", fontVariantNumeric: "tabular-nums" }}>
                          ${a.cost_usd.toFixed(4)}
                        </td>
                        <td style={{ padding: "9px 16px", fontFamily: MONO, color: "var(--color-text-muted)", fontVariantNumeric: "tabular-nums" }}>
                          {a.latency_ms < 1000 ? `${a.latency_ms}ms` : `${(a.latency_ms / 1000).toFixed(1)}s`}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                  <tfoot>
                    <tr style={{ backgroundColor: "var(--color-background)" }}>
                      <td style={{ padding: "9px 16px", fontFamily: FONT, fontWeight: 700, fontSize: 12, color: "var(--color-text-primary)" }}>
                        Total
                      </td>
                      <td colSpan={2} style={{ padding: "9px 16px", fontFamily: MONO, fontSize: 12, color: "var(--color-text-muted)", fontVariantNumeric: "tabular-nums" }}>
                        {cost.total_tokens?.toLocaleString() ?? "—"} tokens
                      </td>
                      <td style={{ padding: "9px 16px", fontFamily: MONO, fontWeight: 700, fontSize: 13, color: "var(--color-text-primary)", fontVariantNumeric: "tabular-nums" }}>
                        ${cost.total_cost_usd?.toFixed(4) ?? "—"}
                      </td>
                      <td />
                    </tr>
                  </tfoot>
                </table>
              ) : (
                <div style={{ padding: "12px 16px" }}>
                  <p style={{ fontFamily: MONO, fontSize: 12, color: "var(--color-text-muted)", fontVariantNumeric: "tabular-nums" }}>
                    Total: {hasCost ? `$${cost.total_cost_usd!.toFixed(4)}` : "—"}
                    {cost.total_tokens ? ` · ${cost.total_tokens.toLocaleString()} tokens` : ""}
                  </p>
                </div>
              )}
            </>
          )}
        </div>
      )}
    </div>
  );
}

export function ResultsPage({ results, activeRunId, isMobile, onStartNewEval }: ResultsPageProps) {
  if (!results) {
    return (
      <div style={{ display: "flex", alignItems: "center", gap: 8, padding: "40px 0" }}>
        <div style={{
          width: 16, height: 16,
          borderTop: "2px solid var(--color-info)",
          borderBottom: "2px solid transparent",
          borderLeft: "2px solid transparent",
          borderRight: "2px solid transparent",
          borderRadius: "50%",
          animation: "meridian-spin 0.7s linear infinite",
        }} />
        <p style={{ fontFamily: FONT, fontSize: 14, color: "var(--color-text-muted)" }}>Loading results…</p>
      </div>
    );
  }

  const allVendors  = results.vendors ?? [];
  const shortlisted = allVendors.filter(v => v.decision === "shortlisted");
  const rejected    = allVendors.filter(v => v.decision === "rejected");

  function confidenceTier(c: number | null | undefined): { label: string; color: string } {
    if (c == null)  return { label: "—",    color: "var(--color-text-muted)" };
    if (c >= 0.85)  return { label: "high",  color: "var(--color-success)" };
    if (c >= 0.65)  return { label: "med",   color: "var(--color-warning)" };
    return               { label: "low",   color: "var(--color-error)" };
  }

  const REC_LABEL: Record<string, string> = {
    strongly_recommended: "Strong buy",
    recommended:          "Recommended",
    acceptable:           "Acceptable",
    marginal:             "Marginal",
  };

  return (
    <div style={{ maxWidth: 680 }}>
      <div style={{ marginBottom: 32 }}>
        <div style={{ display: "flex", alignItems: "baseline", gap: 12, marginBottom: 8 }}>
          <p style={{
            fontFamily: FONT, fontWeight: 600, fontSize: 11,
            letterSpacing: "0.1em", textTransform: "uppercase",
            color: "var(--color-success)",
          }}>
            Evaluation complete
          </p>
          {results.decision_confidence != null && (
            <span style={{
              fontFamily: MONO, fontSize: 10, fontWeight: 600,
              color: confidenceTier(results.decision_confidence).color,
            }}>
              {Math.round(results.decision_confidence * 100)}% confidence
            </span>
          )}
        </div>
        <h1 style={{
          fontFamily: DISPLAY, fontWeight: 800,
          fontSize: isMobile ? 24 : 32,
          letterSpacing: "-0.03em", lineHeight: 1.0,
          color: "var(--color-text-primary)", marginBottom: 16,
        }}>
          Vendor Rankings
        </h1>

        {/* Human review required banner */}
        {results.requires_human_review && (
          <div role="alert" style={{
            marginBottom: 16, padding: "12px 16px",
            backgroundColor: "color-mix(in srgb, var(--color-warning) 8%, transparent)",
            borderTop: "1px solid var(--color-border)",
            borderBottom: "1px solid var(--color-border)",
            borderLeft: "3px solid var(--color-warning)",
            borderRight: "1px solid var(--color-border)",
            borderRadius: "var(--radius)",
          }}>
            <p style={{
              fontFamily: FONT, fontWeight: 700, fontSize: 12,
              color: "var(--color-warning)", marginBottom: 2,
            }}>Human review required</p>
            {(results.review_reasons ?? []).length > 0 && (
              <p style={{ fontFamily: FONT, fontSize: 12, color: "var(--color-text-secondary)", lineHeight: 1.6 }}>
                {results.review_reasons!.join(" · ")}
              </p>
            )}
          </div>
        )}

        {results.recommendation && (
          <div style={{
            padding: "12px 16px",
            backgroundColor: "var(--color-surface)",
            borderTop: "1px solid var(--color-border)",
            borderBottom: "1px solid var(--color-border)",
            borderLeft: "3px solid var(--color-success)",
            borderRight: "1px solid var(--color-border)",
            borderRadius: "var(--radius)",
            boxShadow: "var(--shadow-sm)",
          }}>
            <p style={{ fontFamily: FONT, fontSize: 10, fontWeight: 600, letterSpacing: "0.08em", textTransform: "uppercase", color: "var(--color-success)", marginBottom: 4 }}>
              Recommendation{results.approval_tier ? ` · ${results.approval_tier}` : ""}
            </p>
            <p style={{ fontFamily: FONT, fontSize: 14, color: "var(--color-text-primary)", lineHeight: 1.6 }}>
              {results.recommendation}
            </p>
          </div>
        )}
      </div>

      {shortlisted.length > 0 && (
        <div style={{ marginBottom: 20 }}>
          <p style={{ fontFamily: FONT, fontSize: 10, fontWeight: 600, letterSpacing: "0.08em", textTransform: "uppercase", color: "var(--color-success)", marginBottom: 10 }}>
            Shortlisted ({shortlisted.length})
          </p>
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
            {shortlisted.map((v, i) => {
              const tier = confidenceTier(v.score_confidence);
              return (
                <div key={v.vendor_name} style={{
                  padding: "14px 16px",
                  borderBottom: i < shortlisted.length - 1 ? "1px solid var(--color-border)" : "none",
                  borderLeft: "3px solid var(--color-success)",
                }}>
                  <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 4 }}>
                    <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                      <p style={{ fontFamily: FONT, fontWeight: 600, fontSize: 14, color: "var(--color-text-primary)" }}>
                        {v.vendor_name}
                      </p>
                      {v.recommendation && (
                        <span style={{
                          fontFamily: FONT, fontWeight: 600, fontSize: 10,
                          letterSpacing: "0.06em", textTransform: "uppercase",
                          color: "var(--color-success)",
                          padding: "1px 6px",
                          borderTop: "1px solid var(--color-success)",
                          borderBottom: "1px solid var(--color-success)",
                          borderLeft: "1px solid var(--color-success)",
                          borderRight: "1px solid var(--color-success)",
                          borderRadius: 3, opacity: 0.7,
                        }}>
                          {REC_LABEL[v.recommendation] ?? v.recommendation}
                        </span>
                      )}
                    </div>
                    <div style={{ display: "flex", alignItems: "baseline", gap: 6 }}>
                      {v.score_confidence != null && (
                        <span style={{
                          fontFamily: MONO, fontSize: 10, fontWeight: 600,
                          color: tier.color, textTransform: "uppercase",
                        }}>
                          {tier.label}
                        </span>
                      )}
                      <span style={{ fontFamily: MONO, fontWeight: 700, fontSize: 22, color: "var(--color-text-primary)", fontVariantNumeric: "tabular-nums" }}>
                        {typeof v.total_score === "number" ? v.total_score.toFixed(1) : "—"}
                      </span>
                    </div>
                  </div>
                  {v.summary && (
                    <p style={{ fontFamily: FONT, fontSize: 12, color: "var(--color-text-muted)", lineHeight: 1.6 }}>
                      {v.summary}
                    </p>
                  )}
                </div>
              );
            })}
          </div>
        </div>
      )}

      {rejected.length > 0 && (
        <div style={{ marginBottom: 32 }}>
          <p style={{ fontFamily: FONT, fontSize: 10, fontWeight: 600, letterSpacing: "0.08em", textTransform: "uppercase", color: "var(--color-error)", marginBottom: 10 }}>
            Rejected ({rejected.length})
          </p>
          <div style={{
            backgroundColor: "var(--color-surface)",
            borderTop: "1px solid var(--color-border)",
            borderBottom: "1px solid var(--color-border)",
            borderLeft: "1px solid var(--color-border)",
            borderRight: "1px solid var(--color-border)",
            borderRadius: "var(--radius)",
            overflow: "hidden",
          }}>
            {rejected.map((v, i) => (
              <div key={v.vendor_name} style={{
                padding: "14px 16px",
                borderBottom: i < rejected.length - 1 ? "1px solid var(--color-border)" : "none",
                borderLeft: "3px solid var(--color-error)",
              }}>
                <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
                  <p style={{ fontFamily: FONT, fontWeight: 500, fontSize: 14, color: "var(--color-text-secondary)" }}>
                    {v.vendor_name}
                  </p>
                  <span style={{ fontFamily: MONO, fontSize: 20, color: "var(--color-text-muted)", fontVariantNumeric: "tabular-nums" }}>
                    {typeof v.total_score === "number" ? v.total_score.toFixed(1) : "—"}
                  </span>
                </div>
                {v.summary && (
                  <p style={{ fontFamily: FONT, fontSize: 12, color: "var(--color-text-muted)", lineHeight: 1.6, marginTop: 4 }}>
                    {v.summary}
                  </p>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      {activeRunId && <CostBreakdown runId={activeRunId} />}

      <div style={{ display: "flex", gap: 12, flexWrap: "wrap", marginTop: 32 }}>
        {activeRunId && (
          <Link
            href={`/${activeRunId}/results`}
            style={{
              display: "inline-flex", alignItems: "center", gap: 6,
              padding: "9px 18px",
              backgroundColor: "var(--color-accent)",
              color: "var(--color-accent-foreground)",
              borderRadius: "var(--radius)",
              fontFamily: FONT, fontWeight: 600, fontSize: 13,
              textDecoration: "none",
              transition: "opacity 150ms ease-out",
            }}
            onMouseEnter={e => { e.currentTarget.style.opacity = "0.88"; }}
            onMouseLeave={e => { e.currentTarget.style.opacity = "1"; }}
          >
            Full report →
          </Link>
        )}
        {activeRunId && (
          <a
            href={`/api/v1/evaluate/${activeRunId}/export`}
            download
            style={{
              display: "inline-flex", alignItems: "center", gap: 6,
              padding: "9px 18px", backgroundColor: "transparent",
              borderTop: "1px solid var(--color-border)",
              borderBottom: "1px solid var(--color-border)",
              borderLeft: "1px solid var(--color-border)",
              borderRight: "1px solid var(--color-border)",
              borderRadius: "var(--radius)",
              fontFamily: FONT, fontWeight: 500, fontSize: 13,
              color: "var(--color-text-secondary)",
              textDecoration: "none",
              transition: "border-color 150ms ease-out, color 150ms ease-out",
            }}
            onMouseEnter={e => { e.currentTarget.style.borderColor = "var(--color-border-strong)"; e.currentTarget.style.color = "var(--color-text-primary)"; }}
            onMouseLeave={e => { e.currentTarget.style.borderColor = "var(--color-border)"; e.currentTarget.style.color = "var(--color-text-secondary)"; }}
          >
            Export CSV
          </a>
        )}
        <button
          type="button" onClick={onStartNewEval}
          style={{
            padding: "9px 18px", backgroundColor: "transparent",
            borderTop: "1px solid var(--color-border)",
            borderBottom: "1px solid var(--color-border)",
            borderLeft: "1px solid var(--color-border)",
            borderRight: "1px solid var(--color-border)",
            borderRadius: "var(--radius)",
            fontFamily: FONT, fontWeight: 500, fontSize: 13,
            color: "var(--color-text-secondary)", cursor: "pointer",
            transition: "border-color 150ms ease-out, color 150ms ease-out",
          }}
          onMouseEnter={e => { e.currentTarget.style.borderColor = "var(--color-border-strong)"; e.currentTarget.style.color = "var(--color-text-primary)"; }}
          onMouseLeave={e => { e.currentTarget.style.borderColor = "var(--color-border)"; e.currentTarget.style.color = "var(--color-text-secondary)"; }}
        >
          New evaluation
        </button>
      </div>
    </div>
  );
}
