"use client";

import { useEffect, useState, useCallback } from "react";
import { useParams, useRouter } from "next/navigation";
import { TopBar } from "@/components/TopBar";
import { useThemeContext } from "@/components/ThemeProvider";
import { PALETTE, PALETTE_LIGHT, FONT, MONO, TOKENS } from "@/lib/theme";

const API = process.env.NEXT_PUBLIC_API_URL ?? "";
function getToken() { return typeof window !== "undefined" ? (localStorage.getItem("access_token") ?? "") : ""; }

// ── Types ──────────────────────────────────────────────────────────────────────

interface MandatoryCheck {
  check_id: string;
  name: string;
  description: string;
  what_passes: string;
  source?: string;
  is_locked?: boolean;
  page_reference?: string;
}

interface ScoringCriterion {
  criterion_id: string;
  name: string;
  weight: number;
  rubric_9_10?: string;
  rubric_6_8?: string;
  rubric_3_5?: string;
  rubric_0_2?: string;
  source?: string;
  is_locked?: boolean;
  page_reference?: string;
}

interface EvaluationSetup {
  setup_id: string;
  department: string;
  rfp_id: string;
  mandatory_checks: MandatoryCheck[];
  scoring_criteria: ScoringCriterion[];
  total_weight: number;
  confirmed_by: string;
  source?: string;
}

// ── Helpers ────────────────────────────────────────────────────────────────────

function uid() { return Math.random().toString(36).slice(2, 10).toUpperCase(); }

function SectionLabel({ children, isDark }: { children: React.ReactNode; isDark: boolean }) {
  const P = isDark ? PALETTE : PALETTE_LIGHT;
  return (
    <div style={{ fontSize: 10, fontWeight: 700, color: P.text.muted, letterSpacing: "0.07em", textTransform: "uppercase", marginBottom: 12, fontFamily: FONT }}>
      {children}
    </div>
  );
}

function SourceLegend() {
  const items = [
    { key: "org",  label: "Organisation", color: "var(--color-text-muted)"    },
    { key: "dept", label: "Department",   color: "var(--color-warning)"       },
    { key: "rfp",  label: "From RFP",     color: "var(--color-accent)"        },
    { key: "user", label: "Added by you", color: "var(--color-info)"          },
  ];
  return (
    <div style={{ display: "flex", gap: 10, flexWrap: "wrap", marginBottom: 12 }}>
      {items.map(item => (
        <span key={item.key} style={{ fontSize: 10, color: item.color, fontFamily: FONT, display: "flex", alignItems: "center", gap: 4 }}>
          <span style={{ width: 6, height: 6, borderRadius: "50%", background: item.color, display: "inline-block" }} />
          {item.label}
        </span>
      ))}
    </div>
  );
}

function SourceBadge({ source, isLocked }: { source?: string; isLocked?: boolean }) {
  if (!source) return null;
  const map: Record<string, { label: string; bg: string; color: string; border: string }> = {
    org:  { label: "Organisation", bg: "var(--color-text-muted)18",    color: "var(--color-text-muted)",    border: "var(--color-text-muted)40"    },
    dept: { label: "Department",   bg: "var(--color-warning)18",       color: "var(--color-warning)",       border: "var(--color-warning)40"       },
    rfp:  { label: "From RFP",     bg: "var(--color-accent)18",        color: "var(--color-accent)",        border: "var(--color-accent)40"        },
    user: { label: "Added by you", bg: "var(--color-info)18",          color: "var(--color-info)",          border: "var(--color-info)40"          },
  };
  const style = map[source];
  if (!style) return null;
  return (
    <span style={{
      background: style.bg, border: `1px solid ${style.border}`,
      borderRadius: 20, padding: "2px 8px",
      fontSize: 10, color: style.color, fontWeight: 600, fontFamily: FONT,
    }}>
      {style.label}{isLocked ? " 🔒" : ""}
    </span>
  );
}

