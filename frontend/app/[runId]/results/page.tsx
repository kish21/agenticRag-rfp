"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";

interface CriterionScore {
  criterion_id: string;
  criterion_name?: string;
  raw_score: number;
  weighted_contribution: number;
  score_rationale?: string;
}

interface ShortlistedVendor {
  rank: number;
  vendor_id: string;
  vendor_name: string;
  total_score: number;
  score_confidence: number;
  recommendation: string;
  criterion_breakdown: CriterionScore[];
}

interface RejectedVendor {
  vendor_id: string;
  vendor_name: string;
  failed_checks: string[];
  rejection_reasons: string[];
  evidence_citations: string[];
}

interface ApprovalRouting {
  approval_tier: number;
  approver_role: string;
  sla_hours: number;
  sla_deadline: string;
}

interface Results {
  shortlisted_vendors: ShortlistedVendor[];
  rejected_vendors: RejectedVendor[];
  approval_routing: ApprovalRouting;
  requires_human_review: boolean;
  review_reasons: string[];
}

const REC_BADGE: Record<string, string> = {
  strongly_recommended: "bg-green-100 text-green-800",
  recommended:          "bg-blue-100 text-blue-800",
  acceptable:           "bg-slate-100 text-slate-700",
  marginal:             "bg-amber-100 text-amber-700",
};

