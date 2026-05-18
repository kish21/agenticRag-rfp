"use client";

import { useState } from "react";
import { FONT } from "@/lib/theme";

interface InputProps extends Omit<React.InputHTMLAttributes<HTMLInputElement>, "size"> {
  label?: string;
  error?: string;
  /** "underline" = borderless with bottom border only (login/signup style) | "box" = bordered box */
  variant?: "underline" | "box";
}

export function Input({
  label,
  error,
  variant = "box",
  id,
  style,
  ...props
}: InputProps) {
  const [focused, setFocused] = useState(false);
  const inputId = id ?? label?.toLowerCase().replace(/\s+/g, "-");

  const baseInput: React.CSSProperties = {
    display: "block",
    width: "100%",
    fontFamily: FONT,
    fontWeight: 400,
    fontSize: 14,
    color: "var(--color-text-primary)",
    background: "transparent",
    outline: "none",
    transition: "border-color 150ms ease-out, box-shadow 150ms ease-out",
    boxSizing: "border-box",
  };

  const variantInput: React.CSSProperties =
    variant === "underline"
      ? {
          borderTop: "none",
          borderLeft: "none",
          borderRight: "none",
          borderBottom: `1.5px solid ${
            error ? "var(--color-error)" : focused ? "var(--color-accent)" : "var(--color-border-strong)"
          }`,
          borderRadius: 0,
          padding: "8px 0",
        }
      : {
          borderTop: `1px solid ${error ? "var(--color-error)" : focused ? "var(--color-accent)" : "var(--color-border)"}`,
          borderBottom: `1px solid ${error ? "var(--color-error)" : focused ? "var(--color-accent)" : "var(--color-border)"}`,
          borderLeft: `1px solid ${error ? "var(--color-error)" : focused ? "var(--color-accent)" : "var(--color-border)"}`,
          borderRight: `1px solid ${error ? "var(--color-error)" : focused ? "var(--color-accent)" : "var(--color-border)"}`,
          borderRadius: "var(--radius)",
          padding: "9px 12px",
          backgroundColor: "var(--color-surface)",
          boxShadow: focused ? `0 0 0 3px color-mix(in srgb, var(--color-accent) 15%, transparent)` : "none",
        };

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
      {label && (
        <label
          htmlFor={inputId}
          style={{
            fontFamily: FONT,
            fontWeight: 500,
            fontSize: 11,
            letterSpacing: "0.08em",
            textTransform: "uppercase",
            color: focused ? "var(--color-accent)" : error ? "var(--color-error)" : "var(--color-text-muted)",
            transition: "color 150ms ease-out",
          }}
        >
          {label}
        </label>
      )}

      <input
        id={inputId}
        style={{ ...baseInput, ...variantInput, ...style }}
        onFocus={(e) => { setFocused(true); props.onFocus?.(e); }}
        onBlur={(e) => { setFocused(false); props.onBlur?.(e); }}
        suppressHydrationWarning
        {...props}
      />

      {error && (
        <span
          role="alert"
          style={{
            fontFamily: FONT,
            fontSize: 12,
            color: "var(--color-error)",
            lineHeight: 1.4,
          }}
        >
          {error}
        </span>
      )}
    </div>
  );
}
