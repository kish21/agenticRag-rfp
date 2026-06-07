"use client";

/**
 * Reviewer correction screen (P1.9 / #60).
 *
 * A reviewer corrects ONE criterion score or mandatory pass/fail check for a
 * vendor, with a reason. The correction is stored org-scoped and fed back to the
 * Evaluation Agent as a calibration example for that same criterion/check on
 * future runs — the platform learns from its own reviewers.
 *
 * Authorization is enforced by the backend (admin-only POST /correct); a 403 is
 * surfaced inline rather than guessing role names here.
 */

import { useEffect, useMemo, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import Link from "next/link";
import { api, isLoggedIn, ApiError } from "@/lib/api";
import { FONT, DISPLAY, MONO } from "@/lib/theme";
import { useBreakpoint } from "@/lib/hooks";

type TargetType = "criterion" | "check";

interface VendorRow { vendor_id: string; vendor_name: string }
interface SetupCriterion { criterion_id: string; name: string }
interface SetupCheck { check_id: string; name: string }
interface CorrectionRow {
  correction_id: string;
  target_type: TargetType;
  target_id: string;
  target_name?: string;
  vendor_id?: string;
  corrected_value?: Record<string, unknown>;
  reason: string;
  corrected_by?: string;
  created_at?: string;
}

const CHECK_DECISIONS = [
  { value: "pass", label: "Pass", color: "var(--color-success)" },
  { value: "fail", label: "Fail", color: "var(--color-error)" },
  { value: "insufficient_evidence", label: "Insufficient", color: "var(--color-warning)" },
];
const MIN_REASON = 20;

export default function OverridePage() {
  const params = useParams();
  const router = useRouter();
  const bp = useBreakpoint();
  const runId = params?.runId as string | undefined;

  const pad = bp === "mobile" ? "24px 20px" : bp === "tablet" ? "32px 24px" : "48px 32px";

  const [vendors, setVendors] = useState<VendorRow[]>([]);
  const [criteria, setCriteria] = useState<SetupCriterion[]>([]);
  const [checks, setChecks] = useState<SetupCheck[]>([]);
  const [existing, setExisting] = useState<CorrectionRow[]>([]);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [loaded, setLoaded] = useState(false);

  // form state
  const [vendorId, setVendorId] = useState("");
  const [targetType, setTargetType] = useState<TargetType>("criterion");
  const [targetId, setTargetId] = useState("");
  const [score, setScore] = useState<number | null>(null);
  const [decision, setDecision] = useState("");
  const [reason, setReason] = useState("");

  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [submitted, setSubmitted] = useState(false);

  async function loadCorrections() {
    if (!runId) return;
    const res = await api.get<{ corrections: CorrectionRow[] }>(
      `/api/v1/evaluate/${runId}/corrections`);
    setExisting(res.corrections ?? []);
  }

  useEffect(() => {
    if (!isLoggedIn()) { router.replace("/login"); return; }
    if (!runId) return;
    (async () => {
      try {
        const results = await api.get<{ decision?: Record<string, unknown> }>(
          `/api/v1/evaluate/${runId}/results`);
        const dec = (results.decision ?? {}) as Record<string, unknown>;
        const sl = (dec.shortlisted_vendors as Record<string, unknown>[]) ?? [];
        const rj = (dec.rejected_vendors as Record<string, unknown>[]) ?? [];
        const rows: VendorRow[] = [...sl, ...rj]
          .filter((v) => v && v.vendor_id)
          .map((v) => ({
            vendor_id: String(v.vendor_id),
            vendor_name: String(v.vendor_name ?? v.vendor_id),
          }));
        setVendors(rows);

        const setup = await api.get<{
          scoring_criteria?: SetupCriterion[]; mandatory_checks?: SetupCheck[];
        }>(`/api/v1/evaluate/${runId}/setup`);
        setCriteria(setup.scoring_criteria ?? []);
        setChecks(setup.mandatory_checks ?? []);

        await loadCorrections();
      } catch (e) {
        setLoadError(e instanceof Error ? e.message : "Failed to load run details");
      } finally {
        setLoaded(true);
      }
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [runId, router]);

  const targetName = useMemo(() => {
    if (targetType === "criterion") return criteria.find((c) => c.criterion_id === targetId)?.name ?? "";
    return checks.find((c) => c.check_id === targetId)?.name ?? "";
  }, [targetType, targetId, criteria, checks]);

  const valueValid = targetType === "criterion" ? score !== null : decision !== "";
  const reasonValid = reason.trim().length >= MIN_REASON;
  const formValid = !!vendorId && !!targetId && valueValid && reasonValid && !submitting;

  function resetForm() {
    setTargetId(""); setScore(null); setDecision(""); setReason("");
  }

  async function submit() {
    if (!formValid || !runId) return;
    setSubmitting(true); setSubmitError(null); setSubmitted(false);
    try {
      const corrected_value = targetType === "criterion"
        ? { raw_score: score }
        : { decision };
      await api.post(`/api/v1/evaluate/${runId}/correct`, {
        body: {
          target_type: targetType,
          target_id: targetId,
          target_name: targetName,
          vendor_id: vendorId,
          corrected_value,
          reason: reason.trim(),
        },
      });
      setSubmitted(true);
      resetForm();
      await loadCorrections();
    } catch (e) {
      const msg = e instanceof ApiError
        ? (e.status === 403
            ? "You don't have permission to submit corrections for this run."
            : e.message)
        : "Failed to submit the correction.";
      setSubmitError(msg);
    } finally {
      setSubmitting(false);
    }
  }

  // ── styles shared by inputs ────────────────────────────────────────────────
  const labelStyle: React.CSSProperties = {
    display: "block", fontFamily: FONT, fontSize: 11, fontWeight: 600,
    letterSpacing: "0.08em", textTransform: "uppercase",
    color: "var(--color-text-muted)", marginBottom: 8,
  };
  const fieldStyle: React.CSSProperties = {
    width: "100%", padding: "10px 12px",
    backgroundColor: "var(--color-background)",
    borderTop: "1px solid var(--color-border)",
    borderBottom: "1px solid var(--color-border)",
    borderLeft: "1px solid var(--color-border)",
    borderRight: "1px solid var(--color-border)",
    borderRadius: "var(--radius)",
    fontFamily: FONT, fontSize: 14, color: "var(--color-text-primary)",
    outline: "none",
  };

  return (
    <div style={{
      minHeight: "100vh",
      backgroundColor: "var(--color-background)",
      background: "var(--bg-gradient)",
      padding: pad,
    }}>
      <div style={{ maxWidth: 720, margin: "0 auto" }}>

        <Link href={runId ? `/${runId}/results` : "/"} style={{
          display: "inline-flex", alignItems: "center", gap: 6,
          fontFamily: FONT, fontSize: 13, fontWeight: 500,
          color: "var(--color-text-muted)", textDecoration: "none", marginBottom: 32,
        }}>
          ← Back to results
        </Link>

        {/* Header */}
        <div style={{ marginBottom: 28 }}>
          <p style={{
            fontFamily: FONT, fontWeight: 600, fontSize: 11,
            letterSpacing: "0.1em", textTransform: "uppercase",
            color: "var(--color-accent)", marginBottom: 8,
          }}>
            Human review · teaches the AI
          </p>
          <h1 style={{
            fontFamily: DISPLAY, fontWeight: 800, fontSize: 34,
            letterSpacing: "-0.03em", lineHeight: 1.0,
            color: "var(--color-text-primary)", marginBottom: 12,
          }}>
            Correct an evaluation
          </h1>
          <p style={{ fontFamily: FONT, fontSize: 14, lineHeight: 1.6, color: "var(--color-text-muted)" }}>
            Disagree with a score or a pass/fail call? Record the right answer and why.
            Your correction becomes a private example that calibrates this evaluation for
            your organization next time — it never bypasses the AI&apos;s safeguards.
          </p>
        </div>

        {!loaded && !loadError && (
          <div style={{ display: "flex", alignItems: "center", gap: 10, padding: "32px 0" }}>
            <div className="oc-spin" />
            <p style={{ fontFamily: FONT, fontSize: 14, color: "var(--color-text-muted)" }}>Loading run…</p>
          </div>
        )}

        {loadError && (
          <div role="alert" style={alertStyle("var(--color-error)")}>
            <p style={{ fontFamily: FONT, fontSize: 14, color: "var(--color-error)" }}>{loadError}</p>
          </div>
        )}

        {loaded && !loadError && (
          <>
            {/* Form card */}
            <div style={{
              backgroundColor: "var(--color-surface)",
              borderTop: "2px solid var(--color-accent)",
              borderBottom: "1px solid var(--color-border)",
              borderLeft: "1px solid var(--color-border)",
              borderRight: "1px solid var(--color-border)",
              borderRadius: "var(--radius)",
              boxShadow: "var(--shadow-md)",
              padding: bp === "mobile" ? 20 : 28,
              marginBottom: 40,
            }}>
              {/* Vendor */}
              <div style={{ marginBottom: 22 }}>
                <label htmlFor="oc-vendor" style={labelStyle}>Vendor</label>
                <select id="oc-vendor" value={vendorId}
                  onChange={(e) => setVendorId(e.target.value)} style={fieldStyle}>
                  <option value="">Select a vendor…</option>
                  {vendors.map((v) => (
                    <option key={v.vendor_id} value={v.vendor_id}>{v.vendor_name}</option>
                  ))}
                </select>
              </div>

              {/* What to correct — segmented toggle */}
              <div style={{ marginBottom: 22 }}>
                <span style={labelStyle}>What to correct</span>
                <div role="tablist" aria-label="Correction type" style={{ display: "flex", gap: 8 }}>
                  {(["criterion", "check"] as TargetType[]).map((t) => {
                    const active = targetType === t;
                    return (
                      <button key={t} role="tab" aria-selected={active} type="button"
                        onClick={() => { setTargetType(t); setTargetId(""); setScore(null); setDecision(""); }}
                        className="oc-seg"
                        style={{
                          flex: 1, padding: "10px 12px", cursor: "pointer",
                          fontFamily: FONT, fontSize: 13, fontWeight: 600,
                          borderRadius: "var(--radius)",
                          borderTop: `1px solid ${active ? "var(--color-accent)" : "var(--color-border)"}`,
                          borderBottom: `1px solid ${active ? "var(--color-accent)" : "var(--color-border)"}`,
                          borderLeft: `1px solid ${active ? "var(--color-accent)" : "var(--color-border)"}`,
                          borderRight: `1px solid ${active ? "var(--color-accent)" : "var(--color-border)"}`,
                          backgroundColor: active ? "var(--color-accent)" : "transparent",
                          color: active ? "var(--color-accent-foreground)" : "var(--color-text-secondary)",
                        }}>
                        {t === "criterion" ? "Criterion score" : "Mandatory check"}
                      </button>
                    );
                  })}
                </div>
              </div>

              {/* Target */}
              <div style={{ marginBottom: 22 }}>
                <label htmlFor="oc-target" style={labelStyle}>
                  {targetType === "criterion" ? "Criterion" : "Check"}
                </label>
                <select id="oc-target" value={targetId}
                  onChange={(e) => setTargetId(e.target.value)} style={fieldStyle}>
                  <option value="">
                    {targetType === "criterion" ? "Select a criterion…" : "Select a check…"}
                  </option>
                  {targetType === "criterion"
                    ? criteria.map((c) => <option key={c.criterion_id} value={c.criterion_id}>{c.name}</option>)
                    : checks.map((c) => <option key={c.check_id} value={c.check_id}>{c.name}</option>)}
                </select>
              </div>

              {/* Corrected value */}
              <div style={{ marginBottom: 22 }}>
                <span style={labelStyle}>Corrected {targetType === "criterion" ? "score" : "decision"}</span>
                {targetType === "criterion" ? (
                  <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
                    {Array.from({ length: 11 }, (_, n) => {
                      const active = score === n;
                      return (
                        <button key={n} type="button" onClick={() => setScore(n)} className="oc-chip"
                          aria-pressed={active}
                          style={{
                            width: 40, height: 40, cursor: "pointer",
                            fontFamily: MONO, fontSize: 15, fontWeight: 700,
                            fontVariantNumeric: "tabular-nums",
                            borderRadius: "var(--radius)",
                            borderTop: `1px solid ${active ? "var(--color-accent)" : "var(--color-border)"}`,
                            borderBottom: `1px solid ${active ? "var(--color-accent)" : "var(--color-border)"}`,
                            borderLeft: `1px solid ${active ? "var(--color-accent)" : "var(--color-border)"}`,
                            borderRight: `1px solid ${active ? "var(--color-accent)" : "var(--color-border)"}`,
                            backgroundColor: active ? "var(--color-accent)" : "transparent",
                            color: active ? "var(--color-accent-foreground)" : "var(--color-text-secondary)",
                          }}>
                          {n}
                        </button>
                      );
                    })}
                  </div>
                ) : (
                  <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
                    {CHECK_DECISIONS.map((d) => {
                      const active = decision === d.value;
                      return (
                        <button key={d.value} type="button" onClick={() => setDecision(d.value)} className="oc-chip"
                          aria-pressed={active}
                          style={{
                            padding: "10px 16px", cursor: "pointer",
                            fontFamily: FONT, fontSize: 13, fontWeight: 600,
                            borderRadius: "var(--radius)",
                            borderTop: `1px solid ${active ? d.color : "var(--color-border)"}`,
                            borderBottom: `1px solid ${active ? d.color : "var(--color-border)"}`,
                            borderLeft: `3px solid ${d.color}`,
                            borderRight: `1px solid ${active ? d.color : "var(--color-border)"}`,
                            backgroundColor: active ? "var(--color-surface-hover)" : "transparent",
                            color: active ? "var(--color-text-primary)" : "var(--color-text-secondary)",
                          }}>
                          {d.label}
                        </button>
                      );
                    })}
                  </div>
                )}
              </div>

              {/* Reason */}
              <div style={{ marginBottom: 6 }}>
                <label htmlFor="oc-reason" style={labelStyle}>Reason</label>
                <textarea id="oc-reason" value={reason} rows={3}
                  onChange={(e) => setReason(e.target.value)}
                  placeholder="Explain why the AI got this wrong — this is what the model learns from."
                  style={{ ...fieldStyle, resize: "vertical", lineHeight: 1.6 }} />
                <p style={{
                  fontFamily: MONO, fontSize: 11, marginTop: 6, textAlign: "right",
                  color: reasonValid ? "var(--color-text-muted)" : "var(--color-warning)",
                }}>
                  {reason.trim().length}/{MIN_REASON} min
                </p>
              </div>

              {submitError && (
                <div role="alert" style={{ ...alertStyle("var(--color-error)"), marginBottom: 16 }}>
                  <p style={{ fontFamily: FONT, fontSize: 13, color: "var(--color-error)" }}>{submitError}</p>
                </div>
              )}
              {submitted && (
                <div role="status" style={{ ...alertStyle("var(--color-success)"), marginBottom: 16 }}>
                  <p style={{ fontFamily: FONT, fontSize: 13, color: "var(--color-success)" }}>
                    Correction recorded. It will guide future evaluations of this item.
                  </p>
                </div>
              )}

              <button type="button" onClick={submit} disabled={!formValid} className="oc-submit"
                style={{
                  display: "inline-flex", alignItems: "center", justifyContent: "center", gap: 8,
                  width: bp === "mobile" ? "100%" : "auto",
                  padding: "11px 22px",
                  backgroundColor: formValid ? "var(--color-accent)" : "var(--color-surface-hover)",
                  color: formValid ? "var(--color-accent-foreground)" : "var(--color-text-muted)",
                  borderRadius: "var(--radius)",
                  fontFamily: FONT, fontWeight: 600, fontSize: 14,
                  cursor: formValid ? "pointer" : "not-allowed",
                  borderTop: "none", borderBottom: "none", borderLeft: "none", borderRight: "none",
                }}>
                {submitting && <span className="oc-spin oc-spin-sm" />}
                {submitting ? "Recording…" : "Record correction"}
              </button>
            </div>

            {/* Existing corrections */}
            <div>
              <p style={{
                fontFamily: FONT, fontSize: 10, fontWeight: 600,
                letterSpacing: "0.08em", textTransform: "uppercase",
                color: "var(--color-text-muted)", marginBottom: 10,
              }}>
                Corrections on record ({existing.length})
              </p>
              {existing.length === 0 ? (
                <p style={{ fontFamily: FONT, fontSize: 13, color: "var(--color-text-muted)", padding: "8px 0" }}>
                  No corrections recorded for this run yet.
                </p>
              ) : (
                <div style={{
                  backgroundColor: "var(--color-surface)",
                  borderTop: "1px solid var(--color-border)",
                  borderBottom: "1px solid var(--color-border)",
                  borderLeft: "1px solid var(--color-border)",
                  borderRight: "1px solid var(--color-border)",
                  borderRadius: "var(--radius)", overflow: "hidden",
                }}>
                  {existing.map((c, i) => (
                    <div key={c.correction_id} style={{
                      padding: "14px 16px",
                      borderBottom: i < existing.length - 1 ? "1px solid var(--color-border)" : "none",
                      borderLeft: "3px solid var(--color-accent)",
                    }}>
                      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", gap: 12 }}>
                        <p style={{ fontFamily: FONT, fontWeight: 600, fontSize: 13, color: "var(--color-text-primary)" }}>
                          {c.target_name || c.target_id}
                        </p>
                        <span style={{ fontFamily: MONO, fontSize: 12, color: "var(--color-accent)", whiteSpace: "nowrap" }}>
                          {formatCorrected(c)}
                        </span>
                      </div>
                      <p style={{ fontFamily: FONT, fontSize: 12, color: "var(--color-text-muted)", lineHeight: 1.6, marginTop: 4 }}>
                        {c.reason}
                      </p>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </>
        )}
      </div>

      <style>{`
        @keyframes spin { to { transform: rotate(360deg); } }
        .oc-spin {
          width: 16px; height: 16px; border-radius: 50%;
          border-top: 2px solid var(--color-accent);
          border-bottom: 2px solid transparent;
          border-left: 2px solid transparent;
          border-right: 2px solid transparent;
          animation: spin 0.7s linear infinite;
        }
        .oc-spin-sm {
          width: 14px; height: 14px;
          border-top-color: var(--color-accent-foreground);
        }
        .oc-seg, .oc-chip, .oc-submit {
          transition: transform var(--transition), opacity var(--transition),
                      background-color var(--transition);
        }
        .oc-seg:hover, .oc-chip:hover { transform: translateY(-1px); }
        .oc-submit:not(:disabled):hover { transform: translateY(-1px); }
        .oc-submit:not(:disabled):active { transform: translateY(0); }
        .oc-seg:focus-visible, .oc-chip:focus-visible,
        .oc-submit:focus-visible, select:focus-visible, textarea:focus-visible {
          outline: 2px solid var(--color-accent); outline-offset: 2px;
        }
      `}</style>
    </div>
  );
}

function alertStyle(accent: string): React.CSSProperties {
  return {
    padding: "12px 16px",
    backgroundColor: "var(--color-surface)",
    borderTop: "1px solid var(--color-border)",
    borderBottom: "1px solid var(--color-border)",
    borderLeft: `3px solid ${accent}`,
    borderRight: "1px solid var(--color-border)",
    borderRadius: "var(--radius)",
  };
}

function formatCorrected(c: CorrectionRow): string {
  const v = c.corrected_value ?? {};
  if (c.target_type === "criterion" && "raw_score" in v) return `→ ${v.raw_score as number}/10`;
  if (c.target_type === "check" && "decision" in v) return `→ ${String(v.decision)}`;
  return "→ corrected";
}
