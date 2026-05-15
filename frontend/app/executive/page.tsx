"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { TopBar } from "@/components/TopBar";
import { FONT, MONO, TOKENS } from "@/lib/theme";

const API = process.env.NEXT_PUBLIC_API_URL ?? "";
function getToken() { return typeof window !== "undefined" ? (localStorage.getItem("access_token") ?? "") : ""; }

interface EvalRun {
  run_id: string; rfp_title: string; department: string;
  status: "running" | "pending_approval" | "complete" | "blocked";
  vendor_count: number; shortlisted_count: number; rejected_count: number;
  approval_tier?: number; approver_role?: string;
  sla_deadline?: string; started_at: string;
  contract_value?: string; recommended_vendor?: string;
}

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
    <span style={{ fontFamily: MONO, fontSize: 11, color: urgent ? "var(--color-error)" : "var(--color-warning)", fontWeight: 600 }}>
      {txt}
    </span>
  );
}

function KpiTile({ label, value, sub, colour }: { label: string; value: string | number; sub?: string; colour?: string }) {
  return (
    <div style={{
      background: "var(--color-surface)", borderRadius: TOKENS.radius.card,
      border: "1px solid var(--color-border)", padding: "20px 22px",
      boxShadow: "var(--shadow-sm)",
    }}>
      <div style={{ fontSize: 10, fontWeight: 600, color: "var(--color-text-muted)", letterSpacing: "0.08em", textTransform: "uppercase", marginBottom: 12, fontFamily: FONT }}>
        {label}
      </div>
      <div style={{ fontFamily: MONO, fontSize: 32, fontWeight: 700, color: colour ?? "var(--color-text-primary)", letterSpacing: "-0.03em", lineHeight: 1, marginBottom: 6 }}>
        {value}
      </div>
      {sub && <div style={{ fontSize: 11, color: "var(--color-text-muted)", fontFamily: FONT }}>{sub}</div>}
    </div>
  );
}

const STATUS_CFG = {
  running:          { colour: "var(--color-info)",    label: "Running"        },
  pending_approval: { colour: "var(--color-warning)", label: "Needs approval" },
  complete:         { colour: "var(--color-success)", label: "Complete"       },
  blocked:          { colour: "var(--color-error)",   label: "Blocked"        },
};

function StatusPill({ status }: { status: EvalRun["status"] }) {
  const cfg = STATUS_CFG[status] ?? { colour: "var(--color-text-muted)", label: status };
  return (
    <span style={{
      fontSize: 11, fontWeight: 600, color: cfg.colour,
      background: cfg.colour + "18", padding: "3px 9px",
      borderRadius: 12, border: `1px solid ${cfg.colour}40`, fontFamily: FONT,
      display: "inline-block",
    }}>
      {cfg.label}
    </span>
  );
}

const COL_HEADER: React.CSSProperties = {
  fontSize: 10, fontWeight: 600, color: "var(--color-text-muted)",
  letterSpacing: "0.07em", textTransform: "uppercase", fontFamily: FONT,
};

