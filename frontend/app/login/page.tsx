"use client";

import { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { FONT, DISPLAY, MONO } from "@/lib/theme";
import { useThemeContext } from "@/components/ThemeProvider";

export default function LoginPage() {
  const router = useRouter();
  const { isDark } = useThemeContext();

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [mounted, setMounted] = useState(false);
  const [focusedField, setFocusedField] = useState<"email" | "password" | null>(null);

  useEffect(() => {
    setMounted(true);
    const token = localStorage.getItem("access_token");
    if (token) router.push("/");
  }, [router]);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    setLoading(true);

    try {
      const body = new URLSearchParams({ username: email, password });
      const res = await fetch("/api/v1/auth/token", {
        method: "POST",
        headers: { "Content-Type": "application/x-www-form-urlencoded" },
        body: body.toString(),
      });

      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        setError(data.detail ?? "Invalid email or password.");
        return;
      }

      const data = await res.json();
      localStorage.setItem("access_token", data.access_token);
      router.push("/");
    } catch {
      setError("Unable to reach the server. Please try again.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div
      style={{
        minHeight: "100vh",
        display: "flex",
        fontFamily: FONT,
      }}
    >
      {/* ── Left: Brand panel (intentionally hardcoded dark, like AgentSwitcherRail) */}
      <div
        style={{
          width: "45%",
          minWidth: 340,
          backgroundColor: "#090E1A",
          display: "flex",
          flexDirection: "column",
          justifyContent: "space-between",
          padding: "48px 48px 40px",
          position: "relative",
          overflow: "hidden",
          flexShrink: 0,
        }}
      >
        {/* Subtle grid texture */}
        <div
          aria-hidden
          style={{
            position: "absolute",
            inset: 0,
            backgroundImage:
              "linear-gradient(rgba(255,255,255,0.025) 1px, transparent 1px), linear-gradient(90deg, rgba(255,255,255,0.025) 1px, transparent 1px)",
            backgroundSize: "40px 40px",
            pointerEvents: "none",
          }}
        />

        {/* Accent glow — top right */}
        <div
          aria-hidden
          style={{
            position: "absolute",
            top: -80,
            right: -80,
            width: 320,
            height: 320,
            borderRadius: "50%",
            background: "radial-gradient(circle, rgba(99,102,241,0.18) 0%, transparent 70%)",
            pointerEvents: "none",
          }}
        />

        {/* Top: wordmark */}
        <div style={{ position: "relative", zIndex: 1 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 0 }}>
            {/* Logo mark — thin accent square */}
            <div
              style={{
                width: 28,
                height: 28,
                border: "1.5px solid rgba(99,102,241,0.7)",
                borderRadius: 5,
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
              }}
            >
              <div
                style={{
                  width: 10,
                  height: 10,
                  backgroundColor: "rgba(99,102,241,0.9)",
                  borderRadius: 2,
                }}
              />
            </div>
            <span
              style={{
                fontFamily: DISPLAY,
                fontWeight: 700,
                fontSize: 14,
                letterSpacing: "0.12em",
                textTransform: "uppercase",
                color: "rgba(255,255,255,0.55)",
              }}
            >
              Meridian AI
            </span>
          </div>
        </div>

        {/* Middle: massive editorial wordmark */}
        <div
          style={{
            position: "relative",
            zIndex: 1,
            flex: 1,
            display: "flex",
            flexDirection: "column",
            justifyContent: "center",
          }}
        >
          {/* The hero text — cropped at right edge intentionally */}
          <div style={{ overflow: "hidden", marginLeft: -4 }}>
            <div
              style={{
                fontFamily: DISPLAY,
                fontWeight: 800,
                fontSize: "clamp(64px, 9vw, 108px)",
                lineHeight: 0.9,
                letterSpacing: "-0.04em",
                color: "rgba(255,255,255,0.92)",
                whiteSpace: "nowrap",
              }}
            >
              Meridian
            </div>
          </div>

          <div
            style={{
              width: 48,
              height: 2,
              backgroundColor: "rgba(99,102,241,0.8)",
              marginTop: 24,
              marginBottom: 20,
            }}
          />

          <p
            style={{
              fontFamily: FONT,
              fontWeight: 400,
              fontSize: 14,
              lineHeight: 1.7,
              color: "rgba(255,255,255,0.4)",
              maxWidth: 260,
              letterSpacing: "0.01em",
            }}
          >
            Enterprise vendor governance.
            <br />
            AI-evaluated. Audit-ready.
          </p>
        </div>

        {/* Bottom: compliance note */}
        <div style={{ position: "relative", zIndex: 1 }}>
          <p
            style={{
              fontFamily: MONO,
              fontWeight: 400,
              fontSize: 10,
              letterSpacing: "0.08em",
              color: "rgba(255,255,255,0.2)",
              textTransform: "uppercase",
            }}
          >
            Meridian Financial Services
            <br />
            SOC 2 · ISO 27001 · GDPR
          </p>
        </div>
      </div>

      {/* ── Right: Form panel */}
      <div
        style={{
          flex: 1,
          display: "flex",
          flexDirection: "column",
          justifyContent: "center",
          alignItems: "center",
          background: "var(--bg-gradient)",
          padding: "48px 32px",
        }}
      >
        <div style={{ width: "100%", maxWidth: 380 }}>
          {/* Section label */}
          <p
            style={{
              fontFamily: FONT,
              fontWeight: 600,
              fontSize: 11,
              letterSpacing: "0.1em",
              textTransform: "uppercase",
              color: "var(--color-text-muted)",
              marginBottom: 12,
            }}
          >
            Sign in
          </p>

          {/* Heading */}
          <h1
            style={{
              fontFamily: DISPLAY,
              fontWeight: 800,
              fontSize: 28,
              lineHeight: 1.1,
              letterSpacing: "-0.03em",
              color: "var(--color-text-primary)",
              marginBottom: 8,
            }}
          >
            Welcome back
          </h1>
          <p
            style={{
              fontFamily: FONT,
              fontWeight: 400,
              fontSize: 14,
              color: "var(--color-text-secondary)",
              marginBottom: 40,
              lineHeight: 1.6,
            }}
          >
            Enter your credentials to access the platform.
          </p>

          <form onSubmit={handleSubmit}>
            {/* Email field — underline style */}
            <div style={{ marginBottom: 32 }}>
              <label
                htmlFor="email"
                style={{
                  display: "block",
                  fontFamily: FONT,
                  fontWeight: 500,
                  fontSize: 11,
                  letterSpacing: "0.08em",
                  textTransform: "uppercase",
                  color: focusedField === "email" ? "var(--color-accent)" : "var(--color-text-muted)",
                  marginBottom: 8,
                  transition: "color 150ms ease-out",
                }}
              >
                Email address
              </label>
              <input
                id="email"
                type="email"
                autoComplete="email"
                required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                onFocus={() => setFocusedField("email")}
                onBlur={() => setFocusedField(null)}
                suppressHydrationWarning
                style={{
                  display: "block",
                  width: "100%",
                  background: "transparent",
                  borderTop: "none",
                  borderLeft: "none",
                  borderRight: "none",
                  borderBottom: `1.5px solid ${focusedField === "email" ? "var(--color-accent)" : "var(--color-border-strong)"}`,
                  borderRadius: 0,
                  padding: "8px 0",
                  fontFamily: FONT,
                  fontWeight: 400,
                  fontSize: 15,
                  color: "var(--color-text-primary)",
                  outline: "none",
                  transition: "border-color 150ms ease-out",
                  boxSizing: "border-box",
                }}
                placeholder="you@company.com"
              />
            </div>

            {/* Password field — underline style */}
            <div style={{ marginBottom: 40 }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", marginBottom: 8 }}>
                <label
                  htmlFor="password"
                  style={{
                    fontFamily: FONT,
                    fontWeight: 500,
                    fontSize: 11,
                    letterSpacing: "0.08em",
                    textTransform: "uppercase",
                    color: focusedField === "password" ? "var(--color-accent)" : "var(--color-text-muted)",
                    transition: "color 150ms ease-out",
                  }}
                >
                  Password
                </label>
                <a
                  href="#"
                  style={{
                    fontFamily: FONT,
                    fontWeight: 500,
                    fontSize: 12,
                    color: "var(--color-text-muted)",
                    textDecoration: "none",
                  }}
                >
                  Forgot?
                </a>
              </div>
              <input
                id="password"
                type="password"
                autoComplete="current-password"
                required
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                onFocus={() => setFocusedField("password")}
                onBlur={() => setFocusedField(null)}
                suppressHydrationWarning
                style={{
                  display: "block",
                  width: "100%",
                  background: "transparent",
                  borderTop: "none",
                  borderLeft: "none",
                  borderRight: "none",
                  borderBottom: `1.5px solid ${focusedField === "password" ? "var(--color-accent)" : "var(--color-border-strong)"}`,
                  borderRadius: 0,
                  padding: "8px 0",
                  fontFamily: FONT,
                  fontWeight: 400,
                  fontSize: 15,
                  color: "var(--color-text-primary)",
                  outline: "none",
                  transition: "border-color 150ms ease-out",
                  boxSizing: "border-box",
                }}
                placeholder="••••••••••••"
              />
            </div>

            {/* Error message */}
            {error && (
              <div
                role="alert"
                style={{
                  marginBottom: 20,
                  padding: "10px 14px",
                  backgroundColor: "color-mix(in srgb, var(--color-error) 10%, transparent)",
                  borderTop: "none",
                  borderBottom: "none",
                  borderRight: "none",
                  borderLeft: "2px solid var(--color-error)",
                  borderRadius: "0 4px 4px 0",
                  fontFamily: FONT,
                  fontWeight: 500,
                  fontSize: 13,
                  color: "var(--color-error)",
                  lineHeight: 1.5,
                }}
              >
                {error}
              </div>
            )}

            {/* Submit button */}
            <button
              type="submit"
              disabled={loading}
              onMouseEnter={(e) => {
                if (!loading) {
                  (e.currentTarget as HTMLButtonElement).style.opacity = "0.88";
                  (e.currentTarget as HTMLButtonElement).style.transform = "translateY(-1px)";
                }
              }}
              onMouseLeave={(e) => {
                (e.currentTarget as HTMLButtonElement).style.opacity = "1";
                (e.currentTarget as HTMLButtonElement).style.transform = "translateY(0)";
              }}
              onMouseDown={(e) => {
                if (!loading) (e.currentTarget as HTMLButtonElement).style.transform = "translateY(0) scale(0.98)";
              }}
              onMouseUp={(e) => {
                if (!loading) (e.currentTarget as HTMLButtonElement).style.transform = "translateY(-1px)";
              }}
              style={{
                display: "block",
                width: "100%",
                padding: "14px 0",
                backgroundColor: "var(--color-accent)",
                color: "var(--color-accent-foreground)",
                border: "none",
                borderRadius: "var(--radius)",
                fontFamily: FONT,
                fontWeight: 600,
                fontSize: 14,
                letterSpacing: "0.02em",
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
          <div
            style={{
              display: "flex",
              alignItems: "center",
              gap: 12,
              margin: "28px 0",
            }}
          >
            <div style={{ flex: 1, height: 1, backgroundColor: "var(--color-border)" }} />
            <span
              style={{
                fontFamily: FONT,
                fontWeight: 400,
                fontSize: 12,
                color: "var(--color-text-muted)",
              }}
            >
              New to Meridian?
            </span>
            <div style={{ flex: 1, height: 1, backgroundColor: "var(--color-border)" }} />
          </div>

          <Link
            href="/signup"
            style={{
              display: "block",
              width: "100%",
              padding: "13px 0",
              backgroundColor: "transparent",
              color: "var(--color-text-primary)",
              borderTop: "1px solid var(--color-border)",
              borderBottom: "1px solid var(--color-border)",
              borderLeft: "1px solid var(--color-border)",
              borderRight: "1px solid var(--color-border)",
              borderRadius: "var(--radius)",
              fontFamily: FONT,
              fontWeight: 500,
              fontSize: 14,
              textAlign: "center",
              textDecoration: "none",
              transition: "background-color 150ms ease-out",
              boxSizing: "border-box",
            }}
            onMouseEnter={(e) => {
              (e.currentTarget as HTMLAnchorElement).style.backgroundColor = "var(--color-surface-hover)";
            }}
            onMouseLeave={(e) => {
              (e.currentTarget as HTMLAnchorElement).style.backgroundColor = "transparent";
            }}
          >
            Create an account
          </Link>

          {/* Footer note */}
          <p
            style={{
              marginTop: 32,
              fontFamily: MONO,
              fontWeight: 400,
              fontSize: 11,
              color: "var(--color-text-muted)",
              letterSpacing: "0.04em",
              lineHeight: 1.6,
              opacity: mounted ? 1 : 0,
              transition: "opacity 400ms ease-out",
            }}
          >
            Protected by enterprise SSO and MFA.
            <br />
            Access is logged and audited.
          </p>
        </div>
      </div>
    </div>
  );
}
