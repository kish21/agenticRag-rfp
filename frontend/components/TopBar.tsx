"use client";

import Link from "next/link";
import { COMPANY, FONT, PALETTE, PALETTE_LIGHT, TOKENS, TOPBAR_BG, TOPBAR_BG_LIGHT } from "@/lib/theme";

export interface Crumb { label: string; href?: string }

interface TopBarProps {
  isDark:   boolean;
  onToggle: () => void;
  crumbs?:  Crumb[];
  right?:   React.ReactNode;
}

export function TopBar({ isDark, onToggle, crumbs, right }: TopBarProps) {
  const P      = isDark ? PALETTE : PALETTE_LIGHT;
  const bg     = isDark ? TOPBAR_BG : TOPBAR_BG_LIGHT;
  const border = isDark ? "rgba(255,255,255,0.06)" : "rgba(0,0,0,0.07)";

  return (
    <header style={{
      position: "sticky", top: 0, zIndex: 30,
      background: bg, backdropFilter: "blur(14px)",
      borderBottom: `1px solid ${border}`,
      height: TOKENS.topbar.height,
      display: "flex", alignItems: "center", padding: "0 28px", gap: 10,
    }}>
      {/* Logo */}
      <Link href="/" style={{ display: "flex", alignItems: "center", gap: 9, textDecoration: "none", flexShrink: 0 }}>
        <div style={{
          width: 26, height: 26, borderRadius: 7, flexShrink: 0,
          background: "linear-gradient(135deg, #00D4AA, #7C3AED)",
          display: "flex", alignItems: "center", justifyContent: "center",
        }}>
          <svg width="12" height="12" viewBox="0 0 12 12" fill="none">
            <circle cx="6" cy="6" r="2.2" fill="white" opacity="0.95" />
            <circle cx="6" cy="6" r="5" stroke="white" strokeWidth="0.85" opacity="0.35" />
          </svg>
        </div>
        <span style={{ fontSize: 13, fontWeight: 600, color: P.text.primary, fontFamily: FONT }}>
          {COMPANY.platformName}
        </span>
      </Link>

      {/* Breadcrumbs */}
      {crumbs && crumbs.length > 0 && (
        <>
          <span style={{ color: P.text.muted, fontSize: 13, flexShrink: 0 }}>·</span>
          <div style={{ display: "flex", alignItems: "center", gap: 4 }}>
            {crumbs.map((c, i) => (
              <span key={i} style={{ display: "flex", alignItems: "center", gap: 4 }}>
                {i > 0 && <span style={{ color: P.text.muted, fontSize: 11, opacity: 0.6 }}>›</span>}
                {c.href ? (
                  <Link href={c.href} style={{ fontSize: 12, color: P.text.secondary, textDecoration: "none", fontFamily: FONT }}>
                    {c.label}
                  </Link>
                ) : (
                  <span style={{ fontSize: 12, color: P.text.primary, fontFamily: FONT, fontWeight: 500 }}>
                    {c.label}
                  </span>
                )}
              </span>
            ))}
          </div>
        </>
      )}

      <div style={{ flex: 1 }} />

      {right}

      <button onClick={onToggle} style={{
        background: isDark ? "rgba(255,255,255,0.06)" : "rgba(0,0,0,0.05)",
        border: `1px solid ${border}`, borderRadius: 7,
        padding: "5px 11px", fontSize: 11, fontFamily: FONT,
        color: P.text.secondary, cursor: "pointer", flexShrink: 0,
      }}>
        {isDark ? "☀ Light" : "☾ Dark"}
      </button>
    </header>
  );
}

// ── Theme hook — localStorage-backed, consistent key across all pages ──────────

import { useState, useEffect } from "react";

export function useTheme() {
  const [isDark, setIsDark] = useState(true);
  useEffect(() => {
    const saved = localStorage.getItem("meridian-theme");
    if (saved !== null) setIsDark(saved === "dark");
  }, []);
  const toggle = () => setIsDark(d => {
    const next = !d;
    localStorage.setItem("meridian-theme", next ? "dark" : "light");
    return next;
  });
  return { isDark, toggle };
}