export default function ExecutivePage() {
  const router = useRouter();
  const [runs,    setRuns]    = useState<EvalRun[]>([]);
  const [loading, setLoading] = useState(true);
  const [error,   setError]   = useState("");

  useEffect(() => {
    fetch(`${API}/api/v1/evaluate/list`, { headers: { Authorization: `Bearer ${getToken()}` } })
      .then(r => { if (!r.ok) throw new Error(`${r.status}`); return r.json(); })
      .then(d => { setRuns(Array.isArray(d) ? d : d.runs ?? []); setLoading(false); })
      .catch(e => { setError(e.message); setLoading(false); });
  }, []);

  const pending   = runs.filter(r => r.status === "pending_approval");
  const complete  = runs.filter(r => r.status === "complete");
  const running   = runs.filter(r => r.status === "running");
  const slaAtRisk = pending.filter(r => r.sla_deadline && new Date(r.sla_deadline).getTime() - Date.now() < 8 * 3_600_000);

  const CARD: React.CSSProperties = {
    background: "var(--color-surface)", borderRadius: TOKENS.radius.card,
    border: "1px solid var(--color-border)", boxShadow: "var(--shadow-sm)",
  };

  return (
    <div style={{ minHeight: "100vh", background: "var(--bg-gradient)", fontFamily: FONT }}>
      <TopBar
        crumbs={[{ label: "Executive view" }]}
        right={
          <span style={{ fontSize: 11, color: "var(--color-text-muted)", fontFamily: FONT }}>
            {new Date().toLocaleDateString("en-US", { weekday: "long", day: "numeric", month: "long" })}
          </span>
        }
      />

      <main style={{ maxWidth: 1100, margin: "0 auto", padding: "36px 28px 80px" }}>

        {/* Page header */}
        <div style={{ marginBottom: 28 }}>
          <h1 style={{ fontSize: 28, fontWeight: 800, color: "var(--color-text-primary)", margin: "0 0 6px", fontFamily: FONT, letterSpacing: "-0.03em" }}>
            Executive overview
          </h1>
          <p style={{ fontSize: 13, color: "var(--color-text-muted)", margin: 0, lineHeight: 1.5 }}>
            Procurement evaluations across all departments — spend, status, and pending approvals.
          </p>
        </div>

        {/* KPI row */}
        <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 16, marginBottom: 28 }}>
          <KpiTile label="Total evaluations"  value={runs.length}      sub="all time" />
          <KpiTile label="Pending approval"   value={pending.length}   sub={`${slaAtRisk.length} SLA at risk`} colour={pending.length > 0 ? "var(--color-warning)" : undefined} />
          <KpiTile label="Running now"        value={running.length}   sub="in pipeline" colour={running.length > 0 ? "var(--color-info)" : undefined} />
          <KpiTile label="Completed"          value={complete.length}  sub="this period" colour="var(--color-success)" />
        </div>

        {loading && (
          <div style={{ ...CARD, padding: "40px", textAlign: "center" }}>
            <span style={{ color: "var(--color-text-muted)", fontSize: 13 }}>Loading evaluations…</span>
          </div>
        )}

        {error && (
          <div style={{ background: "var(--color-error)14", border: "1px solid var(--color-error)", borderRadius: TOKENS.radius.card, padding: "14px 18px", fontSize: 13, color: "var(--color-error)", fontFamily: FONT, marginBottom: 18 }}>
            {error}
          </div>
        )}

        {/* Pending approvals */}
        {!loading && pending.length > 0 && (
          <section style={{ marginBottom: 24 }}>
            <div style={{ fontSize: 11, fontWeight: 600, color: "var(--color-text-muted)", letterSpacing: "0.1em", textTransform: "uppercase", marginBottom: 12, fontFamily: FONT }}>
              Pending approvals
              {slaAtRisk.length > 0 && (
                <span style={{ marginLeft: 8, color: "var(--color-error)", fontWeight: 400 }}>
                  · {slaAtRisk.length} SLA at risk
                </span>
              )}
            </div>
            <div style={{ ...CARD, overflow: "hidden" }}>
              <div style={{ display: "grid", gridTemplateColumns: "1fr 120px 100px 100px 100px 120px", padding: "10px 20px", borderBottom: "1px solid var(--color-border)" }}>
                {["Evaluation", "Department", "Vendors", "Tier", "SLA", "Action"].map(h => <span key={h} style={COL_HEADER}>{h}</span>)}
              </div>
              {pending.map((r, i) => (
                <div key={r.run_id} style={{
                  display: "grid", gridTemplateColumns: "1fr 120px 100px 100px 100px 120px",
                  padding: "13px 20px", alignItems: "center",
                  borderBottom: i < pending.length - 1 ? "1px solid var(--color-border)" : "none",
                  transition: "background var(--transition)",
                }}
                  onMouseEnter={e => (e.currentTarget.style.background = "var(--color-surface-hover)")}
                  onMouseLeave={e => (e.currentTarget.style.background = "transparent")}
                >
                  <div>
                    <div style={{ fontSize: 13, fontWeight: 600, color: "var(--color-text-primary)", fontFamily: FONT }}>{r.rfp_title || r.run_id.slice(0, 16)}</div>
                    {r.recommended_vendor && (
                      <div style={{ fontSize: 11, color: "var(--color-success)", fontFamily: FONT, marginTop: 2 }}>Rec: {r.recommended_vendor}</div>
                    )}
                  </div>
                  <span style={{ fontSize: 12, color: "var(--color-text-secondary)", fontFamily: FONT }}>{r.department}</span>
                  <span style={{ fontFamily: MONO, fontSize: 12, color: "var(--color-text-secondary)" }}>{r.vendor_count}</span>
                  <span style={{ fontFamily: MONO, fontSize: 12, color: "var(--color-warning)" }}>Tier {r.approval_tier ?? "—"}</span>
                  <span>{r.sla_deadline ? <SlaChip deadline={r.sla_deadline} /> : <span style={{ fontSize: 12, color: "var(--color-text-muted)" }}>—</span>}</span>
                  <button onClick={() => router.push(`/${r.run_id}/approve`)} style={{
                    background: "var(--color-warning)", color: "#1A0D00", border: "none",
                    borderRadius: 7, padding: "6px 14px", fontSize: 11,
                    fontFamily: FONT, fontWeight: 700, cursor: "pointer",
                    transition: "opacity var(--transition)",
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
            <div style={{ fontSize: 11, fontWeight: 600, color: "var(--color-text-muted)", letterSpacing: "0.1em", textTransform: "uppercase", marginBottom: 12, fontFamily: FONT }}>
              All evaluations
            </div>
            <div style={{ ...CARD, overflow: "hidden" }}>
              <div style={{ display: "grid", gridTemplateColumns: "1fr 120px 80px 80px 110px 100px", padding: "10px 20px", borderBottom: "1px solid var(--color-border)" }}>
                {["Evaluation", "Department", "Vendors", "Shortlisted", "Status", "Started"].map(h => <span key={h} style={COL_HEADER}>{h}</span>)}
              </div>
              {runs.map((r, i) => (
                <div key={r.run_id}
                  onClick={() => router.push(r.status === "pending_approval" ? `/${r.run_id}/approve` : `/${r.run_id}/results`)}
                  style={{
                    display: "grid", gridTemplateColumns: "1fr 120px 80px 80px 110px 100px",
                    padding: "12px 20px", alignItems: "center", cursor: "pointer",
                    borderBottom: i < runs.length - 1 ? "1px solid var(--color-border)" : "none",
                    transition: "background var(--transition)",
                  }}
                  onMouseEnter={e => (e.currentTarget.style.background = "var(--color-surface-hover)")}
                  onMouseLeave={e => (e.currentTarget.style.background = "transparent")}
                >
                  <div style={{ fontSize: 13, fontWeight: 500, color: "var(--color-text-primary)", fontFamily: FONT, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                    {r.rfp_title || r.run_id.slice(0, 20)}
                  </div>
                  <span style={{ fontSize: 12, color: "var(--color-text-secondary)", fontFamily: FONT }}>{r.department}</span>
                  <span style={{ fontFamily: MONO, fontSize: 12, color: "var(--color-text-secondary)" }}>{r.vendor_count}</span>
                  <span style={{ fontFamily: MONO, fontSize: 12, color: "var(--color-success)" }}>{r.shortlisted_count}</span>
                  <StatusPill status={r.status} />
                  <span style={{ fontFamily: MONO, fontSize: 11, color: "var(--color-text-muted)" }}>
                    {new Date(r.started_at).toLocaleDateString("en-US", { day: "numeric", month: "short" })}
                  </span>
                </div>
              ))}
            </div>
          </section>
        )}

        {!loading && runs.length === 0 && !error && (
          <div style={{ ...CARD, padding: "56px", textAlign: "center" }}>
            <div style={{ fontSize: 13, fontWeight: 600, color: "var(--color-text-primary)", marginBottom: 6, fontFamily: FONT }}>No evaluations yet</div>
            <div style={{ fontSize: 13, color: "var(--color-text-muted)", fontFamily: FONT, marginBottom: 20, lineHeight: 1.5 }}>Start a new RFP evaluation to see data here.</div>
            <button onClick={() => router.push("/procurement/upload")} style={{
              background: "var(--color-accent)", color: "var(--color-accent-foreground)", border: "none",
              borderRadius: TOKENS.radius.btn, padding: "10px 24px",
              fontSize: 13, fontFamily: FONT, fontWeight: 600, cursor: "pointer",
              transition: "background var(--transition)",
            }}>
              Start evaluation →
            </button>
          </div>
        )}
      </main>
    </div>
  );
}
