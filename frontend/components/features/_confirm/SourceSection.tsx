"use client";

import { FONT, DISPLAY, MONO } from "@/lib/theme";
import { SOURCE_LABEL, SOURCE_COLOR } from "./confirmStyles";
import type { SourceKey, MandatoryCheck, ScoringCriterion } from "./types";
import { CriterionRow } from "./CriterionRow";
import { Spinner } from "./Spinner";

export function SourceSection({
  sourceKey,
  mandatoryChecks,
  scoringCriteria,
  showRfpSpinner,
  onUpdateMandatory,
  onRemoveMandatory,
  onUpdateScoring,
  onRemoveScoring,
  onAddMandatory,
  onAddScoring,
}: {
  sourceKey: SourceKey;
  mandatoryChecks: MandatoryCheck[];
  scoringCriteria: ScoringCriterion[];
  showRfpSpinner?: boolean;
  onUpdateMandatory: (id: string, next: MandatoryCheck) => void;
  onRemoveMandatory: (id: string) => void;
  onUpdateScoring: (id: string, next: ScoringCriterion) => void;
  onRemoveScoring: (id: string) => void;
  onAddMandatory?: () => void;
  onAddScoring?: () => void;
}) {
  const color = SOURCE_COLOR[sourceKey];
  const label = SOURCE_LABEL[sourceKey];
  const totalItems = mandatoryChecks.length + scoringCriteria.length;
  const canAdd = !!(onAddMandatory || onAddScoring);

  return (
    <div style={{ marginBottom: 24 }}>
      {/* Section header */}
      <div style={{
        display: "flex", alignItems: "center", gap: 10,
        padding: "10px 16px",
        backgroundColor: "var(--color-surface-hover)",
        borderTop: `2px solid ${color}`,
        borderBottom: "1px solid var(--color-border)",
        borderLeft: "1px solid var(--color-border)",
        borderRight: "1px solid var(--color-border)",
        borderRadius: "var(--radius) var(--radius) 0 0",
      }}>
        <div style={{ width: 8, height: 8, borderRadius: "50%", backgroundColor: color, flexShrink: 0 }} />
        <span style={{
          fontFamily: DISPLAY, fontWeight: 800, fontSize: 11,
          letterSpacing: "0.08em", textTransform: "uppercase",
          color: "var(--color-text-primary)", flex: 1,
        }}>
          {label}
        </span>
        {showRfpSpinner ? (
          <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
            <Spinner size={10} color="var(--color-success)" />
            <span style={{ fontFamily: MONO, fontSize: 10, color: "var(--color-success)" }}>Extracting…</span>
          </div>
        ) : (
          <span style={{ fontFamily: MONO, fontSize: 10, color: "var(--color-text-muted)", fontVariantNumeric: "tabular-nums" }}>
            {mandatoryChecks.length} required · {scoringCriteria.length} scoring
          </span>
        )}
      </div>

      {/* Rows */}
      <div style={{
        backgroundColor: "var(--color-surface)",
        borderTop: "none",
        borderBottom: "1px solid var(--color-border)",
        borderLeft: "1px solid var(--color-border)",
        borderRight: "1px solid var(--color-border)",
        borderRadius: canAdd ? "0" : "0 0 var(--radius) var(--radius)",
        boxShadow: canAdd ? "none" : "var(--shadow-sm)",
      }}>
        {totalItems === 0 ? (
          <p style={{ fontFamily: FONT, fontSize: 12, color: "var(--color-text-muted)", padding: "16px", lineHeight: 1.55 }}>
            No {label.toLowerCase()} criteria for this evaluation.
          </p>
        ) : (
          <>
            {mandatoryChecks.map(mc => (
              <CriterionRow
                key={mc.check_id} item={mc} type="mandatory"
                onUpdate={next => onUpdateMandatory(mc.check_id, next as MandatoryCheck)}
                onRemove={() => onRemoveMandatory(mc.check_id)}
              />
            ))}
            {scoringCriteria.map(sc => (
              <CriterionRow
                key={sc.criterion_id} item={sc} type="scoring"
                onUpdate={next => onUpdateScoring(sc.criterion_id, next as ScoringCriterion)}
                onRemove={() => onRemoveScoring(sc.criterion_id)}
              />
            ))}
          </>
        )}
      </div>

      {/* Add buttons */}
      {canAdd && (
        <div style={{
          display: "flex", gap: 8, padding: "8px 16px",
          backgroundColor: "var(--color-surface)",
          borderBottom: "1px solid var(--color-border)",
          borderLeft: "1px solid var(--color-border)",
          borderRight: "1px solid var(--color-border)",
          borderRadius: "0 0 var(--radius) var(--radius)",
          boxShadow: "var(--shadow-sm)",
        }}>
          {onAddMandatory && (
            <button
              type="button" onClick={onAddMandatory}
              style={{
                background: "none", border: "none", cursor: "pointer", padding: "4px 0",
                fontFamily: FONT, fontSize: 12, color: "var(--color-text-muted)",
                display: "flex", alignItems: "center", gap: 4,
                transition: "color 150ms ease-out",
              }}
              onMouseEnter={e => { e.currentTarget.style.color = "var(--color-text-primary)"; }}
              onMouseLeave={e => { e.currentTarget.style.color = "var(--color-text-muted)"; }}
            >
              + Required check
            </button>
          )}
          {onAddMandatory && onAddScoring && (
            <span style={{ color: "var(--color-border)", fontFamily: MONO, fontSize: 12 }}>·</span>
          )}
          {onAddScoring && (
            <button
              type="button" onClick={onAddScoring}
              style={{
                background: "none", border: "none", cursor: "pointer", padding: "4px 0",
                fontFamily: FONT, fontSize: 12, color: "var(--color-text-muted)",
                display: "flex", alignItems: "center", gap: 4,
                transition: "color 150ms ease-out",
              }}
              onMouseEnter={e => { e.currentTarget.style.color = "var(--color-text-primary)"; }}
              onMouseLeave={e => { e.currentTarget.style.color = "var(--color-text-muted)"; }}
            >
              + Scoring criterion
            </button>
          )}
        </div>
      )}
    </div>
  );
}
