"use client";

import { useEffect, useRef, useState, useCallback } from "react";
import { FONT, DISPLAY, MONO } from "@/lib/theme";
import { useBreakpoint } from "@/lib/hooks";
import { api } from "@/lib/api";
import { formatCurrency } from "@/lib/utils";
import { SOURCE_LABEL, SOURCE_COLOR, ALL_SOURCES } from "./_confirm/confirmStyles";
import { round3, genId, findDupPairs } from "./_confirm/confirmHelpers";
import { Spinner } from "./_confirm/Spinner";
import { SourceSection } from "./_confirm/SourceSection";
import { GapsSection } from "./_confirm/GapsSection";
import type { SourceKey, MandatoryCheck, ScoringCriterion, EvaluationSetup, DupPair } from "./_confirm/types";

interface CostEstimate {
  estimated_cost_low_usd: number;
  estimated_cost_high_usd: number;
  model: string;
  vendor_count: number;
}

function CostEstimateBanner({ runId }: { runId: string }) {
  const [est, setEst] = useState<CostEstimate | null>(null);

  useEffect(() => {
    api.get<CostEstimate>(`/api/v1/evaluate/${runId}/cost-estimate`)
      .then(setEst)
      .catch(() => {});
  }, [runId]);

  if (!est) return null;

  const low  = `$${est.estimated_cost_low_usd.toFixed(3)}`;
  const high = `$${est.estimated_cost_high_usd.toFixed(3)}`;

  return (
    <div style={{
      marginBottom: 20, padding: "10px 16px",
      display: "flex", alignItems: "center", gap: 10,
      backgroundColor: "var(--color-surface)",
      borderTop: "1px solid var(--color-border)",
      borderBottom: "1px solid var(--color-border)",
      borderLeft: "3px solid var(--color-info)",
      borderRight: "1px solid var(--color-border)",
      borderRadius: "var(--radius)",
    }}>
      <div>
        <span style={{
          fontFamily: FONT, fontWeight: 600, fontSize: 12,
          color: "var(--color-text-primary)",
        }}>
          Estimated LLM cost:{" "}
        </span>
        <span style={{
          fontFamily: MONO, fontWeight: 700, fontSize: 12,
          color: "var(--color-info)", fontVariantNumeric: "tabular-nums",
        }}>
          {low} – {high}
        </span>
        <span style={{
          fontFamily: FONT, fontSize: 11, color: "var(--color-text-muted)", marginLeft: 6,
        }}>
          for {est.vendor_count} vendor{est.vendor_count !== 1 ? "s" : ""} · {est.model}
        </span>
      </div>
    </div>
  );
}

interface ConfirmSetupPageProps {
  runId: string;
  onConfirmed: () => void;
  onBack: () => void;
  onAuth401: () => void;
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
  const [rfpConfirmed, setRfpConfirmed] = useState(false);
  const [rfpCheckError, setRfpCheckError] = useState(false);
  const [dupPairs, setDupPairs] = useState<DupPair[]>([]);
  const [dismissedDups, setDismissedDups] = useState<Set<string>>(new Set());
  const [gapsAcknowledged, setGapsAcknowledged] = useState(false);
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
  //
  // fetchSetup polls itself via setTimeout when the backend is still
  // merging extracted RFP criteria. Recursive useCallback would trigger
  // "Cannot access variable before declared" (TDZ) at line 124 since
  // `fetchSetup` is the name being defined. Solve via a ref that always
  // points at the latest closure.

  const fetchSetupRef = useRef<((isRefresh?: boolean) => Promise<void>) | null>(null);

  const fetchSetup = useCallback(async (isRefresh = false) => {
    try {
      const data = await api.get<EvaluationSetup>(`/api/v1/evaluate/${runId}/setup`, { on401: onAuth401 });
      setSetup(data);
      if (!isRefresh) {
        setLoading(false);
        setDupPairs(findDupPairs(data));
      }
      if (data.source === "merged" || data.source === "merged_empty") {
        if (pollCountRef.current < 10) {
          setRfpPolling(true);
          pollRef.current = setTimeout(() => {
            pollCountRef.current += 1;
            fetchSetupRef.current?.(true);
          }, 3000);
        } else {
          setRfpPolling(false);
        }
      } else {
        setRfpPolling(false);
        if (isRefresh) setDupPairs(findDupPairs(data));
      }
    } catch (err) {
      if (!isRefresh) {
        setLoadError(err instanceof Error ? err.message : "Failed to load criteria.");
        setLoading(false);
      }
    }
  }, [runId, onAuth401]);

