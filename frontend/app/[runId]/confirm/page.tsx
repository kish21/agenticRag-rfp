"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { TopBar, useTheme } from "@/components/TopBar";
import { PALETTE, PALETTE_LIGHT, FONT, MONO, TOKENS } from "@/lib/theme";

const API = process.env.NEXT_PUBLIC_API_URL ?? "";
function getToken() { return typeof window !== "undefined" ? (localStorage.getItem("access_token") ?? "") : ""; }

// ── Types (unchanged from original) ───────────────────────────────────────────

interface MandatoryCheck {
  check_id: string; name: string; description: string; what_passes: string;
}
interface ScoringCriterion {
  criterion_id: string; name: string; weight: number;
}
interface EvaluationSetup {
  setup_id: string; department: string; rfp_id: string;
  mandatory_checks: MandatoryCheck[];
  scoring_criteria:  ScoringCriterion[];
  total_weight:      number;
  confirmed_by:      string;
}

// ── Section label ──────────────────────────────────────────────────────────────

function SectionLabel({ children, isDark }: { children: React.ReactNode; isDark: boolean }) {
  const P = isDark ? PALETTE : PALETTE_LIGHT;
  return (
    <div style={{ fontSize: 10, fontWeight: 700, color: P.text.muted, letterSpacing: "0.07em", textTransform: "uppercase", marginBottom: 12, fontFamily: FONT }}>
      {children}
    </div>
  );
}

// ── Page ───────────────────────────────────────────────────────────────────────

