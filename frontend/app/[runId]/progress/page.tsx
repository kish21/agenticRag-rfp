"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";

const AGENTS = [
  { id: "planner",     label: "Planner",     desc: "Decompose RFP into evaluation tasks" },
  { id: "ingestion",   label: "Ingestion",   desc: "Parse vendor PDFs → Qdrant chunks" },
  { id: "retrieval",   label: "Retrieval",   desc: "Hybrid search + Cohere rerank" },
  { id: "extraction",  label: "Extraction",  desc: "Extract structured facts → PostgreSQL" },
  { id: "evaluation",  label: "Evaluation",  desc: "Score vendors against criteria" },
  { id: "comparator",  label: "Comparator",  desc: "Cross-vendor ranking" },
  { id: "decision",    label: "Decision",    desc: "Accept/reject + approval routing" },
  { id: "explanation", label: "Explanation", desc: "Generate grounded report" },
];

type AgentStatus = "pending" | "running" | "done" | "blocked" | "warned";

interface AgentEvent {
  agent: string;
  status: AgentStatus;
  message?: string;
  critic_verdict?: string;
}

const STATUS_STYLES: Record<AgentStatus, string> = {
  pending: "bg-slate-100 text-slate-400",
  running: "bg-blue-100 text-blue-700 animate-pulse",
  done:    "bg-green-100 text-green-700",
  blocked: "bg-red-100 text-red-700",
  warned:  "bg-amber-100 text-amber-700",
};

const STATUS_ICON: Record<AgentStatus, string> = {
  pending: "○",
  running: "◉",
  done:    "✓",
  blocked: "✗",
  warned:  "⚠",
};

export default function ProgressPage() {
  const { runId } = useParams<{ runId: string }>();
  const router = useRouter();
  const [statuses, setStatuses] = useState<Record<string, AgentStatus>>(
    Object.fromEntries(AGENTS.map((a) => [a.id, "pending"]))
  );
  const [messages, setMessages] = useState<Record<string, string>>({});
  const [done, setDone] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    const token = localStorage.getItem("access_token");
    const url = `/api/v1/evaluate/${runId}/stream`;
    const es = new EventSource(
      token ? `${url}?token=${encodeURIComponent(token)}` : url
    );

    es.onmessage = (e) => {
      try {
        const event: AgentEvent = JSON.parse(e.data);
        setStatuses((prev) => ({ ...prev, [event.agent]: event.status }));
        if (event.message) {
          setMessages((prev) => ({ ...prev, [event.agent]: event.message! }));
        }
        if (event.agent === "explanation" && event.status === "done") {
          setDone(true);
          es.close();
        }
        if (event.status === "blocked") {
          setError(`Pipeline blocked at ${event.agent}: ${event.message ?? ""}`);
          es.close();
        }
      } catch {
        // ignore malformed events
      }
    };

    es.onerror = () => {
      setError("Connection lost. The evaluation may still be running.");
      es.close();
    };

    return () => es.close();
  }, [runId]);

  return (
    <main className="min-h-screen bg-slate-50 p-8">
      <div className="max-w-2xl mx-auto space-y-4">

        <div className="bg-white rounded-xl shadow p-6">
          <h1 className="text-xl font-bold text-slate-800">Evaluation in Progress</h1>
          <p className="text-slate-500 text-sm mt-1">Run ID: {runId}</p>
        </div>

        <div className="bg-white rounded-xl shadow divide-y divide-slate-100">
          {AGENTS.map((agent) => {
            const status = statuses[agent.id] ?? "pending";
            const msg = messages[agent.id];
            return (
              <div key={agent.id} className="flex items-center gap-4 px-5 py-3">
                <span className={`w-7 h-7 flex items-center justify-center rounded-full text-sm font-bold ${STATUS_STYLES[status]}`}>
                  {STATUS_ICON[status]}
                </span>
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-semibold text-slate-800">{agent.label}</p>
                  <p className="text-xs text-slate-500 truncate">
                    {msg ?? agent.desc}
                  </p>
                </div>
                <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${STATUS_STYLES[status]}`}>
                  {status}
                </span>
              </div>
            );
          })}
        </div>

        {error && (
          <div className="bg-red-50 border border-red-200 rounded-lg p-4 text-sm text-red-700">
            <b>Pipeline blocked:</b> {error}
          </div>
        )}

        {done && (
          <button
            onClick={() => router.push(`/${runId}/results`)}
            className="w-full py-3 bg-blue-600 text-white rounded-xl font-semibold hover:bg-blue-700"
          >
            View Results →
          </button>
        )}

      </div>
    </main>
  );
}
