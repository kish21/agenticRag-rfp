"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { COMPANY, FONT, MONO, PALETTE, PALETTE_LIGHT, TOKENS } from "@/lib/theme";
import { useTheme } from "@/components/TopBar";

const API = process.env.NEXT_PUBLIC_API_URL ?? "";

export default function LoginPage() {
  const router              = useRouter();
  const { isDark, toggle }  = useTheme();
  const P                   = isDark ? PALETTE : PALETTE_LIGHT;

  const [email,    setEmail]    = useState("");
  const [password, setPassword] = useState("");
  const [error,    setError]    = useState("");
  const [loading,  setLoading]  = useState(false);

  const BG = isDark
    ? "radial-gradient(ellipse 90% 60% at 50% 0%, #111828 0%, #090C14 65%)"
    : "linear-gradient(160deg, #ede9e0 0%, #fafaf9 55%)";

  async function handleLogin(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      const res = await fetch(`${API}/api/v1/auth/token`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, password }),
      });
      const data = await res.json();
      if (!res.ok) {
        setError(data.detail ?? "Login failed");
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

  const inputStyle: React.CSSProperties = {
    width: "100%", padding: "10px 12px",
    background: isDark ? "#0D1117" : "#FFFFFF",
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

  return (
    <div style={{ minHeight: "100vh", background: BG, fontFamily: FONT, display: "flex", flexDirection: "column" }}>
      {/* Minimal top bar */}
      <div style={{
        height: 52, display: "flex", alignItems: "center", justifyContent: "space-between",
        padding: "0 24px", borderBottom: `1px solid ${P.border.dim}`,
        background: isDark ? "#090C1480" : "#FAFAF980", backdropFilter: "blur(12px)",
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
        <button onClick={toggle} style={{
          background: "none", border: `1px solid ${P.border.dim}`, borderRadius: 6,
          padding: "4px 10px", fontSize: 11, color: P.text.muted, cursor: "pointer",
          fontFamily: FONT,
        }}>{isDark ? "Light" : "Dark"}</button>
      </div>

      {/* Card */}
      <div style={{ flex: 1, display: "flex", alignItems: "center", justifyContent: "center", padding: 24 }}>
        <div style={{
          width: "100%", maxWidth: 400,
          background: P.bg.surface, borderRadius: TOKENS.radius.card,
          border: `1px solid ${P.border.mid}`,
          padding: "32px 28px",
        }}>
          <h1 style={{ fontSize: 20, fontWeight: 700, color: P.text.primary, margin: "0 0 4px", fontFamily: FONT }}>
            Sign in
          </h1>
          <p style={{ fontSize: 13, color: P.text.muted, margin: "0 0 24px", fontFamily: FONT }}>
            Sign in to your {COMPANY.shortName} account.
          </p>

          <form onSubmit={handleLogin} suppressHydrationWarning style={{ display: "flex", flexDirection: "column", gap: 16 }}>
            <div>
              <label style={labelStyle}>EMAIL</label>
              <input
                type="email" required autoFocus
                value={email} onChange={e => setEmail(e.target.value)}
                placeholder="you@company.com"
                style={inputStyle}
              />
            </div>

            <div>
              <label style={labelStyle}>PASSWORD</label>
              <input
                type="password" required
                value={password} onChange={e => setPassword(e.target.value)}
                placeholder="••••••••"
                style={inputStyle}
              />
            </div>

            {error && (
              <div style={{
                background: "#EF444414", border: "1px solid #EF4444",
                borderRadius: 6, padding: "10px 12px",
                fontSize: 12, color: "#EF4444", fontFamily: FONT,
              }}>{error}</div>
            )}

            <button type="submit" disabled={loading} style={{
              background: loading ? "#00D4AA80" : "#00D4AA",
              color: "#071510", border: "none",
              borderRadius: TOKENS.radius.btn, padding: "11px",
              fontSize: 14, fontFamily: FONT, fontWeight: 700,
              cursor: loading ? "not-allowed" : "pointer", width: "100%",
              marginTop: 4,
            }}>
              {loading ? "Signing in…" : "Sign in →"}
            </button>
          </form>

          <div style={{ textAlign: "center", marginTop: 20, fontSize: 12, color: P.text.muted, fontFamily: FONT }}>
            New organisation?{" "}
            <span
              onClick={() => router.push("/signup")}
              style={{ color: "#00D4AA", cursor: "pointer", fontWeight: 600 }}
            >
              Create an account
            </span>
          </div>
        </div>
      </div>
    </div>
  );
}
