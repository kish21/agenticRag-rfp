"use client";

import { useState } from "react";
import { FONT, MONO } from "@/lib/theme";
import { SOURCE_LABEL, SOURCE_COLOR, labelCss, inputCss, focusBorder, blurBorder } from "./confirmStyles";
import type { SourceKey, MandatoryCheck, ScoringCriterion } from "./types";

export function CriterionRow({
  item,
  type,
  onUpdate,
  onRemove,
}: {
  item: MandatoryCheck | ScoringCriterion;
  type: "mandatory" | "scoring";
  onUpdate: (next: MandatoryCheck | ScoringCriterion) => void;
  onRemove: () => void;
}) {
  const [expanded, setExpanded] = useState(false);
  const locked = item.is_locked;
  const source = (item.source || "rfp") as SourceKey;
  const sourceColor = SOURCE_COLOR[source] ?? "var(--color-text-muted)";
  const weight = type === "scoring" ? (item as ScoringCriterion).weight : null;
  const itemId = type === "mandatory"
    ? (item as MandatoryCheck).check_id
    : (item as ScoringCriterion).criterion_id;

  return (
    <div style={{
      borderBottom: "1px solid var(--color-border)",
      opacity: locked ? 0.7 : 1,
    }}>
      {/* Row header */}
      <div
        role="button"
        tabIndex={0}
        onClick={() => setExpanded(v => !v)}
        onKeyDown={e => { if (e.key === "Enter" || e.key === " ") setExpanded(v => !v); }}
        style={{
          display: "flex", alignItems: "center", gap: 10,
          padding: "11px 16px", cursor: "pointer",
          transition: "background-color 150ms ease-out",
        }}
        onMouseEnter={e => { (e.currentTarget as HTMLElement).style.backgroundColor = "var(--color-surface-hover)"; }}
        onMouseLeave={e => { (e.currentTarget as HTMLElement).style.backgroundColor = "transparent"; }}
      >
        {locked ? (
          <span style={{ fontSize: 12, flexShrink: 0, color: "var(--color-text-muted)" }}>🔒</span>
        ) : (
          <span style={{
            fontSize: 10, flexShrink: 0, color: "var(--color-text-muted)",
            transform: expanded ? "rotate(90deg)" : "none",
            transition: "transform 150ms ease-out",
            display: "inline-block",
          }}>▶</span>
        )}
        <span style={{
          fontFamily: FONT, fontWeight: 500, fontSize: 13,
          color: "var(--color-text-primary)", flex: 1, minWidth: 0,
          overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap",
        }}>
          {item.name}
        </span>
        {type === "scoring" && weight !== null && (
          <span style={{
            fontFamily: MONO, fontWeight: 600, fontSize: 12,
            color: "var(--color-text-secondary)", flexShrink: 0,
            fontVariantNumeric: "tabular-nums",
          }}>
            {(weight * 100).toFixed(0)}%
          </span>
        )}
        <span style={{
          fontFamily: FONT, fontWeight: 600, fontSize: 9,
          letterSpacing: "0.08em", textTransform: "uppercase",
          color: type === "mandatory" ? "var(--color-warning)" : "var(--color-info)",
          padding: "1px 6px",
          borderTop: `1px solid ${type === "mandatory" ? "var(--color-warning)" : "var(--color-info)"}`,
          borderBottom: `1px solid ${type === "mandatory" ? "var(--color-warning)" : "var(--color-info)"}`,
          borderLeft: `1px solid ${type === "mandatory" ? "var(--color-warning)" : "var(--color-info)"}`,
          borderRight: `1px solid ${type === "mandatory" ? "var(--color-warning)" : "var(--color-info)"}`,
          borderRadius: 3, flexShrink: 0,
        }}>
          {type === "mandatory" ? "required" : "scoring"}
        </span>
        {!locked && (
          <button
            type="button"
            onClick={e => { e.stopPropagation(); onRemove(); }}
            aria-label={`Remove ${item.name}`}
            style={{
              background: "none", border: "none", cursor: "pointer",
              color: "var(--color-text-muted)", fontSize: 16,
              padding: "0 2px", flexShrink: 0, lineHeight: 1,
              transition: "color 150ms ease-out",
            }}
            onMouseEnter={e => { e.currentTarget.style.color = "var(--color-error)"; }}
            onMouseLeave={e => { e.currentTarget.style.color = "var(--color-text-muted)"; }}
          >×</button>
        )}
      </div>

      {/* Expanded detail */}
      {expanded && (
        <div style={{ padding: "0 16px 16px 16px", display: "flex", flexDirection: "column", gap: 12 }}>
          <div>
            <label htmlFor={`name-${itemId}`} style={labelCss}>Name</label>
            <input
              id={`name-${itemId}`} type="text" value={item.name} disabled={locked}
              onChange={e => onUpdate({ ...item, name: e.target.value })}
              style={{ ...inputCss, opacity: locked ? 0.6 : 1, cursor: locked ? "not-allowed" : "text" }}
              onFocus={locked ? undefined : focusBorder}
              onBlur={locked ? undefined : blurBorder}
            />
          </div>
          <div>
            <label htmlFor={`desc-${itemId}`} style={labelCss}>Description</label>
            <textarea
              id={`desc-${itemId}`} rows={2} value={item.description || ""} disabled={locked}
              onChange={e => onUpdate({ ...item, description: e.target.value })}
              style={{ ...inputCss, resize: "vertical", lineHeight: 1.55, minHeight: 52, opacity: locked ? 0.6 : 1, cursor: locked ? "not-allowed" : "text" }}
              onFocus={locked ? undefined : focusBorder}
              onBlur={locked ? undefined : blurBorder}
            />
          </div>
          {type === "mandatory" && (
            <div>
              <label htmlFor={`pass-${itemId}`} style={labelCss}>What passes</label>
              <textarea
                id={`pass-${itemId}`} rows={2}
                value={(item as MandatoryCheck).what_passes || ""} disabled={locked}
                onChange={e => onUpdate({ ...item, what_passes: e.target.value } as MandatoryCheck)}
                style={{ ...inputCss, resize: "vertical", lineHeight: 1.55, minHeight: 52, opacity: locked ? 0.6 : 1, cursor: locked ? "not-allowed" : "text" }}
                onFocus={locked ? undefined : focusBorder}
                onBlur={locked ? undefined : blurBorder}
              />
            </div>
          )}
          {type === "scoring" && (
            <div>
              <label htmlFor={`wt-${itemId}`} style={labelCss}>Weight (0–1)</label>
              <input
                id={`wt-${itemId}`} type="number" min={0} max={1} step={0.001}
                value={(item as ScoringCriterion).weight} disabled={locked}
                onChange={e => onUpdate({ ...item, weight: parseFloat(e.target.value) || 0 } as ScoringCriterion)}
                style={{ ...inputCss, width: 120, opacity: locked ? 0.6 : 1, cursor: locked ? "not-allowed" : "text", fontFamily: MONO }}
                onFocus={locked ? undefined : focusBorder}
                onBlur={locked ? undefined : blurBorder}
              />
            </div>
          )}
          {locked && (
            <p style={{ fontFamily: FONT, fontSize: 11, color: "var(--color-text-muted)", lineHeight: 1.5 }}>
              🔒 Organisation policy — read-only
            </p>
          )}
          <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
            <span style={{ display: "inline-block", width: 7, height: 7, borderRadius: "50%", backgroundColor: sourceColor, flexShrink: 0 }} />
            <span style={{ fontFamily: FONT, fontSize: 11, color: "var(--color-text-muted)" }}>
              Source: {SOURCE_LABEL[source] ?? source}
            </span>
          </div>
        </div>
      )}
    </div>
  );
}
