"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import Link from "next/link";
import { api, isLoggedIn } from "@/lib/api";
import { FONT, DISPLAY, MONO } from "@/lib/theme";

// ── Types matching DecisionOutput / ShortlistedVendor / CriterionScore ────────

interface CriterionScore {
  criterion_id: string;
  vendor_id: string;
  raw_score: number;
  weighted_contribution: number;
  confidence: number;
  rubric_band_applied: string;
  score_rationale: string;
}

interface ShortlistedVendor {
  vendor_id: string;
  vendor_name: string;
  rank: number;
  total_score: number;
  score_confidence: number;
  recommendation: string;
  criterion_breakdown: CriterionScore[];
}

interface RejectedVendor {
  vendor_id: string;
  vendor_name: string;
  rejection_reasons: string[];
}

interface DecisionOutput {
  shortlisted_vendors: ShortlistedVendor[];
  rejected_vendors: RejectedVendor[];
  decision_confidence: number;
}

interface RunResults {
  rfp_title: string;
  vendors: { vendor_name: string; decision: string; total_score: number }[];
  decision: DecisionOutput | null;
}

// ── Helpers ───────────────────────────────────────────────────────────────────

function scoreBar(score: number, max = 10) {
  const pct = Math.min(100, (score / max) * 100);
  const color = score >= 7 ? "var(--color-success)"
              : score >= 4 ? "var(--color-warning)"
              : "var(--color-error)";
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
      <div style={{
        flex: 1, height: 6, backgroundColor: "var(--color-border)",
        borderRadius: 3, overflow: "hidden",
      }}>
        <div style={{
          height: "100%", width: `${pct}%`,
          backgroundColor: color, borderRadius: 3,
          transition: "width 400ms ease-out",
        }} />
      </div>
      <span style={{
        fontFamily: MONO, fontSize: 12, fontWeight: 700,
        color: "var(--color-text-primary)", minWidth: 20, textAlign: "right",
        fontVariantNumeric: "tabular-nums",
      }}>
        {score}
      </span>
    </div>
  );
}

// ── Page ──────────────────────────────────────────────────────────────────────

