"use client";

import { useEffect, useState } from "react";
import { useRouter, useParams } from "next/navigation";
import { FONT, PALETTE, PALETTE_LIGHT, TOKENS, agentColour } from "@/lib/theme";
import { TopBar, useTheme } from "@/components/TopBar";

interface EvalRun {
  run_id: string;
  rfp_title: string;
  department: string;
  status: "running" | "pending_approval" | "complete" | "blocked";
  vendor_count: number;
  shortlisted_count: number;
  rejected_count: number;
  started_at: string;
}

function StatusBadge({ status }: { status: EvalRun["status"] }) {
  const cfg: Record<string, { label: string; bg: string; fg: string }> = {
    running:          { label: "Running",          bg: "#3B82F620", fg: "#3B82F6" },
    pending_approval: { label: "Pending Approval", bg: "#F59E0B20", fg: "#F59E0B" },
    complete:         { label: "Complete",         bg: "#10B98120", fg: "#10B981" },
    blocked:          { label: "Blocked",          bg: "#EF444420", fg: "#EF4444" },
  };
  const c = cfg[status] ?? { label: status, bg: "#ffffff10", fg: "#94A3B8" };
  return (
    <span style={{
      fontSize: 10, fontWeight: 700, letterSpacing: "0.08em", textTransform: "uppercase",
      background: c.bg, color: c.fg, borderRadius: 5, padding: "2px 8px", fontFamily: FONT,
    }}>
      {c.label}
    </span>
  );
}

export default function DepartmentPage() {
  const router = useRouter();
  const params = useParams();
  const { isDark, toggle } = useTheme();
  const P = isDark ? PALETTE : PALETTE_LIGHT;

  const dept = decodeURIComponent(params.dept as string);
  const accent = agentColour(dept);

  const [runs, setRuns] = useState<EvalRun[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const token = localStorage.getItem("access_token");
    fetch("/api/v1/evaluate/list", {
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    })
      .then((r) => r.json())
      .then((d) => {
        const all: EvalRun[] = d.runs ?? [];
        setRuns(all.filter(r =>
          r.department?.toLowerCase() === dept.toLowerCase()
        ));
        setLoading(false);
      })
      .catch(() => setLoading(false));
  }, [dept]);

  return (
    <div style={{ minHeight: "100vh", background: isDark ? "#090C12" : "#F8FAFC", fontFamily: FONT }}>
      <TopBar
        isDark={isDark}
        onToggle={toggle}
        crumbs={[
          { label: "Dashboard", href: "/dashboard" },
          { label: dept },
        ]}
        right={
          <button
            onClick={() => router.push("/procurement/upload")}
            style={{
              fontSize: 12, fontWeight: 600, color: accent,
              background: "none", border: `1px solid ${accent}40`,
              borderRadius: 8, padding: "6px 14px", cursor: "pointer", fontFamily: FONT,
            }}
          >
            + New Evaluation
          </button>
        }
      />

      <div style={{ maxWidth: 900, margin: "0 auto", padding: "40px 24px" }}>
        {/* Department header */}
        <div style={{ marginBottom: 32 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 6 }}>
            <span style={{
              width: 10, height: 10, borderRadius: "50%",
              background: accent, boxShadow: `0 0 8px ${accent}80`,
              display: "inline-block", flexShrink: 0,
            }} />
            <h1 style={{ fontSize: 22, fontWeight: 700, color: P.text.primary, margin: 0, fontFamily: FONT }}>
              {dept}
            </h1>
          </div>
          <p style={{ fontSize: 13, color: P.text.muted, margin: 0, fontFamily: FONT }}>
            {loading ? "Loading…" : `${runs.length} evaluation${runs.length !== 1 ? "s" : ""}`}
          </p>
        </div>

        {/* Run list */}
        {loading ? (
          <div style={{ color: P.text.muted, fontSize: 13, textAlign: "center", padding: "60px 0" }}>
            Loading evaluations…
          </div>
        ) : runs.length === 0 ? (
          <div style={{
            textAlign: "center", padding: "60px 24px",
            border: `1px dashed ${P.border.mid}`,
            borderRadius: TOKENS.radius.card, color: P.text.muted,
          }}>
            <div style={{ fontSize: 14, fontWeight: 600, marginBottom: 8, color: P.text.secondary }}>
              No evaluations yet for {dept}
            </div>
            <div style={{ fontSize: 12, marginBottom: 20 }}>
              Start by uploading an RFP and vendor documents.
            </div>
            <button
              onClick={() => router.push("/procurement/upload")}
              style={{
                background: accent, color: "#fff", border: "none",
                borderRadius: TOKENS.radius.btn, padding: "9px 20px",
                fontSize: 13, fontWeight: 600, cursor: "pointer", fontFamily: FONT,
              }}
            >
              + New Evaluation
            </button>
          </div>
        ) : (
          <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
            {runs.map(run => (
              <div
                key={run.run_id}
                onClick={() => {
                  if (run.status === "complete") router.push(`/${run.run_id}/results`);
                  else if (run.status === "pending_approval") router.push(`/${run.run_id}/approve`);
                  else if (run.status === "running") router.push(`/${run.run_id}/progress`);
                }}
                style={{
                  background: P.bg.surface,
                  border: `1px solid ${P.border.mid}`,
                  borderRadius: TOKENS.radius.card,
                  padding: "16px 20px",
                  cursor: "pointer",
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "space-between",
                  gap: 12,
                  transition: "border-color 120ms",
                }}
              >
                <div style={{ minWidth: 0 }}>
                  <div style={{ fontSize: 14, fontWeight: 600, color: P.text.primary, fontFamily: FONT, marginBottom: 4, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
                    {run.rfp_title || run.run_id.slice(0, 8) + "…"}
                  </div>
                  <div style={{ fontSize: 11, color: P.text.muted, fontFamily: FONT }}>
                    {run.vendor_count} vendor{run.vendor_count !== 1 ? "s" : ""} ·{" "}
                    {run.shortlisted_count} shortlisted ·{" "}
                    {new Date(run.started_at).toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric" })}
                  </div>
                </div>
                <StatusBadge status={run.status} />
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
