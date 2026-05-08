"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { TopBar, useTheme } from "@/components/TopBar";
import { PALETTE, PALETTE_LIGHT, FONT, MONO, TOKENS } from "@/lib/theme";

const API = process.env.NEXT_PUBLIC_API_URL ?? "";
function getToken() { return typeof window !== "undefined" ? (localStorage.getItem("access_token") ?? "") : ""; }

// ── Types ──────────────────────────────────────────────────────────────────────

interface EvalRun {
  run_id: string; rfp_title: string; department: string;
  status: "running" | "pending_approval" | "complete" | "blocked";
  vendor_count: number; shortlisted_count: number; rejected_count: number;
  approval_tier?: number; approver_role?: string;
  sla_deadline?: string; started_at: string;
  contract_value?: string; recommended_vendor?: string;
}

// ── SLA countdown ──────────────────────────────────────────────────────────────

function SlaChip({ deadline }: { deadline: string }) {
  const [txt, setTxt] = useState("");
  useEffect(() => {
    const tick = () => {
      const diff = new Date(deadline).getTime() - Date.now();
      if (diff <= 0) { setTxt("Expired"); return; }
      const h = Math.floor(diff / 3_600_000);
      const m = Math.floor((diff % 3_600_000) / 60_000);
      setTxt(`${h}h ${m}m`);
    };
    tick(); const iv = setInterval(tick, 60_000); return () => clearInterval(iv);
  }, [deadline]);
  const urgent = txt === "Expired" || parseInt(txt) < 4;
  return (
    <span style={{ fontFamily: MONO, fontSize: 11, color: urgent ? "#EF4444" : "#F59E0B", fontWeight: 600 }}>{txt}</span>
  );
}

// ── KPI tile ───────────────────────────────────────────────────────────────────

function KpiTile({ isDark, label, value, sub, colour }: {
  isDark: boolean; label: string; value: string | number;
  sub?: string; colour?: string;
}) {
  const P = isDark ? PALETTE : PALETTE_LIGHT;
  return (
    <div style={{ background: P.bg.surface, borderRadius: TOKENS.radius.card, border: `1px solid ${P.border.mid}`, padding: "18px 20px" }}>
      <div style={{ fontSize: 10, fontWeight: 600, color: P.text.muted, letterSpacing: "0.07em", textTransform: "uppercase", marginBottom: 10, fontFamily: FONT }}>{label}</div>
      <div style={{ fontFamily: MONO, fontSize: 30, fontWeight: 500, color: colour ?? P.text.primary, letterSpacing: "-0.03em", lineHeight: 1, marginBottom: 5 }}>{value}</div>
      {sub && <div style={{ fontSize: 11, color: P.text.muted, fontFamily: FONT }}>{sub}</div>}
    </div>
  );
}

// ── Status pill ────────────────────────────────────────────────────────────────

const STATUS_CFG = {
  running:          { colour: "#3B82F6",  label: "Running"          },
  pending_approval: { colour: "#F59E0B",  label: "Needs approval"   },
  complete:         { colour: "#10B981",  label: "Complete"         },
  blocked:          { colour: "#EF4444",  label: "Blocked"          },
};

function StatusPill({ status }: { status: EvalRun["status"] }) {
  const { colour, label } = STATUS_CFG[status] ?? { colour: "#6B7280", label: status };
  return (
    <span style={{
      fontSize: 11, fontWeight: 600, color: colour,
      background: colour + "18", padding: "3px 8px",
      borderRadius: 12, border: `1px solid ${colour}40`, fontFamily: FONT,
    }}>{label}</span>
  );
}

// ── Page ───────────────────────────────────────────────────────────────────────

