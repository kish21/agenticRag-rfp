"use client";

import { FONT, MONO } from "@/lib/theme";

const labelCss: React.CSSProperties = {
  display: "block",
  fontFamily: FONT,
  fontSize: 11, fontWeight: 600,
  letterSpacing: "0.07em", textTransform: "uppercase",
  color: "var(--color-text-muted)",
  marginBottom: 6,
};

const inputCss: React.CSSProperties = {
  width: "100%", boxSizing: "border-box",
  padding: "9px 12px",
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

interface VendorCardProps {
  index: number;
  id: string;
  name: string;
  file: File;
  canRemove: boolean;
  onRemove: () => void;
  onNameChange: (name: string) => void;
}

export function VendorCard({ index, id, name, file, canRemove, onRemove, onNameChange }: VendorCardProps) {
  return (
    <div
      className="w-full"
      style={{
        padding: "14px 16px",
        backgroundColor: "var(--color-surface)",
        borderTop: "1px solid var(--color-border)",
        borderBottom: "1px solid var(--color-border)",
        borderLeft: "1px solid var(--color-border)",
        borderRight: "1px solid var(--color-border)",
        borderRadius: "var(--radius)",
      }}
    >
      {/* Header row */}
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 10 }}>
        <p style={{
          fontFamily: FONT, fontSize: 10, fontWeight: 600,
          letterSpacing: "0.08em", textTransform: "uppercase",
          color: "var(--color-text-muted)",
        }}>
          Vendor {index + 1}
        </p>
        {canRemove && (
          <button
            type="button"
            onClick={onRemove}
            style={{
              background: "none", border: "none", cursor: "pointer",
              fontFamily: FONT, fontSize: 11, color: "var(--color-text-muted)",
              padding: "4px 0", minHeight: 28,
              transition: "color 150ms ease-out",
            }}
            onMouseEnter={e => { e.currentTarget.style.color = "var(--color-error)"; }}
            onMouseLeave={e => { e.currentTarget.style.color = "var(--color-text-muted)"; }}
          >
            Remove
          </button>
        )}
      </div>

      {/* Vendor name input */}
      <label htmlFor={`vname-${id}`} style={labelCss}>Vendor name</label>
      <input
        id={`vname-${id}`}
        type="text"
        value={name}
        onChange={e => onNameChange(e.target.value)}
        placeholder="Company name"
        suppressHydrationWarning
        style={{ ...inputCss, marginBottom: 10 }}
        onFocus={e => { e.currentTarget.style.borderTopColor = "var(--color-accent)"; e.currentTarget.style.borderBottomColor = "var(--color-accent)"; e.currentTarget.style.borderLeftColor = "var(--color-accent)"; e.currentTarget.style.borderRightColor = "var(--color-accent)"; }}
        onBlur={e => { e.currentTarget.style.borderTopColor = "var(--color-border)"; e.currentTarget.style.borderBottomColor = "var(--color-border)"; e.currentTarget.style.borderLeftColor = "var(--color-border)"; e.currentTarget.style.borderRightColor = "var(--color-border)"; }}
      />

      {/* File chip — read-only, file was set at drop time */}
      <p style={{ ...labelCss, marginBottom: 6 }}>Proposal document</p>
      <div style={{
        display: "flex", alignItems: "center", gap: 8,
        padding: "8px 12px",
        backgroundColor: "var(--color-background)",
        borderTop: "1px solid var(--color-border)",
        borderBottom: "1px solid var(--color-border)",
        borderLeft: "1px solid var(--color-border)",
        borderRight: "1px solid var(--color-border)",
        borderRadius: "var(--radius)",
      }}>
        <span style={{ fontSize: 13 }}>📄</span>
        <p style={{ fontFamily: FONT, fontSize: 12, color: "var(--color-text-primary)", fontWeight: 500, flex: 1, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
          {file.name}
        </p>
        <span style={{ fontFamily: MONO, fontSize: 10, color: "var(--color-text-muted)", flexShrink: 0 }}>
          {(file.size / 1024).toFixed(0)} KB
        </span>
      </div>
    </div>
  );
}
