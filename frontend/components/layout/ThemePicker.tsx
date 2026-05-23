"use client";

import { useState, useRef, useEffect } from "react";
import { THEMES, THEME_GROUPS, type ThemeId } from "@/lib/theme";
import { useThemeContext } from "./ThemeProvider";

export function ThemePicker() {
  const { themeId, setTheme } = useThemeContext();
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    function handleClick(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    }
    document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, []);

  const active = THEMES[themeId];

  return (
    <div ref={ref} style={{ position: "relative", flexShrink: 0 }}>
      {/* Trigger button */}
      <button
        onClick={() => setOpen(o => !o)}
        title="Change theme"
        style={{
          display: "flex", alignItems: "center", gap: 7,
          background: "var(--color-surface)",
          border: "1px solid var(--color-border-strong)",
          borderRadius: "var(--radius)",
          padding: "5px 10px",
          cursor: "pointer",
          color: "var(--color-text-secondary)",
          fontSize: 12,
          fontFamily: "var(--font-sans)",
          transition: "background var(--transition), border-color var(--transition)",
        }}
      >
        {/* Active theme swatch */}
        <span style={{
          display: "inline-flex", alignItems: "center", justifyContent: "center",
          width: 16, height: 16, borderRadius: "50%",
          background: active.colors.accent,
          border: `2px solid ${active.colors.accentForeground}22`,
          flexShrink: 0,
        }} />
        <span style={{ maxWidth: 72, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
          {active.name}
        </span>
        <svg width="10" height="10" viewBox="0 0 10 10" fill="none" style={{ opacity: 0.5, flexShrink: 0 }}>
          <path d="M2 3.5L5 6.5L8 3.5" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" />
        </svg>
      </button>

      {/* Dropdown panel */}
      {open && (
        <div style={{
          position: "absolute", top: "calc(100% + 8px)", right: 0,
          width: 300,
          background: "var(--color-surface)",
          border: "1px solid var(--color-border-strong)",
          borderRadius: "calc(var(--radius) * 1.5)",
          boxShadow: "var(--shadow-lg)",
          zIndex: 100,
          overflow: "hidden",
        }}>
          {/* Header */}
          <div style={{
            padding: "10px 14px 8px",
            borderBottom: "1px solid var(--color-border)",
            fontSize: 11,
            fontWeight: 600,
            color: "var(--color-text-muted)",
            fontFamily: "var(--font-sans)",
            letterSpacing: "0.06em",
            textTransform: "uppercase",
          }}>
            Theme
          </div>

          {/* Groups */}
          <div style={{ maxHeight: 400, overflowY: "auto", padding: "8px 0" }}>
            {THEME_GROUPS.map(group => (
              <div key={group.label} style={{ marginBottom: 4 }}>
                <div style={{
                  padding: "4px 14px 3px",
                  fontSize: 10,
                  fontWeight: 600,
                  color: "var(--color-text-muted)",
                  fontFamily: "var(--font-sans)",
                  letterSpacing: "0.05em",
                  textTransform: "uppercase",
                }}>
                  {group.label}
                </div>
                <div style={{
                  display: "grid",
                  gridTemplateColumns: "1fr 1fr",
                  gap: 1,
                  padding: "0 6px",
                }}>
                  {group.ids.map(id => (
                    <ThemeRow
                      key={id}
                      id={id}
                      isActive={id === themeId}
                      onSelect={() => { setTheme(id); setOpen(false); }}
                    />
                  ))}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

function ThemeRow({ id, isActive, onSelect }: { id: ThemeId; isActive: boolean; onSelect: () => void }) {
  const t = THEMES[id];
  const [hovered, setHovered] = useState(false);

  return (
    <button
      onClick={onSelect}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      title={t.description}
      style={{
        display: "flex", alignItems: "center", gap: 8,
        padding: "6px 8px",
        borderRadius: 6,
        border: isActive ? `1px solid ${t.colors.accent}44` : "1px solid transparent",
        background: hovered
          ? "var(--color-surface-hover)"
          : isActive
          ? `${t.colors.accent}0A`
          : "transparent",
        cursor: "pointer",
        textAlign: "left",
        width: "100%",
        transition: "background 100ms ease",
      }}
    >
      {/* Swatch */}
      <span style={{
        flexShrink: 0,
        width: 20, height: 20,
        borderRadius: "50%",
        background: `linear-gradient(135deg, ${t.colors.background} 50%, ${t.colors.accent} 50%)`,
        border: isActive ? `2px solid ${t.colors.accent}` : "1px solid rgba(0,0,0,0.12)",
        boxShadow: isActive ? `0 0 0 2px ${t.colors.accent}30` : "none",
      }} />

      {/* Name */}
      <span style={{
        fontSize: 12,
        fontFamily: "var(--font-sans)",
        color: isActive ? t.colors.accent : "var(--color-text-secondary)",
        fontWeight: isActive ? 600 : 400,
        overflow: "hidden",
        textOverflow: "ellipsis",
        whiteSpace: "nowrap",
        flex: 1,
      }}>
        {t.name}
      </span>

      {/* Active check */}
      {isActive && (
        <svg width="12" height="12" viewBox="0 0 12 12" fill="none" style={{ flexShrink: 0 }}>
          <path d="M2 6l3 3 5-5" stroke={t.colors.accent} strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      )}
    </button>
  );
}
