"use client";

import Link from "next/link";
import { useState, useEffect } from "react";
import { COMPANY, TOKENS, type ThemeId, DEFAULT_THEME, THEMES, applyThemeVars } from "@/lib/theme";
import { ThemePicker } from "./ThemePicker";

export interface Crumb { label: string; href?: string }

interface TopBarProps {
  isDark?:   boolean;     // kept for backwards compat — no longer drives colours
  onToggle?: () => void;  // kept for backwards compat — no longer used
  crumbs?:   Crumb[];
  right?:    React.ReactNode;
}

export function TopBar({ crumbs, right }: TopBarProps) {
  return (
    <header style={{
      position: "sticky", top: 0, zIndex: 30,
      background: "var(--topbar-bg)",
      backdropFilter: "blur(14px)",
      WebkitBackdropFilter: "blur(14px)",
      borderBottom: "1px solid var(--topbar-border)",
      height: TOKENS.topbar.height,
      display: "flex", alignItems: "center", padding: "0 28px", gap: 10,
    }}>
      {/* Logo */}
      <Link href="/" style={{ display: "flex", alignItems: "center", gap: 9, textDecoration: "none", flexShrink: 0 }}>
        <div style={{
          width: 26, height: 26, borderRadius: 7, flexShrink: 0,
          background: "linear-gradient(135deg, var(--color-accent), var(--color-info))",
          display: "flex", alignItems: "center", justifyContent: "center",
        }}>
          <svg width="12" height="12" viewBox="0 0 12 12" fill="none">
            <circle cx="6" cy="6" r="2.2" fill="white" opacity="0.95" />
            <circle cx="6" cy="6" r="5" stroke="white" strokeWidth="0.85" opacity="0.35" />
          </svg>
        </div>
        <span style={{
          fontSize: 13, fontWeight: 600,
          color: "var(--color-text-primary)",
          fontFamily: "var(--font-sans)",
        }}>
          {COMPANY.platformName}
        </span>
      </Link>

      {/* Breadcrumbs */}
      {crumbs && crumbs.length > 0 && (
        <>
          <span style={{ color: "var(--color-text-muted)", fontSize: 13, flexShrink: 0 }}>·</span>
          <div style={{ display: "flex", alignItems: "center", gap: 4 }}>
            {crumbs.map((c, i) => (
              <span key={i} style={{ display: "flex", alignItems: "center", gap: 4 }}>
                {i > 0 && <span style={{ color: "var(--color-text-muted)", fontSize: 11, opacity: 0.6 }}>›</span>}
                {c.href ? (
                  <Link href={c.href} style={{
                    fontSize: 12,
                    color: "var(--color-text-secondary)",
                    textDecoration: "none",
                    fontFamily: "var(--font-sans)",
                  }}>
                    {c.label}
                  </Link>
                ) : (
                  <span style={{
                    fontSize: 12,
                    color: "var(--color-text-primary)",
                    fontFamily: "var(--font-sans)",
                    fontWeight: 500,
                  }}>
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

      <ThemePicker />
    </header>
  );
}

// ── Theme hook — backwards-compatible, now drives CSS variables ───────────────

const STORAGE_KEY = "meridian-theme-v2";

export function useTheme() {
  const [themeId, setThemeId] = useState<ThemeId>(DEFAULT_THEME);
  const [isDark, setIsDark] = useState(THEMES[DEFAULT_THEME].isDark);

  useEffect(() => {
    const stored = localStorage.getItem(STORAGE_KEY) as ThemeId | null;
    const id = stored && stored in THEMES ? stored : DEFAULT_THEME;
    setThemeId(id);
    setIsDark(THEMES[id].isDark);
    applyThemeVars(id);
  }, []);

  function toggle() {
    // Legacy toggle — cycles between slate (light) and midnight (dark)
    const next: ThemeId = isDark ? "slate" : "midnight";
    setThemeId(next);
    setIsDark(!isDark);
    applyThemeVars(next);
    localStorage.setItem(STORAGE_KEY, next);
  }

  return { isDark, toggle, themeId };
}