  // Keep the ref pointing at the latest closure so the setTimeout callback
  // always calls the current version (closure capture is intentional here).
  useEffect(() => { fetchSetupRef.current = fetchSetup; }, [fetchSetup]);

  useEffect(() => {
    // fetchSetup is async — all setState calls inside it run AFTER the
    // first await, well after this effect commits. The linter's static
    // analysis cannot see through `async`, so we suppress here.
    // eslint-disable-next-line react-hooks/set-state-in-effect
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

    if (!rfpConfirmed) {
      setRfpCheckError(true);
      return;
    }

    const gaps = setup.gaps_report;
    const hasGaps = gaps?.has_gaps &&
      (gaps.score_guides_generated.length + gaps.mandatory_checks_suggested.length) > 0;
    if (hasGaps && !gapsAcknowledged) {
      setConfirmError("Please review and acknowledge the AI-generated criteria before confirming.");
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
  const gaps = setup.gaps_report;
  const hasGaps = !!(gaps?.has_gaps &&
    (gaps.score_guides_generated.length + gaps.mandatory_checks_suggested.length) > 0);
  const confirmBlocked = confirming || (hasGaps && !gapsAcknowledged);

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

        {/* Summary card */}
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

        {/* Cost estimate banner */}
        <CostEstimateBanner runId={runId} />

        {/* RFP identity confirmation */}
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
            <label style={{ display: "flex", alignItems: "flex-start", gap: 10, cursor: "pointer" }}>
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

        {/* Mandatory rejection notice */}
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
              <strong style={{ color: "var(--color-warning)", fontWeight: 600 }}>any 1</strong>{" "}
              of these{" "}
              <strong style={{ color: "var(--color-text-primary)", fontWeight: 600 }}>
                {mandatoryCount} mandatory check{mandatoryCount !== 1 ? "s" : ""}
              </strong>{" "}
              is automatically rejected from the evaluation.
            </p>
          </div>
        )}

        {/* Near-duplicate warnings */}
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

        {/* Gaps / AI-generated section */}
        {setup.gaps_report?.has_gaps && (
          <GapsSection
            gaps={setup.gaps_report}
            acknowledged={gapsAcknowledged}
            onAcknowledge={setGapsAcknowledged}
          />
        )}

        {/* Source sections */}
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

        {/* Weight bar chart */}
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

        {/* Weight warning */}
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
        {hasGaps && !gapsAcknowledged && (
          <p style={{
            fontFamily: FONT, fontSize: 12, color: "var(--color-warning)",
            marginBottom: 12, display: "flex", alignItems: "center", gap: 6,
          }}>
            <span>⚠</span>
            Acknowledge the AI-generated criteria above before confirming.
          </p>
        )}
        <button
          type="button" onClick={handleConfirm} disabled={confirmBlocked}
          style={{
            width: "100%", padding: "13px 24px",
            backgroundColor: confirmBlocked ? "var(--color-surface)" : "var(--color-accent)",
            color: confirmBlocked ? "var(--color-text-muted)" : "var(--color-accent-foreground)",
            borderTop: "1px solid var(--color-border)",
            borderBottom: "1px solid var(--color-border)",
            borderLeft: "1px solid var(--color-border)",
            borderRight: "1px solid var(--color-border)",
            borderRadius: "var(--radius)",
            fontFamily: FONT, fontWeight: 600, fontSize: 14,
            cursor: confirmBlocked ? "not-allowed" : "pointer",
            display: "flex", alignItems: "center", justifyContent: "center", gap: 8,
            boxShadow: confirmBlocked ? "none" : "var(--shadow-sm)",
            transition: "opacity 150ms ease-out, transform 150ms ease-out",
          }}
          onMouseEnter={e => { if (!confirmBlocked) { e.currentTarget.style.opacity = "0.88"; e.currentTarget.style.transform = "translateY(-1px)"; } }}
          onMouseLeave={e => { e.currentTarget.style.opacity = "1"; e.currentTarget.style.transform = "translateY(0)"; }}
        >
          {confirming && <Spinner size={13} color="var(--color-text-muted)" />}
          {confirming ? "Starting evaluation…" : "Confirm & Start Evaluation →"}
        </button>
      </div>
    </>
  );
}
