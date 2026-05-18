"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { FONT, DISPLAY, MONO } from "@/lib/theme";
import { useThemeContext } from "@/components/ThemeProvider";
import { useBreakpoint } from "@/lib/hooks";
import { api, getUserInfo, clearUserInfo, isLoggedIn, type UserInfo } from "@/lib/api";

// ── Types ─────────────────────────────────────────────────────────────────────

type ShellState = "idle" | "running" | "completed";
type CanvasPage = "welcome" | "upload-form" | "progress" | "results";

interface EvalRun {
  run_id: string;
  rfp_title: string;
  status: string;
  vendor_count: number;
  created_at: string;
}

interface AgentEvent {
  agent: string;
  status: "pending" | "running" | "done" | "blocked";
  message: string;
}

interface VendorSlot {
  id: string;
  name: string;
  file: File | null;
}

interface VendorScore {
  vendor_name: string;
  decision: string;
  total_score: number;
  summary?: string;
}

interface EvalResults {
  recommendation?: string;
  approval_tier?: string;
  vendors?: VendorScore[];
}

// ── Constants ─────────────────────────────────────────────────────────────────

const AGENTS = [
  "PlannerAgent", "IngestionAgent", "RetrievalAgent", "ExtractionAgent",
  "EvaluationAgent", "ComparatorAgent", "DecisionAgent", "ExplanationAgent", "CriticAgent",
];

const AGENT_LABELS: Record<string, string> = {
  PlannerAgent: "Planner", IngestionAgent: "Ingestion", RetrievalAgent: "Retrieval",
  ExtractionAgent: "Extraction", EvaluationAgent: "Evaluation", ComparatorAgent: "Comparator",
  DecisionAgent: "Decision", ExplanationAgent: "Explanation", CriticAgent: "Critic",
};

const ROLE_DISPLAY: Record<string, string> = {
  procurement_manager: "Procurement",
  executive: "Executive",
  org_admin: "Admin",
};

const STATUS_DOT: Record<string, string> = {
  completed: "var(--color-success)",
  running:   "var(--color-info)",
  pending:   "var(--color-warning)",
  failed:    "var(--color-error)",
  draft:     "var(--color-text-muted)",
  done:      "var(--color-success)",
  blocked:   "var(--color-error)",
};

const DEPARTMENTS = ["Procurement", "Finance", "Legal", "IT", "Operations", "HR", "Marketing"];

function fmtDate(iso: string) {
  return new Date(iso).toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric" });
}

function mkId() { return Math.random().toString(36).slice(2, 8); }

function greet(email: string) {
  const name = email.split("@")[0].replace(/[._-]/g, " ");
  const h = new Date().getHours();
  const period = h < 12 ? "morning" : h < 17 ? "afternoon" : "evening";
  return `Good ${period}, ${name}.`;
}

// ── Shared style helpers (CSS vars only — no raw hex) ─────────────────────────

const labelCss: React.CSSProperties = {
  display: "block",
  fontFamily: FONT,
  fontSize: 11, fontWeight: 600,
  letterSpacing: "0.07em", textTransform: "uppercase",
  color: "var(--color-text-muted)",
  marginBottom: 8,
};