function WeightBar({ totalPct, isDark }: { totalPct: number; isDark: boolean }) {
  const P = isDark ? PALETTE : PALETTE_LIGHT;
  const over  = totalPct > 100;
  const exact = totalPct === 100;
  const color = exact ? "var(--color-success)" : over ? "var(--color-error)" : "var(--color-warning)";
  const label = exact
    ? "Weights confirmed"
    : over
    ? `${totalPct - 100}% over — reduce a weight`
    : `${100 - totalPct}% unallocated`;
  const fillPct = Math.min(totalPct, 100);
  return (
    <div style={{ marginBottom: 14 }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 6 }}>
        <span style={{ fontSize: 12, color, fontFamily: FONT, fontWeight: 600 }}>{label}</span>
        <span style={{ fontSize: 13, fontFamily: MONO, fontWeight: 700, color }}>{totalPct}%</span>
      </div>
      <div style={{ height: 6, borderRadius: 3, background: P.border.dim, overflow: "hidden" }}>
        <div style={{ height: "100%", width: `${fillPct}%`, background: color, borderRadius: 3, transition: "width 200ms, background 200ms" }} />
      </div>
    </div>
  );
}

// ── Page ───────────────────────────────────────────────────────────────────────

export default function ConfirmPage() {
  const { runId }      = useParams<{ runId: string }>();
  const router         = useRouter();
  const { isDark } = useThemeContext();
  const P          = isDark ? PALETTE : PALETTE_LIGHT;

  const [setup,        setSetup]        = useState<EvaluationSetup | null>(null);
  const [loading,      setLoading]      = useState(true);
  const [confirming,   setConfirming]   = useState(false);
  const [error,        setError]        = useState("");
  const [editMode,     setEditMode]     = useState(false);
  const [saving,       setSaving]       = useState(false);

  // editable local copies
  const [checks,    setChecks]    = useState<MandatoryCheck[]>([]);
  const [criteria,  setCriteria]  = useState<ScoringCriterion[]>([]);

  const BG = "var(--bg-gradient)";

  const CARD = {
    background: P.bg.surface, borderRadius: TOKENS.radius.card,
    border: `1px solid ${P.border.mid}`, padding: "20px 22px",
  };

  useEffect(() => {
    fetch(`${API}/api/v1/evaluate/${runId}/setup`, {
      headers: { Authorization: `Bearer ${getToken()}` },
    })
      .then(r => { if (!r.ok) throw new Error(`${r.status}`); return r.json(); })
      .then((d: EvaluationSetup) => {
        setSetup(d);
        setChecks(d.mandatory_checks ?? []);
        setCriteria(d.scoring_criteria ?? []);
        setLoading(false);
      })
      .catch(e => { setError(`Failed to load setup: ${e.message}`); setLoading(false); });
  }, [runId]);

  const totalPct = Math.round(criteria.reduce((s, c) => s + c.weight, 0) * 100);
  const weightOk = totalPct === 100 || criteria.length === 0;

  // ── Edit helpers ─────────────────────────────────────────────────────────────

  function enterEdit() { setEditMode(true); setError(""); }

  function cancelEdit() {
    if (!setup) return;
    setChecks(setup.mandatory_checks ?? []);
    setCriteria(setup.scoring_criteria ?? []);
    setEditMode(false);
  }

  const saveEdit = useCallback(async () => {
    setSaving(true);
    setError("");
    try {
      const res = await fetch(`${API}/api/v1/evaluate/${runId}/setup`, {
        method: "PUT",
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${getToken()}` },
        body: JSON.stringify({ scoring_criteria: criteria, mandatory_checks: checks }),
      });
      if (!res.ok) {
        const msg = await res.text();
        throw new Error(`Save failed (${res.status}): ${msg}`);
      }
      setSetup(prev => prev ? { ...prev, mandatory_checks: checks, scoring_criteria: criteria, source: "manually_edited" } : prev);
      setEditMode(false);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Save failed");
    } finally {
      setSaving(false);
    }
  }, [runId, checks, criteria]);

  // Scoring criterion field updates
  function updateCriterionName(id: string, name: string) {
    setCriteria(prev => prev.map(c => c.criterion_id === id ? { ...c, name } : c));
  }
  function updateCriterionWeight(id: string, pct: number) {
    const w = Math.max(0, Math.min(100, pct)) / 100;
    setCriteria(prev => prev.map(c => c.criterion_id === id ? { ...c, weight: parseFloat(w.toFixed(3)) } : c));
  }
  function deleteCriterion(id: string) {
    setCriteria(prev => prev.filter(c => c.criterion_id !== id));
  }
  function addCriterion() {
    const NEW_WEIGHT = 0.05;
    setCriteria(prev => {
      const currentTotal = prev.reduce((s, c) => s + c.weight, 0);
      const available = Math.max(0, 1 - currentTotal);
      const newWeight = Math.min(NEW_WEIGHT, available);
      // Proportionally reduce existing unlocked criteria to make room
      const toAbsorb = newWeight - Math.max(0, available - newWeight);
      const unlocked = prev.filter(c => !c.is_locked);
      const unlockedTotal = unlocked.reduce((s, c) => s + c.weight, 0);
      const rebalanced = unlockedTotal > 0 && toAbsorb > 0
        ? prev.map(c => c.is_locked ? c : {
            ...c,
            weight: parseFloat(Math.max(0, c.weight - toAbsorb * (c.weight / unlockedTotal)).toFixed(3)),
          })
        : prev;
      return [...rebalanced, {
        criterion_id: `SC-USER-${uid()}`,
        name: "New criterion",
        weight: parseFloat(newWeight.toFixed(3)),
        source: "user" as const,
        is_locked: false,
      }];
    });
  }

  // Mandatory check field updates
  function updateCheckName(id: string, name: string) {
    setChecks(prev => prev.map(c => c.check_id === id ? { ...c, name } : c));
  }
  function deleteCheck(id: string) {
    setChecks(prev => prev.filter(c => c.check_id !== id));
  }
  function addCheck() {
    setChecks(prev => [...prev, {
      check_id: `MC-USER-${uid()}`,
      name: "New mandatory check",
      description: "",
      what_passes: "",
      source: "user",
      is_locked: false,
    }]);
  }

  // ── Confirm ──────────────────────────────────────────────────────────────────

  async function handleConfirm() {
    setConfirming(true);
    setError("");
    try {
      const res = await fetch(`${API}/api/v1/evaluate/${runId}/confirm`, {
        method: "POST",
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${getToken()}` },
      });
      if (!res.ok) throw new Error(`Confirm failed (${res.status})`);
      router.push(`/${runId}/progress`);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Confirmation failed");
      setConfirming(false);
    }
  }

  // ── Loading / error states ───────────────────────────────────────────────────

  if (loading) return (
    <div style={{ minHeight: "100vh", background: BG, fontFamily: FONT }}>
      <TopBar
        crumbs={[{ label: "Procurement", href: "/" }, { label: "Confirm setup" }]} />
      <div style={{ display: "flex", alignItems: "center", justifyContent: "center", height: "50vh" }}>
        <span style={{ color: P.text.muted, fontSize: 13 }}>Loading evaluation setup…</span>
      </div>
    </div>
  );

  if (!setup) return (
    <div style={{ minHeight: "100vh", background: BG, fontFamily: FONT }}>
      <TopBar
        crumbs={[{ label: "Procurement", href: "/" }, { label: "Confirm setup" }]} />
      <div style={{ display: "flex", alignItems: "center", justifyContent: "center", height: "50vh" }}>
        <span style={{ color: "var(--color-error)", fontSize: 13 }}>{error || "Setup not found."}</span>
      </div>
    </div>
  );

  // ── Render ───────────────────────────────────────────────────────────────────

  const inputStyle = (disabled: boolean) => ({
    background: disabled ? P.bg.elevated : P.bg.surface,
    border: `1px solid ${P.border.mid}`,
    borderRadius: 6, padding: "6px 10px",
    fontSize: 13, color: disabled ? P.text.muted : P.text.primary,
    fontFamily: FONT, width: "100%", boxSizing: "border-box" as const,
    cursor: disabled ? "not-allowed" : "text",
  });

  const deleteBtn = (disabled: boolean, onClick: () => void) => (
    <button
      onClick={onClick}
      disabled={disabled}
      title={disabled ? "Locked — cannot delete" : "Delete"}
      style={{
        background: "transparent", border: `1px solid ${disabled ? "var(--color-border)" : "var(--color-error)60"}`,
        borderRadius: 6, padding: "5px 10px", fontSize: 12,
        color: disabled ? "var(--color-text-muted)" : "var(--color-error)",
        cursor: disabled ? "not-allowed" : "pointer", flexShrink: 0,
      }}
    >
      {disabled ? "🔒" : "✕"}
    </button>
  );

  return (
    <div style={{ minHeight: "100vh", background: BG, fontFamily: FONT }}>
      <TopBar
        crumbs={[
          { label: "Procurement", href: "/" },
          { label: "New evaluation", href: "/procurement/upload" },
          { label: "Confirm setup" },
        ]} />

      <main style={{ maxWidth: 780, margin: "0 auto", padding: "36px 28px 80px", display: "flex", flexDirection: "column", gap: 18 }}>

        {/* Header card */}
        <div style={CARD}>
          <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", marginBottom: 12 }}>
            <div>
              <h1 style={{ fontSize: 18, fontWeight: 700, color: P.text.primary, margin: "0 0 4px", fontFamily: FONT }}>
                Confirm evaluation setup
              </h1>
              <p style={{ fontSize: 12, color: P.text.muted, margin: 0 }}>
                Review and optionally edit criteria before the pipeline starts.
              </p>
            </div>
            <span style={{
              background: "var(--color-accent)18", border: "1px solid var(--color-accent)40",
              borderRadius: 20, padding: "4px 12px",
              fontSize: 11, color: "var(--color-accent)", fontWeight: 600, fontFamily: FONT, flexShrink: 0,
            }}>
              Identity confirmed
            </span>
          </div>
          <div style={{ display: "flex", gap: 24, flexWrap: "wrap" }}>
            {([
              ["RFP", setup.rfp_id],
              ["Department", setup.department],
              ["Setup ID", setup.setup_id],
              ["Criteria source", setup.source ?? "merged"],
            ] as [string, string][]).map(([k, v]) => (
              <div key={k}>
                <div style={{ fontSize: 10, fontWeight: 600, color: P.text.muted, letterSpacing: "0.06em", textTransform: "uppercase", fontFamily: FONT }}>{k}</div>
                <div style={{ fontSize: 13, color: P.text.primary, fontFamily: MONO, marginTop: 2 }}>{v}</div>
              </div>
            ))}
          </div>
        </div>

        {/* Edit mode toggle */}
        <div style={{ display: "flex", justifyContent: "flex-end", gap: 8 }}>
          {editMode ? (
            <>
              <button onClick={cancelEdit} style={{
                background: "transparent", border: `1px solid ${P.border.mid}`,
                borderRadius: TOKENS.radius.btn, padding: "8px 16px",
                fontSize: 12, fontFamily: FONT, color: P.text.secondary, cursor: "pointer",
              }}>
                Cancel
              </button>
              <button onClick={saveEdit} disabled={saving} style={{
                background: saving ? "var(--color-border)" : "var(--color-info)",
                color: saving ? "var(--color-text-muted)" : "var(--color-accent-foreground)",
                border: "none", borderRadius: TOKENS.radius.btn,
                padding: "8px 16px", fontSize: 12, fontFamily: FONT, fontWeight: 600,
                cursor: saving ? "not-allowed" : "pointer",
              }}>
                {saving ? "Saving…" : "Save changes"}
              </button>
            </>
          ) : (
            <button onClick={enterEdit} style={{
              background: "transparent", border: `1px solid ${P.border.mid}`,
              borderRadius: TOKENS.radius.btn, padding: "8px 16px",
              fontSize: 12, fontFamily: FONT, color: P.text.secondary, cursor: "pointer",
            }}>
              Edit criteria
            </button>
          )}
        </div>

        {/* Mandatory checks */}
        <div style={CARD}>
          <SectionLabel isDark={isDark}>Mandatory checks — {checks.length} criteria</SectionLabel>
          <SourceLegend />
          <p style={{ fontSize: 12, color: P.text.muted, marginBottom: 14, fontFamily: FONT }}>
            Vendors failing any of these checks are rejected before scoring begins.
          </p>
          <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
            {checks.map(c => (
              <div key={c.check_id} style={{
                background: P.bg.elevated, borderRadius: 8,
                border: `1px solid ${P.border.dim}`, padding: "12px 14px",
              }}>
                <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: editMode ? 8 : 5, flexWrap: "wrap" }}>
                  <span style={{ fontFamily: MONO, fontSize: 10, color: P.text.muted, background: P.bg.elevated, padding: "2px 7px", borderRadius: 4 }}>
                    {c.check_id}
                  </span>
                  {!editMode && (
                    <span style={{ fontSize: 13, fontWeight: 600, color: P.text.primary, fontFamily: FONT }}>{c.name}</span>
                  )}
                  <SourceBadge source={c.source} isLocked={c.is_locked} />
                  {c.page_reference && (
                    <span style={{ fontSize: 10, color: P.text.muted, fontFamily: MONO }}>p. {c.page_reference}</span>
                  )}
                </div>
                {editMode ? (
                  <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
                    <input
                      value={c.name}
                      disabled={!!c.is_locked}
                      onChange={e => updateCheckName(c.check_id, e.target.value)}
                      style={{ ...inputStyle(!!c.is_locked), flex: 1 }}
                    />
                    {deleteBtn(!!c.is_locked, () => deleteCheck(c.check_id))}
                  </div>
                ) : (
                  <>
                    <p style={{ fontSize: 12, color: P.text.muted, margin: "0 0 5px", fontFamily: FONT }}>{c.description}</p>
                    <p style={{ fontSize: 12, color: "var(--color-success)", margin: 0, fontFamily: FONT }}>✓ Passes when: {c.what_passes}</p>
                  </>
                )}
              </div>
            ))}
          </div>
          {editMode && (
            <button onClick={addCheck} style={{
              marginTop: 10, background: "transparent",
              border: `1px dashed ${P.border.mid}`, borderRadius: 8,
              padding: "8px 14px", fontSize: 12, color: P.text.muted,
              fontFamily: FONT, cursor: "pointer", width: "100%",
            }}>
              + Add mandatory check
            </button>
          )}
        </div>

        {/* Scoring rubric */}
        <div style={CARD}>
          <SectionLabel isDark={isDark}>Scoring criteria — {criteria.length} weighted</SectionLabel>
          <WeightBar totalPct={totalPct} isDark={isDark} />
          <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
            {criteria.map(c => {
              const pct = Math.round(c.weight * 100);
              return (
                <div key={c.criterion_id} style={{
                  background: P.bg.elevated, borderRadius: 8,
                  border: `1px solid ${P.border.dim}`, padding: "10px 14px",
                }}>
                  {editMode ? (
                    <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
                      <input
                        value={c.name}
                        disabled={!!c.is_locked}
                        onChange={e => updateCriterionName(c.criterion_id, e.target.value)}
                        placeholder="Criterion name"
                        style={{ ...inputStyle(!!c.is_locked), flex: 1 }}
                      />
                      <div style={{ display: "flex", alignItems: "center", gap: 4, flexShrink: 0 }}>
                        <input
                          type="number"
                          min={0} max={100}
                          value={Math.round(c.weight * 100)}
                          disabled={!!c.is_locked}
                          onChange={e => updateCriterionWeight(c.criterion_id, parseFloat(e.target.value) || 0)}
                          style={{ ...inputStyle(!!c.is_locked), width: 64, textAlign: "right" }}
                        />
                        <span style={{ fontSize: 12, color: P.text.muted, fontFamily: MONO }}>%</span>
                      </div>
                      <SourceBadge source={c.source} isLocked={c.is_locked} />
                      {deleteBtn(!!c.is_locked, () => deleteCriterion(c.criterion_id))}
                    </div>
                  ) : (
                    <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
                      <div style={{ flex: 1 }}>
                        <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 5 }}>
                          <span style={{ fontSize: 13, color: P.text.primary, fontFamily: FONT }}>{c.name}</span>
                          <SourceBadge source={c.source} isLocked={c.is_locked} />
                          {c.page_reference && (
                            <span style={{ fontSize: 10, color: P.text.muted, fontFamily: MONO }}>p. {c.page_reference}</span>
                          )}
                        </div>
                        <div style={{ height: 4, borderRadius: 2, background: P.border.dim, overflow: "hidden" }}>
                          <div style={{ height: "100%", width: `${pct}%`, background: "var(--color-accent)", borderRadius: 2 }} />
                        </div>
                      </div>
                      <span style={{ fontFamily: MONO, fontSize: 14, fontWeight: 600, color: "var(--color-accent)", flexShrink: 0 }}>{pct}%</span>
                    </div>
                  )}
                </div>
              );
            })}
          </div>
          {editMode && (
            <button onClick={addCriterion} style={{
              marginTop: 10, background: "transparent",
              border: `1px dashed ${P.border.mid}`, borderRadius: 8,
              padding: "8px 14px", fontSize: 12, color: P.text.muted,
              fontFamily: FONT, cursor: "pointer", width: "100%",
            }}>
              + Add scoring criterion
            </button>
          )}
        </div>

        {/* Error */}
        {error && (
          <div style={{ background: "var(--color-error)14", border: "1px solid var(--color-error)", borderRadius: 8, padding: "10px 14px", fontSize: 13, color: "var(--color-error)", fontFamily: FONT }}>
            {error}
          </div>
        )}

        {/* Actions */}
        <div style={{ display: "flex", gap: 12 }}>
          <button onClick={() => router.back()} style={{
            background: "transparent", border: `1px solid ${P.border.mid}`,
            borderRadius: TOKENS.radius.btn, padding: "10px 20px",
            fontSize: 13, fontFamily: FONT, color: P.text.secondary, cursor: "pointer",
          }}>
            ← Back
          </button>
          <button
            onClick={handleConfirm}
            disabled={confirming || editMode || !weightOk}
            title={
              editMode ? "Save changes before confirming" :
              !weightOk ? `Weights must sum to 100% (currently ${totalPct}%)` :
              undefined
            }
            style={{
              flex: 1,
              background: (confirming || editMode || !weightOk) ? "var(--color-border)" : "var(--color-accent)",
              color: (confirming || editMode || !weightOk) ? "var(--color-text-muted)" : "var(--color-accent-foreground)",
              border: "none", borderRadius: TOKENS.radius.btn,
              padding: "10px 20px", fontSize: 13, fontFamily: FONT, fontWeight: 600,
              cursor: (confirming || editMode || !weightOk) ? "not-allowed" : "pointer",
              transition: "background 160ms",
            }}
          >
            {confirming ? "Starting pipeline…" : "Confirm and start evaluation →"}
          </button>
        </div>

      </main>
    </div>
  );
}