export default function ComparePage() {
  const params = useParams();
  const router = useRouter();
  const runId  = params?.runId as string | undefined;

  const [data,   setData]   = useState<RunResults | null>(null);
  const [error,  setError]  = useState<string | null>(null);
  const [active, setActive] = useState<string | null>(null); // expanded vendor

  useEffect(() => {
    if (!isLoggedIn()) { router.replace("/login"); return; }
    if (!runId) return;
    api.get<RunResults>(`/api/v1/evaluate/${runId}/results`, {
      on401: () => router.push("/login"),
    })
      .then(d => { setData(d); })
      .catch(e => setError(e?.message ?? "Failed to load results"));
  }, [runId, router]);

  // Collect all unique criterion_ids across shortlisted vendors
  const shortlisted = data?.decision?.shortlisted_vendors ?? [];
  const rejected    = data?.decision?.rejected_vendors    ?? [];

  const criteriaIds: string[] = [];
  for (const v of shortlisted) {
    for (const c of v.criterion_breakdown ?? []) {
      if (!criteriaIds.includes(c.criterion_id)) criteriaIds.push(c.criterion_id);
    }
  }

  const scoreFor = (vendor: ShortlistedVendor, criterionId: string) =>
    vendor.criterion_breakdown?.find(c => c.criterion_id === criterionId);

  return (
    <div style={{
      minHeight: "100vh",
      backgroundColor: "var(--color-background)",
      background: "var(--bg-gradient)",
      padding: "48px 32px",
    }}>
      <div style={{ maxWidth: 960, margin: "0 auto" }}>

        {/* Back */}
        <Link href={`/${runId}/results`} style={{
          display: "inline-flex", alignItems: "center", gap: 6,
          fontFamily: FONT, fontSize: 13, fontWeight: 500,
          color: "var(--color-text-muted)", textDecoration: "none", marginBottom: 32,
        }}>
          ← Back to results
        </Link>

        {/* Loading */}
        {!data && !error && (
          <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
            <div style={{
              width: 16, height: 16, borderRadius: "50%",
              borderTop: "2px solid var(--color-info)",
              borderBottom: "2px solid transparent",
              borderLeft: "2px solid transparent",
              borderRight: "2px solid transparent",
              animation: "spin 0.7s linear infinite",
            }} />
            <p style={{ fontFamily: FONT, fontSize: 14, color: "var(--color-text-muted)" }}>
              Loading comparison…
            </p>
          </div>
        )}

        {/* Error */}
        {error && (
          <div style={{
            padding: "12px 16px", borderRadius: "var(--radius)",
            borderTop: "1px solid var(--color-border)",
            borderBottom: "1px solid var(--color-border)",
            borderLeft: "3px solid var(--color-error)",
            borderRight: "1px solid var(--color-border)",
          }}>
            <p style={{ fontFamily: FONT, fontSize: 14, color: "var(--color-error)" }}>{error}</p>
          </div>
        )}

        {data && (
          <>
            {/* Header */}
            <div style={{ marginBottom: 32 }}>
              <p style={{
                fontFamily: FONT, fontWeight: 600, fontSize: 11,
                letterSpacing: "0.1em", textTransform: "uppercase",
                color: "var(--color-info)", marginBottom: 8,
              }}>
                Vendor Comparison
              </p>
              <h1 style={{
                fontFamily: DISPLAY, fontWeight: 800, fontSize: 32,
                letterSpacing: "-0.03em", lineHeight: 1.0,
                color: "var(--color-text-primary)", marginBottom: 4,
              }}>
                {data.rfp_title || "Evaluation"}
              </h1>
              <p style={{ fontFamily: FONT, fontSize: 13, color: "var(--color-text-muted)" }}>
                {shortlisted.length} shortlisted · {rejected.length} rejected
                {data.decision?.decision_confidence != null && (
                  <> · Confidence {Math.round(data.decision.decision_confidence * 100)}%</>
                )}
              </p>
            </div>

            {/* Score summary cards */}
            <div style={{
              display: "grid",
              gridTemplateColumns: `repeat(${Math.min(shortlisted.length + rejected.length, 4)}, 1fr)`,
              gap: 12, marginBottom: 32,
            }}>
              {shortlisted.map(v => (
                <div key={v.vendor_id} style={{
                  padding: "14px 16px",
                  backgroundColor: "var(--color-surface)",
                  borderTop: "1px solid var(--color-border)",
                  borderBottom: "1px solid var(--color-border)",
                  borderLeft: "3px solid var(--color-success)",
                  borderRight: "1px solid var(--color-border)",
                  borderRadius: "var(--radius)",
                  boxShadow: "var(--shadow-sm)",
                }}>
                  <p style={{ fontFamily: FONT, fontWeight: 700, fontSize: 13, color: "var(--color-text-primary)", marginBottom: 4 }}>
                    {v.vendor_name}
                  </p>
                  <p style={{ fontFamily: MONO, fontWeight: 800, fontSize: 28, color: "var(--color-success)", lineHeight: 1, marginBottom: 4, fontVariantNumeric: "tabular-nums" }}>
                    {v.total_score?.toFixed(1) ?? "—"}
                  </p>
                  <p style={{ fontFamily: FONT, fontSize: 10, fontWeight: 600, letterSpacing: "0.08em", textTransform: "uppercase", color: "var(--color-success)" }}>
                    #{v.rank} · Shortlisted
                  </p>
                </div>
              ))}
              {rejected.map(v => (
                <div key={v.vendor_id} style={{
                  padding: "14px 16px",
                  backgroundColor: "var(--color-surface)",
                  borderTop: "1px solid var(--color-border)",
                  borderBottom: "1px solid var(--color-border)",
                  borderLeft: "3px solid var(--color-error)",
                  borderRight: "1px solid var(--color-border)",
                  borderRadius: "var(--radius)",
                }}>
                  <p style={{ fontFamily: FONT, fontWeight: 600, fontSize: 13, color: "var(--color-text-secondary)", marginBottom: 4 }}>
                    {v.vendor_name}
                  </p>
                  <p style={{ fontFamily: MONO, fontWeight: 700, fontSize: 22, color: "var(--color-error)", lineHeight: 1, marginBottom: 4 }}>
                    —
                  </p>
                  <p style={{ fontFamily: FONT, fontSize: 10, fontWeight: 600, letterSpacing: "0.08em", textTransform: "uppercase", color: "var(--color-error)" }}>
                    Rejected
                  </p>
                </div>
              ))}
            </div>

            {/* Criterion breakdown table — shortlisted only */}
            {criteriaIds.length > 0 && shortlisted.length > 0 && (
              <div style={{ marginBottom: 32 }}>
                <p style={{
                  fontFamily: FONT, fontSize: 10, fontWeight: 600,
                  letterSpacing: "0.08em", textTransform: "uppercase",
                  color: "var(--color-text-muted)", marginBottom: 12,
                }}>
                  Score breakdown by criterion
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
                  {/* Table header */}
                  <div style={{
                    display: "grid",
                    gridTemplateColumns: `200px repeat(${shortlisted.length}, 1fr)`,
                    borderBottom: "1px solid var(--color-border)",
                    backgroundColor: "var(--color-background)",
                  }}>
                    <div style={{ padding: "10px 16px" }}>
                      <p style={{ fontFamily: FONT, fontSize: 10, fontWeight: 600, letterSpacing: "0.06em", textTransform: "uppercase", color: "var(--color-text-muted)" }}>
                        Criterion
                      </p>
                    </div>
                    {shortlisted.map(v => (
                      <div key={v.vendor_id} style={{ padding: "10px 16px" }}>
                        <p style={{ fontFamily: FONT, fontSize: 12, fontWeight: 700, color: "var(--color-text-primary)" }}>
                          {v.vendor_name}
                        </p>
                      </div>
                    ))}
                  </div>

                  {/* Rows */}
                  {criteriaIds.map((cid, i) => (
                    <div key={cid} style={{
                      display: "grid",
                      gridTemplateColumns: `200px repeat(${shortlisted.length}, 1fr)`,
                      borderBottom: i < criteriaIds.length - 1 ? "1px solid var(--color-border)" : "none",
                    }}>
                      <div style={{ padding: "12px 16px", borderRight: "1px solid var(--color-border)" }}>
                        <p style={{
                          fontFamily: FONT, fontSize: 12, fontWeight: 500,
                          color: "var(--color-text-primary)", lineHeight: 1.4,
                        }}>
                          {cid.replace(/_/g, " ").replace(/\b\w/g, c => c.toUpperCase())}
                        </p>
                      </div>
                      {shortlisted.map(v => {
                        const c = scoreFor(v, cid);
                        return (
                          <div key={v.vendor_id}
                            style={{ padding: "12px 16px", cursor: c ? "pointer" : "default" }}
                            onClick={() => c && setActive(active === `${v.vendor_id}-${cid}` ? null : `${v.vendor_id}-${cid}`)}
                          >
                            {c ? (
                              <>
                                {scoreBar(c.raw_score)}
                                {active === `${v.vendor_id}-${cid}` && (
                                  <p style={{
                                    fontFamily: FONT, fontSize: 11,
                                    color: "var(--color-text-muted)", lineHeight: 1.5, marginTop: 6,
                                  }}>
                                    {c.score_rationale}
                                  </p>
                                )}
                              </>
                            ) : (
                              <p style={{ fontFamily: MONO, fontSize: 12, color: "var(--color-text-muted)" }}>—</p>
                            )}
                          </div>
                        );
                      })}
                    </div>
                  ))}
                </div>
                <p style={{ fontFamily: FONT, fontSize: 11, color: "var(--color-text-muted)", marginTop: 6 }}>
                  Click any score to see the rationale.
                </p>
              </div>
            )}

            {/* Rejection reasons */}
            {rejected.length > 0 && (
              <div style={{ marginBottom: 32 }}>
                <p style={{
                  fontFamily: FONT, fontSize: 10, fontWeight: 600,
                  letterSpacing: "0.08em", textTransform: "uppercase",
                  color: "var(--color-error)", marginBottom: 12,
                }}>
                  Rejection reasons
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
                    <div key={v.vendor_id} style={{
                      padding: "14px 16px",
                      borderBottom: i < rejected.length - 1 ? "1px solid var(--color-border)" : "none",
                      borderLeft: "3px solid var(--color-error)",
                    }}>
                      <p style={{ fontFamily: FONT, fontWeight: 600, fontSize: 13, color: "var(--color-text-primary)", marginBottom: 6 }}>
                        {v.vendor_name}
                      </p>
                      <ul style={{ margin: 0, paddingLeft: 16 }}>
                        {(v.rejection_reasons ?? []).map((r, j) => (
                          <li key={j} style={{ fontFamily: FONT, fontSize: 12, color: "var(--color-text-muted)", lineHeight: 1.6 }}>
                            {r}
                          </li>
                        ))}
                      </ul>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* No data fallback */}
            {shortlisted.length === 0 && rejected.length === 0 && (
              <p style={{ fontFamily: FONT, fontSize: 14, color: "var(--color-text-muted)", padding: "24px 0" }}>
                No vendor comparison data available for this evaluation.
              </p>
            )}

            {/* Actions */}
            <div style={{ display: "flex", gap: 12 }}>
              <Link href={`/${runId}/results`} style={{
                display: "inline-flex", alignItems: "center", gap: 6,
                padding: "9px 18px",
                backgroundColor: "var(--color-accent)",
                color: "var(--color-accent-foreground)",
                borderRadius: "var(--radius)",
                fontFamily: FONT, fontWeight: 600, fontSize: 13,
                textDecoration: "none",
              }}>
                ← Full report
              </Link>
            </div>
          </>
        )}
      </div>

      <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
    </div>
  );
}