export default function ConfirmPage() {
  const { runId }      = useParams<{ runId: string }>();
  const router         = useRouter();
  const { isDark, toggle } = useTheme();
  const P              = isDark ? PALETTE : PALETTE_LIGHT;

  const [setup,      setSetup]      = useState<EvaluationSetup | null>(null);
  const [loading,    setLoading]    = useState(true);
  const [confirming, setConfirming] = useState(false);
  const [error,      setError]      = useState("");

  const BG = isDark
    ? "radial-gradient(ellipse 90% 60% at 50% 0%, #111828 0%, #090C14 65%)"
    : "linear-gradient(160deg, #ede9e0 0%, #fafaf9 55%)";

  useEffect(() => {
    fetch(`${API}/api/v1/evaluate/${runId}/setup`, {
      headers: { Authorization: `Bearer ${getToken()}` },
    })
      .then(r => { if (!r.ok) throw new Error(`${r.status}`); return r.json(); })
      .then(d => { setSetup(d); setLoading(false); })
      .catch(e => { setError(`Failed to load setup: ${e.message}`); setLoading(false); });
  }, [runId]);

  async function handleConfirm() {
    setConfirming(true);
    setError("");
    try {
      const res = await fetch(`${API}/api/v1/evaluate/${runId}/confirm`, {
        method: "POST",
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${getToken()}` },
      });
      if (!res.ok) throw new Error(`Confirm failed (${res.status})`);
      router.push(`/${runId}/progress`);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Confirmation failed");
      setConfirming(false);
    }
  }

  const CARD = {
    background: P.bg.surface, borderRadius: TOKENS.radius.card,
    border: `1px solid ${P.border.mid}`,
    padding: "20px 22px",
  };

  if (loading) return (
    <div style={{ minHeight: "100vh", background: BG, fontFamily: FONT }}>
      <TopBar isDark={isDark} onToggle={toggle}
        crumbs={[{ label: "Procurement", href: "/" }, { label: "Confirm setup" }]} />
      <div style={{ display: "flex", alignItems: "center", justifyContent: "center", height: "50vh" }}>
        <span style={{ color: P.text.muted, fontSize: 13 }}>Loading evaluation setup…</span>
      </div>
    </div>
  );

  if (!setup) return (
    <div style={{ minHeight: "100vh", background: BG, fontFamily: FONT }}>
      <TopBar isDark={isDark} onToggle={toggle}
        crumbs={[{ label: "Procurement", href: "/" }, { label: "Confirm setup" }]} />
      <div style={{ display: "flex", alignItems: "center", justifyContent: "center", height: "50vh" }}>
        <span style={{ color: "#EF4444", fontSize: 13 }}>{error || "Setup not found."}</span>
      </div>
    </div>
  );

  const totalPct  = Math.round(setup.total_weight * 100);
  const weightOk  = totalPct === 100;

  return (
    <div style={{ minHeight: "100vh", background: BG, fontFamily: FONT }}>
      <TopBar isDark={isDark} onToggle={toggle}
        crumbs={[
          { label: "Procurement", href: "/" },
          { label: "New evaluation", href: "/procurement/upload" },
          { label: "Confirm setup" },
        ]} />

      <main style={{ maxWidth: 760, margin: "0 auto", padding: "36px 28px 80px", display: "flex", flexDirection: "column", gap: 18 }}>

        {/* Header card */}
        <div style={CARD}>
          <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", marginBottom: 12 }}>
            <div>
              <h1 style={{ fontSize: 18, fontWeight: 700, color: P.text.primary, margin: "0 0 4px", fontFamily: FONT }}>
                Confirm evaluation setup
              </h1>
              <p style={{ fontSize: 12, color: P.text.muted, margin: 0 }}>
                Review carefully — this cannot be changed once confirmed.
              </p>
            </div>
            <span style={{
              background: "#00D4AA18", border: "1px solid #00D4AA40",
              borderRadius: 20, padding: "4px 12px",
              fontSize: 11, color: "#00D4AA", fontWeight: 600, fontFamily: FONT, flexShrink: 0,
            }}>
              Identity confirmed
            </span>
          </div>
          <div style={{ display: "flex", gap: 24, flexWrap: "wrap" }}>
            {[
              ["RFP", setup.rfp_id],
              ["Department", setup.department],
              ["Setup ID", setup.setup_id],
            ].map(([k, v]) => (
              <div key={k}>
                <div style={{ fontSize: 10, fontWeight: 600, color: P.text.muted, letterSpacing: "0.06em", textTransform: "uppercase", fontFamily: FONT }}>{k}</div>
                <div style={{ fontSize: 13, color: P.text.primary, fontFamily: MONO, marginTop: 2 }}>{v}</div>
              </div>
            ))}
          </div>
        </div>

        {/* Mandatory checks */}
        <div style={CARD}>
          <SectionLabel isDark={isDark}>Mandatory checks — {setup.mandatory_checks.length} criteria</SectionLabel>
          <p style={{ fontSize: 12, color: P.text.muted, marginBottom: 14, fontFamily: FONT }}>
            Vendors failing any of these checks are rejected before scoring begins.
          </p>
          <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
            {setup.mandatory_checks.map(c => (
              <div key={c.check_id} style={{
                background: P.bg.elevated, borderRadius: 8,
                border: `1px solid ${P.border.dim}`, padding: "12px 14px",
              }}>
                <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 5 }}>
                  <span style={{
                    fontFamily: MONO, fontSize: 10, color: P.text.muted,
                    background: P.bg.elevated, padding: "2px 7px", borderRadius: 4,
                  }}>{c.check_id}</span>
                  <span style={{ fontSize: 13, fontWeight: 600, color: P.text.primary, fontFamily: FONT }}>{c.name}</span>
                </div>
                <p style={{ fontSize: 12, color: P.text.muted, margin: "0 0 5px", fontFamily: FONT }}>{c.description}</p>
                <p style={{ fontSize: 12, color: "#10B981", margin: 0, fontFamily: FONT }}>✓ Passes when: {c.what_passes}</p>
              </div>
            ))}
          </div>
        </div>

        {/* Scoring rubric */}
        <div style={CARD}>
          <SectionLabel isDark={isDark}>Scoring rubric — total weight: {totalPct}%</SectionLabel>
          {!weightOk && (
            <div style={{
              background: "#F59E0B14", border: "1px solid #F59E0B",
              borderRadius: 8, padding: "8px 12px", marginBottom: 12,
              fontSize: 12, color: "#F59E0B", fontFamily: FONT,
            }}>
              ⚠ Weights sum to {totalPct}% — should be 100%. Check config before confirming.
            </div>
          )}
          <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
            {setup.scoring_criteria.map(c => {
              const pct = Math.round(c.weight * 100);
              return (
                <div key={c.criterion_id} style={{
                  display: "flex", alignItems: "center", gap: 12,
                  background: P.bg.elevated, borderRadius: 8,
                  border: `1px solid ${P.border.dim}`, padding: "10px 14px",
                }}>
                  <div style={{ flex: 1 }}>
                    <div style={{ fontSize: 13, color: P.text.primary, fontFamily: FONT }}>{c.name}</div>
                    <div style={{ height: 4, borderRadius: 2, background: P.border.dim, marginTop: 6, overflow: "hidden" }}>
                      <div style={{ height: "100%", width: `${pct}%`, background: "#00D4AA", borderRadius: 2 }} />
                    </div>
                  </div>
                  <span style={{ fontFamily: MONO, fontSize: 14, fontWeight: 600, color: "#00D4AA", flexShrink: 0 }}>{pct}%</span>
                </div>
              );
            })}
          </div>
        </div>

        {/* Error */}
        {error && (
          <div style={{ background: "#EF444414", border: "1px solid #EF4444", borderRadius: 8, padding: "10px 14px", fontSize: 13, color: "#EF4444", fontFamily: FONT }}>
            {error}
          </div>
        )}

        {/* Actions */}
        <div style={{ display: "flex", gap: 12 }}>
          <button onClick={() => router.back()} style={{
            background: "transparent", border: `1px solid ${P.border.mid}`,
            borderRadius: TOKENS.radius.btn, padding: "10px 20px",
            fontSize: 13, fontFamily: FONT, color: P.text.secondary, cursor: "pointer",
          }}>
            ← Back
          </button>
          <button onClick={handleConfirm} disabled={confirming} style={{
            flex: 1, background: confirming ? P.border.mid : "#00D4AA",
            color: confirming ? P.text.muted : "#071510",
            border: "none", borderRadius: TOKENS.radius.btn,
            padding: "10px 20px", fontSize: 13, fontFamily: FONT, fontWeight: 600,
            cursor: confirming ? "not-allowed" : "pointer", transition: "background 160ms",
          }}>
            {confirming ? "Starting pipeline…" : "Confirm and start evaluation →"}
          </button>
        </div>
      </main>
    </div>
  );
}
