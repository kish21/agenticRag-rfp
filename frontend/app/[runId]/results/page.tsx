"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import Link from "next/link";
import { api, isLoggedIn } from "@/lib/api";
import { FONT, DISPLAY, MONO } from "@/lib/theme";
import { useBreakpoint } from "@/lib/hooks";

interface VendorScore {
  vendor_name: string;
  decision: string;
  total_score: number;
  summary?: string;
}

interface EvalResults {
  recommendation?: string;
  approval_tier?: string;
  vendors?: VendorScore[];
}

export default function ResultsPage() {
  const params   = useParams();
  const router   = useRouter();
  const bp       = useBreakpoint();
  const runId    = params?.runId as string | undefined;

  const [results, setResults] = useState<EvalResults | null>(null);
  const [error,   setError]   = useState<string | null>(null);

  useEffect(() => {
    if (!isLoggedIn()) { router.replace("/login"); return; }
    if (!runId) return;
    api.get<EvalResults>(`/api/v1/evaluate/${runId}/results`)
      .then(setResults)
      .catch(e => setError(e?.message ?? "Failed to load results"));
  }, [runId, router]);

  const allVendors  = results?.vendors ?? [];
  const shortlisted = allVendors.filter(v => v.decision === "shortlisted");
  const rejected    = allVendors.filter(v => v.decision === "rejected");

  return (
    <div style={{
      minHeight: "100vh",
      backgroundColor: "var(--color-background)",
      background: "var(--bg-gradient)",
      padding: "48px 32px",
    }}>
      <div style={{ maxWidth: 720, margin: "0 auto" }}>

        {/* Back */}
        <Link
          href="/"
          style={{
            display: "inline-flex", alignItems: "center", gap: 6,
            fontFamily: FONT, fontSize: 13, fontWeight: 500,
            color: "var(--color-text-muted)", textDecoration: "none",
            marginBottom: 32,
          }}
        >
          ← Back to evaluations
        </Link>

        {/* Loading */}
        {!results && !error && (
          <div style={{ display: "flex", alignItems: "center", gap: 10, padding: "40px 0" }}>
            <div style={{
              width: 16, height: 16,
              borderTop: "2px solid var(--color-info)",
              borderBottom: "2px solid transparent",
              borderLeft: "2px solid transparent",
              borderRight: "2px solid transparent",
              borderRadius: "50%",
              animation: "spin 0.7s linear infinite",
            }} />
            <p style={{ fontFamily: FONT, fontSize: 14, color: "var(--color-text-muted)" }}>
              Loading results…
            </p>
          </div>
        )}

        {/* Error */}
        {error && (
          <div role="alert" style={{
            padding: "14px 16px",
            backgroundColor: "var(--color-surface)",
            borderTop: "1px solid var(--color-border)",
            borderBottom: "1px solid var(--color-border)",
            borderLeft: "3px solid var(--color-error)",
            borderRight: "1px solid var(--color-border)",
            borderRadius: "var(--radius)",
          }}>
            <p style={{ fontFamily: FONT, fontSize: 14, color: "var(--color-error)" }}>{error}</p>
          </div>
        )}

        {/* Results */}
        {results && (
          <>
            {/* Header */}
            <div style={{ marginBottom: 32 }}>
              <p style={{
                fontFamily: FONT, fontWeight: 600, fontSize: 11,
                letterSpacing: "0.1em", textTransform: "uppercase",
                color: "var(--color-success)", marginBottom: 8,
              }}>
                Evaluation complete
              </p>
              <h1 style={{
                fontFamily: DISPLAY, fontWeight: 800,
                fontSize: 36, letterSpacing: "-0.03em", lineHeight: 1.0,
                color: "var(--color-text-primary)", marginBottom: 16,
              }}>
                Vendor Rankings
              </h1>

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
                  <p style={{
                    fontFamily: FONT, fontSize: 10, fontWeight: 600,
                    letterSpacing: "0.08em", textTransform: "uppercase",
                    color: "var(--color-success)", marginBottom: 4,
                  }}>
                    Recommendation{results.approval_tier ? ` · ${results.approval_tier}` : ""}
                  </p>
                  <p style={{ fontFamily: FONT, fontSize: 14, color: "var(--color-text-primary)", lineHeight: 1.6 }}>
                    {results.recommendation}
                  </p>
                </div>
              )}
            </div>

            {/* Shortlisted */}
            {shortlisted.length > 0 && (
              <div style={{ marginBottom: 20 }}>
                <p style={{
                  fontFamily: FONT, fontSize: 10, fontWeight: 600,
                  letterSpacing: "0.08em", textTransform: "uppercase",
                  color: "var(--color-success)", marginBottom: 10,
                }}>
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
                  {shortlisted.map((v, i) => (
                    <div key={v.vendor_name} style={{
                      padding: "14px 16px",
                      borderBottom: i < shortlisted.length - 1 ? "1px solid var(--color-border)" : "none",
                      borderLeft: "3px solid var(--color-success)",
                    }}>
                      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: v.summary ? 4 : 0 }}>
                        <p style={{ fontFamily: FONT, fontWeight: 600, fontSize: 14, color: "var(--color-text-primary)" }}>
                          {v.vendor_name}
                        </p>
                        <span style={{ fontFamily: MONO, fontWeight: 700, fontSize: 22, color: "var(--color-text-primary)", fontVariantNumeric: "tabular-nums" }}>
                          {typeof v.total_score === "number" ? v.total_score.toFixed(1) : "—"}
                        </span>
                      </div>
                      {v.summary && (
                        <p style={{ fontFamily: FONT, fontSize: 12, color: "var(--color-text-muted)", lineHeight: 1.6 }}>
                          {v.summary}
                        </p>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Rejected */}
            {rejected.length > 0 && (
              <div style={{ marginBottom: 40 }}>
                <p style={{
                  fontFamily: FONT, fontSize: 10, fontWeight: 600,
                  letterSpacing: "0.08em", textTransform: "uppercase",
                  color: "var(--color-error)", marginBottom: 10,
                }}>
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

            {/* No vendor data */}
            {allVendors.length === 0 && (
              <p style={{ fontFamily: FONT, fontSize: 14, color: "var(--color-text-muted)", padding: "24px 0" }}>
                No vendor scores available for this evaluation.
              </p>
            )}

            {/* Actions */}
            <div style={{ display: "flex", gap: 12, flexWrap: "wrap" }}>
              <Link
                href="/"
                style={{
                  display: "inline-flex", alignItems: "center", gap: 6,
                  padding: "9px 18px",
                  backgroundColor: "var(--color-accent)",
                  color: "var(--color-accent-foreground)",
                  borderRadius: "var(--radius)",
                  fontFamily: FONT, fontWeight: 600, fontSize: 13,
                  textDecoration: "none",
                }}
              >
                ← Back to dashboard
              </Link>
              <Link
                href={`/${runId}/compare`}
                style={{
                  display: "inline-flex", alignItems: "center", gap: 6,
                  padding: "9px 18px",
                  backgroundColor: "transparent",
                  borderTop: "1px solid var(--color-border)",
                  borderBottom: "1px solid var(--color-border)",
                  borderLeft: "1px solid var(--color-border)",
                  borderRight: "1px solid var(--color-border)",
                  borderRadius: "var(--radius)",
                  fontFamily: FONT, fontWeight: 500, fontSize: 13,
                  color: "var(--color-text-secondary)",
                  textDecoration: "none",
                }}
              >
                Compare vendors
              </Link>
            </div>
          </>
        )}
      </div>

      <style>{`
        @keyframes spin {
          to { transform: rotate(360deg); }
        }
      `}</style>
    </div>
  );
}
