import { FONT } from "@/lib/theme";

export function inputStyle(field: string, focusedField: string | null): React.CSSProperties {
  return {
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
  };
}

export function labelStyle(field: string, focusedField: string | null): React.CSSProperties {
  return {
    display: "block",
    fontFamily: FONT,
    fontWeight: 500,
    fontSize: 11,
    letterSpacing: "0.08em",
    textTransform: "uppercase",
    color: focusedField === field ? "var(--color-accent)" : "var(--color-text-muted)",
    marginBottom: 8,
    transition: "color 150ms ease-out",
  };
}

export const submitStyle: React.CSSProperties = {
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
