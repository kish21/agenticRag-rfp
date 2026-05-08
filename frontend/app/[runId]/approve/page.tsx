"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { TopBar, useTheme } from "@/components/TopBar";
import { PALETTE, PALETTE_LIGHT, FONT, MONO, TOKENS } from "@/lib/theme";

const API = process.env.NEXT_PUBLIC_API_URL ?? "";
function getToken() { return typeof window !== "undefined" ? (localStorage.getItem("access_token") ?? "") : ""; }

// ── Types ──────────────────────────────────────────────────────────────────────

interface VendorSummary {
  rank: number; vendor_id: string; vendor_name: string;
  total_score: number; recommendation: string;
}
interface ApprovalContext {
  rfp_title: string; department: string; run_id: string;
  shortlisted_vendors: VendorSummary[];
  recommended_vendor: string;
  top_evidence: string[];
  risk_flags: string[];
  approval_tier: number; approver_role: string;
  sla_hours: number; sla_deadline: string;
  contract_value_estimate?: string;
  review_reasons: string[];
}

// ── SLA Countdown ──────────────────────────────────────────────────────────────

function SlaCountdown({ deadline }: { deadline: string }) {
  const [left, setLeft] = useState("");
  useEffect(() => {
    const tick = () => {
      const diff = new Date(deadline).getTime() - Date.now();
      if (diff <= 0) { setLeft("Expired"); return; }
      const h = Math.floor(diff / 3_600_000);
      const m = Math.floor((diff % 3_600_000) / 60_000);
      setLeft(`${h}h ${m}m remaining`);
    };
    tick();
    const iv = setInterval(tick, 60_000);
    return () => clearInterval(iv);
  }, [deadline]);
  const urgent = left.startsWith("Expired") || parseInt(left) < 4;
  return (
    <span style={{ fontFamily: MONO, fontSize: 12, color: urgent ? "#EF4444" : "#F59E0B", fontWeight: 600 }}>
      {left}
    </span>
  );
}

// ── Page ───────────────────────────────────────────────────────────────────────

