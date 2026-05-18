"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { FONT, DISPLAY, MONO } from "@/lib/theme";
import { useThemeContext } from "@/components/ThemeProvider";
import { ThemePicker } from "@/components/ThemePicker";
import { useBreakpoint } from "@/lib/hooks";
import { api, getUserInfo, clearUserInfo, isLoggedIn } from "@/lib/api";

interface EvalRun {
  run_id: string;
  rfp_title: string;
  status: string;
  vendor_count: number;
  created_at: string;
  updated_at: string;
}

const STATUS_COLOR: Record<string, string> = {
  completed:   "var(--color-success)",
  running:     "var(--color-info)",
  pending:     "var(--color-warning)",
  failed:      "var(--color-error)",
  draft:       "var(--color-text-muted)",
};

const STATUS_LABEL: Record<string, string> = {
  completed: "Complete",
  running:   "Running",
  pending:   "Pending",
  failed:    "Failed",
  draft:     "Draft",
};

function formatDate(iso: string) {
  return new Date(iso).toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric" });
}

export default function HomePage() {
  const router = useRouter();
  const { isDark } = useThemeContext();
  const bp = useBreakpoint();
  const isMobile = bp === "mobile";

  const [runs, setRuns] = useState<EvalRun[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [userName, setUserName] = useState("");
  const [hoveredRow, setHoveredRow] = useState<string | null>(null);

  useEffect(() => {
    if (!isLoggedIn()) { router.push("/login"); return; }

    const userInfo = getUserInfo();
    if (userInfo) setUserName(userInfo.email);

    api.get<{ runs?: EvalRun[] } | EvalRun[]>("/api/v1/evaluate/list", {
      on401: () => router.push("/login"),
    })
      .then((data) => setRuns(Array.isArray(data) ? data : (data.runs ?? [])))
      .catch(() => setError("Could not load evaluations. Is the backend running?"))
      .finally(() => setLoading(false));
  }, [router]);

  async function signOut() {
    await api.post("/api/v1/auth/logout").catch(() => {});
    clearUserInfo();
    router.push("/login");
  }

  const topBarBg = isDark ? "rgba(9,14,26,0.92)" : "rgba(246,249,252,0.92)";

  return (
    <div style={{ minHeight: "100vh", background: "var(--bg-gradient)", fontFamily: FONT }}>

      {/* ── Top bar */}
      <header
        style={{
          position: "sticky", top: 0, zIndex: 50,
          display: "flex", alignItems: "center", justifyContent: "space-between",
          padding: "0 32px", height: 56,
          backgroundColor: topBarBg,
          borderBottom: "1px solid var(--color-border)",
          backdropFilter: "blur(12px)",
        }}
      >
        {/* Logo */}
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <div
            style={{
              width: 24, height: 24,
              border: "1.5px solid var(--color-accent)",
              borderRadius: 4,
              display: "flex", alignItems: "center", justifyContent: "center",
            }}
          >
            <div style={{ width: 8, height: 8, backgroundColor: "var(--color-accent)", borderRadius: 2 }} />
          </div>
          <span
            style={{
              fontFamily: DISPLAY, fontWeight: 700, fontSize: 14,
              letterSpacing: "0.06em", textTransform: "uppercase",
              color: "var(--color-text-primary)",
            }}
          >
            Meridian AI
          </span>
        </div>

        {/* Right side */}
        <div style={{ display: "flex", alignItems: "center", gap: 16 }}>
          <ThemePicker />
          {userName && (
            <span style={{ fontFamily: MONO, fontSize: 12, color: "var(--color-text-muted)" }}>
              {userName}
            </span>
          )}
          <button
            onClick={signOut}
            onMouseEnter={(e) => { (e.currentTarget).style.color = "var(--color-text-primary)"; }}
            onMouseLeave={(e) => { (e.currentTarget).style.color = "var(--color-text-muted)"; }}
            style={{
              background: "none", border: "none", cursor: "pointer",
              fontFamily: FONT, fontWeight: 500, fontSize: 13,
              color: "var(--color-text-muted)",
              transition: "color 150ms ease-out", padding: 0,
            }}
          >
            Sign out
          </button>
        </div>
      </header>

      {/* ── Main content */}
      <main style={{ maxWidth: 960, margin: "0 auto", padding: "48px 32px" }}>

        {/* Page header */}
        <div style={{ display: "flex", alignItems: "flex-end", justifyContent: "space-between", marginBottom: 40 }}>
          <div>
            <p
              style={{
                fontFamily: FONT, fontWeight: 600, fontSize: 11,
                letterSpacing: "0.1em", textTransform: "uppercase",
                color: "var(--color-text-muted)", marginBottom: 8,
              }}
            >
              RFP Evaluations
            </p>
            <h1
              style={{
                fontFamily: DISPLAY, fontWeight: 800, fontSize: 32,
                lineHeight: 1.0, letterSpacing: "-0.03em",
                color: "var(--color-text-primary)",
              }}
            >
              Vendor evaluations
            </h1>
          </div>

          <Link
            href="/procurement/upload"
            onMouseEnter={(e) => { (e.currentTarget as HTMLAnchorElement).style.opacity = "0.88"; (e.currentTarget as HTMLAnchorElement).style.transform = "translateY(-1px)"; }}
            onMouseLeave={(e) => { (e.currentTarget as HTMLAnchorElement).style.opacity = "1"; (e.currentTarget as HTMLAnchorElement).style.transform = "translateY(0)"; }}
            style={{
              display: "inline-flex", alignItems: "center", gap: 8,
              padding: "10px 20px",
              backgroundColor: "var(--color-accent)",
              color: "var(--color-accent-foreground)",
              borderRadius: "var(--radius)",
              fontFamily: FONT, fontWeight: 600, fontSize: 13,
              textDecoration: "none",
              boxShadow: "var(--shadow-sm)",
              transition: "opacity 150ms ease-out, transform 150ms ease-out",
            }}
          >
            <span style={{ fontSize: 16, lineHeight: 1 }}>+</span>
            New evaluation
          </Link>
        </div>

        {/* Stats row */}
        {!loading && runs.length > 0 && (
          <div style={{ display: "flex", gap: 16, marginBottom: 32 }}>
            {[
              { label: "Total", value: runs.length },
              { label: "Running", value: runs.filter(r => r.status === "running").length },
              { label: "Complete", value: runs.filter(r => r.status === "completed").length },
              { label: "Pending", value: runs.filter(r => r.status === "pending" || r.status === "draft").length },
            ].map(({ label, value }) => (
              <div
                key={label}
                style={{
                  flex: 1,
                  padding: "16px 20px",
                  backgroundColor: "var(--color-surface)",
                  borderTop: "1px solid var(--color-border)",
                  borderBottom: "1px solid var(--color-border)",
                  borderLeft: "1px solid var(--color-border)",
                  borderRight: "1px solid var(--color-border)",
                  borderRadius: "var(--radius)",
                  boxShadow: "var(--shadow-sm)",
                }}
              >
                <p style={{ fontFamily: MONO, fontWeight: 700, fontSize: 28, color: "var(--color-text-primary)", lineHeight: 1, marginBottom: 4, fontVariantNumeric: "tabular-nums" }}>
                  {value}
                </p>
                <p style={{ fontFamily: FONT, fontWeight: 500, fontSize: 11, letterSpacing: "0.08em", textTransform: "uppercase", color: "var(--color-text-muted)" }}>
                  {label}
                </p>
              </div>
            ))}
          </div>
        )}

        {/* Table */}
        <div
          style={{
            backgroundColor: "var(--color-surface)",
            borderTop: "1px solid var(--color-border)",
            borderBottom: "1px solid var(--color-border)",
            borderLeft: "1px solid var(--color-border)",
            borderRight: "1px solid var(--color-border)",
            borderRadius: "var(--radius)",
            boxShadow: "var(--shadow-sm)",
            overflow: "hidden",
          }}
        >
          {/* Table header */}
          <div
            style={{
              display: "grid",
              gridTemplateColumns: "1fr 120px 80px 120px 40px",
              padding: "10px 20px",
              borderBottom: "1px solid var(--color-border)",
              backgroundColor: "var(--color-background)",
            }}
          >
            {["RFP Title", "Status", "Vendors", "Created", ""].map((h) => (
              <span
                key={h}
                style={{
                  fontFamily: FONT, fontWeight: 600, fontSize: 11,
                  letterSpacing: "0.08em", textTransform: "uppercase",
                  color: "var(--color-text-muted)",
                }}
              >
                {h}
              </span>
            ))}
          </div>

          {/* Loading */}
          {loading && (
            <div style={{ padding: "48px 20px", textAlign: "center" }}>
              <p style={{ fontFamily: FONT, fontSize: 14, color: "var(--color-text-muted)" }}>Loading evaluations…</p>
            </div>
          )}

          {/* Error */}
          {error && (
            <div style={{ padding: "32px 20px" }}>
              <p role="alert" style={{ fontFamily: FONT, fontSize: 14, color: "var(--color-error)" }}>{error}</p>
            </div>
          )}

          {/* Empty state */}
          {!loading && !error && runs.length === 0 && (
            <div style={{ padding: "64px 20px", textAlign: "center" }}>
              <p style={{ fontFamily: DISPLAY, fontWeight: 700, fontSize: 18, color: "var(--color-text-primary)", marginBottom: 8 }}>
                No evaluations yet
              </p>
              <p style={{ fontFamily: FONT, fontSize: 14, color: "var(--color-text-muted)", marginBottom: 24 }}>
                Upload your first RFP to start evaluating vendors.
              </p>
              <Link
                href="/procurement/upload"
                style={{
                  display: "inline-flex", alignItems: "center", gap: 8,
                  padding: "10px 20px",
                  backgroundColor: "var(--color-accent)",
                  color: "var(--color-accent-foreground)",
                  borderRadius: "var(--radius)",
                  fontFamily: FONT, fontWeight: 600, fontSize: 13,
                  textDecoration: "none",
                }}
              >
                Upload first RFP
              </Link>
            </div>
          )}

          {/* Rows */}
          {!loading && runs.map((run) => (
            <div
              key={run.run_id}
              onMouseEnter={() => setHoveredRow(run.run_id)}
              onMouseLeave={() => setHoveredRow(null)}
              onClick={() => router.push(`/${run.run_id}/results`)}
              style={{
                display: "grid",
                gridTemplateColumns: "1fr 120px 80px 120px 40px",
                padding: "14px 20px",
                borderBottom: "1px solid var(--color-border)",
                backgroundColor: hoveredRow === run.run_id ? "var(--color-surface-hover)" : "transparent",
                cursor: "pointer",
                transition: "background-color 150ms ease-out",
                alignItems: "center",
              }}
            >
              <div>
                <p style={{ fontFamily: FONT, fontWeight: 500, fontSize: 14, color: "var(--color-text-primary)", lineHeight: 1.3 }}>
                  {run.rfp_title || "Untitled RFP"}
                </p>
                <p style={{ fontFamily: MONO, fontSize: 11, color: "var(--color-text-muted)", marginTop: 2 }}>
                  {run.run_id}
                </p>
              </div>

              <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                <div
                  style={{
                    width: 7, height: 7, borderRadius: "50%",
                    backgroundColor: STATUS_COLOR[run.status] ?? "var(--color-text-muted)",
                    flexShrink: 0,
                  }}
                />
                <span style={{ fontFamily: FONT, fontWeight: 500, fontSize: 13, color: "var(--color-text-secondary)" }}>
                  {STATUS_LABEL[run.status] ?? run.status}
                </span>
              </div>

              <span style={{ fontFamily: MONO, fontWeight: 500, fontSize: 13, color: "var(--color-text-secondary)", fontVariantNumeric: "tabular-nums" }}>
                {run.vendor_count ?? "—"}
              </span>

              <span style={{ fontFamily: MONO, fontSize: 12, color: "var(--color-text-muted)" }}>
                {formatDate(run.created_at)}
              </span>

              <span style={{ color: "var(--color-text-muted)", fontSize: 16 }}>→</span>
            </div>
          ))}
        </div>
      </main>
    </div>
  );
}
