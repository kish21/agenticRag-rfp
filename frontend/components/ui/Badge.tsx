"use client";

import { FONT, MONO } from "@/lib/theme";

type BadgeVariant = "success" | "warning" | "error" | "info" | "neutral" | "accent";

interface BadgeProps {
  children: React.ReactNode;
  variant?: BadgeVariant;
  /** Use monospace font — good for status codes, IDs */
  mono?: boolean;
  dot?: boolean;
  style?: React.CSSProperties;
}

const VARIANT_STYLES: Record<BadgeVariant, React.CSSProperties> = {
  success: {
    backgroundColor: "color-mix(in srgb, var(--color-success) 14%, transparent)",
    color: "var(--color-success)",
    borderTop: "1px solid color-mix(in srgb, var(--color-success) 28%, transparent)",
    borderBottom: "1px solid color-mix(in srgb, var(--color-success) 28%, transparent)",
    borderLeft: "1px solid color-mix(in srgb, var(--color-success) 28%, transparent)",
    borderRight: "1px solid color-mix(in srgb, var(--color-success) 28%, transparent)",
  },
  warning: {
    backgroundColor: "color-mix(in srgb, var(--color-warning) 14%, transparent)",
    color: "var(--color-warning)",
    borderTop: "1px solid color-mix(in srgb, var(--color-warning) 28%, transparent)",
    borderBottom: "1px solid color-mix(in srgb, var(--color-warning) 28%, transparent)",
    borderLeft: "1px solid color-mix(in srgb, var(--color-warning) 28%, transparent)",
    borderRight: "1px solid color-mix(in srgb, var(--color-warning) 28%, transparent)",
  },
  error: {
    backgroundColor: "color-mix(in srgb, var(--color-error) 14%, transparent)",
    color: "var(--color-error)",
    borderTop: "1px solid color-mix(in srgb, var(--color-error) 28%, transparent)",
    borderBottom: "1px solid color-mix(in srgb, var(--color-error) 28%, transparent)",
    borderLeft: "1px solid color-mix(in srgb, var(--color-error) 28%, transparent)",
    borderRight: "1px solid color-mix(in srgb, var(--color-error) 28%, transparent)",
  },
  info: {
    backgroundColor: "color-mix(in srgb, var(--color-info) 14%, transparent)",
    color: "var(--color-info)",
    borderTop: "1px solid color-mix(in srgb, var(--color-info) 28%, transparent)",
    borderBottom: "1px solid color-mix(in srgb, var(--color-info) 28%, transparent)",
    borderLeft: "1px solid color-mix(in srgb, var(--color-info) 28%, transparent)",
    borderRight: "1px solid color-mix(in srgb, var(--color-info) 28%, transparent)",
  },
  neutral: {
    backgroundColor: "var(--color-surface)",
    color: "var(--color-text-secondary)",
    borderTop: "1px solid var(--color-border)",
    borderBottom: "1px solid var(--color-border)",
    borderLeft: "1px solid var(--color-border)",
    borderRight: "1px solid var(--color-border)",
  },
  accent: {
    backgroundColor: "color-mix(in srgb, var(--color-accent) 14%, transparent)",
    color: "var(--color-accent)",
    borderTop: "1px solid color-mix(in srgb, var(--color-accent) 28%, transparent)",
    borderBottom: "1px solid color-mix(in srgb, var(--color-accent) 28%, transparent)",
    borderLeft: "1px solid color-mix(in srgb, var(--color-accent) 28%, transparent)",
    borderRight: "1px solid color-mix(in srgb, var(--color-accent) 28%, transparent)",
  },
};

export function Badge({ children, variant = "neutral", mono = false, dot = false, style }: BadgeProps) {
  return (
    <span
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: 5,
        padding: "2px 8px",
        borderRadius: 999,
        fontFamily: mono ? MONO : FONT,
        fontWeight: mono ? 500 : 600,
        fontSize: 11,
        letterSpacing: mono ? "0" : "0.04em",
        lineHeight: 1.8,
        whiteSpace: "nowrap",
        ...VARIANT_STYLES[variant],
        ...style,
      }}
    >
      {dot && (
        <span
          style={{
            width: 5, height: 5, borderRadius: "50%",
            backgroundColor: "currentColor",
            flexShrink: 0,
          }}
        />
      )}
      {children}
    </span>
  );
}
