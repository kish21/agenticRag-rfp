"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { FONT, DISPLAY, MONO } from "@/lib/theme";
import { useThemeContext } from "@/components/layout/ThemeProvider";
import { ThemePicker } from "@/components/layout/ThemePicker";
import { isLoggedIn, getUserInfo, type UserInfo } from "@/lib/api";
import { useBreakpoint } from "@/lib/hooks";

export default function SettingsPage() {
  const router = useRouter();
  const { isDark } = useThemeContext();
  const bp = useBreakpoint();
  const [userInfo, setUserInfo] = useState<UserInfo | null>(null);

  useEffect(() => {
    if (!isLoggedIn()) { router.push("/login"); return; }
    setUserInfo(getUserInfo());
  }, [router]);

  return (
    <div style={{
      minHeight: "100vh",
      background: "var(--bg-gradient)",
      padding: bp === "mobile" ? "24px 20px" : bp === "tablet" ? "32px 24px" : "48px 32px",
    }}>
      <div style={{ maxWidth: 640 }}>

        {/* Header */}
        <div style={{ marginBottom: 40 }}>
          <button
            type="button"
            onClick={() => router.back()}
            style={{
              background: "none", border: "none", cursor: "pointer",
              fontFamily: FONT, fontSize: 13, color: "var(--color-text-muted)",
              padding: 0, marginBottom: 24,
              transition: "color 150ms ease-out",
            }}
            onMouseEnter={e => { e.currentTarget.style.color = "var(--color-text-primary)"; }}
            onMouseLeave={e => { e.currentTarget.style.color = "var(--color-text-muted)"; }}
          >
            ← Back
          </button>
          <h1 style={{
            fontFamily: DISPLAY, fontWeight: 800, fontSize: 32,
            letterSpacing: "-0.03em", lineHeight: 1.0,
            color: "var(--color-text-primary)", marginBottom: 8,
          }}>
            My Settings
          </h1>
          <p style={{
            fontFamily: FONT, fontSize: 14, fontWeight: 400,
            color: "var(--color-text-secondary)", lineHeight: 1.65,
          }}>
            Manage your account preferences.
          </p>
        </div>

        {/* Account */}
        <section style={{ marginBottom: 32 }}>
          <p style={{
            fontFamily: FONT, fontWeight: 600, fontSize: 10,
            letterSpacing: "0.1em", textTransform: "uppercase",
            color: "var(--color-text-muted)", marginBottom: 12,
          }}>Account</p>
          <div style={{
            backgroundColor: "var(--color-surface)",
            borderTop: "1px solid var(--color-border)",
            borderBottom: "1px solid var(--color-border)",
            borderLeft: "1px solid var(--color-border)",
            borderRight: "1px solid var(--color-border)",
            borderRadius: "var(--radius)",
            boxShadow: "var(--shadow-sm)",
            padding: "16px 20px",
          }}>
            {userInfo ? (
              <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                  <span style={{ fontFamily: FONT, fontSize: 13, color: "var(--color-text-secondary)" }}>Email</span>
                  <span style={{ fontFamily: MONO, fontSize: 12, color: "var(--color-text-primary)" }}>{userInfo.email}</span>
                </div>
                <div style={{ height: 1, backgroundColor: "var(--color-border)" }} />
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                  <span style={{ fontFamily: FONT, fontSize: 13, color: "var(--color-text-secondary)" }}>Role</span>
                  <span style={{ fontFamily: MONO, fontSize: 12, color: "var(--color-text-primary)" }}>{userInfo.role}</span>
                </div>
              </div>
            ) : (
              <p style={{ fontFamily: FONT, fontSize: 13, color: "var(--color-text-muted)" }}>Loading…</p>
            )}
          </div>
        </section>

        {/* Theme */}
        <section style={{ marginBottom: 32 }}>
          <p style={{
            fontFamily: FONT, fontWeight: 600, fontSize: 10,
            letterSpacing: "0.1em", textTransform: "uppercase",
            color: "var(--color-text-muted)", marginBottom: 12,
          }}>Theme</p>
          <div style={{
            backgroundColor: "var(--color-surface)",
            borderTop: "1px solid var(--color-border)",
            borderBottom: "1px solid var(--color-border)",
            borderLeft: "1px solid var(--color-border)",
            borderRight: "1px solid var(--color-border)",
            borderRadius: "var(--radius)",
            boxShadow: "var(--shadow-sm)",
            padding: "16px 20px",
          }}>
            <ThemePicker />
          </div>
        </section>

      </div>
    </div>
  );
}