export default function ApprovePage() {
  const { runId }          = useParams<{ runId: string }>();
  const router             = useRouter();
  const { isDark, toggle } = useTheme();
  const P                  = isDark ? PALETTE : PALETTE_LIGHT;

  const [ctx,        setCtx]        = useState<ApprovalContext | null>(null);
  const [loading,    setLoading]    = useState(true);
  const [error,      setError]      = useState("");
  const [action,     setAction]     = useState<"approve" | "reject" | "escalate" | "">("");
  const [reason,     setReason]     = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [done,       setDone]       = useState<"approve" | "reject" | "escalate" | "">("");

  const BG = isDark
    ? "radial-gradient(ellipse 90% 60% at 50% 0%, #111828 0%, #090C14 65%)"
    : "linear-gradient(160deg, #ede9e0 0%, #fafaf9 55%)";

  useEffect(() => {
    fetch(`${API}/api/v1/evaluate/${runId}/results`, {
      headers: { Authorization: `Bearer ${getToken()}` },
    })
      .then(r => { if (!r.ok) throw new Error(`${r.status}`); return r.json(); })
      .then(d => {
        // /results returns {run_id, status, rfp_title, department, decision: DecisionOutput}
        const dec = d.decision ?? d;
        const ar  = dec.approval_routing ?? {};
        const top = (dec.shortlisted_vendors ?? [])[0];
        const ctx: ApprovalContext = {
          rfp_title:           d.rfp_title ?? dec.rfp_title ?? `Evaluation ${runId.slice(0, 8)}`,
          department:          d.department ?? dec.department ?? "Procurement",
          run_id:              runId,
          shortlisted_vendors: (dec.shortlisted_vendors ?? []).slice(0, 3),
          recommended_vendor:  top?.vendor_name ?? top?.vendor_id ?? "—",
          top_evidence:        (top?.criterion_breakdown ?? []).filter((c: { score_rationale?: string }) => c.score_rationale).map((c: { score_rationale?: string }) => c.score_rationale!).slice(0, 4),
          risk_flags:          dec.review_reasons ?? [],
          approval_tier:       ar.approval_tier ?? 1,
          approver_role:       ar.approver_role ?? "procurement_director",
          sla_hours:           ar.sla_hours ?? 24,
          sla_deadline:        ar.sla_deadline ?? new Date(Date.now() + 24 * 3600 * 1000).toISOString(),
          contract_value_estimate: d.contract_value_estimate,
          review_reasons:      dec.review_reasons ?? [],
        };
        setCtx(ctx);
        setLoading(false);
      })
      .catch(e => { setError(`Failed to load: ${e.message}`); setLoading(false); });
  }, [runId]);

  async function submit() {
    if (!action || (action !== "approve" && reason.trim().length < 20)) return;
    setSubmitting(true);
    try {
      const res = await fetch(`${API}/api/v1/evaluate/${runId}/override`, {
        method: "POST",
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${getToken()}` },
        body: JSON.stringify({ action, reason: reason.trim(), approver_role: ctx?.approver_role }),
      });
      if (!res.ok) throw new Error(`Submit failed (${res.status})`);
      setDone(action);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Submission failed");
      setSubmitting(false);
    }
  }

  const CARD = { background: P.bg.surface, borderRadius: TOKENS.radius.card, border: `1px solid ${P.border.mid}`, padding: "20px 22px" };

  if (loading) return (
    <div style={{ minHeight: "100vh", background: BG, fontFamily: FONT }}>
      <TopBar isDark={isDark} onToggle={toggle} crumbs={[{ label: "Approval required" }]} />
      <div style={{ display: "flex", alignItems: "center", justifyContent: "center", height: "50vh" }}>
        <span style={{ color: P.text.muted, fontSize: 13 }}>Loading approval context…</span>
      </div>
    </div>
  );

  if (!ctx) return (
    <div style={{ minHeight: "100vh", background: BG, fontFamily: FONT }}>
      <TopBar isDark={isDark} onToggle={toggle} crumbs={[{ label: "Approval required" }]} />
      <div style={{ display: "flex", alignItems: "center", justifyContent: "center", height: "50vh" }}>
        <span style={{ color: "#EF4444", fontSize: 13 }}>{error}</span>
      </div>
    </div>
  );

  if (done) return (
    <div style={{ minHeight: "100vh", background: BG, fontFamily: FONT }}>
      <TopBar isDark={isDark} onToggle={toggle} crumbs={[{ label: "Approval complete" }]} />
      <div style={{ display: "flex", alignItems: "center", justifyContent: "center", minHeight: "60vh" }}>
        <div style={{ ...CARD, textAlign: "center", maxWidth: 400, padding: "40px 32px" }}>
          <div style={{ fontSize: 40, marginBottom: 14 }}>
            {done === "approve" ? "✓" : done === "reject" ? "✗" : "⬆"}
          </div>
          <h2 style={{ fontSize: 18, fontWeight: 700, color: done === "approve" ? "#10B981" : done === "reject" ? "#EF4444" : "#F59E0B", margin: "0 0 8px", fontFamily: FONT }}>
            {done === "approve" ? "Approved" : done === "reject" ? "Rejected" : "Escalated"}
          </h2>
          <p style={{ fontSize: 13, color: P.text.muted, margin: "0 0 20px", fontFamily: FONT }}>
            Decision recorded with full audit trail.
          </p>
          <button onClick={() => router.push(`/${runId}/results`)} style={{
            background: "#00D4AA", color: "#071510", border: "none",
            borderRadius: TOKENS.radius.btn, padding: "10px 24px",
            fontSize: 13, fontFamily: FONT, fontWeight: 600, cursor: "pointer", width: "100%",
          }}>
            View full results
          </button>
        </div>
      </div>
    </div>
  );

  const needsReason = action === "reject" || action === "escalate";
  const canSubmit   = action === "approve" || (needsReason && reason.trim().length >= 20);

  return (
    <div style={{ minHeight: "100vh", background: BG, fontFamily: FONT }}>
      <TopBar isDark={isDark} onToggle={toggle}
        crumbs={[{ label: "Approval required" }, { label: ctx.rfp_title }]}
        right={<SlaCountdown deadline={ctx.sla_deadline} />}
      />

      <main style={{ maxWidth: 820, margin: "0 auto", padding: "36px 28px 80px", display: "flex", flexDirection: "column", gap: 18 }}>

        {/* Header */}
        <div style={{ ...CARD, borderLeft: "3px solid #F59E0B" }}>
          <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", flexWrap: "wrap", gap: 12 }}>
            <div>
              <div style={{ fontSize: 11, fontWeight: 600, color: "#F59E0B", letterSpacing: "0.06em", textTransform: "uppercase", marginBottom: 6, fontFamily: FONT }}>
                Approval required — Tier {ctx.approval_tier}
              </div>
              <h1 style={{ fontSize: 20, fontWeight: 700, color: P.text.primary, margin: "0 0 6px", fontFamily: FONT }}>
                {ctx.rfp_title}
              </h1>
              <div style={{ display: "flex", gap: 18, flexWrap: "wrap" }}>
                {[
                  ["Department", ctx.department],
                  ["Approver role", ctx.approver_role.replace(/_/g, " ")],
                  ["SLA", `${ctx.sla_hours}h`],
                  ...(ctx.contract_value_estimate ? [["Est. value", ctx.contract_value_estimate] as [string, string]] : []),
                ].map(([k, v]) => (
                  <div key={k}>
                    <div style={{ fontSize: 10, fontWeight: 600, color: P.text.muted, textTransform: "uppercase", letterSpacing: "0.06em", fontFamily: FONT }}>{k}</div>
                    <div style={{ fontSize: 13, color: P.text.primary, fontFamily: FONT, marginTop: 2 }}>{v}</div>
                  </div>
                ))}
              </div>
            </div>
            <div style={{ textAlign: "right" }}>
              <div style={{ fontSize: 10, fontWeight: 600, color: P.text.muted, textTransform: "uppercase", letterSpacing: "0.06em", fontFamily: FONT, marginBottom: 4 }}>SLA deadline</div>
              <div style={{ fontSize: 12, color: P.text.secondary, fontFamily: FONT, marginBottom: 4 }}>
                {new Date(ctx.sla_deadline).toLocaleString()}
              </div>
              <SlaCountdown deadline={ctx.sla_deadline} />
            </div>
          </div>
        </div>

        {/* AI recommendation */}
        <div style={CARD}>
          <div style={{ fontSize: 10, fontWeight: 600, color: P.text.muted, letterSpacing: "0.07em", textTransform: "uppercase", marginBottom: 12, fontFamily: FONT }}>
            AI recommendation
          </div>
          <div style={{ fontSize: 16, fontWeight: 600, color: "#10B981", marginBottom: 4, fontFamily: FONT }}>
            {ctx.recommended_vendor}
          </div>
          <div style={{ fontSize: 12, color: P.text.muted, marginBottom: 14, fontFamily: FONT }}>Highest-ranked vendor across all criteria</div>
          {ctx.top_evidence.length > 0 && (
            <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
              {ctx.top_evidence.map((e, i) => (
                <div key={i} style={{
                  background: P.bg.elevated, borderRadius: 7, border: `1px solid ${P.border.dim}`,
                  padding: "8px 12px", fontSize: 12, color: P.text.secondary, fontFamily: FONT, fontStyle: "italic",
                }}>
                  &ldquo;{e}&rdquo;
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Vendor comparison */}
        {ctx.shortlisted_vendors.length > 0 && (
          <div style={CARD}>
            <div style={{ fontSize: 10, fontWeight: 600, color: P.text.muted, letterSpacing: "0.07em", textTransform: "uppercase", marginBottom: 12, fontFamily: FONT }}>
              Shortlisted vendors
            </div>
            <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
              {ctx.shortlisted_vendors.map(v => (
                <div key={v.vendor_id} style={{
                  display: "flex", alignItems: "center", gap: 14,
                  background: P.bg.elevated, borderRadius: 8, border: `1px solid ${P.border.dim}`, padding: "10px 14px",
                }}>
                  <div style={{
                    width: 28, height: 28, borderRadius: "50%", flexShrink: 0,
                    background: v.rank === 1 ? "#00D4AA" : P.border.mid,
                    display: "flex", alignItems: "center", justifyContent: "center",
                    fontFamily: MONO, fontSize: 12, fontWeight: 700,
                    color: v.rank === 1 ? "#071510" : P.text.muted,
                  }}>#{v.rank}</div>
                  <div style={{ flex: 1 }}>
                    <div style={{ fontSize: 13, fontWeight: 600, color: P.text.primary, fontFamily: FONT }}>{v.vendor_name || v.vendor_id}</div>
                    <div style={{ fontSize: 11, color: P.text.muted, fontFamily: FONT }}>{v.recommendation.replace(/_/g, " ")}</div>
                  </div>
                  <div style={{ fontFamily: MONO, fontSize: 18, fontWeight: 700, color: v.rank === 1 ? "#00D4AA" : P.text.secondary }}>
                    {v.total_score.toFixed(1)}<span style={{ fontSize: 11, color: P.text.muted }}>/10</span>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Risk flags */}
        {ctx.risk_flags.length > 0 && (
          <div style={{ background: "#EF444410", border: "1px solid #EF444440", borderRadius: TOKENS.radius.card, padding: "16px 18px" }}>
            <div style={{ fontSize: 10, fontWeight: 600, color: "#EF4444", letterSpacing: "0.07em", textTransform: "uppercase", marginBottom: 10, fontFamily: FONT }}>
              Review flags
            </div>
            {ctx.risk_flags.map((f, i) => (
              <div key={i} style={{ fontSize: 12, color: P.text.secondary, fontFamily: FONT, marginBottom: 5 }}>⚠ {f}</div>
            ))}
          </div>
        )}

        {/* Approval action */}
        <div style={CARD}>
          <div style={{ fontSize: 10, fontWeight: 600, color: P.text.muted, letterSpacing: "0.07em", textTransform: "uppercase", marginBottom: 14, fontFamily: FONT }}>
            Your decision
          </div>

          <div style={{ display: "flex", gap: 10, marginBottom: 16 }}>
            {(["approve", "reject", "escalate"] as const).map(a => {
              const colours = {
                approve:  { bg: "#10B98118", border: "#10B98140", text: "#10B981" },
                reject:   { bg: "#EF444418", border: "#EF444440", text: "#EF4444" },
                escalate: { bg: "#F59E0B18", border: "#F59E0B40", text: "#F59E0B" },
              };
              const c = colours[a];
              const selected = action === a;
              return (
                <button key={a} onClick={() => setAction(a)} style={{
                  flex: 1, padding: "10px 12px", borderRadius: 8,
                  border: `1px solid ${selected ? c.border : P.border.dim}`,
                  background: selected ? c.bg : "transparent",
                  color: selected ? c.text : P.text.muted,
                  fontSize: 13, fontFamily: FONT, fontWeight: selected ? 600 : 400,
                  cursor: "pointer", transition: "all 140ms", textTransform: "capitalize",
                }}>
                  {a === "approve" ? "✓ Approve" : a === "reject" ? "✗ Reject" : "⬆ Escalate"}
                </button>
              );
            })}
          </div>

          {needsReason && (
            <div style={{ marginBottom: 14 }}>
              <textarea
                rows={4} value={reason} onChange={e => setReason(e.target.value)}
                placeholder={`Reason for ${action} (minimum 20 characters — stored for audit)`}
                suppressHydrationWarning
                style={{
                  width: "100%", fontFamily: FONT, fontSize: 13,
                  padding: "10px 12px", borderRadius: 8,
                  border: `1px solid ${reason.trim().length >= 20 ? "#10B981" : P.border.mid}`,
                  background: P.bg.elevated, color: P.text.primary,
                  outline: "none", resize: "vertical", boxSizing: "border-box",
                }}
              />
              <div style={{ fontSize: 11, color: P.text.muted, marginTop: 4, fontFamily: FONT }}>
                {reason.trim().length} / 20 minimum
              </div>
            </div>
          )}

          {error && (
            <div style={{ background: "#EF444414", border: "1px solid #EF4444", borderRadius: 8, padding: "10px 14px", fontSize: 13, color: "#EF4444", fontFamily: FONT, marginBottom: 12 }}>
              {error}
            </div>
          )}

          <button onClick={submit} disabled={!canSubmit || submitting} style={{
            width: "100%", background: !canSubmit || submitting ? P.border.mid : "#00D4AA",
            color: !canSubmit || submitting ? P.text.muted : "#071510",
            border: "none", borderRadius: TOKENS.radius.btn,
            padding: "11px", fontSize: 13, fontFamily: FONT, fontWeight: 600,
            cursor: !canSubmit || submitting ? "not-allowed" : "pointer",
            transition: "background 160ms",
          }}>
            {submitting ? "Submitting…" : action ? `Confirm ${action}` : "Select a decision above"}
          </button>
        </div>
      </main>
    </div>
  );
}
