"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";

interface EvalRun {
  run_id: string;
  rfp_title: string;
  department: string;
  status: "running" | "pending_approval" | "complete" | "blocked";
  vendor_count: number;
  shortlisted_count: number;
  rejected_count: number;
  approval_tier?: number;
  approver_role?: string;
  sla_deadline?: string;
  started_at: string;
}

const STATUS_STYLE: Record<EvalRun["status"], string> = {
  running:          "bg-blue-100 text-blue-700",
  pending_approval: "bg-amber-100 text-amber-800",
  complete:         "bg-green-100 text-green-700",
  blocked:          "bg-red-100 text-red-700",
};

function SlaCountdown({ deadline }: { deadline: string }) {
  const [remaining, setRemaining] = useState("");

  useEffect(() => {
    function calc() {
      const diff = new Date(deadline).getTime() - Date.now();
      if (diff <= 0) { setRemaining("OVERDUE"); return; }
      const h = Math.floor(diff / 3600000);
      const m = Math.floor((diff % 3600000) / 60000);
      setRemaining(`${h}h ${m}m`);
    }
    calc();
    const t = setInterval(calc, 60000);
    return () => clearInterval(t);
  }, [deadline]);

  const overdue = remaining === "OVERDUE";
  return (
    <span className={`text-xs font-mono font-semibold ${overdue ? "text-red-600" : "text-amber-700"}`}>
      {overdue ? "⚠ OVERDUE" : `⏱ ${remaining}`}
    </span>
  );
}

export default function DashboardPage() {
  const router = useRouter();
  const [runs, setRuns] = useState<EvalRun[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const token = localStorage.getItem("access_token");
    fetch("/api/v1/evaluate/list", {
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    })
      .then((r) => r.json())
      .then((d) => { setRuns(d.runs ?? []); setLoading(false); })
      .catch(() => setLoading(false));
  }, []);

  const pending = runs.filter((r) => r.status === "pending_approval");
  const active  = runs.filter((r) => r.status === "running");
  const rest    = runs.filter((r) => r.status !== "pending_approval" && r.status !== "running");

  return (
    <main className="min-h-screen bg-slate-50 p-8">
      <div className="max-w-5xl mx-auto space-y-6">

        {/* Header */}
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold text-slate-800">Evaluation Dashboard</h1>
            <p className="text-slate-500 text-sm mt-1">All runs · Pending approvals · Cross-department</p>
          </div>
          <button
            onClick={() => router.push("/")}
            className="px-4 py-2 bg-blue-600 text-white rounded-lg text-sm font-medium hover:bg-blue-700"
          >
            + New Evaluation
          </button>
        </div>

        {/* Summary cards */}
        <div className="grid grid-cols-3 gap-4">
          {[
            { label: "Active",           value: active.length,  color: "text-blue-600" },
            { label: "Pending Approval", value: pending.length, color: "text-amber-600" },
            { label: "Total Runs",       value: runs.length,    color: "text-slate-700" },
          ].map((card) => (
            <div key={card.label} className="bg-white rounded-xl shadow p-5">
              <p className="text-sm text-slate-500">{card.label}</p>
              <p className={`text-3xl font-bold mt-1 ${card.color}`}>{card.value}</p>
            </div>
          ))}
        </div>

        {/* Pending approvals */}
        {pending.length > 0 && (
          <div className="bg-white rounded-xl shadow p-6">
            <h2 className="text-base font-semibold text-amber-700 mb-4">
              ⏳ Pending Approval ({pending.length})
            </h2>
            <div className="space-y-3">
              {pending.map((run) => (
                <div
                  key={run.run_id}
                  className="flex items-center justify-between border border-amber-100 rounded-lg px-4 py-3 bg-amber-50 cursor-pointer hover:bg-amber-100"
                  onClick={() => router.push(`/${run.run_id}/results`)}
                >
                  <div>
                    <p className="font-medium text-slate-800 text-sm">{run.rfp_title}</p>
                    <p className="text-xs text-slate-500">{run.department} · Tier {run.approval_tier} — {run.approver_role?.replace(/_/g, " ")}</p>
                  </div>
                  <div className="text-right">
                    {run.sla_deadline && <SlaCountdown deadline={run.sla_deadline} />}
                    <p className="text-xs text-slate-500 mt-0.5">{run.shortlisted_count} shortlisted</p>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Active runs */}
        {active.length > 0 && (
          <div className="bg-white rounded-xl shadow p-6">
            <h2 className="text-base font-semibold text-blue-700 mb-4">
              ◉ Active Runs ({active.length})
            </h2>
            <div className="space-y-3">
              {active.map((run) => (
                <div
                  key={run.run_id}
                  className="flex items-center justify-between border border-blue-100 rounded-lg px-4 py-3 cursor-pointer hover:bg-blue-50"
                  onClick={() => router.push(`/${run.run_id}/progress`)}
                >
                  <div>
                    <p className="font-medium text-slate-800 text-sm">{run.rfp_title}</p>
                    <p className="text-xs text-slate-500">{run.department} · {run.vendor_count} vendors</p>
                  </div>
                  <span className="text-xs px-2 py-0.5 rounded-full bg-blue-100 text-blue-700 font-medium animate-pulse">
                    running
                  </span>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* All other runs */}
        {!loading && rest.length > 0 && (
          <div className="bg-white rounded-xl shadow p-6">
            <h2 className="text-base font-semibold text-slate-700 mb-4">All Runs</h2>
            <div className="space-y-2">
              {rest.map((run) => (
                <div
                  key={run.run_id}
                  className="flex items-center justify-between border border-slate-100 rounded-lg px-4 py-3 cursor-pointer hover:bg-slate-50"
                  onClick={() => router.push(`/${run.run_id}/results`)}
                >
                  <div>
                    <p className="font-medium text-slate-800 text-sm">{run.rfp_title}</p>
                    <p className="text-xs text-slate-500">
                      {run.department} · {run.shortlisted_count} shortlisted · {run.rejected_count} rejected
                    </p>
                  </div>
                  <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${STATUS_STYLE[run.status]}`}>
                    {run.status.replace(/_/g, " ")}
                  </span>
                </div>
              ))}
            </div>
          </div>
        )}

        {loading && (
          <p className="text-center text-slate-400 text-sm">Loading runs...</p>
        )}
        {!loading && runs.length === 0 && (
          <div className="text-center py-16 text-slate-400">
            <p className="text-lg">No evaluation runs yet.</p>
            <p className="text-sm mt-1">Start one by clicking &ldquo;New Evaluation&rdquo; above.</p>
          </div>
        )}

      </div>
    </main>
  );
}
