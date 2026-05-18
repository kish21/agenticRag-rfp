"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { FONT, DISPLAY, MONO } from "@/lib/theme";
import { useThemeContext } from "@/components/ThemeProvider";

const INDUSTRIES = [
  "Financial Services",
  "Banking",
  "Insurance",
  "Asset Management",
  "Healthcare",
  "Technology",
  "Government",
  "Manufacturing",
  "Energy & Utilities",
  "Professional Services",
  "Other",
];

type Step = 1 | 2;

export default function SignupPage() {
  const router = useRouter();
  const { isDark } = useThemeContext();

  const [step, setStep] = useState<Step>(1);
  const [orgName, setOrgName] = useState("");
  const [industry, setIndustry] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [focusedField, setFocusedField] = useState<string | null>(null);

  function handleStep1(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    if (!orgName.trim()) { setError("Organisation name is required."); return; }
    if (!industry) { setError("Please select your industry."); return; }
    setStep(2);
  }

  async function handleStep2(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    if (password.length < 8) { setError("Password must be at least 8 characters."); return; }
    if (password !== confirmPassword) { setError("Passwords do not match."); return; }

    setLoading(true);
    try {
      const res = await fetch("/api/v1/auth/signup", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ org_name: orgName, industry, email, password }),
      });

      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        setError(data.detail ?? "Registration failed. Please try again.");
        return;
      }

      router.push("/login?registered=1");
    } catch {
      setError("Unable to reach the server. Please try again.");
    } finally {
      setLoading(false);
    }
  }

  const inputStyle = (field: string): React.CSSProperties => ({
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

  const labelStyle = (field: string): React.CSSProperties => ({
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

  return (
    <div style={{ minHeight: "100vh", display: "flex", fontFamily: FONT }}>

      {/* ── Left: Brand panel — same as Login for continuity */}
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

        {/* Wordmark */}
        <div style={{ position: "relative", zIndex: 1 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
            <div
              style={{
                width: 28, height: 28,
                border: "1.5px solid rgba(99,102,241,0.7)",
                borderRadius: 5,
                display: "flex", alignItems: "center", justifyContent: "center",
              }}
            >
              <div style={{ width: 10, height: 10, backgroundColor: "rgba(99,102,241,0.9)", borderRadius: 2 }} />
            </div>
            <span
              style={{
                fontFamily: DISPLAY, fontWeight: 700, fontSize: 14,
                letterSpacing: "0.12em", textTransform: "uppercase",
                color: "rgba(255,255,255,0.55)",
              }}
            >
              Meridian AI
            </span>
          </div>
        </div>

        {/* Hero text */}
        <div style={{ position: "relative", zIndex: 1, flex: 1, display: "flex", flexDirection: "column", justifyContent: "center" }}>
          <div style={{ overflow: "hidden", marginLeft: -4 }}>
            <div
              style={{
                fontFamily: DISPLAY, fontWeight: 800,
                fontSize: "clamp(64px, 9vw, 108px)",
                lineHeight: 0.9, letterSpacing: "-0.04em",
                color: "rgba(255,255,255,0.92)", whiteSpace: "nowrap",
              }}
            >
              Meridian
            </div>
          </div>
          <div style={{ width: 48, height: 2, backgroundColor: "rgba(99,102,241,0.8)", marginTop: 24, marginBottom: 20 }} />
          <p
            style={{
              fontFamily: FONT, fontWeight: 400, fontSize: 14,
              lineHeight: 1.7, color: "rgba(255,255,255,0.4)",
              maxWidth: 260, letterSpacing: "0.01em",
            }}
          >
            Enterprise vendor governance.
            <br />
            AI-evaluated. Audit-ready.
          </p>
        </div>

        <div style={{ position: "relative", zIndex: 1 }}>
          <p style={{ fontFamily: MONO, fontWeight: 400, fontSize: 10, letterSpacing: "0.08em", color: "rgba(255,255,255,0.2)", textTransform: "uppercase" }}>
            Meridian Financial Services
            <br />
            SOC 2 · ISO 27001 · GDPR
          </p>
        </div>
      </div>

      {/* ── Right: Form panel */}
      <div
        style={{
          flex: 1, display: "flex", flexDirection: "column",
          justifyContent: "center", alignItems: "center",
          background: "var(--bg-gradient)", padding: "48px 32px",
        }}
      >
        <div style={{ width: "100%", maxWidth: 380 }}>

          {/* Step indicator — two thin bars, not numbered circles */}
          <div style={{ display: "flex", gap: 6, marginBottom: 32 }}>
            {([1, 2] as Step[]).map((s) => (
              <div
                key={s}
                style={{
                  flex: 1, height: 2,
                  backgroundColor: s <= step ? "var(--color-accent)" : "var(--color-border)",
                  borderRadius: 2,
                  transition: "background-color 300ms ease-out",
                }}
              />
            ))}
          </div>

          {/* Section label */}
          <p
            style={{
              fontFamily: FONT, fontWeight: 600, fontSize: 11,
              letterSpacing: "0.1em", textTransform: "uppercase",
              color: "var(--color-text-muted)", marginBottom: 12,
            }}
          >
            {step === 1 ? "Step 1 of 2" : "Step 2 of 2"}
          </p>

          <h1
            style={{
              fontFamily: DISPLAY, fontWeight: 800, fontSize: 28,
              lineHeight: 1.1, letterSpacing: "-0.03em",
              color: "var(--color-text-primary)", marginBottom: 8,
            }}
          >
            {step === 1 ? "Your organisation" : "Your account"}
          </h1>
          <p
            style={{
              fontFamily: FONT, fontWeight: 400, fontSize: 14,
              color: "var(--color-text-secondary)", marginBottom: 36, lineHeight: 1.6,
            }}
          >
            {step === 1
              ? "Tell us about your organisation so we can configure your workspace."
              : "Create your administrator account for this workspace."}
          </p>

          {/* ── Step 1: Organisation details */}
          {step === 1 && (
            <form onSubmit={handleStep1}>
              <div style={{ marginBottom: 32 }}>
                <label style={labelStyle("orgName")} htmlFor="orgName">Organisation name</label>
                <input
                  id="orgName"
                  type="text"
                  required
                  value={orgName}
                  onChange={(e) => setOrgName(e.target.value)}
                  onFocus={() => setFocusedField("orgName")}
                  onBlur={() => setFocusedField(null)}
                  suppressHydrationWarning
                  style={inputStyle("orgName")}
                  placeholder="Acme Financial Ltd"
                />
              </div>

              <div style={{ marginBottom: 40 }}>
                <label style={labelStyle("industry")} htmlFor="industry">Industry</label>
                <select
                  id="industry"
                  required
                  value={industry}
                  onChange={(e) => setIndustry(e.target.value)}
                  onFocus={() => setFocusedField("industry")}
                  onBlur={() => setFocusedField(null)}
                  style={{
                    ...inputStyle("industry"),
                    cursor: "pointer",
                    appearance: "none",
                    paddingRight: 24,
                    color: industry ? "var(--color-text-primary)" : "var(--color-text-muted)",
                  }}
                >
                  <option value="" disabled>Select industry…</option>
                  {INDUSTRIES.map((ind) => (
                    <option key={ind} value={ind} style={{ backgroundColor: "var(--color-surface)", color: "var(--color-text-primary)" }}>
                      {ind}
                    </option>
                  ))}
                </select>
              </div>

              {error && <ErrorBanner message={error} />}

              <button
                type="submit"
                onMouseEnter={(e) => { (e.currentTarget).style.opacity = "0.88"; (e.currentTarget).style.transform = "translateY(-1px)"; }}
                onMouseLeave={(e) => { (e.currentTarget).style.opacity = "1"; (e.currentTarget).style.transform = "translateY(0)"; }}
                onMouseDown={(e) => { (e.currentTarget).style.transform = "translateY(0) scale(0.98)"; }}
                onMouseUp={(e) => { (e.currentTarget).style.transform = "translateY(-1px)"; }}
                style={submitStyle}
              >
                Continue →
              </button>
            </form>
          )}

          {/* ── Step 2: Account credentials */}
          {step === 2 && (
            <form onSubmit={handleStep2}>
              <div style={{ marginBottom: 32 }}>
                <label style={labelStyle("email")} htmlFor="email">Work email</label>
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
                  style={inputStyle("email")}
                  placeholder="you@company.com"
                />
              </div>

              <div style={{ marginBottom: 32 }}>
                <label style={labelStyle("password")} htmlFor="password">Password</label>
                <input
                  id="password"
                  type="password"
                  autoComplete="new-password"
                  required
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  onFocus={() => setFocusedField("password")}
                  onBlur={() => setFocusedField(null)}
                  suppressHydrationWarning
                  style={inputStyle("password")}
                  placeholder="Min. 8 characters"
                />
              </div>

              <div style={{ marginBottom: 40 }}>
                <label style={labelStyle("confirm")} htmlFor="confirm">Confirm password</label>
                <input
                  id="confirm"
                  type="password"
                  autoComplete="new-password"
                  required
                  value={confirmPassword}
                  onChange={(e) => setConfirmPassword(e.target.value)}
                  onFocus={() => setFocusedField("confirm")}
                  onBlur={() => setFocusedField(null)}
                  suppressHydrationWarning
                  style={{
                    ...inputStyle("confirm"),
                    borderBottom: confirmPassword && confirmPassword !== password
                      ? "1.5px solid var(--color-error)"
                      : inputStyle("confirm").borderBottom,
                  }}
                  placeholder="Repeat password"
                />
                {confirmPassword && confirmPassword !== password && (
                  <p style={{ fontFamily: FONT, fontSize: 12, color: "var(--color-error)", marginTop: 6 }}>
                    Passwords do not match
                  </p>
                )}
              </div>

              {error && <ErrorBanner message={error} />}

              <div style={{ display: "flex", gap: 12 }}>
                <button
                  type="button"
                  onClick={() => { setStep(1); setError(""); }}
                  onMouseEnter={(e) => { (e.currentTarget).style.backgroundColor = "var(--color-surface-hover)"; }}
                  onMouseLeave={(e) => { (e.currentTarget).style.backgroundColor = "transparent"; }}
                  style={{
                    flex: "0 0 auto",
                    padding: "14px 20px",
                    backgroundColor: "transparent",
                    color: "var(--color-text-secondary)",
                    borderTop: "1px solid var(--color-border)",
                    borderBottom: "1px solid var(--color-border)",
                    borderLeft: "1px solid var(--color-border)",
                    borderRight: "1px solid var(--color-border)",
                    borderRadius: "var(--radius)",
                    fontFamily: FONT,
                    fontWeight: 500,
                    fontSize: 14,
                    cursor: "pointer",
                    transition: "background-color 150ms ease-out",
                  }}
                >
                  ← Back
                </button>
                <button
                  type="submit"
                  disabled={loading}
                  onMouseEnter={(e) => { if (!loading) { (e.currentTarget).style.opacity = "0.88"; (e.currentTarget).style.transform = "translateY(-1px)"; } }}
                  onMouseLeave={(e) => { (e.currentTarget).style.opacity = "1"; (e.currentTarget).style.transform = "translateY(0)"; }}
                  onMouseDown={(e) => { if (!loading) (e.currentTarget).style.transform = "translateY(0) scale(0.98)"; }}
                  onMouseUp={(e) => { if (!loading) (e.currentTarget).style.transform = "translateY(-1px)"; }}
                  style={{ ...submitStyle, flex: 1, opacity: loading ? 0.6 : 1, cursor: loading ? "not-allowed" : "pointer" }}
                >
                  {loading ? "Creating account…" : "Create account"}
                </button>
              </div>
            </form>
          )}

          {/* Sign in link */}
          <div style={{ display: "flex", alignItems: "center", gap: 12, margin: "28px 0" }}>
            <div style={{ flex: 1, height: 1, backgroundColor: "var(--color-border)" }} />
            <span style={{ fontFamily: FONT, fontWeight: 400, fontSize: 12, color: "var(--color-text-muted)" }}>
              Already have an account?
            </span>
            <div style={{ flex: 1, height: 1, backgroundColor: "var(--color-border)" }} />
          </div>

          <Link
            href="/login"
            style={{
              display: "block", width: "100%", padding: "13px 0",
              backgroundColor: "transparent",
              color: "var(--color-text-primary)",
              borderTop: "1px solid var(--color-border)",
              borderBottom: "1px solid var(--color-border)",
              borderLeft: "1px solid var(--color-border)",
              borderRight: "1px solid var(--color-border)",
              borderRadius: "var(--radius)",
              fontFamily: FONT, fontWeight: 500, fontSize: 14,
              textAlign: "center", textDecoration: "none",
              transition: "background-color 150ms ease-out",
              boxSizing: "border-box",
            }}
            onMouseEnter={(e) => { (e.currentTarget as HTMLAnchorElement).style.backgroundColor = "var(--color-surface-hover)"; }}
            onMouseLeave={(e) => { (e.currentTarget as HTMLAnchorElement).style.backgroundColor = "transparent"; }}
          >
            Sign in instead
          </Link>
        </div>
      </div>
    </div>
  );
}

function ErrorBanner({ message }: { message: string }) {
  return (
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
      {message}
    </div>
  );
}

const submitStyle: React.CSSProperties = {
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
  cursor: "pointer",
  transition: "opacity 150ms ease-out, transform 150ms ease-out",
  boxShadow: "var(--shadow-sm)",
};
