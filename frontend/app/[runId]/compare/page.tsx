"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { TopBar, useTheme } from "@/components/TopBar";
import { PALETTE, PALETTE_LIGHT, FONT, MONO, TOKENS } from "@/lib/theme";

const API = process.env.NEXT_PUBLIC_API_URL ?? "";
function getToken() { return typeof window !== "undefined" ? (localStorage.getItem("access_token") ?? "") : ""; }

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
  failed_checks: string[]; rejection_reasons: string[];
}
interface Results {
  shortlisted_vendors: ShortlistedVendor[];
  rejected_vendors: RejectedVendor[];
}

function scoreColour(score: number) {
  if (score >= 8) return "#10B981";
  if (score >= 6) return "#00D4AA";
  if (score >= 4) return "#F59E0B";
  return "#EF4444";
}

export default function ComparePage() {
  const { runId }          = useParams<{ runId: string }>();
  const router             = useRouter();
  const { isDark, toggle } = useTheme();
  const P                  = isDark ? PALETTE : PALETTE_LIGHT;

  const [results,  setResults]  = useState<Results | null>(null);
  const [loading,  setLoading]  = useState(true);
  const [error,    setError]    = useState("");

  useEffect(() => {
    fetch(`${API}/api/v1/evaluate/${runId}/results`, {
      headers: { Authorization: `Bearer ${getToken()}` },
    })
      .then(r => r.json())
      .then(d => { setResults(d); setLoading(false); })
      .catch(() => { setError("Failed to load results."); setLoading(false); });
  }, [runId]);

  const BG = isDark ? "#090C12" : "#F8FAFC";
  const CARD = { background: P.bg.surface, border: `1px solid ${P.border.mid}`, borderRadius: TOKENS.radius.card };

  if (loading) return (
    <div style={{ minHeight: "100vh", background: BG, fontFamily: FONT }}>
      <TopBar isDark={isDark} onToggle={toggle} crumbs={[{ label: "Results", href: `/${runId}/results` }, { label: "Compare" }]} />
      <div style={{ display: "flex", justifyContent: "center", alignItems: "center", height: "50vh" }}>
        <span style={{ color: P.text.muted, fontSize: 13 }}>Loading comparison…</span>
      </div>
    </div>
  );

  if (!results || error) return (
    <div style={{ minHeight: "100vh", background: BG, fontFamily: FONT }}>
      <TopBar isDark={isDark} onToggle={toggle} crumbs={[{ label: "Results", href: `/${runId}/results` }, { label: "Compare" }]} />
      <div style={{ display: "flex", justifyContent: "center", alignItems: "center", height: "50vh" }}>
        <span style={{ color: "#EF4444", fontSize: 13 }}>{error || "No results found."}</span>
      </div>
    </div>
  );

  const shortlisted = results.shortlisted_vendors ?? [];
  const rejected    = results.rejected_vendors    ?? [];
  const allVendors  = shortlisted;

  // Build union of all criteria across all shortlisted vendors
  const criteriaMap = new Map<string, string>();
  for (const v of shortlisted) {
    for (const c of (v.criterion_breakdown ?? [])) {
      criteriaMap.set(c.criterion_id, c.criterion_name ?? c.criterion_id);
    }
  }
  const criteria = Array.from(criteriaMap.entries());

  const COL_W = Math.max(140, Math.floor(600 / Math.max(allVendors.length, 1)));

  return (
    <div style={{ minHeight: "100vh", background: BG, fontFamily: FONT }}>
      <TopBar
        isDark={isDark}
        onToggle={toggle}
        crumbs={[
          { label: "Procurement", href: "/" },
          { label: runId.slice(0, 8) + "…" },
          { label: "Results", href: `/${runId}/results` },
          { label: "Compare" },
        ]}
        right={
          <button
            onClick={() => router.push(`/${runId}/results`)}
            style={{ fontSize: 12, color: P.text.muted, background: "none", border: `1px solid ${P.border.mid}`, borderRadius: 7, padding: "5px 12px", cursor: "pointer", fontFamily: FONT }}
          >
            ← Results
          </button>
        }
      />

      <div style={{ maxWidth: 1100, margin: "0 auto", padding: "36px 24px 80px" }}>
        <h1 style={{ fontSize: 20, fontWeight: 700, color: P.text.primary, margin: "0 0 6px", fontFamily: FONT }}>
          Side-by-side comparison
        </h1>
        <p style={{ fontSize: 12, color: P.text.muted, margin: "0 0 28px", fontFamily: FONT }}>
          {shortlisted.length} shortlisted vendor{shortlisted.length !== 1 ? "s" : ""} · {criteria.length} scoring criteria
        </p>

        {shortlisted.length === 0 ? (
          <div style={{ ...CARD, padding: "40px 24px", textAlign: "center", color: P.text.muted, fontSize: 13 }}>
            No shortlisted vendors to compare. {rejected.length > 0 && `${rejected.length} vendor(s) were rejected.`}
          </div>
        ) : (
          <div style={{ overflowX: "auto" }}>
            <table style={{ borderCollapse: "collapse", width: "100%", minWidth: 400 }}>
              <thead>
                <tr>
                  {/* Criteria column header */}
                  <th style={{
                    textAlign: "left", padding: "10px 16px", fontSize: 11, fontWeight: 700,
                    color: P.text.muted, fontFamily: FONT, letterSpacing: "0.06em",
                    background: P.bg.elevated, borderBottom: `1px solid ${P.border.mid}`,
                    minWidth: 160, position: "sticky", left: 0, zIndex: 2,
                  }}>
                    CRITERION
                  </th>
                  {shortlisted.map(v => (
                    <th key={v.vendor_id} style={{
                      textAlign: "center", padding: "10px 16px", fontSize: 12, fontWeight: 700,
                      color: P.text.primary, fontFamily: FONT,
                      background: P.bg.elevated, borderBottom: `1px solid ${P.border.mid}`,
                      minWidth: COL_W,
                    }}>
                      <div style={{ fontSize: 13, fontWeight: 700, marginBottom: 4 }}>
                        #{v.rank} {v.vendor_name || v.vendor_id}
                      </div>
                      <div style={{ fontFamily: MONO, fontSize: 18, fontWeight: 800, color: scoreColour(v.total_score) }}>
                        {v.total_score.toFixed(1)}
                      </div>
                      <div style={{ fontSize: 10, color: P.text.muted, marginTop: 2 }}>
                        {v.recommendation.replace(/_/g, " ").replace(/^\w/, c => c.toUpperCase())}
                      </div>
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {criteria.map(([criterionId, criterionName], rowIdx) => (
                  <tr key={criterionId} style={{ background: rowIdx % 2 === 0 ? P.bg.surface : P.bg.elevated }}>
                    <td style={{
                      padding: "10px 16px", fontSize: 12, color: P.text.secondary, fontFamily: FONT,
                      borderBottom: `1px solid ${P.border.dim}`,
                      position: "sticky", left: 0, background: rowIdx % 2 === 0 ? P.bg.surface : P.bg.elevated,
                      zIndex: 1,
                    }}>
                      {criterionName}
                    </td>
                    {shortlisted.map(v => {
                      const sc = v.criterion_breakdown?.find(c => c.criterion_id === criterionId);
                      const raw = sc?.raw_score ?? null;
                      const col = raw !== null ? scoreColour(raw) : P.text.muted;
                      return (
                        <td key={v.vendor_id} style={{
                          textAlign: "center", padding: "10px 16px",
                          borderBottom: `1px solid ${P.border.dim}`,
                        }}>
                          {raw !== null ? (
                            <div title={sc?.score_rationale ?? ""} style={{ cursor: sc?.score_rationale ? "help" : "default" }}>
                              <span style={{ fontFamily: MONO, fontSize: 14, fontWeight: 700, color: col }}>
                                {raw.toFixed(1)}
                              </span>
                              <div style={{ marginTop: 4, height: 4, borderRadius: 2, background: P.border.dim, overflow: "hidden", width: 60, margin: "4px auto 0" }}>
                                <div style={{ height: "100%", width: `${raw * 10}%`, background: col, borderRadius: 2 }} />
                              </div>
                            </div>
                          ) : (
                            <span style={{ color: P.text.muted, fontSize: 11 }}>—</span>
                          )}
                        </td>
                      );
                    })}
                  </tr>
                ))}
                {/* Total row */}
                <tr style={{ background: P.bg.elevated, borderTop: `2px solid ${P.border.mid}` }}>
                  <td style={{
                    padding: "12px 16px", fontSize: 12, fontWeight: 700, color: P.text.primary, fontFamily: FONT,
                    position: "sticky", left: 0, background: P.bg.elevated, zIndex: 1,
                  }}>
                    TOTAL SCORE
                  </td>
                  {shortlisted.map(v => (
                    <td key={v.vendor_id} style={{ textAlign: "center", padding: "12px 16px" }}>
                      <span style={{ fontFamily: MONO, fontSize: 16, fontWeight: 800, color: scoreColour(v.total_score) }}>
                        {v.total_score.toFixed(1)}
                      </span>
                    </td>
                  ))}
                </tr>
              </tbody>
            </table>
          </div>
        )}

        {/* Rejected vendors summary */}
        {rejected.length > 0 && (
          <div style={{ marginTop: 32 }}>
            <div style={{ fontSize: 11, fontWeight: 700, color: P.text.muted, letterSpacing: "0.07em", textTransform: "uppercase", marginBottom: 12, fontFamily: FONT }}>
              Rejected vendors ({rejected.length})
            </div>
            <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
              {rejected.map(v => (
                <div key={v.vendor_id} style={{
                  ...CARD, padding: "12px 16px",
                  display: "flex", alignItems: "center", justifyContent: "space-between", gap: 12,
                }}>
                  <span style={{ fontSize: 13, fontWeight: 600, color: "#EF4444", fontFamily: FONT }}>
                    {v.vendor_name || v.vendor_id}
                  </span>
                  <span style={{ fontSize: 11, color: P.text.muted, fontFamily: FONT }}>
                    Failed: {(v.failed_checks ?? []).join(", ") || "—"}
                  </span>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
