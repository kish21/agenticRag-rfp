"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { TopBar } from "@/components/TopBar";
import { useThemeContext } from "@/components/ThemeProvider";
import { PALETTE, PALETTE_LIGHT, FONT, MONO, TOKENS } from "@/lib/theme";

const API = process.env.NEXT_PUBLIC_API_URL ?? "";
function getToken() { return typeof window !== "undefined" ? (localStorage.getItem("access_token") ?? "") : ""; }

// ── Types (unchanged from original) ───────────────────────────────────────────

interface CriterionScore {
  criterion_id: string; criterion_name?: string;
  raw_score: number; weighted_contribution: number; score_rationale?: string;
}
interface ShortlistedVendor {
  rank: number; vendor_id: string; vendor_name: string;
  total_score: number; score_confidence: number; recommendation: string;
  criterion_breakdown: CriterionScore[];
}
interface RejectedVendor {
  vendor_id: string; vendor_name: string;
  failed_checks: string[]; rejection_reasons: string[]; evidence_citations: string[];
}
interface ApprovalRouting {
  approval_tier: number; approver_role: string; sla_hours: number; sla_deadline: string;
}
interface Results {
  shortlisted_vendors: ShortlistedVendor[]; rejected_vendors: RejectedVendor[];
  approval_routing: ApprovalRouting; requires_human_review: boolean; review_reasons: string[];
}

// ── Score bar ──────────────────────────────────────────────────────────────────

const SCORE_BAND_LABEL: (score: number) => string = (score) => {
  if (score >= 8) return "8–10: Strongly recommended — meets or exceeds most criteria";
  if (score >= 6) return "6–7.9: Recommended — meets key criteria with minor gaps";
  if (score >= 4) return "4–5.9: Acceptable — partial compliance, consider risk";
  return "0–3.9: Marginal — significant gaps, high risk";
};

function ScoreBar({ score }: { score: number }) {
  const colour = score >= 8 ? "var(--color-success)" : score >= 6 ? "var(--color-info)" : score >= 4 ? "var(--color-warning)" : "var(--color-error)";
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
      <div style={{ flex: 1, height: 5, borderRadius: 3, background: "var(--color-border)", overflow: "hidden" }}>
        <div style={{ height: "100%", width: `${score * 10}%`, background: colour, borderRadius: 3, transition: "width 600ms ease" }} />
      </div>
      <span
        title={SCORE_BAND_LABEL(score)}
        style={{ fontFamily: MONO, fontSize: 13, fontWeight: 600, color: colour, flexShrink: 0, cursor: "help", borderBottom: `1px dotted ${colour}60` }}
      >
        {score.toFixed(1)}
      </span>
    </div>
  );
}

// ── Recommendation badge ───────────────────────────────────────────────────────

const REC_COLOUR: Record<string, string> = {
  strongly_recommended: "var(--color-success)",
  recommended:          "var(--color-info)",
  acceptable:           "var(--color-warning)",
  marginal:             "var(--color-error)",
};

function RecBadge({ rec }: { rec: string }) {
  const colour = REC_COLOUR[rec] ?? "#6B7280";
  return (
    <span style={{
      fontSize: 11, fontWeight: 600, color: colour,
      background: colour + "18", padding: "3px 9px",
      borderRadius: 12, border: `1px solid ${colour}40`, fontFamily: FONT,
    }}>
      {rec.replace(/_/g, " ").replace(/^\w/, c => c.toUpperCase())}
    </span>
  );
}

// ── Tab button ─────────────────────────────────────────────────────────────────

