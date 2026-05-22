"use client";

import { useEffect, useRef, useState, useCallback } from "react";
import { FONT, DISPLAY, MONO } from "@/lib/theme";
import { useBreakpoint } from "@/lib/hooks";
import { api } from "@/lib/api";
import { formatCurrency } from "@/lib/utils";

// ── Types ─────────────────────────────────────────────────────────────────────

interface MandatoryCheck {
  check_id: string;
  name: string;
  description: string;
  what_passes: string;
  extraction_target_id: string;
  source: string;
  is_locked: boolean;
}

interface ScoringCriterion {
  criterion_id: string;
  name: string;
  weight: number;
  description?: string;
  rubric_9_10?: string;
  rubric_6_8?: string;
  rubric_3_5?: string;
  rubric_0_2?: string;
  extraction_target_ids?: string[];
  source: string;
  is_locked: boolean;
}

interface EvaluationSetup {
  mandatory_checks: MandatoryCheck[];
  scoring_criteria: ScoringCriterion[];
  total_weight: number;
  source: string;
  currency?: string;
  contract_value?: number | null;
  vendor_count?: number;
  rfp_title?: string;
  department?: string;
}

type SourceKey = "org" | "dept" | "user" | "rfp";

interface DupPair {
  a: { name: string; source: SourceKey };
  b: { name: string; source: SourceKey };
  idA: string;
  idB: string;
}

interface ConfirmSetupPageProps {
  runId: string;
  onConfirmed: () => void;
  onBack: () => void;
  onAuth401: () => void;
}

// ── Design tokens ─────────────────────────────────────────────────────────────

const SOURCE_LABEL: Record<SourceKey, string> = {
  org:  "Organisation",
  dept: "Department",
  user: "Your Criteria",
  rfp:  "RFP-Extracted",
};

const SOURCE_COLOR: Record<SourceKey, string> = {
  org:  "var(--color-accent)",
  dept: "var(--color-info)",
  user: "var(--color-warning)",
  rfp:  "var(--color-success)",
};

const ALL_SOURCES: SourceKey[] = ["org", "dept", "user", "rfp"];

const labelCss: React.CSSProperties = {
  display: "block",
  fontFamily: FONT, fontSize: 11, fontWeight: 600,
  letterSpacing: "0.07em", textTransform: "uppercase",
  color: "var(--color-text-muted)", marginBottom: 6,
};

