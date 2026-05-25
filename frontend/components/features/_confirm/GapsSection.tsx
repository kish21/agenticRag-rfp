"use client";

import { FONT, DISPLAY, MONO } from "@/lib/theme";
import type { GapsReport } from "./types";

interface GapsSectionProps {
  gaps: GapsReport;
  acknowledged: boolean;
  onAcknowledge: (v: boolean) => void;
}

export function GapsSection({ gaps, acknowledged, onAcknowledge }: GapsSectionProps) {
  const scoreCount     = gaps.score_guides_generated.length;
  const mandatoryCount = gaps.mandatory_checks_suggested.length;
  const totalGenerated = scoreCount + mandatoryCount;

  if (totalGenerated === 0) return null;

  return (
    <div style={{ marginBottom: 24 }}>
      {/* Header bar */}
      <div style={{
        display: "flex", alignItems: "center", justifyContent: "space-between",
        padding: "10px 16px",
        backgroundColor: "var(--color-surface-hover)",
        borderTop: "2px solid var(--color-warning)",
        borderBottom: "1px solid var(--color-border)",
        borderLeft: "1px solid var(--color-border)",
        borderRight: "1px solid var(--color-border)",
        borderRadius: "var(--radius) var(--radius) 0 0",
      }}>
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <div style={{ width: 8, height: 8, borderRadius: "50%", backgroundColor: "var(--color-warning)", flexShrink: 0 }} />
          <span style={{
            fontFamily: DISPLAY, fontWeight: 800, fontSize: 11,
            letterSpacing: "0.08em", textTransform: "uppercase",
            color: "var(--color-text-primary)",
          }}>
            AI Generated
          </span>
          <span style={{
            fontFamily: MONO, fontWeight: 700, fontSize: 10,
            color: "var(--color-warning)",
            padding: "2px 7px",
            borderTop: "1px solid var(--color-warning)",
            borderBottom: "1px solid var(--color-warning)",
            borderLeft: "1px solid var(--color-warning)",
            borderRight: "1px solid var(--color-warning)",
            borderRadius: 3,
            letterSpacing: "0.04em",
          }}>
            needs review
          </span>
        </div>
        <span style={{ fontFamily: MONO, fontSize: 10, color: "var(--color-text-muted)", fontVariantNumeric: "tabular-nums" }}>
          {mandatoryCount} required · {scoreCount} scoring
        </span>
      </div>

      {/* Explanation + item list */}
      <div style={{
        backgroundColor: "var(--color-surface)",
        borderTop: "none",
        borderBottom: "1px solid var(--color-border)",
        borderLeft: "1px solid var(--color-border)",
        borderRight: "1px solid var(--color-border)",
      }}>
        {/* Why this section exists */}
        <div style={{
          padding: "14px 16px 12px",
          borderBottom: "1px solid var(--color-border)",
          backgroundColor: "color-mix(in srgb, var(--color-warning) 6%, var(--color-surface))",
        }}>
          <p style={{
            fontFamily: FONT, fontSize: 12, lineHeight: 1.65,
            color: "var(--color-text-secondary)", margin: 0,
          }}>
            Neither your CSV nor your RFP defined{" "}
            {scoreCount > 0 && (
              <>
                score guides for{" "}
                <strong style={{ color: "var(--color-text-primary)", fontWeight: 600 }}>
                  {scoreCount} {scoreCount === 1 ? "criterion" : "criteria"}
                </strong>
              </>
            )}
            {scoreCount > 0 && mandatoryCount > 0 && ", or "}
            {mandatoryCount > 0 && (
              <>
                <strong style={{ color: "var(--color-text-primary)", fontWeight: 600 }}>
                  {mandatoryCount} mandatory {mandatoryCount === 1 ? "check" : "checks"}
                </strong>
              </>
            )}
            {". "}
            The AI suggested these based on your department domain. Review, edit, or remove them below.
            They appear in the{" "}
            <strong style={{ color: "var(--color-warning)", fontWeight: 600 }}>AI Generated</strong>{" "}
            section above.
          </p>
        </div>

        {/* Score guide items */}
        {scoreCount > 0 && (
          <div style={{ padding: "12px 16px", borderBottom: mandatoryCount > 0 ? "1px solid var(--color-border)" : "none" }}>
            <p style={{
              fontFamily: FONT, fontWeight: 600, fontSize: 11,
              letterSpacing: "0.06em", textTransform: "uppercase",
              color: "var(--color-text-muted)", marginBottom: 8,
            }}>
              Score guides generated for
            </p>
            <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
              {gaps.score_guides_generated.map((item, i) => (
                <div key={i} style={{ display: "flex", alignItems: "center", gap: 8 }}>
                  <span style={{
                    fontSize: 12, color: "var(--color-warning)", flexShrink: 0, lineHeight: 1,
                  }}>⚠</span>
                  <span style={{
                    fontFamily: FONT, fontSize: 13, color: "var(--color-text-primary)", lineHeight: 1.4,
                  }}>
                    {item.criterion_name}
                  </span>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Mandatory check items */}
        {mandatoryCount > 0 && (
          <div style={{ padding: "12px 16px" }}>
            <p style={{
              fontFamily: FONT, fontWeight: 600, fontSize: 11,
              letterSpacing: "0.06em", textTransform: "uppercase",
              color: "var(--color-text-muted)", marginBottom: 8,
            }}>
              Mandatory checks suggested
            </p>
            <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
              {gaps.mandatory_checks_suggested.map((item, i) => (
                <div key={i} style={{ display: "flex", alignItems: "center", gap: 8 }}>
                  <span style={{
                    fontSize: 12, color: "var(--color-warning)", flexShrink: 0, lineHeight: 1,
                  }}>⚠</span>
                  <span style={{
                    fontFamily: FONT, fontSize: 13, color: "var(--color-text-primary)", lineHeight: 1.4,
                  }}>
                    {item.criterion_name}
                  </span>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>

      {/* Acknowledgment checkbox */}
      <div style={{
        padding: "12px 16px",
        backgroundColor: "var(--color-surface)",
        borderBottom: "1px solid var(--color-border)",
        borderLeft: "1px solid var(--color-border)",
        borderRight: "1px solid var(--color-border)",
        borderRadius: "0 0 var(--radius) var(--radius)",
        boxShadow: "var(--shadow-sm)",
      }}>
        <label style={{ display: "flex", alignItems: "flex-start", gap: 10, cursor: "pointer" }}>
          <input
            type="checkbox"
            checked={acknowledged}
            onChange={e => onAcknowledge(e.target.checked)}
            style={{ marginTop: 2, flexShrink: 0, accentColor: "var(--color-warning)", width: 15, height: 15 }}
          />
          <span style={{ fontFamily: FONT, fontSize: 13, color: "var(--color-text-secondary)", lineHeight: 1.6 }}>
            I have reviewed the AI-generated criteria above and edited or removed anything that does not apply.
            The remaining items can be included in the evaluation.
          </span>
        </label>
      </div>
    </div>
  );
}
