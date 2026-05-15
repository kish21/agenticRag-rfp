"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { COMPANY, FONT, MONO, PALETTE, PALETTE_LIGHT, TOKENS } from "@/lib/theme";
import { useThemeContext } from "@/components/ThemeProvider";

const API = process.env.NEXT_PUBLIC_API_URL ?? "";

export default function SignupPage() {
  const router             = useRouter();
  const { isDark } = useThemeContext();
  const P          = isDark ? PALETTE : PALETTE_LIGHT;

  const [step,     setStep]     = useState<1 | 2>(1);
  const [orgName,  setOrgName]  = useState("");
  const [industry, setIndustry] = useState("Financial Services");
  const [email,    setEmail]    = useState("");
  const [password, setPassword] = useState("");
  const [confirm,  setConfirm]  = useState("");
  const [error,    setError]    = useState("");
  const [loading,  setLoading]  = useState(false);

  const BG = "var(--bg-gradient)";

  const inputStyle: React.CSSProperties = {
    width: "100%", padding: "10px 12px",
    background: "var(--color-background)",
    border: `1px solid ${P.border.mid}`,
    borderRadius: 8,
    color: P.text.primary,
    fontFamily: MONO, fontSize: 13,
    outline: "none", boxSizing: "border-box",
  };

  const labelStyle: React.CSSProperties = {
    fontSize: 11, fontWeight: 600, color: P.text.secondary,
    fontFamily: FONT, marginBottom: 5, display: "block", letterSpacing: "0.05em",
  };

  function nextStep(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    if (!orgName.trim()) { setError("Organisation name is required"); return; }
    setStep(2);
  }

  async function handleSignup(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    if (password !== confirm) { setError("Passwords do not match"); return; }
    if (password.length < 8)  { setError("Password must be at least 8 characters"); return; }

    setLoading(true);
    try {
      const res = await fetch(`${API}/api/v1/auth/signup`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ org_name: orgName, industry, email, password }),
      });
      const data = await res.json();
      if (!res.ok) {
        setError(data.detail ?? "Signup failed");
        return;
      }
      localStorage.setItem("access_token", data.access_token);
      router.push("/");
    } catch {
      setError("Could not reach the server. Is the backend running?");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div style={{ minHeight: "100vh", background: BG, fontFamily: FONT, display: "flex", flexDirection: "column" }}>
      {/* Minimal top bar */}
      <div style={{
        height: 52, display: "flex", alignItems: "center", justifyContent: "space-between",
        padding: "0 24px", borderBottom: `1px solid ${P.border.dim}`,
        background: "var(--topbar-bg)", backdropFilter: "blur(12px)",
      }}>
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <div style={{
            width: 28, height: 28, borderRadius: 8,
            background: `linear-gradient(135deg, ${COMPANY.logoGradient.from}, ${COMPANY.logoGradient.to})`,
            display: "flex", alignItems: "center", justifyContent: "center",
            fontSize: 14, fontWeight: 800, color: "#fff",
          }}>M</div>
          <span style={{ fontSize: 14, fontWeight: 700, color: P.text.primary }}>{COMPANY.platformName}</span>
        </div>
        <span style={{ fontSize: 11, color: "var(--color-text-muted)", fontFamily: FONT }}>
          {COMPANY.platformName}
        </span>
      </div>

      {/* Card */}
      <div style={{ flex: 1, display: "flex", alignItems: "center", justifyContent: "center", padding: 24 }}>
        <div style={{
          width: "100%", maxWidth: 420,
          background: P.bg.surface, borderRadius: TOKENS.radius.card,
          border: `1px solid ${P.border.mid}`,
          padding: "32px 28px",
        }}>
          {/* Step indicator */}
          <div style={{ display: "flex", gap: 6, marginBottom: 24 }}>
            {[1, 2].map(n => (
              <div key={n} style={{
                flex: 1, height: 3, borderRadius: 2,
                background: n <= step ? "var(--color-accent)" : "var(--color-border)",
                transition: "background 300ms",
              }} />
            ))}
          </div>

          <h1 style={{ fontSize: 20, fontWeight: 700, color: P.text.primary, margin: "0 0 4px", fontFamily: FONT }}>
            {step === 1 ? "Create your organisation" : "Set up your account"}
          </h1>
          <p style={{ fontSize: 13, color: P.text.muted, margin: "0 0 24px", fontFamily: FONT }}>
            {step === 1
              ? "You'll be the owner and can invite your team after setup."
              : "Create your login credentials for this organisation."}
          </p>

          {step === 1 ? (
            <form onSubmit={nextStep} style={{ display: "flex", flexDirection: "column", gap: 16 }}>
              <div>
                <label style={labelStyle}>ORGANISATION NAME</label>
                <input
                  suppressHydrationWarning
                  type="text" required autoFocus
                  value={orgName} onChange={e => setOrgName(e.target.value)}
                  placeholder="Acme Financial Group"
                  style={inputStyle}
                />
              </div>

              <div>
                <label style={labelStyle}>INDUSTRY</label>
                <select
                  value={industry} onChange={e => setIndustry(e.target.value)}
                  style={{ ...inputStyle, cursor: "pointer" }}
                >
                  {["Financial Services","Healthcare","Manufacturing","Technology","Government","Legal","Retail","Other"].map(i => (
                    <option key={i} value={i}>{i}</option>
                  ))}
                </select>
              </div>

              {error && (
                <div style={{
                  background: "var(--color-error)14", border: "1px solid var(--color-error)",
                  borderRadius: 6, padding: "10px 12px",
                  fontSize: 12, color: "var(--color-error)", fontFamily: FONT,
                }}>{error}</div>
              )}

              <button type="submit" style={{
                background: "var(--color-accent)", color: "var(--color-accent-foreground)", border: "none",
                borderRadius: TOKENS.radius.btn, padding: "11px",
                fontSize: 14, fontFamily: FONT, fontWeight: 700,
                cursor: "pointer", width: "100%", marginTop: 4,
              }}>
                Continue →
              </button>
            </form>
          ) : (
            <form onSubmit={handleSignup} style={{ display: "flex", flexDirection: "column", gap: 16 }}>
              <div style={{
                background: "var(--color-accent)18",
                border: "1px solid var(--color-accent)40",
                borderRadius: 6, padding: "8px 12px",
                fontSize: 12, color: "var(--color-accent)", fontFamily: FONT,
              }}>
                Organisation: <strong>{orgName}</strong>
                <span
                  onClick={() => setStep(1)}
                  style={{ float: "right", cursor: "pointer", opacity: 0.7 }}
                >← change</span>
              </div>

              <div>
                <label style={labelStyle}>EMAIL</label>
                <input
                  suppressHydrationWarning
                  type="email" required autoFocus
                  value={email} onChange={e => setEmail(e.target.value)}
                  placeholder="you@company.com"
                  style={inputStyle}
                />
              </div>

              <div>
                <label style={labelStyle}>PASSWORD</label>
                <input
                  suppressHydrationWarning
                  type="password" required
                  value={password} onChange={e => setPassword(e.target.value)}
                  placeholder="At least 8 characters"
                  style={inputStyle}
                />
              </div>

              <div>
                <label style={labelStyle}>CONFIRM PASSWORD</label>
                <input
                  suppressHydrationWarning
                  type="password" required
                  value={confirm} onChange={e => setConfirm(e.target.value)}
                  placeholder="••••••••"
                  style={inputStyle}
                />
              </div>

              {error && (
                <div style={{
                  background: "var(--color-error)14", border: "1px solid var(--color-error)",
                  borderRadius: 6, padding: "10px 12px",
                  fontSize: 12, color: "var(--color-error)", fontFamily: FONT,
                }}>{error}</div>
              )}

              <button type="submit" disabled={loading} style={{
                background: loading ? "var(--color-accent-hover)" : "var(--color-accent)",
                color: "var(--color-accent-foreground)", border: "none",
                borderRadius: TOKENS.radius.btn, padding: "11px",
                fontSize: 14, fontFamily: FONT, fontWeight: 700,
                cursor: loading ? "not-allowed" : "pointer", width: "100%", marginTop: 4,
              }}>
                {loading ? "Creating account…" : "Create account →"}
              </button>
            </form>
          )}

          <div style={{ textAlign: "center", marginTop: 20, fontSize: 12, color: P.text.muted, fontFamily: FONT }}>
            Already have an account?{" "}
            <span
              onClick={() => router.push("/login")}
              style={{ color: "var(--color-accent)", cursor: "pointer", fontWeight: 600 }}
            >
              Sign in
            </span>
          </div>
        </div>
      </div>
    </div>
  );
}
