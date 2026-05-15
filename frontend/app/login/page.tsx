"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { COMPANY, FONT, MONO, TOKENS } from "@/lib/theme";
import { ThemePicker } from "@/components/ThemePicker";

const API = process.env.NEXT_PUBLIC_API_URL ?? "";

export default function LoginPage() {
  const router = useRouter();

  const [email,    setEmail]    = useState("");
  const [password, setPassword] = useState("");
  const [error,    setError]    = useState("");
  const [loading,  setLoading]  = useState(false);

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
      if (!res.ok) { setError(data.detail ?? "Login failed"); return; }
      localStorage.setItem("access_token", data.access_token);
      router.push("/");
    } catch {
      setError("Could not reach the server. Is the backend running?");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div style={{ minHeight: "100vh", background: "var(--bg-gradient)", fontFamily: FONT, display: "flex", flexDirection: "column" }}>

      {/* Top bar */}
      <div style={{
        height: 52, display: "flex", alignItems: "center", justifyContent: "space-between",
        padding: "0 24px",
        borderBottom: "1px solid var(--topbar-border)",
        background: "var(--topbar-bg)",
        backdropFilter: "blur(12px)",
        WebkitBackdropFilter: "blur(12px)",
      }}>
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <div style={{
            width: 28, height: 28, borderRadius: 8,
            background: `linear-gradient(135deg, ${COMPANY.logoGradient.from}, ${COMPANY.logoGradient.to})`,
            display: "flex", alignItems: "center", justifyContent: "center",
            fontSize: 13, fontWeight: 800, color: "#fff", fontFamily: FONT,
          }}>M</div>
          <span style={{ fontSize: 14, fontWeight: 700, color: "var(--color-text-primary)", fontFamily: FONT }}>
            {COMPANY.platformName}
          </span>
        </div>
        <ThemePicker />
      </div>

      {/* Centred card */}
      <div style={{ flex: 1, display: "flex", alignItems: "center", justifyContent: "center", padding: 24 }}>
        <div style={{
          width: "100%", maxWidth: 400,
          background: "var(--color-surface)",
          borderRadius: TOKENS.radius.card,
          border: "1px solid var(--color-border-strong)",
          boxShadow: "var(--shadow-md)",
          padding: "36px 32px",
        }}>

          {/* Heading */}
          <h1 style={{ fontSize: 22, fontWeight: 800, color: "var(--color-text-primary)", margin: "0 0 4px", fontFamily: FONT, letterSpacing: "-0.02em" }}>
            Sign in
          </h1>
          <p style={{ fontSize: 13, color: "var(--color-text-muted)", margin: "0 0 28px", fontFamily: FONT, lineHeight: 1.5 }}>
            Sign in to your {COMPANY.shortName} account.
          </p>

          <form onSubmit={handleLogin} suppressHydrationWarning style={{ display: "flex", flexDirection: "column", gap: 16 }}>

            <div>
              <label style={{ fontSize: 11, fontWeight: 600, color: "var(--color-text-muted)", fontFamily: FONT, marginBottom: 6, display: "block", letterSpacing: "0.06em", textTransform: "uppercase" }}>
                Email
              </label>
              <input
                suppressHydrationWarning
                type="email" required autoFocus
                value={email} onChange={e => setEmail(e.target.value)}
                placeholder="you@company.com"
                style={{
                  width: "100%", padding: "10px 12px",
                  background: "var(--color-background)",
                  border: "1px solid var(--color-border-strong)",
                  borderRadius: 8,
                  color: "var(--color-text-primary)",
                  fontFamily: MONO, fontSize: 13,
                  outline: "none", boxSizing: "border-box",
                  transition: "border-color var(--transition)",
                }}
              />
            </div>

            <div>
              <label style={{ fontSize: 11, fontWeight: 600, color: "var(--color-text-muted)", fontFamily: FONT, marginBottom: 6, display: "block", letterSpacing: "0.06em", textTransform: "uppercase" }}>
                Password
              </label>
              <input
                suppressHydrationWarning
                type="password" required
                value={password} onChange={e => setPassword(e.target.value)}
                placeholder="••••••••"
                style={{
                  width: "100%", padding: "10px 12px",
                  background: "var(--color-background)",
                  border: "1px solid var(--color-border-strong)",
                  borderRadius: 8,
                  color: "var(--color-text-primary)",
                  fontFamily: MONO, fontSize: 13,
                  outline: "none", boxSizing: "border-box",
                  transition: "border-color var(--transition)",
                }}
              />
            </div>

            {error && (
              <div style={{
                background: "var(--color-error)14",
                border: "1px solid var(--color-error)",
                borderRadius: 6, padding: "10px 12px",
                fontSize: 12, color: "var(--color-error)", fontFamily: FONT,
              }}>
                {error}
              </div>
            )}

            <button
              type="submit"
              disabled={loading}
              style={{
                background: loading ? "var(--color-accent-hover)" : "var(--color-accent)",
                color: "var(--color-accent-foreground)",
                border: "none",
                borderRadius: TOKENS.radius.btn,
                padding: "12px",
                fontSize: 14, fontFamily: FONT, fontWeight: 700,
                cursor: loading ? "not-allowed" : "pointer",
                width: "100%", marginTop: 4,
                transition: "background var(--transition)",
                letterSpacing: "-0.01em",
              }}
            >
              {loading ? "Signing in…" : "Sign in →"}
            </button>
          </form>

          <div style={{ textAlign: "center", marginTop: 24, fontSize: 12, color: "var(--color-text-muted)", fontFamily: FONT }}>
            New organisation?{" "}
            <span
              onClick={() => router.push("/signup")}
              style={{ color: "var(--color-accent)", cursor: "pointer", fontWeight: 600 }}
            >
              Create an account
            </span>
          </div>
        </div>
      </div>

      {/* Footer */}
      <div style={{ textAlign: "center", padding: "16px 24px", fontSize: 11, color: "var(--color-text-muted)", fontFamily: FONT }}>
        {COMPANY.name} · Enterprise AI Platform
      </div>
    </div>
  );
}
