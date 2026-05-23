"use client";

import Link from "next/link";
import { FONT, DISPLAY, MONO } from "@/lib/theme";
import { type EvalResults } from "@/lib/types";

interface ResultsPageProps {
  results: EvalResults | null;
  activeRunId: string | null;
  isMobile: boolean;
  onStartNewEval: () => void;
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

  return (
    <div style={{ maxWidth: 680 }}>
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
          fontSize: isMobile ? 24 : 32,
          letterSpacing: "-0.03em", lineHeight: 1.0,
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

      <div style={{ display: "flex", gap: 12, flexWrap: "wrap" }}>
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