export default function ExecutivePage() {
  const { isDark, toggle } = useTheme();
  const P      = isDark ? PALETTE : PALETTE_LIGHT;
  const router = useRouter();

  const [runs,    setRuns]    = useState<EvalRun[]>([]);
  const [loading, setLoading] = useState(true);
  const [error,   setError]   = useState("");

  const BG = isDark
    ? "radial-gradient(ellipse 90% 60% at 50% 0%, #111828 0%, #090C14 65%)"
    : "linear-gradient(160deg, #ede9e0 0%, #fafaf9 55%)";

  useEffect(() => {
    fetch(`${API}/api/v1/evaluate/list`, {
      headers: { Authorization: `Bearer ${getToken()}` },
    })
      .then(r => { if (!r.ok) throw new Error(`${r.status}`); return r.json(); })
      .then(d => { setRuns(Array.isArray(d) ? d : d.runs ?? []); setLoading(false); })
      .catch(e => { setError(e.message); setLoading(false); });
  }, []);

  const pending    = runs.filter(r => r.status === "pending_approval");
  const complete   = runs.filter(r => r.status === "complete");
  const running    = runs.filter(r => r.status === "running");
  const slaAtRisk  = pending.filter(r => r.sla_deadline && new Date(r.sla_deadline).getTime() - Date.now() < 8 * 3_600_000);

  const CARD = { background: P.bg.surface, borderRadius: TOKENS.radius.card, border: `1px solid ${P.border.mid}` };

  return (
    <div style={{ minHeight: "100vh", background: BG, fontFamily: FONT }}>
      <TopBar isDark={isDark} onToggle={toggle}
        crumbs={[{ label: "Executive view" }]}
        right={
          <span style={{ fontSize: 11, color: P.text.muted, fontFamily: FONT }}>
            {new Date().toLocaleDateString("en-GB", { weekday: "long", day: "numeric", month: "long" })}
          </span>
        }
      />

      <main style={{ maxWidth: 1100, margin: "0 auto", padding: "36px 28px 80px" }}>

        <div style={{ marginBottom: 28 }}>
          <h1 style={{ fontSize: 22, fontWeight: 700, color: P.text.primary, margin: "0 0 5px", fontFamily: FONT }}>
            Executive overview
          </h1>
          <p style={{ fontSize: 13, color: P.text.muted, margin: 0 }}>
            Procurement evaluations across all departments — spend, status, and pending approvals.
          </p>
        </div>

        {/* KPI row */}
        <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 16, marginBottom: 28 }}>
          <KpiTile isDark={isDark} label="Total evaluations" value={runs.length} sub="all time" />
          <KpiTile isDark={isDark} label="Pending approval" value={pending.length} sub={`${slaAtRisk.length} SLA at risk`} colour={pending.length > 0 ? "#F59E0B" : undefined} />
          <KpiTile isDark={isDark} label="Running now" value={running.length} sub="in pipeline" colour={running.length > 0 ? "#3B82F6" : undefined} />
          <KpiTile isDark={isDark} label="Completed" value={complete.length} sub="this period" colour="#10B981" />
        </div>

        {loading && (
          <div style={{ ...CARD, padding: "40px", textAlign: "center" }}>
            <span style={{ color: P.text.muted, fontSize: 13 }}>Loading evaluations…</span>
          </div>
        )}

        {error && (
          <div style={{ background: "#EF444414", border: "1px solid #EF4444", borderRadius: TOKENS.radius.card, padding: "14px 18px", fontSize: 13, color: "#EF4444", fontFamily: FONT, marginBottom: 18 }}>
            {error}
          </div>
        )}

        {/* Pending approvals */}
        {!loading && pending.length > 0 && (
          <section style={{ marginBottom: 24 }}>
            <div style={{ fontSize: 12, fontWeight: 600, color: P.text.primary, marginBottom: 12, fontFamily: FONT }}>
              Pending approvals
              {slaAtRisk.length > 0 && (
                <span style={{ marginLeft: 8, fontSize: 11, color: "#EF4444", fontWeight: 400 }}>
                  · {slaAtRisk.length} SLA at risk
                </span>
              )}
            </div>
            <div style={{ ...CARD, overflow: "hidden" }}>
              <div style={{
                display: "grid", gridTemplateColumns: "1fr 120px 100px 100px 100px 120px",
                padding: "10px 20px", borderBottom: `1px solid ${P.border.dim}`,
                fontSize: 10, fontWeight: 600, color: P.text.muted,
                letterSpacing: "0.06em", textTransform: "uppercase", fontFamily: FONT,
              }}>
                {["Evaluation", "Department", "Vendors", "Tier", "SLA", "Action"].map(h => <span key={h}>{h}</span>)}
              </div>
              {pending.map((r, i) => (
                <div key={r.run_id} style={{
                  display: "grid", gridTemplateColumns: "1fr 120px 100px 100px 100px 120px",
                  padding: "13px 20px", alignItems: "center",
                  borderBottom: i < pending.length - 1 ? `1px solid ${P.border.dim}` : "none",
                }}>
                  <div>
                    <div style={{ fontSize: 13, fontWeight: 600, color: P.text.primary, fontFamily: FONT }}>{r.rfp_title || r.run_id.slice(0, 16)}</div>
                    {r.recommended_vendor && (
                      <div style={{ fontSize: 11, color: "#10B981", fontFamily: FONT, marginTop: 2 }}>Rec: {r.recommended_vendor}</div>
                    )}
                  </div>
                  <span style={{ fontSize: 12, color: P.text.secondary, fontFamily: FONT }}>{r.department}</span>
                  <span style={{ fontFamily: MONO, fontSize: 12, color: P.text.secondary }}>{r.vendor_count}</span>
                  <span style={{ fontFamily: MONO, fontSize: 12, color: "#F59E0B" }}>Tier {r.approval_tier ?? "—"}</span>
                  <span>{r.sla_deadline ? <SlaChip deadline={r.sla_deadline} /> : <span style={{ fontSize: 12, color: P.text.muted }}>—</span>}</span>
                  <button onClick={() => router.push(`/${r.run_id}/approve`)} style={{
                    background: "#F59E0B", color: "#1A0D00", border: "none",
                    borderRadius: 7, padding: "6px 14px", fontSize: 11,
                    fontFamily: FONT, fontWeight: 600, cursor: "pointer",
                  }}>
                    Review →
                  </button>
                </div>
              ))}
            </div>
          </section>
        )}

        {/* All evaluations */}
        {!loading && runs.length > 0 && (
          <section>
            <div style={{ fontSize: 12, fontWeight: 600, color: P.text.primary, marginBottom: 12, fontFamily: FONT }}>
              All evaluations
            </div>
            <div style={{ ...CARD, overflow: "hidden" }}>
              <div style={{
                display: "grid", gridTemplateColumns: "1fr 120px 80px 80px 100px 100px",
                padding: "10px 20px", borderBottom: `1px solid ${P.border.dim}`,
                fontSize: 10, fontWeight: 600, color: P.text.muted,
                letterSpacing: "0.06em", textTransform: "uppercase", fontFamily: FONT,
              }}>
                {["Evaluation", "Department", "Vendors", "Shortlisted", "Status", "Started"].map(h => <span key={h}>{h}</span>)}
              </div>
              {runs.map((r, i) => (
                <div key={r.run_id}
                  onClick={() => router.push(r.status === "pending_approval" ? `/${r.run_id}/approve` : `/${r.run_id}/results`)}
                  style={{
                    display: "grid", gridTemplateColumns: "1fr 120px 80px 80px 100px 100px",
                    padding: "12px 20px", alignItems: "center", cursor: "pointer",
                    borderBottom: i < runs.length - 1 ? `1px solid ${P.border.dim}` : "none",
                    transition: "background 120ms",
                  }}
                  onMouseEnter={e => (e.currentTarget.style.background = P.bg.elevated)}
                  onMouseLeave={e => (e.currentTarget.style.background = "transparent")}
                >
                  <div style={{ fontSize: 13, fontWeight: 500, color: P.text.primary, fontFamily: FONT, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                    {r.rfp_title || r.run_id.slice(0, 20)}
                  </div>
                  <span style={{ fontSize: 12, color: P.text.secondary, fontFamily: FONT }}>{r.department}</span>
                  <span style={{ fontFamily: MONO, fontSize: 12, color: P.text.secondary }}>{r.vendor_count}</span>
                  <span style={{ fontFamily: MONO, fontSize: 12, color: "#10B981" }}>{r.shortlisted_count}</span>
                  <StatusPill status={r.status} />
                  <span style={{ fontFamily: MONO, fontSize: 11, color: P.text.muted }}>
                    {new Date(r.started_at).toLocaleDateString("en-GB", { day: "numeric", month: "short" })}
                  </span>
                </div>
              ))}
            </div>
          </section>
        )}

        {!loading && runs.length === 0 && !error && (
          <div style={{ ...CARD, padding: "48px", textAlign: "center" }}>
            <div style={{ fontSize: 32, marginBottom: 12 }}>📋</div>
            <div style={{ fontSize: 15, fontWeight: 600, color: P.text.primary, marginBottom: 6, fontFamily: FONT }}>No evaluations yet</div>
            <div style={{ fontSize: 13, color: P.text.muted, fontFamily: FONT, marginBottom: 20 }}>Start a new RFP evaluation to see data here.</div>
            <button onClick={() => router.push("/procurement/upload")} style={{
              background: "#00D4AA", color: "#071510", border: "none",
              borderRadius: TOKENS.radius.btn, padding: "10px 24px",
              fontSize: 13, fontFamily: FONT, fontWeight: 600, cursor: "pointer",
            }}>
              Start evaluation →
            </button>
          </div>
        )}
      </main>
    </div>
  );
}
