"use client";

import { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { FONT, DISPLAY, MONO } from "@/lib/theme";
import { useThemeContext } from "@/components/layout/ThemeProvider";
import { useBreakpoint } from "@/lib/hooks";
import { api, setUserInfo, isLoggedIn } from "@/lib/api";
import LeftBrandPanel from "@/components/auth/LeftBrandPanel";

export default function LoginPage() {
  const router = useRouter();
  const { isDark } = useThemeContext();
  const bp = useBreakpoint();
  const isDesktop = bp === "desktop";

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [focusedField, setFocusedField] = useState<"email" | "password" | null>(null);

  useEffect(() => {
    if (isLoggedIn()) router.push("/");
  }, [router]);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      // Backend sets HttpOnly cookie; response body has role/org_id for display
      const data = await api.post<{ role: string; org_id: string }>(
        "/api/v1/auth/token",
        { body: { email, password } }
      );
      setUserInfo({ email, role: data.role, org_id: data.org_id });
      router.push("/");
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Invalid email or password.");
    } finally {
      setLoading(false);
    }
  }

  // ── Shared input style ────────────────────────────────────────────────────
  const inputStyle = (field: "email" | "password"): React.CSSProperties => ({
    display: "block",
    width: "100%",
    background: "transparent",
    borderTop: "none",
    borderLeft: "none",
    borderRight: "none",
    borderBottom: `1.5px solid ${focusedField === field ? "var(--color-accent)" : "var(--color-border-strong)"}`,
    borderRadius: 0,
    padding: "8px 0",
    fontFamily: FONT,
    fontWeight: 400,
    fontSize: 15,
    color: "var(--color-text-primary)",
    outline: "none",
    transition: "border-color 150ms ease-out",
    boxSizing: "border-box",
  });

  const labelStyle = (field: "email" | "password"): React.CSSProperties => ({
    display: "block",
    fontFamily: FONT,
    fontWeight: 500,
    fontSize: 11,
    letterSpacing: "0.08em",
    textTransform: "uppercase",
    color: focusedField === field ? "var(--color-accent)" : "var(--color-text-muted)",
    marginBottom: 8,
    transition: "color 150ms ease-out",
  });

  // ── Padding based on breakpoint ───────────────────────────────────────────
  const formPadding = isDesktop ? "48px 32px" : bp === "tablet" ? "32px 24px" : "24px 20px";

  return (
    <div style={{ minHeight: "100vh", display: "flex", fontFamily: FONT }}>

      {/* ── Left brand panel — desktop only ──────────────────────────────── */}
      {isDesktop && <LeftBrandPanel />}

      {/* ── Right / full-width form panel ────────────────────────────────── */}
      <div
        style={{
          flex: 1,
          display: "flex",
          flexDirection: "column",
          justifyContent: "center",
          alignItems: "center",
          background: "var(--bg-gradient)",
          padding: formPadding,
        }}
      >
        <div style={{ width: "100%", maxWidth: isDesktop ? 380 : 440 }}>

          {/* Compact logo — mobile/tablet only */}
          {!isDesktop && (
            <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 40 }}>
              <div
                style={{
                  width: 28, height: 28,
                  border: "1.5px solid var(--color-accent)",
                  borderRadius: 5,
                  display: "flex", alignItems: "center", justifyContent: "center",
                }}
              >
                <div style={{ width: 10, height: 10, backgroundColor: "var(--color-accent)", borderRadius: 2 }} />
              </div>
              <span
                style={{
                  fontFamily: DISPLAY, fontWeight: 700, fontSize: 14,
                  letterSpacing: "0.12em", textTransform: "uppercase",
                  color: "var(--color-text-primary)",
                }}
              >
                Meridian AI
              </span>
            </div>
          )}

          {/* Section label */}
          <p style={{ fontFamily: FONT, fontWeight: 600, fontSize: 11, letterSpacing: "0.1em", textTransform: "uppercase", color: "var(--color-text-muted)", marginBottom: 12 }}>
            Sign in
          </p>
          <h1
            style={{
              fontFamily: DISPLAY, fontWeight: 800, fontSize: 28,
              lineHeight: 1.1, letterSpacing: "-0.03em",
              color: "var(--color-text-primary)", marginBottom: 8,
            }}
          >
            Welcome back
          </h1>
          <p style={{ fontFamily: FONT, fontWeight: 400, fontSize: 14, color: "var(--color-text-secondary)", marginBottom: 40, lineHeight: 1.6 }}>
            Enter your credentials to access the platform.
          </p>

          <form onSubmit={handleSubmit}>
            {/* Email */}
            <div style={{ marginBottom: 32 }}>
              <label htmlFor="email" style={labelStyle("email")}>Email address</label>
              <input
                id="email" type="email" autoComplete="email" required
                value={email} onChange={(e) => setEmail(e.target.value)}
                onFocus={() => setFocusedField("email")} onBlur={() => setFocusedField(null)}
                suppressHydrationWarning style={inputStyle("email")}
                placeholder="you@company.com"
              />
            </div>

            {/* Password */}
            <div style={{ marginBottom: 40 }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", marginBottom: 8 }}>
                <label htmlFor="password" style={{ ...labelStyle("password"), marginBottom: 0 }}>Password</label>
                <a href="#" style={{ fontFamily: FONT, fontWeight: 500, fontSize: 12, color: "var(--color-text-muted)", textDecoration: "none" }}>
                  Forgot?
                </a>
              </div>
              <input
                id="password" type="password" autoComplete="current-password" required
                value={password} onChange={(e) => setPassword(e.target.value)}
                onFocus={() => setFocusedField("password")} onBlur={() => setFocusedField(null)}
                suppressHydrationWarning style={inputStyle("password")}
                placeholder="••••••••••••"
              />
            </div>

            {/* Error */}
            {error && (
              <div
                role="alert"
                style={{
                  marginBottom: 20, padding: "10px 14px",
                  backgroundColor: "color-mix(in srgb, var(--color-error) 10%, transparent)",
                  borderTop: "none", borderBottom: "none", borderRight: "none",
                  borderLeft: "2px solid var(--color-error)",
                  borderRadius: "0 4px 4px 0",
                  fontFamily: FONT, fontWeight: 500, fontSize: 13,
                  color: "var(--color-error)", lineHeight: 1.5,
                }}
              >
                {error}
              </div>
            )}

            {/* Submit */}
            <button
              type="submit" disabled={loading}
              onMouseEnter={(e) => { if (!loading) { (e.currentTarget).style.opacity = "0.88"; (e.currentTarget).style.transform = "translateY(-1px)"; } }}
              onMouseLeave={(e) => { (e.currentTarget).style.opacity = "1"; (e.currentTarget).style.transform = "translateY(0)"; }}
              onMouseDown={(e) => { if (!loading) (e.currentTarget).style.transform = "translateY(0) scale(0.98)"; }}
              onMouseUp={(e) => { if (!loading) (e.currentTarget).style.transform = "translateY(-1px)"; }}
              style={{
                display: "block", width: "100%", padding: "14px 0",
                backgroundColor: "var(--color-accent)", color: "var(--color-accent-foreground)",
                border: "none", borderRadius: "var(--radius)",
                fontFamily: FONT, fontWeight: 600, fontSize: 14, letterSpacing: "0.02em",
                cursor: loading ? "not-allowed" : "pointer",
                opacity: loading ? 0.6 : 1,
                transition: "opacity 150ms ease-out, transform 150ms ease-out",
                boxShadow: "var(--shadow-sm)",
              }}
            >
              {loading ? "Signing in…" : "Sign in"}
            </button>
          </form>

          {/* Divider */}
          <div style={{ display: "flex", alignItems: "center", gap: 12, margin: "28px 0" }}>
            <div style={{ flex: 1, height: 1, backgroundColor: "var(--color-border)" }} />
            <span style={{ fontFamily: FONT, fontWeight: 400, fontSize: 12, color: "var(--color-text-muted)" }}>New to Meridian?</span>
            <div style={{ flex: 1, height: 1, backgroundColor: "var(--color-border)" }} />
          </div>

          <Link
            href="/signup"
            style={{
              display: "block", width: "100%", padding: "13px 0",
              backgroundColor: "transparent", color: "var(--color-text-primary)",
              borderTop: "1px solid var(--color-border)", borderBottom: "1px solid var(--color-border)",
              borderLeft: "1px solid var(--color-border)", borderRight: "1px solid var(--color-border)",
              borderRadius: "var(--radius)",
              fontFamily: FONT, fontWeight: 500, fontSize: 14,
              textAlign: "center", textDecoration: "none",
              transition: "background-color 150ms ease-out",
              boxSizing: "border-box",
            }}
            onMouseEnter={(e) => { (e.currentTarget as HTMLAnchorElement).style.backgroundColor = "var(--color-surface-hover)"; }}
            onMouseLeave={(e) => { (e.currentTarget as HTMLAnchorElement).style.backgroundColor = "transparent"; }}
          >
            Create an account
          </Link>

          <p
            style={{
              marginTop: 32, fontFamily: MONO, fontWeight: 400, fontSize: 11,
              color: "var(--color-text-muted)", letterSpacing: "0.04em", lineHeight: 1.6,
            }}
          >
            Protected by enterprise SSO and MFA.
            <br />Access is logged and audited.
          </p>
        </div>
      </div>
    </div>
  );
}
