"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter, useSearchParams } from "next/navigation";

interface CurrentDecision {
  vendor_id: string;
  vendor_name: string;
  decision_type: "shortlisted" | "rejected";
  rank?: number;
  total_score?: number;
  rejection_reasons?: string[];
  evidence_citations?: string[];
}

const MIN_REASON_LENGTH = 20;

export default function OverridePage() {
  const { runId } = useParams<{ runId: string }>();
  const searchParams = useSearchParams();
  const router = useRouter();
  const vendorId = searchParams.get("vendor") ?? "";

  const [decision, setDecision] = useState<CurrentDecision | null>(null);
  const [reason, setReason] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState(false);

  useEffect(() => {
    if (!vendorId) return;
    const token = localStorage.getItem("access_token");
    fetch(`/api/v1/evaluate/${runId}/decision?vendor=${vendorId}`, {
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    })
      .then((r) => r.json())
      .then(setDecision)
      .catch(() => setError("Failed to load current decision."));
  }, [runId, vendorId]);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (reason.trim().length < MIN_REASON_LENGTH) {
      setError(`Reason must be at least ${MIN_REASON_LENGTH} characters.`);
      return;
    }
    setSubmitting(true);
    setError("");
    try {
      const token = localStorage.getItem("access_token");
      const res = await fetch(`/api/v1/evaluate/${runId}/override`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: JSON.stringify({ vendor_id: vendorId, reason: reason.trim() }),
      });
      if (!res.ok) {
        const data = await res.json();
        throw new Error(data.detail ?? `Override failed: ${res.status}`);
      }
      setSuccess(true);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Override failed");
      setSubmitting(false);
    }
  }

  const reasonLen = reason.trim().length;
  const reasonOk = reasonLen >= MIN_REASON_LENGTH;

  if (success) return (
    <main className="min-h-screen bg-slate-50 flex items-center justify-center p-8">
      <div className="bg-white rounded-xl shadow p-8 max-w-md w-full text-center space-y-4">
        <p className="text-4xl">✓</p>
        <h2 className="text-lg font-bold text-green-700">Override recorded</h2>
        <p className="text-slate-500 text-sm">
          The override has been saved with a full audit trail.
        </p>
        <button
          onClick={() => router.push(`/${runId}/results`)}
          className="w-full py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 text-sm font-medium"
        >
          Back to Results
        </button>
      </div>
    </main>
  );

  return (
    <main className="min-h-screen bg-slate-50 p-8">
      <div className="max-w-xl mx-auto space-y-5">

        <div className="bg-white rounded-xl shadow p-6">
          <h1 className="text-xl font-bold text-slate-800">Human Override</h1>
          <p className="text-slate-500 text-sm mt-1">
            Every override is logged with your identity and reason for audit compliance.
          </p>
        </div>

        {/* Current decision */}
        {decision && (
          <div className="bg-white rounded-xl shadow p-6">
            <h2 className="text-sm font-semibold text-slate-600 mb-3">Current Decision</h2>
            <div className="flex items-center justify-between">
              <p className="font-semibold text-slate-800">
                {decision.vendor_name || decision.vendor_id}
              </p>
              <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${
                decision.decision_type === "shortlisted"
                  ? "bg-green-100 text-green-800"
                  : "bg-red-100 text-red-800"
              }`}>
                {decision.decision_type === "shortlisted"
                  ? `Shortlisted — Rank #${decision.rank}`
                  : "Rejected"}
              </span>
            </div>
            {decision.decision_type === "rejected" && decision.evidence_citations && (
              <div className="mt-3 space-y-1">
                <p className="text-xs text-slate-500 font-medium">Evidence:</p>
                {decision.evidence_citations.map((c, i) => (
                  <p key={i} className="text-xs italic text-slate-600 bg-slate-50 rounded px-2 py-1">
                    &ldquo;{c}&rdquo;
                  </p>
                ))}
              </div>
            )}
          </div>
        )}

        {/* Override form */}
        <form onSubmit={handleSubmit} className="bg-white rounded-xl shadow p-6 space-y-4">
          <div>
            <label className="block text-sm font-medium text-slate-700 mb-1">
              Override Reason
              <span className="text-slate-400 font-normal ml-1">
                (minimum {MIN_REASON_LENGTH} characters — required for audit)
              </span>
            </label>
            <textarea
              rows={4}
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              placeholder="Explain why this decision is being overridden. Be specific — this will be reviewed by procurement leadership."
              className="w-full text-sm border border-slate-300 rounded-lg p-3 focus:outline-none focus:ring-2 focus:ring-blue-500 resize-none"
            />
            <div className="flex justify-between mt-1">
              <span className={`text-xs ${reasonOk ? "text-green-600" : "text-slate-400"}`}>
                {reasonLen}/{MIN_REASON_LENGTH} minimum
              </span>
              {reasonOk && <span className="text-xs text-green-600">✓ Length ok</span>}
            </div>
          </div>

          {error && (
            <p className="text-sm text-red-600 bg-red-50 rounded p-2">{error}</p>
          )}

          <div className="flex gap-3">
            <button
              type="button"
              onClick={() => router.back()}
              className="px-4 py-2 text-sm border border-slate-300 rounded-lg text-slate-600 hover:bg-slate-50"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={submitting || !reasonOk}
              className="flex-1 py-2 bg-amber-600 text-white rounded-lg font-medium hover:bg-amber-700 disabled:opacity-50 text-sm"
            >
              {submitting ? "Submitting..." : "Submit Override"}
            </button>
          </div>
        </form>

      </div>
    </main>
  );
}