function Tab({ label, active, count, onClick }: { label: string; active: boolean; count?: number; onClick: () => void }) {
  return (
    <button onClick={onClick} style={{
      background: "none", border: "none", cursor: "pointer", fontFamily: FONT,
      fontSize: 13, fontWeight: active ? 600 : 400,
      color: active ? "var(--color-accent)" : "var(--color-text-muted)",
      borderBottom: `2px solid ${active ? "var(--color-accent)" : "transparent"}`,
      padding: "10px 16px", transition: "color var(--transition)",
    }}>
      {label}
      {count !== undefined && (
        <span style={{ marginLeft: 6, fontSize: 11, background: active ? "var(--color-accent)20" : "var(--color-border)", color: active ? "var(--color-accent)" : "var(--color-text-muted)", padding: "1px 6px", borderRadius: 10 }}>
          {count}
        </span>
      )}
    </button>
  );
}

// ── Page ───────────────────────────────────────────────────────────────────────

export default function ResultsPage() {
  const { runId }          = useParams<{ runId: string }>();
  const router             = useRouter();
  const { isDark } = useThemeContext();
  const P                  = isDark ? PALETTE : PALETTE_LIGHT;

  const [results,      setResults]      = useState<Results | null>(null);
  const [agentLog,     setAgentLog]     = useState<{ts: string; agent: string; status: string; message: string}[]>([]);
  const [vendorNames,  setVendorNames]  = useState<Record<string, string>>({});
  const [reEvaluating, setReEvaluating] = useState(false);
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const [auditTrail,   setAuditTrail]   = useState<any[]>([]);
  const [loading,     setLoading]     = useState(true);
  const [error,       setError]       = useState("");
  const [downloading, setDownloading] = useState<"pdf" | "excel" | null>(null);
  const [tab,         setTab]         = useState<"shortlisted" | "rejected" | "routing">("shortlisted");
  const [expanded,    setExpanded]    = useState<string | null>(null);
  const [logOpen,     setLogOpen]     = useState(false);
  const [auditOpen,   setAuditOpen]   = useState(false);

  const BG = "var(--bg-gradient)";

  useEffect(() => {
    const token = getToken();
    const headers = { Authorization: `Bearer ${token}` };
    Promise.all([
      fetch(`${API}/api/v1/evaluate/${runId}/results`, { headers })
        .then(r => { if (!r.ok) throw new Error(`${r.status}`); return r.json(); }),
      fetch(`${API}/api/v1/evaluate/${runId}/audit`, { headers })
        .then(r => r.ok ? r.json() : { events: [] })
        .catch(() => ({ events: [] })),
    ])
      .then(([d, a]) => {
        setResults(d.decision ?? d);
        setAgentLog(d.agent_log ?? []);
        setVendorNames(d.vendor_names ?? {});
        setAuditTrail(a.events ?? []);
        setLoading(false);
      })
      .catch(e => { setError(`Failed to load results: ${e.message}`); setLoading(false); });
  }, [runId]);

  async function download(format: "pdf" | "excel") {
    setDownloading(format);
    try {
      const ext = format === "pdf" ? "pdf" : "xlsx";
      const res = await fetch(`${API}/api/v1/evaluate/${runId}/report?format=${format}`, {
        headers: { Authorization: `Bearer ${getToken()}` },
      });
      if (res.ok) {
        const blob = await res.blob();
        const url  = URL.createObjectURL(blob);
        const a    = Object.assign(document.createElement("a"), { href: url, download: `evaluation-${runId}.${ext}` });
        a.click();
        URL.revokeObjectURL(url);
      }
    } finally { setDownloading(null); }
  }

  async function reEvaluate() {
    setReEvaluating(true);
    try {
      const res = await fetch(`${API}/api/v1/evaluate/${runId}/re-evaluate`, {
        method: "POST",
        headers: { Authorization: `Bearer ${getToken()}` },
      });
      if (!res.ok) throw new Error(`${res.status}`);
      router.push(`/${runId}/progress`);
    } catch {
      setReEvaluating(false);
    }
  }

  const CARD = { background: P.bg.surface, borderRadius: TOKENS.radius.card, border: `1px solid ${P.border.mid}` };

  if (loading) return (
    <div style={{ minHeight: "100vh", background: BG, fontFamily: FONT }}>
      <TopBar crumbs={[{ label: "Procurement", href: "/" }, { label: "Results" }]} />
      <div style={{ display: "flex", alignItems: "center", justifyContent: "center", height: "50vh" }}>
        <span style={{ color: "var(--color-text-muted)", fontSize: 13 }}>Loading results…</span>
      </div>
    </div>
  );

  if (!results) return (
    <div style={{ minHeight: "100vh", background: BG, fontFamily: FONT }}>
      <TopBar crumbs={[{ label: "Procurement", href: "/" }, { label: "Results" }]} />
      <div style={{ display: "flex", alignItems: "center", justifyContent: "center", height: "50vh" }}>
        <span style={{ color: "var(--color-error)", fontSize: 13 }}>{error}</span>
      </div>
    </div>
  );

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const shortlisted: any[] = results?.shortlisted_vendors ?? [];
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const rejected:    any[] = results?.rejected_vendors    ?? [];
  const allZero = shortlisted.length > 0 && shortlisted.every((v: { total_score: number }) => v.total_score === 0);
  const showReEvaluate = shortlisted.length === 0 || allZero;
  const ar          = results.approval_routing;

  return (
    <div style={{ minHeight: "100vh", background: BG, fontFamily: FONT }}>
      <TopBar
        crumbs={[
          { label: "Procurement", href: "/" },
          { label: runId.slice(0, 8) + "…" },
          { label: "Results" },
        ]}
        right={
          <div style={{ display: "flex", gap: 8 }}>
            <button onClick={() => download("pdf")} disabled={!!downloading} style={{
              background: "transparent", border: "1px solid var(--color-info)",
              borderRadius: 7, padding: "5px 12px", fontSize: 11,
              color: "var(--color-info)", cursor: "pointer", fontFamily: FONT, fontWeight: 500,
            }}>
              {downloading === "pdf" ? "…" : "↓ PDF"}
            </button>
            <button onClick={() => download("excel")} disabled={!!downloading} style={{
              background: "transparent", border: "1px solid var(--color-success)",
              borderRadius: 7, padding: "5px 12px", fontSize: 11,
              color: "var(--color-success)", cursor: "pointer", fontFamily: FONT, fontWeight: 500,
            }}>
              {downloading === "excel" ? "…" : "↓ Excel"}
            </button>
          </div>
        }
      />

      <main style={{ maxWidth: 900, margin: "0 auto", padding: "36px 28px 80px", display: "flex", flexDirection: "column", gap: 18 }}>

        {/* Zero-score / no-shortlist banner */}
        {showReEvaluate && (
          <div style={{
            background: "var(--color-warning)10", border: "1px solid var(--color-warning)50",
            borderRadius: TOKENS.radius.card, padding: "16px 20px",
            display: "flex", alignItems: "center", justifyContent: "space-between", gap: 16,
          }}>
            <div>
              <div style={{ fontSize: 13, fontWeight: 600, color: "var(--color-warning)", fontFamily: FONT, marginBottom: 3 }}>
                {shortlisted.length === 0 ? "No vendors were shortlisted" : "All vendors scored 0.0"}
              </div>
              <div style={{ fontSize: 12, color: "var(--color-text-muted)", fontFamily: FONT }}>
                The pipeline may have run before documents were fully indexed. Re-evaluate to retry with the same setup and documents.
              </div>
            </div>
            <button onClick={reEvaluate} disabled={reEvaluating} style={{
              background: "var(--color-warning)", color: "#1A1200", border: "none",
              borderRadius: TOKENS.radius.btn, padding: "9px 20px",
              fontSize: 13, fontFamily: FONT, fontWeight: 600,
              cursor: reEvaluating ? "not-allowed" : "pointer", flexShrink: 0,
              opacity: reEvaluating ? 0.6 : 1,
            }}>
              {reEvaluating ? "Starting…" : "↺ Re-evaluate"}
            </button>
          </div>
        )}

        {/* Summary header */}
        <div style={{ ...CARD, padding: "20px 22px" }}>
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 12 }}>
            <h1 style={{ fontSize: 18, fontWeight: 700, color: P.text.primary, margin: 0, fontFamily: FONT }}>
              Evaluation results
            </h1>
            <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
              {shortlisted.length > 1 && (
                <button onClick={() => router.push(`/${runId}/compare`)} style={{
                  background: "transparent", border: "1px solid var(--color-accent)40",
                  borderRadius: 7, padding: "5px 12px", fontSize: 11,
                  color: "var(--color-accent)", cursor: "pointer", fontFamily: FONT, fontWeight: 500,
                }}>
                  ⇔ Compare
                </button>
              )}
              <div style={{ fontFamily: MONO, fontSize: 11, color: P.text.muted }}>{runId}</div>
            </div>
          </div>
          <div style={{ display: "flex", gap: 24 }}>
            <div>
              <div style={{ fontSize: 10, fontWeight: 600, color: P.text.muted, textTransform: "uppercase", letterSpacing: "0.07em", fontFamily: FONT }}>Shortlisted</div>
              <div style={{ fontFamily: MONO, fontSize: 22, fontWeight: 600, color: "var(--color-success)", marginTop: 3 }}>{(shortlisted ?? []).length}</div>
            </div>
            <div>
              <div style={{ fontSize: 10, fontWeight: 600, color: "var(--color-text-muted)", textTransform: "uppercase", letterSpacing: "0.07em", fontFamily: FONT }}>Rejected</div>
              <div style={{ fontFamily: MONO, fontSize: 22, fontWeight: 600, color: "var(--color-error)", marginTop: 3 }}>{(rejected ?? []).length}</div>
            </div>
            {ar && (
              <div>
                <div style={{ fontSize: 10, fontWeight: 600, color: "var(--color-text-muted)", textTransform: "uppercase", letterSpacing: "0.07em", fontFamily: FONT }}>Approval tier</div>
                <div style={{ fontFamily: MONO, fontSize: 22, fontWeight: 600, color: "var(--color-warning)", marginTop: 3 }}>{ar.approval_tier}</div>
              </div>
            )}
          </div>
        </div>

        {/* Approval routing notice */}
        {ar && (
          <div style={{
            background: "var(--color-warning)12", border: "1px solid var(--color-warning)50",
            borderRadius: TOKENS.radius.card, padding: "14px 18px",
          }}>
            <div style={{ fontSize: 13, fontWeight: 600, color: "var(--color-warning)", marginBottom: 5, fontFamily: FONT }}>
              Approval required — Tier {ar.approval_tier}
            </div>
            <div style={{ fontSize: 12, color: "var(--color-text-secondary)", fontFamily: FONT }}>
              Routed to: <strong>{ar.approver_role.replace(/_/g, " ")}</strong>
              {" · "}SLA: {ar.sla_hours}h
              {" · "}Deadline: {new Date(ar.sla_deadline).toLocaleString()}
            </div>
            {results.requires_human_review && (
              <div style={{ fontSize: 12, color: "var(--color-error)", fontFamily: FONT, marginTop: 6 }}>
                ⚠ Human review required: {(results.review_reasons ?? []).join("; ")}
              </div>
            )}
            <button onClick={() => router.push(`/${runId}/approve`)} style={{
              marginTop: 10, background: "var(--color-warning)", color: "#1A0D00", border: "none",
              borderRadius: 7, padding: "7px 16px", fontSize: 12,
              fontFamily: FONT, fontWeight: 600, cursor: "pointer",
            }}>
              Open approval screen →
            </button>
          </div>
        )}

        {/* Tabs */}
        <div style={{ ...CARD, overflow: "hidden" }}>
          <div style={{ display: "flex", borderBottom: `1px solid ${P.border.dim}`, padding: "0 8px" }}>
            <Tab label="Shortlisted" active={tab === "shortlisted"} count={shortlisted.length} onClick={() => setTab("shortlisted")} />
            <Tab label="Rejected"    active={tab === "rejected"}    count={rejected.length}    onClick={() => setTab("rejected")} />
          </div>

          <div style={{ padding: "18px 20px" }}>
            {/* Shortlisted tab */}
            {tab === "shortlisted" && (
              <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
                {shortlisted.length === 0 && (
                  <p style={{ fontSize: 13, color: P.text.muted, fontFamily: FONT }}>No vendors shortlisted.</p>
                )}
                {shortlisted.map(v => {
                  const open = expanded === v.vendor_id;
                  return (
                    <div key={v.vendor_id} style={{ background: P.bg.elevated, borderRadius: 10, border: `1px solid ${P.border.dim}`, overflow: "hidden" }}>
                      {/* Vendor header */}
                      <div style={{ padding: "14px 16px", display: "flex", alignItems: "center", gap: 14 }}>
                        <div style={{
                          width: 32, height: 32, borderRadius: "50%", flexShrink: 0,
                          background: "var(--color-accent)", display: "flex", alignItems: "center", justifyContent: "center",
                          fontFamily: MONO, fontSize: 13, fontWeight: 700, color: "var(--color-accent-foreground)",
                        }}>#{v.rank}</div>
                        <div style={{ flex: 1 }}>
                          <div style={{ fontSize: 14, fontWeight: 600, color: P.text.primary, fontFamily: FONT, marginBottom: 4 }}>
                            {vendorNames[v.vendor_id] || v.vendor_name || v.vendor_id}
                          </div>
                          <ScoreBar score={v.total_score} />
                        </div>
                        <div style={{ display: "flex", flexDirection: "column", alignItems: "flex-end", gap: 6 }}>
                          <RecBadge rec={v.recommendation} />
                          <span style={{ fontSize: 11, color: P.text.muted, fontFamily: FONT }}>
                            {Math.round(v.score_confidence * 100)}% confidence
                          </span>
                        </div>
                      </div>

                      {/* Expand/collapse criteria */}
                      <button onClick={() => setExpanded(open ? null : v.vendor_id)} style={{
                        width: "100%", background: "none", border: "none", borderTop: `1px solid ${P.border.dim}`,
                        padding: "8px 16px", textAlign: "left", cursor: "pointer",
                        fontSize: 11, color: P.text.muted, fontFamily: FONT, display: "flex", justifyContent: "space-between",
                      }}>
                        <span>{open ? "Hide" : "Show"} criterion breakdown</span>
                        <span>{open ? "▲" : "▼"}</span>
                      </button>

                      {open && (
                        <div style={{ borderTop: `1px solid ${P.border.dim}`, padding: "12px 16px" }}>
                          <table style={{ width: "100%", borderCollapse: "collapse" }}>
                            <thead>
                              <tr>
                                {["Criterion", "Score /10", "Contribution", "Rationale"].map(h => (
                                  <th key={h} style={{ fontSize: 10, fontWeight: 600, color: P.text.muted, textAlign: "left", padding: "4px 8px", fontFamily: FONT, textTransform: "uppercase", letterSpacing: "0.05em" }}>{h}</th>
                                ))}
                              </tr>
                            </thead>
                            <tbody>
                              {/* eslint-disable-next-line @typescript-eslint/no-explicit-any */}
                              {v.criterion_breakdown.map((c: any) => (
                                <tr key={c.criterion_id} style={{ borderTop: `1px solid ${P.border.dim}` }}>
                                  <td style={{ fontSize: 12, color: P.text.primary, padding: "7px 8px", fontFamily: FONT }}>{c.criterion_name ?? c.criterion_id}</td>
                                  <td style={{ fontFamily: MONO, fontSize: 12, color: P.text.secondary, padding: "7px 8px" }}>{c.raw_score}/10</td>
                                  <td style={{ fontFamily: MONO, fontSize: 12, color: "var(--color-accent)", padding: "7px 8px" }}>{c.weighted_contribution.toFixed(2)}</td>
                                  <td style={{ fontSize: 11, color: P.text.muted, padding: "7px 8px", fontFamily: FONT, fontStyle: "italic" }}>{c.score_rationale ?? "—"}</td>
                                </tr>
                              ))}
                            </tbody>
                          </table>
                          <button onClick={() => router.push(`/${runId}/override?vendor=${v.vendor_id}`)} style={{
                            marginTop: 10, background: "transparent", border: `1px solid var(--color-warning)`,
                            borderRadius: 6, padding: "5px 12px", fontSize: 11,
                            color: "var(--color-warning)", cursor: "pointer", fontFamily: FONT,
                          }}>
                            Override this decision
                          </button>
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            )}

            {/* Rejected tab */}
            {tab === "rejected" && (
              <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
                {rejected.length === 0 && (
                  <p style={{ fontSize: 13, color: P.text.muted, fontFamily: FONT }}>No vendors rejected.</p>
                )}
                {rejected.map(v => (
                  <div key={v.vendor_id} style={{ background: "var(--color-error)10", border: "1px solid var(--color-error)30", borderRadius: 10, padding: "14px 16px" }}>
                    <div style={{ fontSize: 14, fontWeight: 600, color: "var(--color-error)", fontFamily: FONT, marginBottom: 6 }}>
                      {vendorNames[v.vendor_id] || v.vendor_name || v.vendor_id}
                    </div>
                    <div style={{ fontSize: 12, color: P.text.muted, fontFamily: FONT, marginBottom: 8 }}>
                      Failed checks: {v.failed_checks.join(", ")}
                    </div>
                    {/* eslint-disable-next-line @typescript-eslint/no-explicit-any */}
                    {v.evidence_citations.map((cite: any, i: number) => (
                      <div key={i} style={{
                        background: P.bg.surface, border: `1px solid ${P.border.dim}`,
                        borderRadius: 6, padding: "7px 10px", marginBottom: 5,
                        fontSize: 12, color: P.text.secondary, fontFamily: FONT, fontStyle: "italic",
                      }}>
                        &ldquo;{cite}&rdquo;
                      </div>
                    ))}
                    <button onClick={() => router.push(`/${runId}/override?vendor=${v.vendor_id}`)} style={{
                      marginTop: 4, background: "transparent", border: `1px solid #F59E0B`,
                      borderRadius: 6, padding: "5px 12px", fontSize: 11,
                      color: "#F59E0B", cursor: "pointer", fontFamily: FONT,
                    }}>
                      Override rejection
                    </button>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>

        {/* ── What happened — activity log ──────────────────────────────── */}
        {agentLog.length > 0 && (
          <div style={{ background: P.bg.surface, borderRadius: TOKENS.radius.card, border: `1px solid ${P.border.mid}`, overflow: "hidden" }}>
            <button
              onClick={() => setLogOpen(o => !o)}
              style={{
                width: "100%", background: "none", border: "none", cursor: "pointer",
                padding: "14px 20px", display: "flex", justifyContent: "space-between", alignItems: "center",
              }}
            >
              <span style={{ fontSize: 13, fontWeight: 600, color: P.text.primary, fontFamily: FONT }}>
                What happened during this evaluation
              </span>
              <span style={{ fontSize: 11, color: P.text.muted, fontFamily: FONT }}>{logOpen ? "▲ hide" : "▼ show"}</span>
            </button>

            {logOpen && (
              <div style={{ borderTop: `1px solid ${P.border.dim}`, padding: "8px 0" }}>
                {agentLog.map((entry, i) => {
                  const dotColour = entry.status === "done" ? "var(--color-success)" : entry.status === "blocked" ? "var(--color-error)" : "var(--color-info)";
                  const isLast    = i === agentLog.length - 1;
                  const time      = new Date(entry.ts).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
                  return (
                    <div key={i} style={{ display: "flex", gap: 0, padding: "0 20px" }}>
                      {/* Timeline spine */}
                      <div style={{ display: "flex", flexDirection: "column", alignItems: "center", marginRight: 14, paddingTop: 8 }}>
                        <div style={{ width: 8, height: 8, borderRadius: "50%", background: dotColour, flexShrink: 0 }} />
                        {!isLast && <div style={{ width: 1, flex: 1, background: P.border.dim, minHeight: 20 }} />}
                      </div>
                      {/* Content */}
                      <div style={{ paddingBottom: isLast ? 16 : 10, paddingTop: 4, flex: 1 }}>
                        <div style={{ fontSize: 13, color: P.text.primary, fontFamily: FONT, lineHeight: 1.5 }}>{entry.message}</div>
                        <div style={{ fontSize: 10, color: P.text.muted, fontFamily: MONO, marginTop: 2 }}>{time}</div>
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        )}
        {/* ── Audit trail ──────────────────────────────────────────────── */}
        {auditTrail.length > 0 && (
          <div style={{ background: P.bg.surface, borderRadius: TOKENS.radius.card, border: `1px solid ${P.border.mid}`, overflow: "hidden" }}>
            <button
              onClick={() => setAuditOpen(o => !o)}
              style={{
                width: "100%", background: "none", border: "none", cursor: "pointer",
                padding: "14px 20px", display: "flex", justifyContent: "space-between", alignItems: "center",
              }}
            >
              <span style={{ fontSize: 13, fontWeight: 600, color: P.text.primary, fontFamily: FONT }}>
                Audit trail ({auditTrail.length} events)
              </span>
              <span style={{ fontSize: 11, color: P.text.muted, fontFamily: FONT }}>{auditOpen ? "▲ hide" : "▼ show"}</span>
            </button>

            {auditOpen && (
              <div style={{ borderTop: `1px solid ${P.border.dim}` }}>
                <table style={{ width: "100%", borderCollapse: "collapse" }}>
                  <thead>
                    <tr style={{ background: P.bg.elevated }}>
                      {["When", "Event", "Actor", "Agent", "Detail"].map(h => (
                        <th key={h} style={{
                          fontSize: 10, fontWeight: 600, color: P.text.muted, textAlign: "left",
                          padding: "8px 14px", fontFamily: FONT, textTransform: "uppercase", letterSpacing: "0.06em",
                        }}>{h}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {auditTrail.map((ev, i) => {
                      const isRun      = ev.event_type.startsWith("run.");
                      const isOverride = ev.event_type.startsWith("override.");
                      const dotColour  = isOverride ? "var(--color-warning)" : ev.event_type.endsWith(".blocked") ? "var(--color-error)" : ev.event_type.endsWith(".completed") ? "var(--color-success)" : "var(--color-info)";
                      const time       = new Date(ev.ts).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
                      const date       = new Date(ev.ts).toLocaleDateString();
                      return (
                        <tr key={i} style={{ borderTop: `1px solid ${P.border.dim}`, background: i % 2 === 0 ? "transparent" : P.bg.elevated + "60" }}>
                          <td style={{ padding: "7px 14px", fontFamily: MONO, fontSize: 11, color: P.text.muted, whiteSpace: "nowrap" }}>
                            {date}<br />{time}
                          </td>
                          <td style={{ padding: "7px 14px" }}>
                            <span style={{
                              fontSize: 11, fontWeight: 600,
                              color: dotColour, background: dotColour + "18",
                              padding: "2px 8px", borderRadius: 10,
                              fontFamily: MONO, border: `1px solid ${dotColour}40`,
                            }}>{ev.event_type}</span>
                          </td>
                          <td style={{ padding: "7px 14px", fontSize: 12, color: isRun || isOverride ? P.text.primary : P.text.muted, fontFamily: FONT }}>
                            {ev.actor}
                          </td>
                          <td style={{ padding: "7px 14px", fontSize: 11, color: P.text.muted, fontFamily: MONO }}>
                            {ev.agent ?? "—"}
                          </td>
                          <td style={{ padding: "7px 14px", fontSize: 11, color: P.text.muted, fontFamily: FONT, maxWidth: 260, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                            {Object.entries(ev.detail || {}).map(([k, v]) => `${k}: ${v}`).join(" · ") || "—"}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        )}
      </main>
    </div>
  );
}