const inputCss: React.CSSProperties = {
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

function focusBorder(e: React.FocusEvent<HTMLInputElement | HTMLTextAreaElement>) {
  const el = e.currentTarget;
  el.style.borderTopColor = "var(--color-accent)";
  el.style.borderBottomColor = "var(--color-accent)";
  el.style.borderLeftColor = "var(--color-accent)";
  el.style.borderRightColor = "var(--color-accent)";
}

function blurBorder(e: React.FocusEvent<HTMLInputElement | HTMLTextAreaElement>) {
  const el = e.currentTarget;
  el.style.borderTopColor = "var(--color-border)";
  el.style.borderBottomColor = "var(--color-border)";
  el.style.borderLeftColor = "var(--color-border)";
  el.style.borderRightColor = "var(--color-border)";
}

// ── Helpers ───────────────────────────────────────────────────────────────────

function round3(n: number): number {
  return Math.round(n * 1000) / 1000;
}

function genId(source: SourceKey, type: "mandatory" | "scoring"): string {
  const prefix = type === "mandatory" ? "MC" : "SC";
  const rand = Math.random().toString(36).slice(2, 10).toUpperCase();
  return `${prefix}-${source.toUpperCase()}-${rand}`;
}

function normName(n: string): string {
  return n.toLowerCase().replace(/[^a-z0-9 ]/g, " ").replace(/\s+/g, " ").trim();
}

function isNearDup(a: string, b: string): boolean {
  const wa = normName(a).split(" ").filter(Boolean);
  const wb = normName(b).split(" ").filter(Boolean);
  if (wa.length < 3 || wb.length < 3) return false;
  const wbStr = wb.join(" ");
  for (let i = 0; i <= wa.length - 3; i++) {
    if (wbStr.includes(wa.slice(i, i + 3).join(" "))) return true;
  }
  return false;
}

function findDupPairs(setup: EvaluationSetup): DupPair[] {
  const all: Array<{ name: string; source: SourceKey; id: string; type: "mandatory" | "scoring" }> = [
    ...setup.mandatory_checks.map(c => ({ name: c.name, source: c.source as SourceKey, id: c.check_id, type: "mandatory" as const })),
    ...setup.scoring_criteria.map(c => ({ name: c.name, source: c.source as SourceKey, id: c.criterion_id, type: "scoring" as const })),
  ];
  const pairs: DupPair[] = [];
  for (let i = 0; i < all.length; i++) {
    for (let j = i + 1; j < all.length; j++) {
      if (all[i].source !== all[j].source && isNearDup(all[i].name, all[j].name)) {
        pairs.push({ a: all[i], b: all[j], idA: all[i].id, idB: all[j].id });
      }
    }
  }
  return pairs;
}

// ── Spinner ───────────────────────────────────────────────────────────────────

function Spinner({ size = 12, color = "var(--color-text-muted)" }: { size?: number; color?: string }) {
  return (
    <div style={{
      width: size, height: size, flexShrink: 0,
      borderTop: `2px solid ${color}`,
      borderBottom: "2px solid transparent",
      borderLeft: "2px solid transparent",
      borderRight: "2px solid transparent",
      borderRadius: "50%",
      animation: "csp-spin 0.7s linear infinite",
    }} />
  );
}

// ── Criterion row (expandable) ────────────────────────────────────────────────

function CriterionRow({
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

// ── Source section ────────────────────────────────────────────────────────────

function SourceSection({
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

      {/* Inline add buttons (#50) */}
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

// ── Main component ────────────────────────────────────────────────────────────

export function ConfirmSetupPage({ runId, onConfirmed, onBack, onAuth401 }: ConfirmSetupPageProps) {
  const bp = useBreakpoint();
  const isMobile = bp === "mobile";

  const [setup, setSetup] = useState<EvaluationSetup | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState("");
  const [rfpPolling, setRfpPolling] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const [confirmError, setConfirmError] = useState("");
  const [weightWarning, setWeightWarning] = useState(false);
  const [rfpConfirmed, setRfpConfirmed] = useState(false);        // #52
  const [rfpCheckError, setRfpCheckError] = useState(false);      // #52
  const [dupPairs, setDupPairs] = useState<DupPair[]>([]);         // #51
  const [dismissedDups, setDismissedDups] = useState<Set<string>>(new Set()); // #51
  const pollRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const pollCountRef = useRef(0);

  // ── Derived ───────────────────────────────────────────────────────────────

  const mandatoryBySource = useCallback((src: SourceKey): MandatoryCheck[] =>
    (setup?.mandatory_checks ?? []).filter(c => c.source === src), [setup]);

  const scoringBySource = useCallback((src: SourceKey): ScoringCriterion[] =>
    (setup?.scoring_criteria ?? []).filter(c => c.source === src), [setup]);

  const scoringTotal = (setup?.scoring_criteria ?? []).reduce((s, c) => s + (c.weight || 0), 0);
  const weightOff = Math.abs(scoringTotal - 1.0) > 0.02 && (setup?.scoring_criteria.length ?? 0) > 0;

  // ── Fetch ─────────────────────────────────────────────────────────────────

  const fetchSetup = useCallback(async (isRefresh = false) => {
    try {
      const data = await api.get<EvaluationSetup>(`/api/v1/evaluate/${runId}/setup`, { on401: onAuth401 });
      setSetup(data);
      if (!isRefresh) {
        setLoading(false);
        setDupPairs(findDupPairs(data)); // #51 — compute once on initial load
      }
      if (data.source === "merged" || data.source === "merged_empty") {
        if (pollCountRef.current < 10) {
          setRfpPolling(true);
          pollRef.current = setTimeout(() => {
            pollCountRef.current += 1;
            fetchSetup(true);
          }, 3000);
        } else {
          setRfpPolling(false);
        }
      } else {
        setRfpPolling(false);
        if (isRefresh) setDupPairs(findDupPairs(data)); // refresh dups once LLM-refined
      }
    } catch (err) {
      if (!isRefresh) {
        setLoadError(err instanceof Error ? err.message : "Failed to load criteria.");
        setLoading(false);
      }
    }
  }, [runId, onAuth401]);

  useEffect(() => {
    fetchSetup();
    return () => { if (pollRef.current) clearTimeout(pollRef.current); };
  }, [fetchSetup]);

  // ── Mutators ──────────────────────────────────────────────────────────────

  function updateMandatory(id: string, next: MandatoryCheck) {
    setSetup(prev => prev ? { ...prev, mandatory_checks: prev.mandatory_checks.map(c => c.check_id === id ? next : c) } : prev);
  }

  function removeMandatory(id: string) {
    setSetup(prev => prev ? { ...prev, mandatory_checks: prev.mandatory_checks.filter(c => c.check_id !== id) } : prev);
  }

  function updateScoring(id: string, next: ScoringCriterion) {
    setSetup(prev => {
      if (!prev) return prev;
      const updated = prev.scoring_criteria.map(c => c.criterion_id === id ? next : c);
      return { ...prev, scoring_criteria: updated, total_weight: round3(updated.reduce((s, c) => s + (c.weight || 0), 0)) };
    });
  }

  function removeScoring(id: string) {
    setSetup(prev => {
      if (!prev) return prev;
      const updated = prev.scoring_criteria.filter(c => c.criterion_id !== id);
      return { ...prev, scoring_criteria: updated, total_weight: round3(updated.reduce((s, c) => s + (c.weight || 0), 0)) };
    });
  }

  // #50 — inline add
  function addMandatory(source: SourceKey) {
    const id = genId(source, "mandatory");
    const blank: MandatoryCheck = {
      check_id: id, name: "New requirement", description: "", what_passes: "",
      extraction_target_id: `ext-${id.toLowerCase()}`, source, is_locked: false,
    };
    setSetup(prev => prev ? { ...prev, mandatory_checks: [...prev.mandatory_checks, blank] } : prev);
  }

  function addScoring(source: SourceKey) {
    const id = genId(source, "scoring");
    const blank: ScoringCriterion = {
      criterion_id: id, name: "New criterion", weight: 0,
      source, is_locked: false,
    };
    setSetup(prev => {
      if (!prev) return prev;
      const updated = [...prev.scoring_criteria, blank];
      return { ...prev, scoring_criteria: updated, total_weight: round3(updated.reduce((s, c) => s + (c.weight || 0), 0)) };
    });
  }

  function autoBalance() {
    setSetup(prev => {
      if (!prev || !prev.scoring_criteria.length) return prev;
      const n = prev.scoring_criteria.length;
      const even = round3(1.0 / n);
      const balanced = prev.scoring_criteria.map((c, i) => ({
        ...c, weight: i === n - 1 ? round3(1.0 - even * (n - 1)) : even,
      }));
      return { ...prev, scoring_criteria: balanced, total_weight: 1.0 };
    });
    setWeightWarning(false);
  }

  // ── Confirm action ────────────────────────────────────────────────────────

  async function handleConfirm() {
    if (!setup) return;
    setConfirmError("");
    setRfpCheckError(false);

    // #52 — RFP identity check
    if (!rfpConfirmed) {
      setRfpCheckError(true);
      return;
    }

    const total = setup.scoring_criteria.reduce((s, c) => s + (c.weight || 0), 0);
    if (Math.abs(total - 1.0) > 0.02) {
      setWeightWarning(true);
      return;
    }

    setWeightWarning(false);
    setConfirming(true);
    try {
      await api.put(`/api/v1/evaluate/${runId}/setup`, {
        body: { scoring_criteria: setup.scoring_criteria, mandatory_checks: setup.mandatory_checks },
        on401: onAuth401,
      });
      await api.post(`/api/v1/evaluate/${runId}/confirm`, { on401: onAuth401 });
      onConfirmed();
    } catch (err) {
      setConfirmError(err instanceof Error ? err.message : "Failed to start evaluation.");
    } finally {
      setConfirming(false);
    }
  }

  // ── Render ────────────────────────────────────────────────────────────────

  if (loading) {
    return (
      <div style={{ display: "flex", alignItems: "center", gap: 10, padding: "40px 0" }}>
        <Spinner size={14} color="var(--color-info)" />
        <p style={{ fontFamily: FONT, fontSize: 14, color: "var(--color-text-muted)" }}>Loading evaluation criteria…</p>
      </div>
    );
  }

  if (loadError) {
    return (
      <div role="alert" style={{
        padding: "16px 20px", backgroundColor: "var(--color-surface)",
        borderTop: "1px solid var(--color-error)", borderBottom: "1px solid var(--color-error)",
        borderLeft: "3px solid var(--color-error)", borderRight: "1px solid var(--color-error)",
        borderRadius: "var(--radius)", fontFamily: FONT, fontSize: 13, color: "var(--color-error)",
      }}>
        {loadError}
      </div>
    );
  }

  if (!setup) return null;

  const currency = setup.currency || "GBP";
  const totalCriteria = setup.mandatory_checks.length + setup.scoring_criteria.length;
  const estMinutes = Math.max(2, Math.ceil((setup.vendor_count ?? 1) * totalCriteria * 0.05));
  const mandatoryCount = setup.mandatory_checks.length;
  const visibleDups = dupPairs.filter(p => !dismissedDups.has(p.idA + p.idB));

  return (
    <>
      <style>{`
        @keyframes csp-spin { to { transform: rotate(360deg); } }
      `}</style>

      <div className="w-full" style={{ maxWidth: 680 }}>
        {/* Back */}
        <button
          type="button" onClick={onBack}
          style={{
            background: "none", border: "none", cursor: "pointer",
            fontFamily: FONT, fontSize: 12, color: "var(--color-text-muted)",
            padding: 0, marginBottom: 20,
            display: "flex", alignItems: "center", gap: 4,
            transition: "color 150ms ease-out",
          }}
          onMouseEnter={e => { e.currentTarget.style.color = "var(--color-text-primary)"; }}
          onMouseLeave={e => { e.currentTarget.style.color = "var(--color-text-muted)"; }}
        >
          ← Back
        </button>

        {/* Header */}
        <div style={{ marginBottom: 28 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 8 }}>
            <h1 style={{
              fontFamily: DISPLAY, fontWeight: 800,
              fontSize: isMobile ? 22 : 28,
              letterSpacing: "-0.03em", lineHeight: 1.0,
              color: "var(--color-text-primary)", margin: 0,
            }}>
              Evaluation Setup
            </h1>
            <span style={{
              fontFamily: MONO, fontWeight: 600, fontSize: 10,
              letterSpacing: "0.06em", textTransform: "uppercase",
              color: "var(--color-warning)",
              padding: "2px 8px",
              borderTop: "1px solid var(--color-warning)",
              borderBottom: "1px solid var(--color-warning)",
              borderLeft: "1px solid var(--color-warning)",
              borderRight: "1px solid var(--color-warning)",
              borderRadius: 3,
            }}>pending confirm</span>
          </div>
          <p style={{ fontFamily: FONT, fontSize: 14, color: "var(--color-text-secondary)", lineHeight: 1.65, maxWidth: 520 }}>
            Review and adjust the criteria that will be used to evaluate each vendor. Locked criteria are set by your organisation.
          </p>
        </div>

        {/* RFP extraction in-progress banner */}
        {rfpPolling && (
          <div style={{
            marginBottom: 20, padding: "12px 16px",
            display: "flex", alignItems: "center", gap: 10,
            backgroundColor: "var(--color-surface)",
            borderTop: "1px solid var(--color-border)",
            borderBottom: "1px solid var(--color-border)",
            borderLeft: "3px solid var(--color-info)",
            borderRight: "1px solid var(--color-border)",
            borderRadius: "var(--radius)",
          }}>
            <Spinner size={12} color="var(--color-info)" />
            <div>
              <p style={{ fontFamily: FONT, fontWeight: 600, fontSize: 13, color: "var(--color-info)", lineHeight: 1 }}>
                Extracting criteria from your RFP…
              </p>
              <p style={{ fontFamily: FONT, fontSize: 12, color: "var(--color-text-muted)", lineHeight: 1.5, marginTop: 3 }}>
                The AI is reading your RFP to find additional requirements. This takes ~20 seconds. They will appear in the RFP-Extracted section below.
              </p>
            </div>
          </div>
        )}

        {/* #48 — Summary card */}
        <div style={{
          display: "grid",
          gridTemplateColumns: isMobile ? "1fr 1fr" : "repeat(4, 1fr)",
          gap: 1,
          marginBottom: 28,
          borderTop: "1px solid var(--color-border)",
          borderBottom: "1px solid var(--color-border)",
          borderLeft: "1px solid var(--color-border)",
          borderRight: "1px solid var(--color-border)",
          borderRadius: "var(--radius)",
          overflow: "hidden",
          backgroundColor: "var(--color-border)",
          boxShadow: "var(--shadow-sm)",
        }}>
          {[
            { label: "Vendors",   value: String(setup.vendor_count ?? 0) },
            { label: "Contract",  value: setup.contract_value != null ? formatCurrency(setup.contract_value, currency) : "—" },
            { label: "Criteria",  value: String(totalCriteria) },
            { label: "Est. time", value: `~${estMinutes} min` },
          ].map(item => (
            <div key={item.label} style={{ backgroundColor: "var(--color-surface)", padding: "14px 16px" }}>
              <div style={{ fontFamily: MONO, fontWeight: 700, fontSize: isMobile ? 17 : 20, color: "var(--color-text-primary)", fontVariantNumeric: "tabular-nums", letterSpacing: "-0.02em" }}>
                {item.value}
              </div>
              <div style={{ fontFamily: FONT, fontSize: 11, fontWeight: 500, letterSpacing: "0.05em", textTransform: "uppercase", color: "var(--color-text-muted)", marginTop: 3 }}>
                {item.label}
              </div>
            </div>
          ))}
        </div>

        {/* #52 — RFP identity checkbox */}
        {(setup.rfp_title || setup.department) && (
          <div style={{
            marginBottom: 20, padding: "14px 16px",
            backgroundColor: "var(--color-surface)",
            borderTop: rfpCheckError ? "1px solid var(--color-error)" : "1px solid var(--color-border)",
            borderBottom: rfpCheckError ? "1px solid var(--color-error)" : "1px solid var(--color-border)",
            borderLeft: rfpCheckError ? "3px solid var(--color-error)" : "1px solid var(--color-border)",
            borderRight: rfpCheckError ? "1px solid var(--color-error)" : "1px solid var(--color-border)",
            borderRadius: "var(--radius)",
            boxShadow: "var(--shadow-sm)",
          }}>
            <label style={{
              display: "flex", alignItems: "flex-start", gap: 10, cursor: "pointer",
            }}>
              <input
                type="checkbox"
                checked={rfpConfirmed}
                onChange={e => { setRfpConfirmed(e.target.checked); if (e.target.checked) setRfpCheckError(false); }}
                style={{ marginTop: 2, flexShrink: 0, accentColor: "var(--color-accent)", width: 15, height: 15 }}
              />
              <span style={{ fontFamily: FONT, fontSize: 13, color: "var(--color-text-secondary)", lineHeight: 1.6 }}>
                Confirm: this RFP is{" "}
                <strong style={{ color: "var(--color-text-primary)", fontWeight: 600 }}>
                  &ldquo;{setup.rfp_title}&rdquo;
                </strong>
                {setup.department && (
                  <>, department{" "}
                    <strong style={{ color: "var(--color-text-primary)", fontWeight: 600 }}>
                      {setup.department}
                    </strong>
                  </>
                )}
              </span>
            </label>
            {rfpCheckError && (
              <p role="alert" style={{ fontFamily: FONT, fontSize: 12, color: "var(--color-error)", marginTop: 8, marginLeft: 25 }}>
                Please confirm the RFP identity before starting the evaluation.
              </p>
            )}
          </div>
        )}

        {/* #53 — Mandatory rejection notice */}
        {mandatoryCount > 0 && (
          <div style={{
            marginBottom: 20, padding: "10px 14px",
            display: "flex", alignItems: "center", gap: 8,
            backgroundColor: "var(--color-surface)",
            borderTop: "1px solid var(--color-border)",
            borderBottom: "1px solid var(--color-border)",
            borderLeft: "3px solid var(--color-warning)",
            borderRight: "1px solid var(--color-border)",
            borderRadius: "var(--radius)",
          }}>
            <span style={{ fontSize: 14, flexShrink: 0 }}>⚑</span>
            <p style={{ fontFamily: FONT, fontSize: 12, color: "var(--color-text-secondary)", lineHeight: 1.55, margin: 0 }}>
              A vendor failing{" "}
              <strong style={{ color: "var(--color-warning)", fontWeight: 600 }}>
                any 1
              </strong>{" "}
              of these{" "}
              <strong style={{ color: "var(--color-text-primary)", fontWeight: 600 }}>
                {mandatoryCount} mandatory check{mandatoryCount !== 1 ? "s" : ""}
              </strong>{" "}
              is automatically rejected from the evaluation.
            </p>
          </div>
        )}

        {/* #51 — Near-duplicate warnings */}
        {visibleDups.map(pair => (
          <div
            key={pair.idA + pair.idB}
            role="alert"
            style={{
              marginBottom: 12, padding: "10px 14px",
              backgroundColor: "var(--color-surface)",
              borderTop: "1px solid var(--color-border)",
              borderBottom: "1px solid var(--color-border)",
              borderLeft: "3px solid var(--color-info)",
              borderRight: "1px solid var(--color-border)",
              borderRadius: "var(--radius)",
              display: "flex", alignItems: "flex-start", gap: 10,
            }}
          >
            <span style={{ fontSize: 14, flexShrink: 0, marginTop: 1 }}>⚠</span>
            <div style={{ flex: 1 }}>
              <p style={{ fontFamily: FONT, fontSize: 12, color: "var(--color-text-secondary)", lineHeight: 1.55, margin: 0 }}>
                <strong style={{ color: "var(--color-text-primary)" }}>&ldquo;{pair.a.name}&rdquo;</strong>
                {" "}({SOURCE_LABEL[pair.a.source] ?? pair.a.source}) and{" "}
                <strong style={{ color: "var(--color-text-primary)" }}>&ldquo;{pair.b.name}&rdquo;</strong>
                {" "}({SOURCE_LABEL[pair.b.source] ?? pair.b.source}) look similar — are these the same requirement?
              </p>
            </div>
            <button
              type="button"
              onClick={() => setDismissedDups(prev => new Set([...prev, pair.idA + pair.idB]))}
              aria-label="Dismiss warning"
              style={{
                background: "none", border: "none", cursor: "pointer",
                color: "var(--color-text-muted)", fontSize: 16, padding: "0 2px",
                flexShrink: 0, lineHeight: 1, transition: "color 150ms ease-out",
              }}
              onMouseEnter={e => { e.currentTarget.style.color = "var(--color-text-primary)"; }}
              onMouseLeave={e => { e.currentTarget.style.color = "var(--color-text-muted)"; }}
            >×</button>
          </div>
        ))}

        {/* 4 source sections */}
        {ALL_SOURCES.map(src => (
          <SourceSection
            key={src}
            sourceKey={src}
            mandatoryChecks={mandatoryBySource(src)}
            scoringCriteria={scoringBySource(src)}
            showRfpSpinner={src === "rfp" && rfpPolling}
            onUpdateMandatory={updateMandatory}
            onRemoveMandatory={removeMandatory}
            onUpdateScoring={updateScoring}
            onRemoveScoring={removeScoring}
            onAddMandatory={src === "dept" || src === "user" ? () => addMandatory(src) : undefined}
            onAddScoring={src === "dept" || src === "user" ? () => addScoring(src) : undefined}
          />
        ))}

        {/* #49 — Weight bar chart */}
        {setup.scoring_criteria.length > 0 && (
          <div style={{
            marginBottom: 16, padding: "14px 16px",
            backgroundColor: "var(--color-surface)",
            borderTop: "1px solid var(--color-border)",
            borderBottom: "1px solid var(--color-border)",
            borderLeft: "1px solid var(--color-border)",
            borderRight: "1px solid var(--color-border)",
            borderRadius: "var(--radius)",
            boxShadow: "var(--shadow-sm)",
          }}>
            <p style={{ fontFamily: FONT, fontWeight: 600, fontSize: 11, letterSpacing: "0.06em", textTransform: "uppercase", color: "var(--color-text-muted)", marginBottom: 12 }}>
              Scoring weight distribution
            </p>
            <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
              {[...setup.scoring_criteria]
                .sort((a, b) => b.weight - a.weight)
                .map(sc => (
                  <div key={sc.criterion_id} style={{ display: "flex", alignItems: "center", gap: 10 }}>
                    <span style={{
                      fontFamily: FONT, fontSize: 12, color: "var(--color-text-secondary)",
                      width: isMobile ? 100 : 160, flexShrink: 0,
                      overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap",
                    }}>
                      {sc.name}
                    </span>
                    <div style={{ flex: 1, height: 6, backgroundColor: "var(--color-surface-hover)", borderRadius: 3, overflow: "hidden" }}>
                      <div style={{
                        width: `${Math.min(100, (sc.weight / Math.max(scoringTotal, 0.001)) * 100).toFixed(1)}%`,
                        height: "100%",
                        backgroundColor: SOURCE_COLOR[(sc.source as SourceKey)] ?? "var(--color-accent)",
                        borderRadius: 3,
                        transition: "width 400ms ease-out",
                      }} />
                    </div>
                    <span style={{
                      fontFamily: MONO, fontWeight: 600, fontSize: 11,
                      color: "var(--color-text-muted)", width: 36, textAlign: "right", flexShrink: 0,
                      fontVariantNumeric: "tabular-nums",
                    }}>
                      {(sc.weight * 100).toFixed(0)}%
                    </span>
                  </div>
                ))}
            </div>
          </div>
        )}

        {/* Weight total + auto-balance */}
        {setup.scoring_criteria.length > 0 && (
          <div style={{
            display: "flex", alignItems: "center", justifyContent: "space-between",
            padding: "12px 16px",
            backgroundColor: "var(--color-surface)",
            borderTop: weightOff ? "1px solid var(--color-warning)" : "1px solid var(--color-border)",
            borderBottom: weightOff ? "1px solid var(--color-warning)" : "1px solid var(--color-border)",
            borderLeft: weightOff ? "3px solid var(--color-warning)" : "1px solid var(--color-border)",
            borderRight: weightOff ? "1px solid var(--color-warning)" : "1px solid var(--color-border)",
            borderRadius: "var(--radius)",
            marginBottom: 24,
            boxShadow: "var(--shadow-sm)",
          }}>
            <div>
              <span style={{
                fontFamily: FONT, fontWeight: 600, fontSize: 11,
                letterSpacing: "0.06em", textTransform: "uppercase",
                color: weightOff ? "var(--color-warning)" : "var(--color-text-muted)",
              }}>
                Total scoring weight
              </span>
              <span style={{
                fontFamily: MONO, fontWeight: 700, fontSize: 18,
                color: weightOff ? "var(--color-warning)" : "var(--color-success)",
                marginLeft: 12, fontVariantNumeric: "tabular-nums",
              }}>
                {scoringTotal.toFixed(3)}
              </span>
              {weightOff && (
                <span style={{ fontFamily: FONT, fontSize: 11, color: "var(--color-warning)", marginLeft: 8 }}>
                  (must equal 1.000)
                </span>
              )}
            </div>
            <button
              type="button" onClick={autoBalance}
              style={{
                padding: "6px 14px", backgroundColor: "transparent",
                borderTop: "1px solid var(--color-border)",
                borderBottom: "1px solid var(--color-border)",
                borderLeft: "1px solid var(--color-border)",
                borderRight: "1px solid var(--color-border)",
                borderRadius: "var(--radius)",
                fontFamily: FONT, fontWeight: 500, fontSize: 12,
                color: "var(--color-text-secondary)", cursor: "pointer",
                transition: "border-color 150ms ease-out, color 150ms ease-out",
              }}
              onMouseEnter={e => { e.currentTarget.style.borderTopColor = "var(--color-border-strong)"; e.currentTarget.style.borderBottomColor = "var(--color-border-strong)"; e.currentTarget.style.borderLeftColor = "var(--color-border-strong)"; e.currentTarget.style.borderRightColor = "var(--color-border-strong)"; e.currentTarget.style.color = "var(--color-text-primary)"; }}
              onMouseLeave={e => { e.currentTarget.style.borderTopColor = "var(--color-border)"; e.currentTarget.style.borderBottomColor = "var(--color-border)"; e.currentTarget.style.borderLeftColor = "var(--color-border)"; e.currentTarget.style.borderRightColor = "var(--color-border)"; e.currentTarget.style.color = "var(--color-text-secondary)"; }}
            >
              Auto-balance
            </button>
          </div>
        )}

        {/* Weight warning banner */}
        {weightWarning && (
          <div role="alert" style={{
            marginBottom: 16, padding: "10px 14px",
            backgroundColor: "var(--color-surface)",
            borderTop: "1px solid var(--color-warning)",
            borderBottom: "1px solid var(--color-warning)",
            borderLeft: "3px solid var(--color-warning)",
            borderRight: "1px solid var(--color-warning)",
            borderRadius: "var(--radius)",
            fontFamily: FONT, fontSize: 13, color: "var(--color-warning)",
          }}>
            Scoring weights must sum to 1.00 before confirming. Use Auto-balance to fix.
          </div>
        )}

        {/* Confirm error */}
        {confirmError && (
          <div role="alert" style={{
            marginBottom: 16, padding: "10px 14px",
            backgroundColor: "var(--color-surface)",
            borderTop: "1px solid var(--color-error)",
            borderBottom: "1px solid var(--color-error)",
            borderLeft: "3px solid var(--color-error)",
            borderRight: "1px solid var(--color-error)",
            borderRadius: "var(--radius)",
            fontFamily: FONT, fontSize: 13, color: "var(--color-error)",
          }}>
            {confirmError}
          </div>
        )}

        {/* Confirm button */}
        <button
          type="button" onClick={handleConfirm} disabled={confirming}
          style={{
            width: "100%", padding: "13px 24px",
            backgroundColor: confirming ? "var(--color-surface)" : "var(--color-accent)",
            color: confirming ? "var(--color-text-muted)" : "var(--color-accent-foreground)",
            borderTop: "1px solid var(--color-border)",
            borderBottom: "1px solid var(--color-border)",
            borderLeft: "1px solid var(--color-border)",
            borderRight: "1px solid var(--color-border)",
            borderRadius: "var(--radius)",
            fontFamily: FONT, fontWeight: 600, fontSize: 14,
            cursor: confirming ? "not-allowed" : "pointer",
            display: "flex", alignItems: "center", justifyContent: "center", gap: 8,
            boxShadow: confirming ? "none" : "var(--shadow-sm)",
            transition: "opacity 150ms ease-out, transform 150ms ease-out",
          }}
          onMouseEnter={e => { if (!confirming) { e.currentTarget.style.opacity = "0.88"; e.currentTarget.style.transform = "translateY(-1px)"; } }}
          onMouseLeave={e => { e.currentTarget.style.opacity = "1"; e.currentTarget.style.transform = "translateY(0)"; }}
        >
          {confirming && <Spinner size={13} color="var(--color-text-muted)" />}
          {confirming ? "Starting evaluation…" : "Confirm & Start Evaluation →"}
        </button>
      </div>
    </>
  );
}