export default function ResultsPage() {
  const { runId } = useParams<{ runId: string }>();
  const router = useRouter();
  const [results, setResults] = useState<Results | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [downloading, setDownloading] = useState<"pdf" | "excel" | null>(null);

  useEffect(() => {
    const token = localStorage.getItem("access_token");
    fetch(`/api/v1/evaluate/${runId}/results`, {
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    })
      .then((r) => { if (!r.ok) throw new Error(`${r.status}`); return r.json(); })
      .then((d) => { setResults(d); setLoading(false); })
      .catch((e) => { setError(`Failed to load results: ${e.message}`); setLoading(false); });
  }, [runId]);

  async function download(format: "pdf" | "excel") {
    setDownloading(format);
    const token = localStorage.getItem("access_token");
    const ext = format === "pdf" ? "pdf" : "xlsx";
    const res = await fetch(`/api/v1/evaluate/${runId}/report?format=${format}`, {
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    });
    if (res.ok) {
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `evaluation-${runId}.${ext}`;
      a.click();
      URL.revokeObjectURL(url);
    }
    setDownloading(null);
  }

  if (loading) return (
    <main className="min-h-screen bg-slate-50 flex items-center justify-center">
      <p className="text-slate-500">Loading results...</p>
    </main>
  );

  if (!results) return (
    <main className="min-h-screen bg-slate-50 flex items-center justify-center">
      <p className="text-red-600">{error}</p>
    </main>
  );

  return (
    <main className="min-h-screen bg-slate-50 p-8">
      <div className="max-w-4xl mx-auto space-y-6">

        {/* Header */}
        <div className="bg-white rounded-xl shadow p-6 flex items-start justify-between">
          <div>
            <h1 className="text-xl font-bold text-slate-800">Evaluation Results</h1>
            <p className="text-slate-500 text-sm mt-1">Run: {runId}</p>
            <div className="flex gap-3 mt-2 text-sm text-slate-600">
              <span className="text-green-700 font-medium">{results.shortlisted_vendors.length} shortlisted</span>
              <span className="text-red-600 font-medium">{results.rejected_vendors.length} rejected</span>
            </div>
          </div>
          <div className="flex gap-2">
            <button
              onClick={() => download("pdf")}
              disabled={downloading !== null}
              className="px-3 py-1.5 text-sm bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50"
            >
              {downloading === "pdf" ? "Downloading..." : "↓ PDF"}
            </button>
            <button
              onClick={() => download("excel")}
              disabled={downloading !== null}
              className="px-3 py-1.5 text-sm bg-green-600 text-white rounded-lg hover:bg-green-700 disabled:opacity-50"
            >
              {downloading === "excel" ? "Downloading..." : "↓ Excel"}
            </button>
          </div>
        </div>

        {/* Approval routing notice */}
        {results.approval_routing && (
          <div className="bg-amber-50 border border-amber-200 rounded-xl p-4 text-sm">
            <p className="font-semibold text-amber-800">
              Approval required — Tier {results.approval_routing.approval_tier}
            </p>
            <p className="text-amber-700 mt-1">
              Routed to: <b>{results.approval_routing.approver_role.replace(/_/g, " ")}</b>
              {" · "}SLA: {results.approval_routing.sla_hours}h
              {" · "}Deadline: {new Date(results.approval_routing.sla_deadline).toLocaleString()}
            </p>
            {results.requires_human_review && (
              <p className="text-red-700 mt-1 font-medium">
                ⚠ Human review required: {results.review_reasons.join("; ")}
              </p>
            )}
          </div>
        )}

        {/* Shortlisted */}
        {results.shortlisted_vendors.length > 0 && (
          <div className="bg-white rounded-xl shadow p-6">
            <h2 className="text-base font-semibold text-slate-700 mb-4">Shortlisted Vendors</h2>
            <div className="space-y-4">
              {results.shortlisted_vendors.map((v) => (
                <div key={v.vendor_id} className="border border-slate-200 rounded-lg p-4">
                  <div className="flex items-center justify-between mb-3">
                    <div className="flex items-center gap-3">
                      <span className="w-7 h-7 rounded-full bg-blue-600 text-white text-sm font-bold flex items-center justify-center">
                        {v.rank}
                      </span>
                      <div>
                        <p className="font-semibold text-slate-800">{v.vendor_name || v.vendor_id}</p>
                        <p className="text-xs text-slate-500">Confidence: {Math.round(v.score_confidence * 100)}%</p>
                      </div>
                    </div>
                    <div className="text-right">
                      <p className="text-xl font-bold text-slate-800">{v.total_score.toFixed(1)}<span className="text-sm text-slate-400">/10</span></p>
                      <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${REC_BADGE[v.recommendation] ?? "bg-slate-100 text-slate-600"}`}>
                        {v.recommendation.replace(/_/g, " ")}
                      </span>
                    </div>
                  </div>
                  {v.criterion_breakdown.length > 0 && (
                    <table className="w-full text-xs text-slate-600">
                      <thead>
                        <tr className="border-b border-slate-100">
                          <th className="text-left pb-1 font-medium">Criterion</th>
                          <th className="text-center pb-1 font-medium">Score</th>
                          <th className="text-right pb-1 font-medium">Contribution</th>
                        </tr>
                      </thead>
                      <tbody>
                        {v.criterion_breakdown.map((c) => (
                          <tr key={c.criterion_id} className="border-b border-slate-50">
                            <td className="py-1">{c.criterion_name ?? c.criterion_id}</td>
                            <td className="text-center py-1">{c.raw_score}/10</td>
                            <td className="text-right py-1">{c.weighted_contribution.toFixed(2)}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  )}
                  <button
                    onClick={() => router.push(`/${runId}/override?vendor=${v.vendor_id}`)}
                    className="mt-3 text-xs text-slate-500 hover:text-slate-700 underline"
                  >
                    Override decision
                  </button>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Rejected */}
        {results.rejected_vendors.length > 0 && (
          <div className="bg-white rounded-xl shadow p-6">
            <h2 className="text-base font-semibold text-slate-700 mb-4">Rejected Vendors</h2>
            <div className="space-y-4">
              {results.rejected_vendors.map((v) => (
                <div key={v.vendor_id} className="border border-red-100 rounded-lg p-4 bg-red-50">
                  <p className="font-semibold text-red-800">{v.vendor_name || v.vendor_id}</p>
                  <p className="text-xs text-red-600 mt-1">Failed: {v.failed_checks.join(", ")}</p>
                  {v.evidence_citations.length > 0 && (
                    <div className="mt-2 space-y-1">
                      {v.evidence_citations.map((cite, i) => (
                        <p key={i} className="text-xs text-slate-600 bg-white border border-slate-200 rounded px-2 py-1 italic">
                          &ldquo;{cite}&rdquo;
                        </p>
                      ))}
                    </div>
                  )}
                </div>
              ))}
            </div>
          </div>
        )}

      </div>
    </main>
  );
}
