"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter, useSearchParams } from "next/navigation";
import { TopBar, useTheme } from "@/components/TopBar";
import { PALETTE, PALETTE_LIGHT, FONT, MONO, TOKENS } from "@/lib/theme";

const API            = process.env.NEXT_PUBLIC_API_URL ?? "";
const MIN_REASON_LEN = 20;

function getToken() { return typeof window !== "undefined" ? (localStorage.getItem("access_token") ?? "") : ""; }

interface CurrentDecision {
  vendor_id: string; vendor_name: string;
  decision_type: "shortlisted" | "rejected";
  rank?: number; total_score?: number;
  rejection_reasons?: string[]; evidence_citations?: string[];
}

export default function OverridePage() {
  const { runId }          = useParams<{ runId: string }>();
  const searchParams       = useSearchParams();
  const router             = useRouter();
  const { isDark, toggle } = useTheme();
  const P                  = isDark ? PALETTE : PALETTE_LIGHT;

  const vendorId = searchParams.get("vendor") ?? "";

  const [decision,   setDecision]   = useState<CurrentDecision | null>(null);
  const [reason,     setReason]     = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error,      setError]      = useState("");
  const [success,    setSuccess]    = useState(false);

  const BG = isDark
    ? "radial-gradient(ellipse 90% 60% at 50% 0%, #111828 0%, #090C14 65%)"
    : "linear-gradient(160deg, #ede9e0 0%, #fafaf9 55%)";

  useEffect(() => {
    if (!vendorId) return;
    fetch(`${API}/api/v1/evaluate/${runId}/decision?vendor=${vendorId}`, {
      headers: { Authorization: `Bearer ${getToken()}` },
    })
      .then(r => r.json())
      .then(setDecision)
      .catch(() => setError("Failed to load current decision."));
  }, [runId, vendorId]);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (reason.trim().length < MIN_REASON_LEN) {
      setError(`Reason must be at least ${MIN_REASON_LEN} characters.`);
      return;
    }
    setSubmitting(true);
    setError("");
    try {
      const res = await fetch(`${API}/api/v1/evaluate/${runId}/override`, {
        method: "POST",
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${getToken()}` },
        body: JSON.stringify({ vendor_id: vendorId, reason: reason.trim() }),
      });
      if (!res.ok) {
        const d = await res.json().catch(() => ({}));
        throw new Error(d.detail ?? `Override failed (${res.status})`);
      }
      setSuccess(true);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Override failed");
      setSubmitting(false);
    }
  }

  const reasonLen = reason.trim().length;
  const reasonOk  = reasonLen >= MIN_REASON_LEN;
  const CARD      = { background: P.bg.surface, borderRadius: TOKENS.radius.card, border: `1px solid ${P.border.mid}`, padding: "20px 22px" };

  if (success) return (
    <div style={{ minHeight: "100vh", background: BG, fontFamily: FONT }}>
      <TopBar isDark={isDark} onToggle={toggle}
        crumbs={[{ label: "Procurement", href: "/" }, { label: "Override" }]} />
      <div style={{ display: "flex", alignItems: "center", justifyContent: "center", minHeight: "60vh" }}>
        <div style={{ ...CARD, textAlign: "center", maxWidth: 400, padding: "40px 32px" }}>
          <div style={{ fontSize: 40, marginBottom: 14 }}>✓</div>
          <h2 style={{ fontSize: 18, fontWeight: 700, color: "#10B981", margin: "0 0 8px", fontFamily: FONT }}>Override recorded</h2>
          <p style={{ fontSize: 13, color: P.text.muted, margin: "0 0 20px", fontFamily: FONT }}>
            Saved with full audit trail — identity, timestamp, and reason logged.
          </p>
          <button onClick={() => router.push(`/${runId}/results`)} style={{
            background: "#00D4AA", color: "#071510", border: "none",
            borderRadius: TOKENS.radius.btn, padding: "10px 24px",
            fontSize: 13, fontFamily: FONT, fontWeight: 600, cursor: "pointer", width: "100%",
          }}>
            Back to results
          </button>
        </div>
      </div>
    </div>
  );

  return (
    <div style={{ minHeight: "100vh", background: BG, fontFamily: FONT }}>
      <TopBar isDark={isDark} onToggle={toggle}
        crumbs={[
          { label: "Procurement", href: "/" },
          { label: "Results", href: `/${runId}/results` },
          { label: "Override" },
        ]} />

      <main style={{ maxWidth: 640, margin: "0 auto", padding: "36px 28px 80px", display: "flex", flexDirection: "column", gap: 18 }}>

        {/* Header */}
        <div style={CARD}>
          <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", marginBottom: 6 }}>
            <div>
              <h1 style={{ fontSize: 18, fontWeight: 700, color: P.text.primary, margin: "0 0 4px", fontFamily: FONT }}>
                Human override
              </h1>
              <p style={{ fontSize: 12, color: P.text.muted, margin: 0, fontFamily: FONT }}>
                Every override is logged with your identity, timestamp, and reason for audit compliance.
              </p>
            </div>
            <span style={{
              background: "#F59E0B18", border: "1px solid #F59E0B40",
              borderRadius: 20, padding: "4px 12px", fontSize: 11,
              color: "#F59E0B", fontWeight: 600, fontFamily: FONT, flexShrink: 0,
            }}>
              Audit required
            </span>
          </div>
        </div>

        {/* Current decision */}
        {decision && (
          <div style={CARD}>
            <div style={{ fontSize: 10, fontWeight: 600, color: P.text.muted, letterSpacing: "0.07em", textTransform: "uppercase", marginBottom: 12, fontFamily: FONT }}>
              Current AI decision
            </div>
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 12 }}>
              <span style={{ fontSize: 15, fontWeight: 600, color: P.text.primary, fontFamily: FONT }}>
                {decision.vendor_name || decision.vendor_id}
              </span>
              <span style={{
                fontSize: 12, fontWeight: 600, padding: "4px 10px", borderRadius: 12,
                background: decision.decision_type === "shortlisted" ? "#10B98118" : "#EF444418",
                color:      decision.decision_type === "shortlisted" ? "#10B981"   : "#EF4444",
                border:     `1px solid ${decision.decision_type === "shortlisted" ? "#10B98140" : "#EF444440"}`,
                fontFamily: FONT,
              }}>
                {decision.decision_type === "shortlisted"
                  ? `Shortlisted — Rank #${decision.rank}`
                  : "Rejected"}
              </span>
            </div>
            {decision.total_score !== undefined && (
              <div style={{ fontFamily: MONO, fontSize: 13, color: P.text.muted, marginBottom: 10 }}>
                Score: {decision.total_score.toFixed(1)} / 10
              </div>
            )}
            {decision.evidence_citations && decision.evidence_citations.length > 0 && (
              <div>
                <div style={{ fontSize: 11, fontWeight: 600, color: P.text.muted, marginBottom: 8, fontFamily: FONT }}>Evidence cited by the AI:</div>
                {decision.evidence_citations.map((c, i) => (
                  <div key={i} style={{
                    background: P.bg.elevated, borderRadius: 6, border: `1px solid ${P.border.dim}`,
                    padding: "8px 10px", marginBottom: 6, fontSize: 12, color: P.text.secondary,
                    fontFamily: FONT, fontStyle: "italic",
                  }}>
                    &ldquo;{c}&rdquo;
                  </div>
                ))}
              </div>
            )}
            {decision.rejection_reasons && decision.rejection_reasons.length > 0 && (
              <div style={{ marginTop: 8 }}>
                <div style={{ fontSize: 11, fontWeight: 600, color: "#EF4444", marginBottom: 6, fontFamily: FONT }}>Rejection reasons:</div>
                {decision.rejection_reasons.map((r, i) => (
                  <div key={i} style={{ fontSize: 12, color: P.text.secondary, fontFamily: FONT, marginBottom: 4 }}>• {r}</div>
                ))}
              </div>
            )}
          </div>
        )}

        {/* Override form */}
        <form onSubmit={handleSubmit} style={{ display: "flex", flexDirection: "column", gap: 14 }}>
          <div style={CARD}>
            <div style={{ fontSize: 10, fontWeight: 600, color: P.text.muted, letterSpacing: "0.07em", textTransform: "uppercase", marginBottom: 12, fontFamily: FONT }}>
              Override reason
            </div>
            <textarea
              rows={5}
              value={reason}
              onChange={e => setReason(e.target.value)}
              placeholder="Explain why this decision is being overridden. Be specific — this will be reviewed by procurement leadership and stored permanently."
              suppressHydrationWarning
              style={{
                width: "100%", fontFamily: FONT, fontSize: 13,
                padding: "10px 12px", borderRadius: 8,
                border: `1px solid ${reasonOk ? "#10B981" : P.border.mid}`,
                background: P.bg.elevated, color: P.text.primary,
                outline: "none", resize: "vertical", boxSizing: "border-box",
                transition: "border-color 160ms",
              }}
            />
            <div style={{ display: "flex", justifyContent: "space-between", marginTop: 6 }}>
              <span style={{ fontSize: 11, color: reasonOk ? "#10B981" : P.text.muted, fontFamily: FONT }}>
                {reasonLen} / {MIN_REASON_LEN} minimum characters
              </span>
              {reasonOk && <span style={{ fontSize: 11, color: "#10B981", fontFamily: FONT }}>✓ Length meets requirement</span>}
            </div>
          </div>

          {error && (
            <div style={{ background: "#EF444414", border: "1px solid #EF4444", borderRadius: 8, padding: "10px 14px", fontSize: 13, color: "#EF4444", fontFamily: FONT }}>
              {error}
            </div>
          )}

          <div style={{ display: "flex", gap: 12 }}>
            <button type="button" onClick={() => router.back()} style={{
              background: "transparent", border: `1px solid ${P.border.mid}`,
              borderRadius: TOKENS.radius.btn, padding: "10px 20px",
              fontSize: 13, fontFamily: FONT, color: P.text.secondary, cursor: "pointer",
            }}>
              Cancel
            </button>
            <button type="submit" disabled={submitting || !reasonOk} style={{
              flex: 1, background: submitting || !reasonOk ? P.border.mid : "#F59E0B",
              color: submitting || !reasonOk ? P.text.muted : "#1A0A00",
              border: "none", borderRadius: TOKENS.radius.btn,
              padding: "10px 20px", fontSize: 13, fontFamily: FONT, fontWeight: 600,
              cursor: submitting || !reasonOk ? "not-allowed" : "pointer",
              transition: "background 160ms",
            }}>
              {submitting ? "Submitting…" : "Submit override"}
            </button>
          </div>
        </form>
      </main>
    </div>
  );
}