const inputCss: React.CSSProperties = {
  width: "100%", boxSizing: "border-box",
  padding: "9px 12px",
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

// ── FileDropZone ──────────────────────────────────────────────────────────────

function FileDropZone({
  file, onFile, placeholder, compact = false,
}: {
  file: File | null;
  onFile: (f: File) => void;
  placeholder: string;
  compact?: boolean;
}) {
  const [dragging, setDragging] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  function handleDrop(e: React.DragEvent) {
    e.preventDefault(); setDragging(false);
    const f = e.dataTransfer.files[0];
    if (f && (f.type.includes("pdf") || f.name.endsWith(".docx"))) onFile(f);
  }

  const borderStyle = dragging ? "1px solid var(--color-accent)" : "1px dashed var(--color-border)";

  return (
    <div
      onClick={() => inputRef.current?.click()}
      onDragOver={e => { e.preventDefault(); setDragging(true); }}
      onDragLeave={() => setDragging(false)}
      onDrop={handleDrop}
      role="button"
      tabIndex={0}
      onKeyDown={e => { if (e.key === "Enter" || e.key === " ") inputRef.current?.click(); }}
      aria-label={placeholder}
      style={{
        padding: compact ? "10px 12px" : "20px 16px",
        backgroundColor: dragging ? "var(--color-surface-hover)" : "var(--color-background)",
        borderTop: borderStyle, borderBottom: borderStyle,
        borderLeft: borderStyle, borderRight: borderStyle,
        borderRadius: "var(--radius)", cursor: "pointer", textAlign: "center",
        transition: "background-color 150ms ease-out, border-color 150ms ease-out",
      }}
    >
      {file ? (
        <div style={{ display: "flex", alignItems: "center", gap: 8, justifyContent: "center" }}>
          <span style={{ fontSize: 14 }}>📄</span>
          <p style={{ fontFamily: FONT, fontSize: 12, color: "var(--color-text-primary)", fontWeight: 500 }}>
            {file.name}
          </p>
          <span style={{ fontFamily: MONO, fontSize: 10, color: "var(--color-text-muted)" }}>
            ({(file.size / 1024).toFixed(0)} KB)
          </span>
        </div>
      ) : (
        <p style={{ fontFamily: FONT, fontSize: 12, color: "var(--color-text-muted)", lineHeight: 1.5 }}>
          {placeholder}<br /><span style={{ fontSize: 11 }}>PDF or DOCX</span>
        </p>
      )}
      <input
        ref={inputRef} type="file" accept=".pdf,.docx" style={{ display: "none" }}
        onChange={e => { const f = e.target.files?.[0]; if (f) onFile(f); }}
      />
    </div>
  );
}

// ── Main shell ────────────────────────────────────────────────────────────────

export default function HomePage() {
  const router = useRouter();
  const { isDark } = useThemeContext();
  const bp = useBreakpoint();
  const isMobile = bp === "mobile";
  const isTablet = bp === "tablet";
  const isNarrow = isMobile || isTablet;

  // Shell state machine
  const [shellState, setShellState] = useState<ShellState>("idle");
  const [canvasPage, setCanvasPage] = useState<CanvasPage>("welcome");
  const [activeRunId, setActiveRunId] = useState<string | null>(null);
  const [rightExpanded, setRightExpanded] = useState(false);
  const [sidebarOpen, setSidebarOpen] = useState(false);

  // Data
  const [runs, setRuns] = useState<EvalRun[]>([]);
  const [loading, setLoading] = useState(true);
  const [userInfo, setUserInfo] = useState<UserInfo | null>(null);

  // Upload form
  const [rfpTitle, setRfpTitle] = useState("");
  const [department, setDepartment] = useState("");
  const [rfpFile, setRfpFile] = useState<File | null>(null);
  const [vendors, setVendors] = useState<VendorSlot[]>([{ id: mkId(), name: "", file: null }]);
  const [submitting, setSubmitting] = useState(false);
  const [formError, setFormError] = useState("");

  // Progress + agent log
  const [agentStatuses, setAgentStatuses] = useState<Record<string, { status: string; message: string }>>({});
  const [agentEvents, setAgentEvents] = useState<AgentEvent[]>([]);

  // Results
  const [results, setResults] = useState<EvalResults | null>(null);

  // Chat
  const [chatInput, setChatInput] = useState("");
  const [chatMessages, setChatMessages] = useState<Array<{ role: "user" | "assistant"; text: string }>>([]);

  // Refs
  const logEndRef = useRef<HTMLDivElement>(null);
  const esRef = useRef<EventSource | null>(null);

  const chatVisible = shellState !== "running";

  // ── Auth + initial load ────────────────────────────────────────────────────

  useEffect(() => {
    // if (!isLoggedIn()) { router.push("/login"); return; }
    const info = getUserInfo();
    setUserInfo(info);
    api.get<{ runs?: EvalRun[] } | EvalRun[]>("/api/v1/evaluate/list", {
      on401: () => router.push("/login"),
    })
      .then(data => setRuns(Array.isArray(data) ? data : (data.runs ?? [])))
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [router]);

  // ── SSE stream while running ───────────────────────────────────────────────

  useEffect(() => {
    if (shellState !== "running" || !activeRunId) return;
    const base = process.env.NEXT_PUBLIC_API_SSE_URL ?? "";
    const es = new EventSource(`${base}/api/v1/evaluate/${activeRunId}/stream`, { withCredentials: true });
    esRef.current = es;

    es.onmessage = e => {
      try {
        const ev: AgentEvent = JSON.parse(e.data);
        setAgentEvents(prev => [...prev, ev]);
        setAgentStatuses(prev => ({ ...prev, [ev.agent]: { status: ev.status, message: ev.message } }));
        if (ev.agent === "ExplanationAgent" && ev.status === "done") {
          setShellState("completed");
          setCanvasPage("results");
          es.close();
        }
      } catch { /* malformed event — skip */ }
    };

    es.onerror = () => es.close();
    return () => { es.close(); esRef.current = null; };
  }, [shellState, activeRunId]);

  // ── Results fetch ──────────────────────────────────────────────────────────

  useEffect(() => {
    if (canvasPage !== "results" || !activeRunId) return;
    api.get<EvalResults>(`/api/v1/evaluate/${activeRunId}/results`, {
      on401: () => router.push("/login"),
    }).then(setResults).catch(() => {});
  }, [canvasPage, activeRunId, router]);

  // ── Auto-scroll agent log ──────────────────────────────────────────────────

  useEffect(() => {
    logEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [agentEvents]);

  // ── Handlers ──────────────────────────────────────────────────────────────

  async function signOut() {
    await api.post("/api/v1/auth/logout").catch(() => {});
    clearUserInfo();
    router.push("/login");
  }

  function startNewEval() {
    setCanvasPage("upload-form");
    setFormError("");
    if (isNarrow) setSidebarOpen(false);
  }

  function goHome() {
    setCanvasPage("welcome");
    if (isNarrow) setSidebarOpen(false);
  }

  function openRun(run: EvalRun) {
    setActiveRunId(run.run_id);
    if (run.status === "completed") {
      setShellState("completed");
      setCanvasPage("results");
    } else if (run.status === "running") {
      setShellState("running");
      setCanvasPage("progress");
      setRightExpanded(true);
    } else {
      setCanvasPage("welcome");
    }
    if (isNarrow) setSidebarOpen(false);
  }

  async function handleUploadSubmit(e: React.FormEvent) {
    e.preventDefault();
    setFormError("");
    if (!rfpTitle.trim()) { setFormError("RFP title is required."); return; }
    if (!department) { setFormError("Department is required."); return; }
    if (!rfpFile) { setFormError("RFP document is required."); return; }
    if (vendors.some(v => !v.name.trim() || !v.file)) {
      setFormError("Each vendor must have a name and a proposal document."); return;
    }
    setSubmitting(true);

    const fd = new FormData();
    fd.append("rfp_title", rfpTitle.trim());
    fd.append("department", department);
    fd.append("rfp_file", rfpFile);
    vendors.forEach(v => {
      fd.append("vendor_names", v.name.trim());
      fd.append("vendor_files", v.file!);
    });

    try {
      const res = await api.post<{ run_id: string }>("/api/v1/evaluate/start", {
        body: fd,
        on401: () => router.push("/login"),
      });
      setActiveRunId(res.run_id);
      setAgentStatuses({});
      setAgentEvents([]);
      setResults(null);
      setShellState("running");
      setCanvasPage("progress");
      setRightExpanded(true);
      setRuns(prev => [{
        run_id: res.run_id, rfp_title: rfpTitle.trim(),
        status: "running", vendor_count: vendors.length,
        created_at: new Date().toISOString(),
      }, ...prev]);
    } catch (err) {
      setFormError(err instanceof Error ? err.message : "Failed to start evaluation. Try again.");
    } finally {
      setSubmitting(false);
    }
  }

  function addVendor() { if (vendors.length < 10) setVendors(p => [...p, { id: mkId(), name: "", file: null }]); }
  function removeVendor(id: string) { setVendors(p => p.filter(v => v.id !== id)); }
  function updateVendor(id: string, patch: Partial<VendorSlot>) {
    setVendors(p => p.map(v => v.id === id ? { ...v, ...patch } : v));
  }

  function handleChat(e: React.FormEvent) {
    e.preventDefault();
    if (!chatInput.trim()) return;
    const msg = chatInput.trim();
    setChatInput("");
    setChatMessages(prev => [...prev, { role: "user", text: msg }]);
    setTimeout(() => {
      setChatMessages(prev => [...prev, { role: "assistant", text: "Chat endpoint integration coming soon." }]);
    }, 400);
  }

  // ── Background colours ────────────────────────────────────────────────────

  const sidebarBg = isDark ? "rgba(8,10,18,0.98)" : "rgba(247,249,252,0.98)";
  const navBg     = isDark ? "rgba(8,10,18,0.95)" : "rgba(247,249,252,0.95)";

  // ── Canvas page renderers ─────────────────────────────────────────────────

  function renderWelcome() {
    const total     = runs.length;
    const running   = runs.filter(r => r.status === "running").length;
    const completed = runs.filter(r => r.status === "completed").length;

    return (
      <div style={{ maxWidth: 680 }}>
        {/* Hero greeting */}
        <div style={{ marginBottom: 48 }}>
          <h1 style={{
            fontFamily: DISPLAY, fontWeight: 800,
            fontSize: isMobile ? 36 : 56,
            lineHeight: 1.0, letterSpacing: "-0.04em",
            color: "var(--color-text-primary)", marginBottom: 12,
          }}>
            {userInfo ? greet(userInfo.email) : "Welcome back."}
          </h1>
          <p style={{
            fontFamily: FONT, fontSize: 15, fontWeight: 400,
            color: "var(--color-text-secondary)", lineHeight: 1.65,
          }}>
            Evaluate vendor proposals against RFP criteria using multi-agent AI analysis.
          </p>
        </div>

        {/* Stats — intentionally asymmetric: 1fr 1fr 2fr */}
        {total > 0 && (
          <div style={{
            display: "grid",
            gridTemplateColumns: isMobile ? "1fr 1fr" : "1fr 1fr 2fr",
            gap: 12, marginBottom: 40,
          }}>
            {[
              { label: "Total", value: total },
              { label: "Running", value: running },
              { label: "Complete", value: completed },
            ].map(({ label, value }) => (
              <div key={label} style={{
                padding: "16px 20px",
                backgroundColor: "var(--color-surface)",
                borderTop: "1px solid var(--color-border)",
                borderBottom: "1px solid var(--color-border)",
                borderLeft: "1px solid var(--color-border)",
                borderRight: "1px solid var(--color-border)",
                borderRadius: "var(--radius)",
                boxShadow: "var(--shadow-sm)",
              }}>
                <p style={{
                  fontFamily: MONO, fontWeight: 700, fontSize: 32,
                  color: "var(--color-text-primary)", lineHeight: 1,
                  marginBottom: 4, fontVariantNumeric: "tabular-nums",
                }}>{value}</p>
                <p style={{
                  fontFamily: FONT, fontWeight: 500, fontSize: 10,
                  letterSpacing: "0.1em", textTransform: "uppercase",
                  color: "var(--color-text-muted)",
                }}>{label}</p>
              </div>
            ))}
          </div>
        )}

        {/* CTA */}
        <button
          type="button"
          onClick={startNewEval}
          style={{
            display: "inline-flex", alignItems: "center", gap: 8,
            padding: "11px 24px",
            backgroundColor: "var(--color-accent)",
            color: "var(--color-accent-foreground)",
            borderTop: "none", borderBottom: "none",
            borderLeft: "none", borderRight: "none",
            borderRadius: "var(--radius)",
            fontFamily: FONT, fontWeight: 600, fontSize: 14,
            cursor: "pointer", boxShadow: "var(--shadow-sm)",
            transition: "opacity 150ms ease-out, transform 150ms ease-out",
            marginBottom: 40,
          }}
          onMouseEnter={e => { e.currentTarget.style.opacity = "0.88"; e.currentTarget.style.transform = "translateY(-1px)"; }}
          onMouseLeave={e => { e.currentTarget.style.opacity = "1"; e.currentTarget.style.transform = "translateY(0)"; }}
        >
          <span style={{ fontSize: 18, fontWeight: 300, lineHeight: 1 }}>+</span>
          Start new evaluation
        </button>

        {/* Recent evaluations table */}
        {total > 0 && (
          <>
            <p style={{
              fontFamily: FONT, fontWeight: 600, fontSize: 10,
              letterSpacing: "0.1em", textTransform: "uppercase",
              color: "var(--color-text-muted)", marginBottom: 12,
            }}>
              Recent evaluations
            </p>
            <div style={{
              backgroundColor: "var(--color-surface)",
              borderTop: "1px solid var(--color-border)",
              borderBottom: "1px solid var(--color-border)",
              borderLeft: "1px solid var(--color-border)",
              borderRight: "1px solid var(--color-border)",
              borderRadius: "var(--radius)",
              boxShadow: "var(--shadow-sm)",
              overflow: "hidden",
            }}>
              {runs.slice(0, 6).map((run, i) => (
                <div
                  key={run.run_id}
                  onClick={() => openRun(run)}
                  role="button"
                  tabIndex={0}
                  onKeyDown={e => { if (e.key === "Enter") openRun(run); }}
                  style={{
                    display: "flex", alignItems: "center", justifyContent: "space-between",
                    padding: "12px 16px",
                    borderBottom: i < Math.min(runs.length, 6) - 1 ? "1px solid var(--color-border)" : "none",
                    cursor: "pointer",
                    transition: "background-color 150ms ease-out",
                  }}
                  onMouseEnter={e => { (e.currentTarget as HTMLElement).style.backgroundColor = "var(--color-surface-hover)"; }}
                  onMouseLeave={e => { (e.currentTarget as HTMLElement).style.backgroundColor = "transparent"; }}
                >
                  <div>
                    <p style={{ fontFamily: FONT, fontWeight: 500, fontSize: 13, color: "var(--color-text-primary)" }}>
                      {run.rfp_title || "Untitled RFP"}
                    </p>
                    <p style={{ fontFamily: MONO, fontSize: 11, color: "var(--color-text-muted)", marginTop: 2 }}>
                      {run.created_at ? fmtDate(run.created_at) : ""} · {run.vendor_count ?? 0} vendor{run.vendor_count !== 1 ? "s" : ""}
                    </p>
                  </div>
                  <div style={{ display: "flex", alignItems: "center", gap: 6, flexShrink: 0 }}>
                    <div style={{
                      width: 6, height: 6, borderRadius: "50%",
                      backgroundColor: STATUS_DOT[run.status] ?? "var(--color-text-muted)",
                    }} />
                    <span style={{ fontFamily: FONT, fontSize: 12, color: "var(--color-text-secondary)" }}>
                      {run.status.charAt(0).toUpperCase() + run.status.slice(1)}
                    </span>
                    <span style={{ color: "var(--color-text-muted)", fontSize: 14, marginLeft: 4 }}>→</span>
                  </div>
                </div>
              ))}
            </div>
          </>
        )}

        {/* Empty state */}
        {total === 0 && !loading && (
          <div style={{
            padding: "48px 32px", textAlign: "center",
            backgroundColor: "var(--color-surface)",
            borderTop: "1px solid var(--color-border)",
            borderBottom: "1px solid var(--color-border)",
            borderLeft: "1px solid var(--color-border)",
            borderRight: "1px solid var(--color-border)",
            borderRadius: "var(--radius)",
            boxShadow: "var(--shadow-sm)",
          }}>
            <p style={{ fontFamily: MONO, fontSize: 40, color: "var(--color-text-muted)", marginBottom: 16, lineHeight: 1 }}>◻</p>
            <p style={{ fontFamily: DISPLAY, fontWeight: 700, fontSize: 20, color: "var(--color-text-primary)", marginBottom: 8 }}>
              No evaluations yet
            </p>
            <p style={{ fontFamily: FONT, fontSize: 14, color: "var(--color-text-muted)", lineHeight: 1.65 }}>
              Upload your first RFP to start evaluating vendors.
            </p>
          </div>
        )}
      </div>
    );
  }

  function renderUploadForm() {
    return (
      <div style={{ maxWidth: 620 }}>
        <button
          type="button" onClick={() => setCanvasPage("welcome")}
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

        <h1 style={{
          fontFamily: DISPLAY, fontWeight: 800,
          fontSize: isMobile ? 24 : 32,
          letterSpacing: "-0.03em", lineHeight: 1.0,
          color: "var(--color-text-primary)", marginBottom: 8,
        }}>
          New RFP evaluation
        </h1>
        <p style={{ fontFamily: FONT, fontSize: 14, color: "var(--color-text-muted)", lineHeight: 1.65, marginBottom: 32 }}>
          Upload your RFP and vendor proposals. Nine specialised agents will evaluate and rank each vendor.
        </p>

        <form onSubmit={handleUploadSubmit} noValidate>
          {formError && (
            <div role="alert" style={{
              marginBottom: 20, padding: "10px 14px",
              backgroundColor: "var(--color-surface)",
              borderTop: "1px solid var(--color-error)",
              borderBottom: "1px solid var(--color-error)",
              borderLeft: "3px solid var(--color-error)",
              borderRight: "1px solid var(--color-error)",
              borderRadius: "var(--radius)",
              fontFamily: FONT, fontSize: 13, color: "var(--color-error)",
            }}>
              {formError}
            </div>
          )}

          <div style={{
            display: "grid",
            gridTemplateColumns: isMobile ? "1fr" : "1fr 1fr",
            gap: 16, marginBottom: 20,
          }}>
            <div>
              <label htmlFor="rfp-title" style={labelCss}>RFP Title *</label>
              <input
                id="rfp-title" type="text" value={rfpTitle}
                onChange={e => setRfpTitle(e.target.value)}
                placeholder="e.g. Cloud Infrastructure 2026"
                required suppressHydrationWarning style={inputCss}
                onFocus={e => { e.currentTarget.style.borderColor = "var(--color-accent)"; }}
                onBlur={e => { e.currentTarget.style.borderColor = "var(--color-border)"; }}
              />
            </div>
            <div>
              <label htmlFor="department" style={labelCss}>Department *</label>
              <select
                id="department" value={department}
                onChange={e => setDepartment(e.target.value)}
                required style={{ ...inputCss, cursor: "pointer" }}
                onFocus={e => { e.currentTarget.style.borderColor = "var(--color-accent)"; }}
                onBlur={e => { e.currentTarget.style.borderColor = "var(--color-border)"; }}
              >
                <option value="">Select…</option>
                {DEPARTMENTS.map(d => <option key={d} value={d}>{d}</option>)}
              </select>
            </div>
          </div>

          <div style={{ marginBottom: 24 }}>
            <label style={labelCss}>RFP Document *</label>
            <FileDropZone file={rfpFile} onFile={setRfpFile} placeholder="Drop RFP PDF or DOCX here, or click to browse" />
          </div>

          <div style={{ marginBottom: 28 }}>
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 12 }}>
              <p style={labelCss}>Vendor Proposals *</p>
              {vendors.length < 10 && (
                <button
                  type="button" onClick={addVendor}
                  style={{
                    background: "none", border: "none", cursor: "pointer",
                    fontFamily: FONT, fontSize: 12, fontWeight: 500,
                    color: "var(--color-accent)", padding: 0,
                    transition: "opacity 150ms ease-out",
                  }}
                  onMouseEnter={e => { e.currentTarget.style.opacity = "0.7"; }}
                  onMouseLeave={e => { e.currentTarget.style.opacity = "1"; }}
                >
                  + Add vendor
                </button>
              )}
            </div>
            <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
              {vendors.map((vendor, idx) => (
                <div key={vendor.id} style={{
                  padding: "14px 16px",
                  backgroundColor: "var(--color-surface)",
                  borderTop: "1px solid var(--color-border)",
                  borderBottom: "1px solid var(--color-border)",
                  borderLeft: "1px solid var(--color-border)",
                  borderRight: "1px solid var(--color-border)",
                  borderRadius: "var(--radius)",
                }}>
                  <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 10 }}>
                    <p style={{ fontFamily: FONT, fontSize: 10, fontWeight: 600, letterSpacing: "0.08em", textTransform: "uppercase", color: "var(--color-text-muted)" }}>
                      Vendor {idx + 1}
                    </p>
                    {vendors.length > 1 && (
                      <button
                        type="button" onClick={() => removeVendor(vendor.id)}
                        style={{
                          background: "none", border: "none", cursor: "pointer",
                          fontFamily: FONT, fontSize: 11, color: "var(--color-text-muted)",
                          padding: 0, transition: "color 150ms ease-out",
                        }}
                        onMouseEnter={e => { e.currentTarget.style.color = "var(--color-error)"; }}
                        onMouseLeave={e => { e.currentTarget.style.color = "var(--color-text-muted)"; }}
                      >
                        Remove
                      </button>
                    )}
                  </div>
                  <label htmlFor={`vname-${vendor.id}`} style={{ ...labelCss, marginBottom: 6 }}>Vendor name</label>
                  <input
                    id={`vname-${vendor.id}`} type="text" value={vendor.name}
                    onChange={e => updateVendor(vendor.id, { name: e.target.value })}
                    placeholder="Company name"
                    suppressHydrationWarning style={{ ...inputCss, marginBottom: 10 }}
                    onFocus={e => { e.currentTarget.style.borderColor = "var(--color-accent)"; }}
                    onBlur={e => { e.currentTarget.style.borderColor = "var(--color-border)"; }}
                  />
                  <label style={{ ...labelCss, marginBottom: 6 }}>Proposal document</label>
                  <FileDropZone
                    file={vendor.file}
                    onFile={f => updateVendor(vendor.id, { file: f })}
                    placeholder="Drop vendor proposal"
                    compact
                  />
                </div>
              ))}
            </div>
          </div>

          <button
            type="submit" disabled={submitting}
            style={{
              width: "100%", padding: "12px 24px",
              backgroundColor: submitting ? "var(--color-surface)" : "var(--color-accent)",
              color: submitting ? "var(--color-text-muted)" : "var(--color-accent-foreground)",
              borderTop: "1px solid var(--color-border)",
              borderBottom: "1px solid var(--color-border)",
              borderLeft: "1px solid var(--color-border)",
              borderRight: "1px solid var(--color-border)",
              borderRadius: "var(--radius)",
              fontFamily: FONT, fontWeight: 600, fontSize: 14,
              cursor: submitting ? "not-allowed" : "pointer",
              transition: "opacity 150ms ease-out",
              display: "flex", alignItems: "center", justifyContent: "center", gap: 8,
            }}
          >
            {submitting && (
              <div style={{
                width: 14, height: 14,
                borderTop: "2px solid var(--color-text-muted)",
                borderBottom: "2px solid transparent",
                borderLeft: "2px solid transparent",
                borderRight: "2px solid transparent",
                borderRadius: "50%",
                animation: "meridian-spin 0.7s linear infinite",
              }} />
            )}
            {submitting ? "Starting evaluation…" : "Start evaluation →"}
          </button>
        </form>
      </div>
    );
  }

  function renderProgress() {
    const done  = Object.values(agentStatuses).filter(a => a.status === "done").length;
    const total = AGENTS.length;
    const pct   = total > 0 ? Math.round((done / total) * 100) : 0;

    return (
      <div style={{ maxWidth: 620 }}>
        <div style={{ marginBottom: 32 }}>
          <p style={{
            fontFamily: FONT, fontWeight: 600, fontSize: 11,
            letterSpacing: "0.1em", textTransform: "uppercase",
            color: "var(--color-info)", marginBottom: 8,
          }}>
            Evaluation in progress
          </p>
          <h1 style={{
            fontFamily: DISPLAY, fontWeight: 800,
            fontSize: isMobile ? 24 : 32,
            letterSpacing: "-0.03em", lineHeight: 1.0,
            color: "var(--color-text-primary)", marginBottom: 20,
          }}>
            Analysing vendors…
          </h1>

          <div style={{
            height: 3, backgroundColor: "var(--color-border)",
            borderRadius: 2, overflow: "hidden", marginBottom: 8,
          }}>
            <div style={{
              height: "100%", width: `${pct}%`,
              backgroundColor: "var(--color-info)", borderRadius: 2,
              transition: "width 600ms ease-out",
            }} />
          </div>
          <p style={{ fontFamily: MONO, fontSize: 11, color: "var(--color-text-muted)" }}>
            {done}/{total} agents complete
          </p>
        </div>

        <div style={{
          backgroundColor: "var(--color-surface)",
          borderTop: "1px solid var(--color-border)",
          borderBottom: "1px solid var(--color-border)",
          borderLeft: "1px solid var(--color-border)",
          borderRight: "1px solid var(--color-border)",
          borderRadius: "var(--radius)",
          boxShadow: "var(--shadow-sm)",
          overflow: "hidden",
          marginBottom: 24,
        }}>
          {AGENTS.map((agent, i) => {
            const s = agentStatuses[agent];
            const status     = s?.status ?? "pending";
            const message    = s?.message ?? "Waiting…";
            const isActive   = status === "running";
            const isDone     = status === "done";
            const isBlocked  = status === "blocked";

            return (
              <div key={agent} style={{
                display: "flex", alignItems: "flex-start", gap: 12,
                padding: "12px 16px",
                borderBottom: i < AGENTS.length - 1 ? "1px solid var(--color-border)" : "none",
                backgroundColor: isActive ? "var(--color-surface-hover)" : "transparent",
                borderLeft: isActive ? "2px solid var(--color-info)" : "2px solid transparent",
                transition: "background-color 150ms ease-out",
                ...(isActive ? { animation: "meridian-pulse-border 2s ease-in-out infinite" } : {}),
              }}>
                <div style={{
                  width: 7, height: 7, borderRadius: "50%",
                  flexShrink: 0, marginTop: 5,
                  backgroundColor: isBlocked ? "var(--color-error)"
                    : isDone ? "var(--color-success)"
                    : isActive ? "var(--color-info)"
                    : "var(--color-border)",
                  ...(isActive ? { animation: "meridian-dot-pulse 1.5s ease-in-out infinite" } : {}),
                }} />
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
                    <p style={{
                      fontFamily: FONT, fontWeight: 600, fontSize: 13,
                      color: isDone ? "var(--color-text-secondary)" : "var(--color-text-primary)",
                    }}>
                      {AGENT_LABELS[agent] ?? agent}
                    </p>
                    <span style={{
                      fontFamily: MONO, fontSize: 10, letterSpacing: "0.06em", textTransform: "uppercase",
                      color: isBlocked ? "var(--color-error)"
                        : isDone ? "var(--color-success)"
                        : isActive ? "var(--color-info)"
                        : "var(--color-text-muted)",
                    }}>
                      {status}
                    </span>
                  </div>
                  <p style={{ fontFamily: FONT, fontSize: 12, color: "var(--color-text-muted)", lineHeight: 1.5, marginTop: 2 }}>
                    {message}
                  </p>
                </div>
              </div>
            );
          })}
        </div>

        <button
          type="button"
          onClick={() => {
            esRef.current?.close();
            setShellState("idle");
            setCanvasPage("welcome");
            setRightExpanded(false);
          }}
          style={{
            background: "none", padding: "8px 0",
            borderTop: "none", borderBottom: "none",
            borderLeft: "none", borderRight: "none",
            cursor: "pointer",
            fontFamily: FONT, fontSize: 13, color: "var(--color-text-muted)",
            transition: "color 150ms ease-out",
          }}
          onMouseEnter={e => { e.currentTarget.style.color = "var(--color-error)"; }}
          onMouseLeave={e => { e.currentTarget.style.color = "var(--color-text-muted)"; }}
        >
          Cancel evaluation
        </button>
      </div>
    );
  }

  function renderResults() {
    if (!results) {
      return (
        <div style={{ display: "flex", alignItems: "center", gap: 8, padding: "40px 0" }}>
          <div style={{
            width: 16, height: 16,
            borderTop: "2px solid var(--color-info)",
            borderBottom: "2px solid transparent",
            borderLeft: "2px solid transparent",
            borderRight: "2px solid transparent",
            borderRadius: "50%",
            animation: "meridian-spin 0.7s linear infinite",
          }} />
          <p style={{ fontFamily: FONT, fontSize: 14, color: "var(--color-text-muted)" }}>Loading results…</p>
        </div>
      );
    }

    const allVendors  = results.vendors ?? [];
    const shortlisted = allVendors.filter(v => v.decision === "shortlisted");
    const rejected    = allVendors.filter(v => v.decision === "rejected");

    return (
      <div style={{ maxWidth: 680 }}>
        <div style={{ marginBottom: 32 }}>
          <p style={{
            fontFamily: FONT, fontWeight: 600, fontSize: 11,
            letterSpacing: "0.1em", textTransform: "uppercase",
            color: "var(--color-success)", marginBottom: 8,
          }}>
            Evaluation complete
          </p>
          <h1 style={{
            fontFamily: DISPLAY, fontWeight: 800,
            fontSize: isMobile ? 24 : 32,
            letterSpacing: "-0.03em", lineHeight: 1.0,
            color: "var(--color-text-primary)", marginBottom: 16,
          }}>
            Vendor Rankings
          </h1>

          {results.recommendation && (
            <div style={{
              padding: "12px 16px",
              backgroundColor: "var(--color-surface)",
              borderTop: "1px solid var(--color-border)",
              borderBottom: "1px solid var(--color-border)",
              borderLeft: "3px solid var(--color-success)",
              borderRight: "1px solid var(--color-border)",
              borderRadius: "var(--radius)",
              boxShadow: "var(--shadow-sm)",
            }}>
              <p style={{ fontFamily: FONT, fontSize: 10, fontWeight: 600, letterSpacing: "0.08em", textTransform: "uppercase", color: "var(--color-success)", marginBottom: 4 }}>
                Recommendation{results.approval_tier ? ` · ${results.approval_tier}` : ""}
              </p>
              <p style={{ fontFamily: FONT, fontSize: 14, color: "var(--color-text-primary)", lineHeight: 1.6 }}>
                {results.recommendation}
              </p>
            </div>
          )}
        </div>

        {shortlisted.length > 0 && (
          <div style={{ marginBottom: 20 }}>
            <p style={{ fontFamily: FONT, fontSize: 10, fontWeight: 600, letterSpacing: "0.08em", textTransform: "uppercase", color: "var(--color-success)", marginBottom: 10 }}>
              Shortlisted ({shortlisted.length})
            </p>
            <div style={{
              backgroundColor: "var(--color-surface)",
              borderTop: "1px solid var(--color-border)",
              borderBottom: "1px solid var(--color-border)",
              borderLeft: "1px solid var(--color-border)",
              borderRight: "1px solid var(--color-border)",
              borderRadius: "var(--radius)",
              boxShadow: "var(--shadow-sm)",
              overflow: "hidden",
            }}>
              {shortlisted.map((v, i) => (
                <div key={v.vendor_name} style={{
                  padding: "14px 16px",
                  borderBottom: i < shortlisted.length - 1 ? "1px solid var(--color-border)" : "none",
                  borderLeft: "3px solid var(--color-success)",
                }}>
                  <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: v.summary ? 4 : 0 }}>
                    <p style={{ fontFamily: FONT, fontWeight: 600, fontSize: 14, color: "var(--color-text-primary)" }}>
                      {v.vendor_name}
                    </p>
                    <span style={{ fontFamily: MONO, fontWeight: 700, fontSize: 22, color: "var(--color-text-primary)", fontVariantNumeric: "tabular-nums" }}>
                      {typeof v.total_score === "number" ? v.total_score.toFixed(1) : "—"}
                    </span>
                  </div>
                  {v.summary && (
                    <p style={{ fontFamily: FONT, fontSize: 12, color: "var(--color-text-muted)", lineHeight: 1.6 }}>
                      {v.summary}
                    </p>
                  )}
                </div>
              ))}
            </div>
          </div>
        )}

        {rejected.length > 0 && (
          <div style={{ marginBottom: 32 }}>
            <p style={{ fontFamily: FONT, fontSize: 10, fontWeight: 600, letterSpacing: "0.08em", textTransform: "uppercase", color: "var(--color-error)", marginBottom: 10 }}>
              Rejected ({rejected.length})
            </p>
            <div style={{
              backgroundColor: "var(--color-surface)",
              borderTop: "1px solid var(--color-border)",
              borderBottom: "1px solid var(--color-border)",
              borderLeft: "1px solid var(--color-border)",
              borderRight: "1px solid var(--color-border)",
              borderRadius: "var(--radius)",
              overflow: "hidden",
            }}>
              {rejected.map((v, i) => (
                <div key={v.vendor_name} style={{
                  padding: "14px 16px",
                  borderBottom: i < rejected.length - 1 ? "1px solid var(--color-border)" : "none",
                  borderLeft: "3px solid var(--color-error)",
                }}>
                  <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
                    <p style={{ fontFamily: FONT, fontWeight: 500, fontSize: 14, color: "var(--color-text-secondary)" }}>
                      {v.vendor_name}
                    </p>
                    <span style={{ fontFamily: MONO, fontSize: 20, color: "var(--color-text-muted)", fontVariantNumeric: "tabular-nums" }}>
                      {typeof v.total_score === "number" ? v.total_score.toFixed(1) : "—"}
                    </span>
                  </div>
                  {v.summary && (
                    <p style={{ fontFamily: FONT, fontSize: 12, color: "var(--color-text-muted)", lineHeight: 1.6, marginTop: 4 }}>
                      {v.summary}
                    </p>
                  )}
                </div>
              ))}
            </div>
          </div>
        )}

        <div style={{ display: "flex", gap: 12, flexWrap: "wrap" }}>
          {activeRunId && (
            <Link
              href={`/${activeRunId}/results`}
              style={{
                display: "inline-flex", alignItems: "center", gap: 6,
                padding: "9px 18px",
                backgroundColor: "var(--color-accent)",
                color: "var(--color-accent-foreground)",
                borderRadius: "var(--radius)",
                fontFamily: FONT, fontWeight: 600, fontSize: 13,
                textDecoration: "none",
                transition: "opacity 150ms ease-out",
              }}
              onMouseEnter={e => { e.currentTarget.style.opacity = "0.88"; }}
              onMouseLeave={e => { e.currentTarget.style.opacity = "1"; }}
            >
              Full report →
            </Link>
          )}
          <button
            type="button" onClick={startNewEval}
            style={{
              padding: "9px 18px", backgroundColor: "transparent",
              borderTop: "1px solid var(--color-border)",
              borderBottom: "1px solid var(--color-border)",
              borderLeft: "1px solid var(--color-border)",
              borderRight: "1px solid var(--color-border)",
              borderRadius: "var(--radius)",
              fontFamily: FONT, fontWeight: 500, fontSize: 13,
              color: "var(--color-text-secondary)", cursor: "pointer",
              transition: "border-color 150ms ease-out, color 150ms ease-out",
            }}
            onMouseEnter={e => { e.currentTarget.style.borderColor = "var(--color-border-strong)"; e.currentTarget.style.color = "var(--color-text-primary)"; }}
            onMouseLeave={e => { e.currentTarget.style.borderColor = "var(--color-border)"; e.currentTarget.style.color = "var(--color-text-secondary)"; }}
          >
            New evaluation
          </button>
        </div>
      </div>
    );
  }

  // ── Chat box ───────────────────────────────────────────────────────────────

  const chatPlaceholder = canvasPage === "results"
    ? "Ask about the results — e.g. Why was Vendor B rejected?"
    : "Ask a question or drop a document to analyse…";

  // ── Right panel ───────────────────────────────────────────────────────────

  const agentStatusColor = (status: string) => {
    if (status === "done") return "var(--color-success)";
    if (status === "blocked") return "var(--color-error)";
    if (status === "running") return "var(--color-info)";
    return "var(--color-border)";
  };

  // ── Main render ───────────────────────────────────────────────────────────

  return (
    <>
      <style>{`
        input:focus-visible, select:focus-visible, textarea:focus-visible {
          outline: 2px solid var(--color-accent);
          outline-offset: -1px;
        }
        @keyframes meridian-pulse-border {
          0%, 100% { opacity: 1; }
          50%       { opacity: 0.25; }
        }
        @keyframes meridian-dot-pulse {
          0%, 100% { transform: scale(1); opacity: 1; }
          50%       { transform: scale(1.6); opacity: 0.4; }
        }
        @keyframes meridian-spin {
          to { transform: rotate(360deg); }
        }
        @keyframes meridian-canvas-enter {
          from { opacity: 0; transform: translateY(10px); }
          to   { opacity: 1; transform: translateY(0); }
        }
      `}</style>

      <div style={{
        display: "flex", flexDirection: "column",
        height: "100vh", overflow: "hidden",
        background: "var(--bg-gradient)",
      }}>

        {/* ── Top Nav ──────────────────────────────────────────────────── */}
        <header style={{
          display: "flex", alignItems: "center", justifyContent: "space-between",
          height: 56, padding: "0 20px", flexShrink: 0, zIndex: 40,
          backgroundColor: navBg,
          borderBottom: "1px solid var(--color-border)",
          backdropFilter: "blur(12px)",
        }}>
          <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
            {isNarrow && (
              <button
                type="button"
                onClick={() => setSidebarOpen(o => !o)}
                aria-label="Toggle sidebar"
                style={{
                  background: "none", border: "none", cursor: "pointer",
                  color: "var(--color-text-muted)", padding: 4, marginRight: 4,
                  display: "flex", alignItems: "center",
                  transition: "color 150ms ease-out",
                }}
                onMouseEnter={e => { e.currentTarget.style.color = "var(--color-text-primary)"; }}
                onMouseLeave={e => { e.currentTarget.style.color = "var(--color-text-muted)"; }}
              >
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
                  <line x1="3" y1="6" x2="21" y2="6"/>
                  <line x1="3" y1="12" x2="21" y2="12"/>
                  <line x1="3" y1="18" x2="21" y2="18"/>
                </svg>
              </button>
            )}

            <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
              <div style={{
                width: 22, height: 22, borderRadius: 4,
                borderTop: "1.5px solid var(--color-accent)",
                borderBottom: "1.5px solid var(--color-accent)",
                borderLeft: "1.5px solid var(--color-accent)",
                borderRight: "1.5px solid var(--color-accent)",
                display: "flex", alignItems: "center", justifyContent: "center",
              }}>
                <div style={{ width: 7, height: 7, backgroundColor: "var(--color-accent)", borderRadius: 1 }} />
              </div>
              <span style={{
                fontFamily: DISPLAY, fontWeight: 700, fontSize: 13,
                letterSpacing: "0.05em", textTransform: "uppercase",
                color: "var(--color-text-primary)",
              }}>
                Meridian AI
              </span>
            </div>
          </div>

          <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
            {userInfo && !isMobile && (
              <span style={{ fontFamily: MONO, fontSize: 11, color: "var(--color-text-muted)" }}>
                {userInfo.email}
              </span>
            )}
            {userInfo && (
              <span style={{
                fontFamily: FONT, fontWeight: 600, fontSize: 10,
                letterSpacing: "0.08em", textTransform: "uppercase",
                color: "var(--color-accent)", padding: "2px 8px",
                borderTop: "1px solid var(--color-accent)",
                borderBottom: "1px solid var(--color-accent)",
                borderLeft: "1px solid var(--color-accent)",
                borderRight: "1px solid var(--color-accent)",
                borderRadius: 3,
              }}>
                {ROLE_DISPLAY[userInfo.role] ?? userInfo.role}
              </span>
            )}
          </div>
        </header>

        {/* ── Body ─────────────────────────────────────────────────────── */}
        <div style={{ display: "flex", flex: 1, overflow: "hidden", position: "relative" }}>

          {/* ── Left Sidebar ─────────────────────────────────────────── */}
          {(!isNarrow || sidebarOpen) && (
            <aside style={{
              width: 240, flexShrink: 0,
              display: "flex", flexDirection: "column",
              backgroundColor: sidebarBg,
              borderRight: "1px solid var(--color-border)",
              overflowY: "auto",
              ...(isNarrow ? {
                position: "absolute", top: 0, left: 0, bottom: 0,
                zIndex: 30, boxShadow: "var(--shadow-lg)",
              } : {}),
            }}>
              {/* New evaluation button */}
              <div style={{ padding: "14px 12px 8px" }}>
                <button
                  type="button" onClick={startNewEval}
                  style={{
                    width: "100%",
                    display: "flex", alignItems: "center", gap: 8,
                    padding: "9px 12px",
                    backgroundColor: "var(--color-accent)",
                    color: "var(--color-accent-foreground)",
                    borderTop: "none", borderBottom: "none",
                    borderLeft: "none", borderRight: "none",
                    borderRadius: "var(--radius)",
                    fontFamily: FONT, fontWeight: 600, fontSize: 13,
                    cursor: "pointer",
                    transition: "opacity 150ms ease-out",
                  }}
                  onMouseEnter={e => { e.currentTarget.style.opacity = "0.88"; }}
                  onMouseLeave={e => { e.currentTarget.style.opacity = "1"; }}
                >
                  <span style={{ fontSize: 16, fontWeight: 300, lineHeight: 1 }}>+</span>
                  New evaluation
                </button>
              </div>

              {/* Section label */}
              <div style={{ padding: "8px 16px 4px" }}>
                <p style={{
                  fontFamily: FONT, fontWeight: 600, fontSize: 10,
                  letterSpacing: "0.1em", textTransform: "uppercase",
                  color: "var(--color-text-muted)",
                }}>
                  RFP Evaluations
                </p>
              </div>

              {/* Recents */}
              <div style={{ flex: 1, padding: "0 8px" }}>
                {loading && (
                  <p style={{ fontFamily: FONT, fontSize: 12, color: "var(--color-text-muted)", padding: "8px 8px" }}>
                    Loading…
                  </p>
                )}
                {!loading && runs.length === 0 && (
                  <p style={{
                    fontFamily: FONT, fontSize: 12, color: "var(--color-text-muted)",
                    padding: "8px 8px", lineHeight: 1.6,
                  }}>
                    No evaluations yet.
                  </p>
                )}
                {!loading && runs.slice(0, 10).map(run => {
                  const isActive  = run.run_id === activeRunId;
                  const isRunning = run.status === "running";
                  return (
                    <button
                      key={run.run_id}
                      type="button"
                      onClick={() => openRun(run)}
                      style={{
                        width: "100%", textAlign: "left",
                        display: "flex", alignItems: "center", gap: 8,
                        padding: "7px 8px",
                        backgroundColor: isActive ? "var(--color-surface-hover)" : "transparent",
                        borderTop: "none", borderBottom: "none", borderRight: "none",
                        borderLeft: isActive ? "2px solid var(--color-accent)" : "2px solid transparent",
                        borderRadius: "0 var(--radius) var(--radius) 0",
                        cursor: "pointer",
                        transition: "background-color 150ms ease-out",
                        ...(isRunning ? { animation: "meridian-pulse-border 2.5s ease-in-out infinite" } : {}),
                      }}
                      onMouseEnter={e => { if (!isActive) e.currentTarget.style.backgroundColor = "var(--color-surface-hover)"; }}
                      onMouseLeave={e => { if (!isActive) e.currentTarget.style.backgroundColor = "transparent"; }}
                    >
                      <div style={{
                        width: 6, height: 6, borderRadius: "50%", flexShrink: 0,
                        backgroundColor: STATUS_DOT[run.status] ?? "var(--color-text-muted)",
                        ...(isRunning ? { animation: "meridian-dot-pulse 2s ease-in-out infinite" } : {}),
                      }} />
                      <span style={{
                        fontFamily: FONT, fontSize: 12,
                        fontWeight: isActive ? 600 : 400,
                        color: isActive ? "var(--color-text-primary)" : "var(--color-text-secondary)",
                        overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap",
                        flex: 1,
                      }}>
                        {run.rfp_title || "Untitled RFP"}
                      </span>
                    </button>
                  );
                })}
              </div>

              {/* Bottom nav */}
              <div style={{ borderTop: "1px solid var(--color-border)", padding: "8px" }}>
                <button
                  type="button" onClick={goHome}
                  style={{
                    width: "100%", textAlign: "left",
                    display: "flex", alignItems: "center", gap: 8,
                    padding: "7px 8px", background: "none",
                    borderTop: "none", borderBottom: "none",
                    borderLeft: "none", borderRight: "none",
                    cursor: "pointer", borderRadius: "var(--radius)",
                    fontFamily: FONT, fontSize: 12, color: "var(--color-text-muted)",
                    transition: "color 150ms ease-out, background-color 150ms ease-out",
                  }}
                  onMouseEnter={e => { e.currentTarget.style.color = "var(--color-text-primary)"; e.currentTarget.style.backgroundColor = "var(--color-surface-hover)"; }}
                  onMouseLeave={e => { e.currentTarget.style.color = "var(--color-text-muted)"; e.currentTarget.style.backgroundColor = "transparent"; }}
                >
                  <span style={{ width: 16, textAlign: "center", fontSize: 13 }}>⌂</span>
                  Home
                </button>

                {userInfo?.role === "org_admin" && (
                  <Link
                    href="/admin/settings"
                    style={{
                      display: "flex", alignItems: "center", gap: 8,
                      padding: "7px 8px", borderRadius: "var(--radius)",
                      fontFamily: FONT, fontSize: 12, color: "var(--color-text-muted)",
                      textDecoration: "none",
                      transition: "color 150ms ease-out, background-color 150ms ease-out",
                    }}
                    onMouseEnter={e => { e.currentTarget.style.color = "var(--color-text-primary)"; e.currentTarget.style.backgroundColor = "var(--color-surface-hover)"; }}
                    onMouseLeave={e => { e.currentTarget.style.color = "var(--color-text-muted)"; e.currentTarget.style.backgroundColor = "transparent"; }}
                  >
                    <span style={{ width: 16, textAlign: "center", fontSize: 13 }}>⚙</span>
                    Org Settings
                  </Link>
                )}

                <Link
                  href="/settings"
                  style={{
                    display: "flex", alignItems: "center", gap: 8,
                    padding: "7px 8px", borderRadius: "var(--radius)",
                    fontFamily: FONT, fontSize: 12, color: "var(--color-text-muted)",
                    textDecoration: "none",
                    transition: "color 150ms ease-out, background-color 150ms ease-out",
                  }}
                  onMouseEnter={e => { e.currentTarget.style.color = "var(--color-text-primary)"; e.currentTarget.style.backgroundColor = "var(--color-surface-hover)"; }}
                  onMouseLeave={e => { e.currentTarget.style.color = "var(--color-text-muted)"; e.currentTarget.style.backgroundColor = "transparent"; }}
                >
                  <span style={{ width: 16, textAlign: "center", fontSize: 13 }}>◎</span>
                  My Settings
                </Link>

                <button
                  type="button" onClick={signOut}
                  style={{
                    width: "100%", textAlign: "left",
                    display: "flex", alignItems: "center", gap: 8,
                    padding: "7px 8px", background: "none",
                    borderTop: "none", borderBottom: "none",
                    borderLeft: "none", borderRight: "none",
                    cursor: "pointer", borderRadius: "var(--radius)",
                    fontFamily: FONT, fontSize: 12, color: "var(--color-text-muted)",
                    transition: "color 150ms ease-out, background-color 150ms ease-out",
                  }}
                  onMouseEnter={e => { e.currentTarget.style.color = "var(--color-error)"; e.currentTarget.style.backgroundColor = "var(--color-surface-hover)"; }}
                  onMouseLeave={e => { e.currentTarget.style.color = "var(--color-text-muted)"; e.currentTarget.style.backgroundColor = "transparent"; }}
                >
                  <span style={{ width: 16, textAlign: "center", fontSize: 13 }}>→</span>
                  Sign out
                </button>
              </div>
            </aside>
          )}

          {/* Mobile overlay backdrop */}
          {isNarrow && sidebarOpen && (
            <div
              onClick={() => setSidebarOpen(false)}
              style={{
                position: "absolute", inset: 0, zIndex: 20,
                backgroundColor: "rgba(0,0,0,0.4)",
              }}
            />
          )}

          {/* ── Middle Column ────────────────────────────────────────── */}
          <main style={{
            flex: 1, display: "flex", flexDirection: "column",
            overflow: "hidden", minWidth: 0,
          }}>
            {/* Canvas — scrollable */}
            <div style={{
              flex: 1, overflowY: "auto",
              padding: isMobile ? "24px 16px" : isTablet ? "32px 24px" : "40px 40px",
            }}>
              <div key={canvasPage} style={{ animation: "meridian-canvas-enter 200ms ease-out" }}>
                {canvasPage === "welcome"     && renderWelcome()}
                {canvasPage === "upload-form" && renderUploadForm()}
                {canvasPage === "progress"    && renderProgress()}
                {canvasPage === "results"     && renderResults()}
              </div>
            </div>

            {/* Chat box — pinned bottom, hides when running */}
            <div style={{
              height: chatVisible ? 112 : 0,
              opacity: chatVisible ? 1 : 0,
              overflow: "hidden",
              transition: "height 250ms ease-out, opacity 200ms ease-out",
              flexShrink: 0,
            }}>
              <div style={{
                height: 112,
                borderTop: "1px solid var(--color-border)",
                backgroundColor: "var(--color-surface)",
                padding: "12px 20px 16px",
              }}>
                {chatMessages.length > 0 && (
                  <p style={{
                    fontFamily: FONT, fontSize: 11, color: "var(--color-text-muted)",
                    lineHeight: 1.4, marginBottom: 8,
                    overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap",
                  }}>
                    {chatMessages[chatMessages.length - 1].text}
                  </p>
                )}
                <form onSubmit={handleChat} style={{ display: "flex", gap: 8, alignItems: "center" }}>
                  <label htmlFor="chat-input" style={{ position: "absolute", width: 1, height: 1, overflow: "hidden", clip: "rect(0,0,0,0)" }}>
                    Chat message
                  </label>
                  <input
                    id="chat-input"
                    type="text"
                    value={chatInput}
                    onChange={e => setChatInput(e.target.value)}
                    placeholder={chatPlaceholder}
                    suppressHydrationWarning
                    style={{
                      flex: 1, padding: "8px 12px",
                      backgroundColor: "var(--color-background)",
                      borderTop: "1px solid var(--color-border)",
                      borderBottom: "1px solid var(--color-border)",
                      borderLeft: "1px solid var(--color-border)",
                      borderRight: "1px solid var(--color-border)",
                      borderRadius: "var(--radius)",
                      fontFamily: FONT, fontSize: 13,
                      color: "var(--color-text-primary)",
                      transition: "border-color 150ms ease-out",
                    }}
                    onFocus={e => { e.currentTarget.style.borderColor = "var(--color-accent)"; }}
                    onBlur={e => { e.currentTarget.style.borderColor = "var(--color-border)"; }}
                  />
                  <button
                    type="submit"
                    disabled={!chatInput.trim()}
                    aria-label="Send message"
                    style={{
                      width: 36, height: 36, flexShrink: 0,
                      display: "flex", alignItems: "center", justifyContent: "center",
                      backgroundColor: chatInput.trim() ? "var(--color-accent)" : "var(--color-surface-hover)",
                      borderTop: "none", borderBottom: "none",
                      borderLeft: "none", borderRight: "none",
                      borderRadius: "var(--radius)", fontSize: 15,
                      cursor: chatInput.trim() ? "pointer" : "default",
                      color: chatInput.trim() ? "var(--color-accent-foreground)" : "var(--color-text-muted)",
                      transition: "background-color 150ms ease-out",
                    }}
                  >
                    ↑
                  </button>
                </form>
              </div>
            </div>
          </main>

          {/* ── Right Panel — agent log ───────────────────────────────── */}
          {!isNarrow && (
            <aside style={{
              width: rightExpanded ? 320 : 40,
              flexShrink: 0,
              display: "flex",
              flexDirection: "column",
              backgroundColor: "var(--color-surface)",
              borderLeft: "1px solid var(--color-border)",
              overflow: "hidden",
              transition: "width 250ms ease-out",
            }}>
              {rightExpanded ? (
                <div style={{ display: "flex", flexDirection: "column", height: "100%" }}>
                  {/* Panel header */}
                  <div style={{
                    display: "flex", alignItems: "center", justifyContent: "space-between",
                    padding: "12px 16px",
                    borderBottom: "1px solid var(--color-border)",
                    flexShrink: 0,
                  }}>
                    <div>
                      <p style={{
                        fontFamily: FONT, fontWeight: 600, fontSize: 11,
                        letterSpacing: "0.08em", textTransform: "uppercase",
                        color: "var(--color-text-muted)",
                      }}>
                        Agent Log
                      </p>
                      {shellState === "running" && (
                        <div style={{ display: "flex", alignItems: "center", gap: 4, marginTop: 2 }}>
                          <div style={{
                            width: 5, height: 5, borderRadius: "50%",
                            backgroundColor: "var(--color-info)",
                            animation: "meridian-dot-pulse 1.5s ease-in-out infinite",
                          }} />
                          <p style={{ fontFamily: MONO, fontSize: 10, color: "var(--color-info)" }}>Live</p>
                        </div>
                      )}
                    </div>
                    <button
                      type="button"
                      onClick={() => setRightExpanded(false)}
                      aria-label="Collapse agent log"
                      style={{
                        background: "none", border: "none", cursor: "pointer",
                        color: "var(--color-text-muted)", padding: 4, fontSize: 14,
                        transition: "color 150ms ease-out",
                      }}
                      onMouseEnter={e => { e.currentTarget.style.color = "var(--color-text-primary)"; }}
                      onMouseLeave={e => { e.currentTarget.style.color = "var(--color-text-muted)"; }}
                    >
                      →
                    </button>
                  </div>

                  {/* Events feed */}
                  <div style={{ flex: 1, overflowY: "auto", padding: "12px" }}>
                    {agentEvents.length === 0 && (
                      <p style={{ fontFamily: FONT, fontSize: 12, color: "var(--color-text-muted)", lineHeight: 1.6 }}>
                        {shellState === "running" ? "Waiting for first agent event…" : "No events recorded."}
                      </p>
                    )}
                    {agentEvents.map((ev, i) => (
                      <div key={i} style={{ marginBottom: 12 }}>
                        <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 3 }}>
                          <div style={{
                            width: 5, height: 5, borderRadius: "50%", flexShrink: 0,
                            backgroundColor: agentStatusColor(ev.status),
                          }} />
                          <p style={{
                            fontFamily: MONO, fontSize: 10, fontWeight: 600,
                            color: "var(--color-text-secondary)", letterSpacing: "0.04em",
                          }}>
                            {AGENT_LABELS[ev.agent] ?? ev.agent}
                          </p>
                          <p style={{ fontFamily: MONO, fontSize: 10, color: "var(--color-text-muted)", marginLeft: "auto" }}>
                            {ev.status}
                          </p>
                        </div>
                        <p style={{
                          fontFamily: FONT, fontSize: 11,
                          color: "var(--color-text-muted)", lineHeight: 1.5, paddingLeft: 11,
                        }}>
                          {ev.message}
                        </p>
                      </div>
                    ))}
                    <div ref={logEndRef} />
                  </div>
                </div>
              ) : (
                /* Collapsed strip with rotated label */
                <div
                  onClick={() => setRightExpanded(true)}
                  role="button"
                  tabIndex={0}
                  onKeyDown={e => { if (e.key === "Enter" || e.key === " ") setRightExpanded(true); }}
                  aria-label="Expand agent log"
                  style={{
                    flex: 1, display: "flex",
                    flexDirection: "column",
                    alignItems: "center", justifyContent: "center",
                    cursor: "pointer", gap: 10,
                    transition: "background-color 150ms ease-out",
                  }}
                  onMouseEnter={e => { (e.currentTarget as HTMLElement).style.backgroundColor = "var(--color-surface-hover)"; }}
                  onMouseLeave={e => { (e.currentTarget as HTMLElement).style.backgroundColor = "transparent"; }}
                >
                  <span style={{
                    fontFamily: FONT, fontWeight: 600, fontSize: 10,
                    letterSpacing: "0.12em", textTransform: "uppercase",
                    color: shellState === "running" ? "var(--color-info)" : "var(--color-text-muted)",
                    writingMode: "vertical-rl",
                    textOrientation: "mixed",
                    transform: "rotate(180deg)",
                    userSelect: "none",
                    transition: "color 150ms ease-out",
                  }}>
                    Agent Log
                  </span>
                  {shellState === "running" && (
                    <div style={{
                      width: 6, height: 6, borderRadius: "50%",
                      backgroundColor: "var(--color-info)",
                      animation: "meridian-dot-pulse 1.5s ease-in-out infinite",
                    }} />
                  )}
                </div>
              )}
            </aside>
          )}
        </div>
      </div>
    </>
  );
}
