import { FONT } from "@/lib/theme";
import type { SourceKey } from "./types";

export const SOURCE_LABEL: Record<SourceKey, string> = {
  org:  "Organisation",
  dept: "Department",
  user: "Your Criteria",
  rfp:  "RFP-Extracted",
};

export const SOURCE_COLOR: Record<SourceKey, string> = {
  org:  "var(--color-accent)",
  dept: "var(--color-info)",
  user: "var(--color-warning)",
  rfp:  "var(--color-success)",
};

export const ALL_SOURCES: SourceKey[] = ["org", "dept", "user", "rfp"];

export const labelCss: React.CSSProperties = {
  display: "block",
  fontFamily: FONT, fontSize: 11, fontWeight: 600,
  letterSpacing: "0.07em", textTransform: "uppercase",
  color: "var(--color-text-muted)", marginBottom: 6,
};

export const inputCss: React.CSSProperties = {
  width: "100%", boxSizing: "border-box",
  padding: "7px 10px",
  backgroundColor: "var(--color-background)",
  borderTop: "1px solid var(--color-border)",
  borderBottom: "1px solid var(--color-border)",
  borderLeft: "1px solid var(--color-border)",
  borderRight: "1px solid var(--color-border)",
  borderRadius: "var(--radius)",
  fontFamily: FONT, fontSize: 13,
  color: "var(--color-text-primary)",
  transition: "border-color 150ms ease-out",
};

export function focusBorder(e: React.FocusEvent<HTMLInputElement | HTMLTextAreaElement>) {
  const el = e.currentTarget;
  el.style.borderTopColor = "var(--color-accent)";
  el.style.borderBottomColor = "var(--color-accent)";
  el.style.borderLeftColor = "var(--color-accent)";
  el.style.borderRightColor = "var(--color-accent)";
}

export function blurBorder(e: React.FocusEvent<HTMLInputElement | HTMLTextAreaElement>) {
  const el = e.currentTarget;
  el.style.borderTopColor = "var(--color-border)";
  el.style.borderBottomColor = "var(--color-border)";
  el.style.borderLeftColor = "var(--color-border)";
  el.style.borderRightColor = "var(--color-border)";
}
