"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";

interface MandatoryCheck {
  check_id: string;
  name: string;
  description: string;
  what_passes: string;
}

interface ScoringCriterion {
  criterion_id: string;
  name: string;
  weight: number;
}

interface EvaluationSetup {
  setup_id: string;
  department: string;
  rfp_id: string;
  mandatory_checks: MandatoryCheck[];
  scoring_criteria: ScoringCriterion[];
  total_weight: number;
  confirmed_by: string;
}

export default function ConfirmPage() {
  const { runId } = useParams<{ runId: string }>();
  const router = useRouter();
  const [setup, setSetup] = useState<EvaluationSetup | null>(null);
  const [loading, setLoading] = useState(true);
  const [confirming, setConfirming] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    const token = localStorage.getItem("access_token");
    fetch(`/api/v1/evaluate/${runId}/setup`, {
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    })
      .then((r) => r.json())
      .then((data) => { setSetup(data); setLoading(false); })
      .catch(() => { setError("Failed to load evaluation setup."); setLoading(false); });
  }, [runId]);

  async function handleConfirm() {
    setConfirming(true);
    setError("");
    try {
      const token = localStorage.getItem("access_token");
      const res = await fetch(`/api/v1/evaluate/${runId}/confirm`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
      });
      if (!res.ok) throw new Error(`Confirm failed: ${res.status}`);
      router.push(`/${runId}/progress`);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Confirmation failed");
      setConfirming(false);
    }
  }

  if (loading) {
    return (
      <main className="min-h-screen bg-slate-50 flex items-center justify-center">
        <p className="text-slate-500">Loading evaluation setup...</p>
      </main>
    );
  }

  if (!setup) {
    return (
      <main className="min-h-screen bg-slate-50 flex items-center justify-center">
        <p className="text-red-600">{error || "Setup not found."}</p>
      </main>
    );
  }

  const totalWeightPct = Math.round(setup.total_weight * 100);

  return (
    <main className="min-h-screen bg-slate-50 p-8">
      <div className="max-w-3xl mx-auto space-y-6">

        {/* Header */}
        <div className="bg-white rounded-xl shadow p-6">
          <h1 className="text-xl font-bold text-slate-800">
            Confirm Evaluation Setup
          </h1>
          <p className="text-slate-500 mt-1 text-sm">
            Review the criteria before starting the pipeline. This cannot be
            changed once confirmed.
          </p>
          <div className="mt-3 flex gap-4 text-sm text-slate-600">
            <span><b>RFP:</b> {setup.rfp_id}</span>
            <span><b>Dept:</b> {setup.department}</span>
            <span><b>Setup:</b> {setup.setup_id}</span>
          </div>
        </div>

        {/* Mandatory checks */}
        <div className="bg-white rounded-xl shadow p-6">
          <h2 className="text-base font-semibold text-slate-700 mb-3">
            Mandatory Checks ({setup.mandatory_checks.length})
          </h2>
          <p className="text-xs text-slate-500 mb-4">
            Vendors failing any of these are rejected — not scored.
          </p>
          <div className="space-y-3">
            {setup.mandatory_checks.map((check) => (
              <div
                key={check.check_id}
                className="border border-slate-200 rounded-lg p-3"
              >
                <div className="flex items-center gap-2">
                  <span className="text-xs font-mono bg-slate-100 text-slate-600 px-2 py-0.5 rounded">
                    {check.check_id}
                  </span>
                  <span className="font-medium text-slate-800 text-sm">
                    {check.name}
                  </span>
                </div>
                <p className="text-xs text-slate-500 mt-1">{check.description}</p>
                <p className="text-xs text-green-700 mt-1">
                  ✓ Passes when: {check.what_passes}
                </p>
              </div>
            ))}
          </div>
        </div>

        {/* Scoring criteria */}
        <div className="bg-white rounded-xl shadow p-6">
          <h2 className="text-base font-semibold text-slate-700 mb-3">
            Scoring Criteria — Total weight: {totalWeightPct}%
          </h2>
          {totalWeightPct !== 100 && (
            <p className="text-xs text-amber-600 bg-amber-50 rounded p-2 mb-3">
              ⚠ Weights sum to {totalWeightPct}% — should be 100%.
            </p>
          )}
          <div className="space-y-2">
            {setup.scoring_criteria.map((c) => (
              <div
                key={c.criterion_id}
                className="flex items-center justify-between border border-slate-200 rounded-lg px-4 py-2"
              >
                <span className="text-sm text-slate-800">{c.name}</span>
                <span className="text-sm font-semibold text-blue-600">
                  {Math.round(c.weight * 100)}%
                </span>
              </div>
            ))}
          </div>
        </div>

        {/* Confirm */}
        {error && (
          <p className="text-sm text-red-600 bg-red-50 rounded p-3">{error}</p>
        )}
        <div className="flex gap-3">
          <button
            onClick={() => router.back()}
            className="px-5 py-2 rounded-lg border border-slate-300 text-slate-600 hover:bg-slate-50 text-sm"
          >
            Back
          </button>
          <button
            onClick={handleConfirm}
            disabled={confirming}
            className="flex-1 py-2 bg-blue-600 text-white rounded-lg font-medium hover:bg-blue-700 disabled:opacity-50 text-sm"
          >
            {confirming ? "Starting pipeline..." : "Confirm and Start Evaluation"}
          </button>
        </div>

      </div>
    </main>
  );
}
