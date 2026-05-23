"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { FONT, DISPLAY, MONO } from "@/lib/theme";
import { useThemeContext } from "@/components/layout/ThemeProvider";
import { useBreakpoint } from "@/lib/hooks";
import { api, getUserInfo, clearUserInfo, isLoggedIn, type UserInfo } from "@/lib/api";
import { type EvalRun, type AgentEvent, type EvalResults, type ChatMessage, type ChatSession } from "@/lib/types";
import { AGENTS, AGENT_LABELS, ROLE_DISPLAY, STATUS_DOT } from "@/lib/constants";
import { WelcomePage } from "@/components/features/WelcomePage";
import { ProgressPage } from "@/components/features/ProgressPage";
import { ResultsPage } from "@/components/features/ResultsPage";
import { NewEvaluationForm } from "@/components/features/NewEvaluationForm";
import { ConfirmSetupPage } from "@/components/features/ConfirmSetupPage";
import { DevLogPanel, type DevLogEntry } from "@/components/features/DevLogPanel";

// ── Shell types ───────────────────────────────────────────────────────────────

type ShellState = "idle" | "running" | "completed";
type CanvasPage = "welcome" | "upload-form" | "confirm" | "progress" | "results";

// ── Main shell ────────────────────────────────────────────────────────────────

export default function HomePage() {
  const router = useRouter();
  const { isDark } = useThemeContext();
  const bp = useBreakpoint();
  const isMobile = bp === "mobile";
  const isTablet = bp === "tablet";
  const isNarrow = isMobile || isTablet;

  // Shell state machine
  const [shellState, setShellState]     = useState<ShellState>("idle");
  const [canvasPage, setCanvasPage]     = useState<CanvasPage>("welcome");
  const [activeRunId, setActiveRunId]   = useState<string | null>(null);
  const [confirmRunId, setConfirmRunId] = useState<string | null>(null);
  const [rightExpanded, setRightExpanded] = useState(false);
  const [sidebarOpen, setSidebarOpen]   = useState(false);

  // Data
  const [runs, setRuns]         = useState<EvalRun[]>([]);
  const [loading, setLoading]   = useState(true);
  const [userInfo, setUserInfo] = useState<UserInfo | null>(null);
  const isDevRole = userInfo?.role === "org_admin" || userInfo?.role === "company_admin";
  const [hoveredRunId, setHoveredRunId]   = useState<string | null>(null);
  const [deletingRunId, setDeletingRunId] = useState<string | null>(null);

  // Progress + agent log
  const [agentStatuses, setAgentStatuses] = useState<Record<string, { status: string; message: string }>>({});
  const [agentEvents, setAgentEvents]     = useState<AgentEvent[]>([]);

  // Developer log
  const [devLogEntries, setDevLogEntries]   = useState<DevLogEntry[]>([]);
  const [devLogConnected, setDevLogConnected] = useState(false);
  const [rightTab, setRightTab] = useState<"agent" | "dev">("agent");
  const devEsRef = useRef<EventSource | null>(null);

  // Results
  const [results, setResults] = useState<EvalResults | null>(null);

  // Chat
  const [chatInput, setChatInput]         = useState("");
  const [chatMessages, setChatMessages]   = useState<ChatMessage[]>([]);
  const [chatFocused, setChatFocused]     = useState(false);
  const [chatFile, setChatFile]           = useState<File | null>(null);
  const [chatLoading, setChatLoading]     = useState(false);
  const [chatFileDragging, setChatFileDragging] = useState(false);
  const [chatSessionId, setChatSessionId] = useState<string | null>(null);
  const [chatSessions, setChatSessions]   = useState<ChatSession[]>([]);

  // Saved success criteria
  const [savedCriteria, setSavedCriteria]       = useState<string[]>([]);
  const [criteriaEditMode, setCriteriaEditMode] = useState(false);
  const [savedConfirm, setSavedConfirm]         = useState<string | null>(null);

  // Refs
  const logEndRef = useRef<HTMLDivElement>(null);
  const esRef     = useRef<EventSource | null>(null);

  const chatVisible = shellState !== "running" && canvasPage !== "confirm";

  // ── Background colours (TODO next pass: replace with CSS vars) ────────────
  const sidebarBg = isDark ? "rgba(8,10,18,0.98)" : "rgba(247,249,252,0.98)";
  const navBg     = isDark ? "rgba(8,10,18,0.95)" : "rgba(247,249,252,0.95)";

  // ── Chat session helpers ──────────────────────────────────────────────────

  function _chatStorageKey(email: string) {
    return `meridian_chat_sessions_${email}`;
  }

  function _loadSessions(email: string): ChatSession[] {
    try {
      const raw = localStorage.getItem(_chatStorageKey(email));
      return raw ? (JSON.parse(raw) as ChatSession[]) : [];
    } catch { return []; }
  }

  function _persistSession(email: string, session: ChatSession, allSessions: ChatSession[]) {
    const updated = [session, ...allSessions.filter(s => s.id !== session.id)].slice(0, 20);
    try { localStorage.setItem(_chatStorageKey(email), JSON.stringify(updated)); } catch { /* quota */ }
    setChatSessions(updated);
  }

  function newChatSession() {
    setChatMessages([]);
    setChatSessionId(null);
    setChatInput("");
    setChatFile(null);
    setCanvasPage("welcome");
  }

  function loadChatSession(session: ChatSession) {
    setChatMessages(session.messages);
    setChatSessionId(session.id);
    setChatInput("");
    setChatFile(null);
    setCanvasPage("welcome");
  }

  // ── Auth + initial load ───────────────────────────────────────────────────

  useEffect(() => {
    if (!isLoggedIn()) { router.push("/login"); return; }
    const info = getUserInfo();
    setUserInfo(info);
    if (info?.email) {
      setChatSessions(_loadSessions(info.email));
    }
    api.get<{ runs?: EvalRun[] } | EvalRun[]>("/api/v1/evaluate/list", {
      on401: () => router.push("/login"),
    })
      .then(data => setRuns(Array.isArray(data) ? data : (data.runs ?? [])))
      .catch(() => {})
      .finally(() => setLoading(false));
    api.get<{ criteria: string[] }>("/api/v1/chat/criteria")
      .then(data => setSavedCriteria(data.criteria ?? []))
      .catch(() => {});
  }, [router]);

  // ── SSE stream while running ──────────────────────────────────────────────

  useEffect(() => {
    if (shellState !== "running" || !activeRunId) return;
    let es: EventSource | null = null;
    let retryTimer: ReturnType<typeof setTimeout> | null = null;
    let closed = false;

    function connect() {
      if (closed) return;
      es = new EventSource(`/api/v1/evaluate/${activeRunId}/status`, { withCredentials: true });
      esRef.current = es;

      es.onmessage = e => {
        try {
          const ev = JSON.parse(e.data) as Record<string, unknown>;
          if (ev.type === "heartbeat") return;
          if (ev.type === "done") {
            closed = true; es?.close();
            setShellState("completed"); setCanvasPage("results"); return;
          }
          const agentEv = ev as unknown as AgentEvent;
          if (agentEv.agent) {
            setAgentEvents(prev => [...prev, agentEv]);
            setAgentStatuses(prev => ({ ...prev, [agentEv.agent]: { status: agentEv.status, message: agentEv.message } }));
            if (agentEv.agent === "explanation" && agentEv.status === "done") {
              closed = true; es?.close();
              setShellState("completed"); setCanvasPage("results");
            }
          }
        } catch { /* malformed event */ }
      };

      es.onerror = () => {
        es?.close(); esRef.current = null;
        if (!closed) retryTimer = setTimeout(connect, 2000);
      };
    }

    connect();
    return () => {
      closed = true;
      if (retryTimer) clearTimeout(retryTimer);
      es?.close(); esRef.current = null;
    };
  }, [shellState, activeRunId]);

  // ── Dev log SSE ───────────────────────────────────────────────────────────

  useEffect(() => {
    if (!isDevRole) return;
    const url = activeRunId ? `/api/v1/logs/stream?run_id=${activeRunId}` : `/api/v1/logs/stream`;
    const es = new EventSource(url, { withCredentials: true });
    devEsRef.current = es;
    es.onopen    = () => setDevLogConnected(true);
    es.onerror   = () => setDevLogConnected(false);
    es.onmessage = (e) => {
      try {
        const entry = JSON.parse(e.data);
        if (entry.type === "dev") setDevLogEntries(prev => [...prev.slice(-1999), entry as DevLogEntry]);
      } catch { /* skip */ }
    };
    return () => { es.close(); devEsRef.current = null; setDevLogConnected(false); };
  }, [isDevRole, activeRunId]);

  // ── Results fetch ─────────────────────────────────────────────────────────

  useEffect(() => {
    if (canvasPage !== "results" || !activeRunId) return;
    api.get<EvalResults>(`/api/v1/evaluate/${activeRunId}/results`, {
      on401: () => router.push("/login"),
    }).then(setResults).catch(() => {});
  }, [canvasPage, activeRunId, router]);

  // ── Auto-scroll agent log ─────────────────────────────────────────────────

  useEffect(() => {
    logEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [agentEvents]);

  // ── Handlers ─────────────────────────────────────────────────────────────

  async function signOut() {
    await api.post("/api/v1/auth/logout").catch(() => {});
    clearUserInfo();
    router.push("/login");
  }

  function startNewEval() {
    setCanvasPage("upload-form");
    if (isNarrow) setSidebarOpen(false);
  }

  function goHome() {
    setCanvasPage("welcome");
    if (isNarrow) setSidebarOpen(false);
  }

  function openRun(run: EvalRun) {
    setActiveRunId(run.run_id);
    if (run.status === "completed" || run.status === "complete") {
      setShellState("completed"); setCanvasPage("results");
    } else if (run.status === "running") {
      setShellState("running"); setCanvasPage("progress"); setRightExpanded(true);
    } else if (run.status === "pending_confirm") {
      setConfirmRunId(run.run_id); setCanvasPage("confirm");
    } else if (run.status === "interrupted" || run.status === "failed") {
      setShellState("completed"); setCanvasPage("results");
    } else {
      setCanvasPage("welcome");
    }
    if (isNarrow) setSidebarOpen(false);
  }

  async function deleteRun(e: React.MouseEvent, runId: string) {
    e.stopPropagation();
    setDeletingRunId(runId);
    try {
      await api.delete(`/api/v1/evaluate/${runId}`);
      setRuns(prev => prev.filter(r => r.run_id !== runId));
      if (activeRunId === runId) {
        setActiveRunId(null); setCanvasPage("welcome"); setShellState("idle");
      }
    } catch { /* 409 for completed/running runs */ }
    finally { setDeletingRunId(null); }
  }

  function handleEvalSuccess(runId: string, rfpTitle: string, vendorCount: number) {
    setActiveRunId(runId); setConfirmRunId(runId);
    setAgentStatuses({}); setAgentEvents([]); setDevLogEntries([]); setResults(null);
    setCanvasPage("confirm");
    setRuns(prev => [{
      run_id: runId, rfp_title: rfpTitle,
      status: "pending_confirm", vendor_count: vendorCount,
      created_at: new Date().toISOString(),
    }, ...prev]);
  }

  async function handleCancelEval() {
    esRef.current?.close();
    if (activeRunId) {
      try { await api.post(`/api/v1/evaluate/${activeRunId}/cancel`); } catch { /* best-effort */ }
      setRuns(prev => prev.map(r =>
        r.run_id === activeRunId ? { ...r, status: "interrupted" } : r
      ));
    }
    setShellState("idle"); setCanvasPage("welcome"); setRightExpanded(false);
  }

  async function handleChat(e: React.FormEvent) {
    e.preventDefault();
    if (!chatInput.trim()) return;
    const msg = chatInput.trim();
    const attachedFile = chatFile;
    setChatInput(""); setChatFile(null);
    const ta = document.getElementById("chat-textarea") as HTMLTextAreaElement | null;
    if (ta) ta.style.height = "auto";

    const userMsg: ChatMessage = { role: "user", text: msg };
    const updatedWithUser = [...chatMessages, userMsg];
    setChatMessages(updatedWithUser);
    setChatLoading(true);

    const form = new FormData();
    form.append("message", msg);
    if (attachedFile) form.append("file", attachedFile);

    let assistantMsg: ChatMessage = { role: "assistant", text: "" };
    try {
      const res = await api.post<{ answer: string; suggested_criteria: string[] }>(
        "/api/v1/chat/document", { body: form }
      );
      assistantMsg = {
        role: "assistant", text: res.answer,
        suggestedCriteria: res.suggested_criteria?.length ? res.suggested_criteria : undefined,
      };
    } catch {
      assistantMsg = { role: "assistant", text: "Sorry, something went wrong. Please try again." };
    } finally { setChatLoading(false); }

    const finalMessages = [...updatedWithUser, assistantMsg];
    setChatMessages(finalMessages);

    const email = userInfo?.email ?? "";
    if (email) {
      const sid   = chatSessionId ?? `chat_${Date.now()}`;
      const title = msg.length > 48 ? msg.slice(0, 48) + "…" : msg;
      const now   = new Date().toISOString();
      const session: ChatSession = {
        id: sid, title, messages: finalMessages,
        createdAt: chatSessionId ? (chatSessions.find(s => s.id === sid)?.createdAt ?? now) : now,
        updatedAt: now,
      };
      if (!chatSessionId) setChatSessionId(sid);
      _persistSession(email, session, chatSessions);
    }
  }

  async function handleSaveCriteria(criteria: string[]) {
    try {
      await api.post("/api/v1/chat/criteria", { body: { criteria } });
      setSavedCriteria(criteria);
      setSavedConfirm("Criteria saved");
    } catch {
      setSavedConfirm("Failed to save");
    } finally {
      setTimeout(() => setSavedConfirm(null), 3000);
    }
  }

  // ── Right-panel helper ────────────────────────────────────────────────────

  const agentStatusColor = (status: string) => {
    if (status === "done")    return "var(--color-success)";
    if (status === "blocked") return "var(--color-error)";
    if (status === "running") return "var(--color-info)";
    return "var(--color-border)";
  };

  const chatPlaceholder = chatFile
    ? `Ask about ${chatFile.name} — e.g. "What are our SLA thresholds?"`
    : canvasPage === "results"
      ? "Ask about the results — e.g. Why was Vendor B rejected?"
      : "Ask a question or drop a document to analyse…";

  // ── Render ────────────────────────────────────────────────────────────────

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

        {/* ── Top Nav ──────────────────────────────────────────────── */}
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

        {/* ── Body ─────────────────────────────────────────────────── */}
        <div style={{ display: "flex", flex: 1, overflow: "hidden", position: "relative" }}>

          {/* ── Left Sidebar ─────────────────────────────────────── */}
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
              <div style={{ padding: "14px 12px 8px" }}>
                <button
                  type="button" onClick={startNewEval}
                  style={{
                    width: "100%", display: "flex", alignItems: "center", gap: 8,
                    padding: "9px 12px",
                    backgroundColor: "var(--color-accent)",
                    color: "var(--color-accent-foreground)",
                    borderTop: "none", borderBottom: "none",
                    borderLeft: "none", borderRight: "none",
                    borderRadius: "var(--radius)",
                    fontFamily: FONT, fontWeight: 600, fontSize: 13,
                    cursor: "pointer", transition: "opacity 150ms ease-out",
                  }}
                  onMouseEnter={e => { e.currentTarget.style.opacity = "0.88"; }}
                  onMouseLeave={e => { e.currentTarget.style.opacity = "1"; }}
                >
                  <span style={{ fontSize: 16, fontWeight: 300, lineHeight: 1 }}>+</span>
                  New evaluation
                </button>
              </div>

              {/* Personal chats */}
              <div style={{ padding: "8px 16px 4px", display: "flex", alignItems: "center", justifyContent: "space-between" }}>
                <p style={{
                  fontFamily: FONT, fontWeight: 600, fontSize: 10,
                  letterSpacing: "0.1em", textTransform: "uppercase",
                  color: "var(--color-text-muted)",
                }}>Personal</p>
                <button
                  type="button" onClick={newChatSession} title="New chat"
                  style={{
                    background: "none",
                    borderTop: "none", borderBottom: "none", borderLeft: "none", borderRight: "none",
                    cursor: "pointer", padding: "2px 4px", borderRadius: "var(--radius)",
                    fontFamily: FONT, fontSize: 11, color: "var(--color-text-muted)",
                    transition: "color 150ms ease-out", lineHeight: 1,
                  }}
                  onMouseEnter={e => { e.currentTarget.style.color = "var(--color-accent)"; }}
                  onMouseLeave={e => { e.currentTarget.style.color = "var(--color-text-muted)"; }}
                >+ new</button>
              </div>

              <div style={{ padding: "0 8px 4px" }}>
                {chatSessions.length === 0 && (
                  <p style={{ fontFamily: FONT, fontSize: 11, color: "var(--color-text-muted)", padding: "4px 8px", lineHeight: 1.5 }}>
                    No chats yet. Ask a question below.
                  </p>
                )}
                {chatSessions.slice(0, 8).map(session => {
                  const isActive = session.id === chatSessionId;
                  return (
                    <button
                      key={session.id} type="button"
                      onClick={() => loadChatSession(session)}
                      style={{
                        width: "100%", textAlign: "left",
                        display: "flex", alignItems: "center", gap: 8,
                        padding: "6px 8px",
                        backgroundColor: isActive ? "var(--color-surface-hover)" : "transparent",
                        borderTop: "none", borderBottom: "none", borderRight: "none",
                        borderLeft: isActive ? "2px solid var(--color-accent)" : "2px solid transparent",
                        borderRadius: "0 var(--radius) var(--radius) 0",
                        cursor: "pointer", transition: "background-color 150ms ease-out",
                      }}
                      onMouseEnter={e => { if (!isActive) e.currentTarget.style.backgroundColor = "var(--color-surface-hover)"; }}
                      onMouseLeave={e => { if (!isActive) e.currentTarget.style.backgroundColor = "transparent"; }}
                    >
                      <span style={{ fontSize: 9, color: "var(--color-text-muted)", flexShrink: 0 }}>💬</span>
                      <span style={{
                        fontFamily: FONT, fontSize: 11,
                        fontWeight: isActive ? 600 : 400,
                        color: isActive ? "var(--color-text-primary)" : "var(--color-text-secondary)",
                        overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", flex: 1,
                      }}>
                        {session.title}
                      </span>
                    </button>
                  );
                })}
              </div>

              <div style={{ height: 1, backgroundColor: "var(--color-border)", margin: "4px 0" }} />

              {/* RFP Evaluations */}
              <div style={{ padding: "8px 16px 4px" }}>
                <p style={{
                  fontFamily: FONT, fontWeight: 600, fontSize: 10,
                  letterSpacing: "0.1em", textTransform: "uppercase",
                  color: "var(--color-text-muted)",
                }}>RFP Evaluations</p>
              </div>

              <div style={{ flex: 1, padding: "0 8px" }}>
                {loading && (
                  <p style={{ fontFamily: FONT, fontSize: 12, color: "var(--color-text-muted)", padding: "8px 8px" }}>Loading…</p>
                )}
                {!loading && runs.length === 0 && (
                  <p style={{ fontFamily: FONT, fontSize: 12, color: "var(--color-text-muted)", padding: "8px 8px", lineHeight: 1.6 }}>
                    No evaluations yet.
                  </p>
                )}
                {!loading && runs.slice(0, 10).map(run => {
                  const isActive    = run.run_id === activeRunId;
                  const isRunning   = run.status === "running";
                  const isCompleted = run.status === "completed";
                  const canDelete   = !isCompleted && !isRunning;
                  const isHovered   = hoveredRunId === run.run_id;
                  const isDeleting  = deletingRunId === run.run_id;
                  return (
                    <div
                      key={run.run_id}
                      style={{ position: "relative" }}
                      onMouseEnter={() => setHoveredRunId(run.run_id)}
                      onMouseLeave={() => setHoveredRunId(null)}
                    >
                      <button
                        type="button" onClick={() => openRun(run)}
                        style={{
                          width: "100%", textAlign: "left",
                          display: "flex", alignItems: "center", gap: 8,
                          padding: "7px 8px",
                          paddingRight: canDelete ? 28 : 8,
                          backgroundColor: isActive ? "var(--color-surface-hover)" : "transparent",
                          borderTop: "none", borderBottom: "none", borderRight: "none",
                          borderLeft: isActive ? "2px solid var(--color-accent)" : "2px solid transparent",
                          borderRadius: "0 var(--radius) var(--radius) 0",
                          cursor: "pointer", transition: "background-color 150ms ease-out",
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
                          overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", flex: 1,
                        }}>
                          {run.rfp_title || "Untitled RFP"}
                        </span>
                      </button>

                      {canDelete && (
                        <button
                          type="button"
                          onClick={e => deleteRun(e, run.run_id)}
                          title="Delete run"
                          style={{
                            position: "absolute", right: 6, top: "50%",
                            transform: "translateY(-50%)",
                            opacity: isHovered && !isDeleting ? 1 : 0,
                            pointerEvents: isHovered ? "auto" : "none",
                            background: "none",
                            borderTop: "none", borderBottom: "none", borderLeft: "none", borderRight: "none",
                            cursor: "pointer", padding: "2px 4px",
                            color: "var(--color-text-muted)",
                            fontSize: 13, lineHeight: 1,
                            transition: "opacity 150ms ease-out, color 150ms ease-out",
                          }}
                          onMouseEnter={e => { e.currentTarget.style.color = "var(--color-error)"; }}
                          onMouseLeave={e => { e.currentTarget.style.color = "var(--color-text-muted)"; }}
                        >
                          {isDeleting ? "…" : "×"}
                        </button>
                      )}
                    </div>
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

          {/* ── Middle Column ──────────────────────────────────────── */}
          <main style={{ flex: 1, display: "flex", flexDirection: "column", overflow: "hidden", minWidth: 0 }}>

            {/* Canvas */}
            <div style={{
              flex: 1, overflowY: "auto",
              padding: isMobile ? "24px 16px" : isTablet ? "32px 24px" : "40px 40px",
            }}>
              {/* Upload form — kept mounted during confirm so back-nav restores files */}
              {(canvasPage === "upload-form" || canvasPage === "confirm") && (
                <div style={{ display: canvasPage === "upload-form" ? "block" : "none" }}>
                  <NewEvaluationForm
                    onBack={() => setCanvasPage("welcome")}
                    onSuccess={handleEvalSuccess}
                    onAuth401={() => router.push("/login")}
                  />
                </div>
              )}

              {canvasPage !== "upload-form" && canvasPage !== "confirm" && (
                <div key={canvasPage} style={{ animation: "meridian-canvas-enter 200ms ease-out" }}>
                  {canvasPage === "welcome" && (
                    <WelcomePage
                      runs={runs}
                      loading={loading}
                      userInfo={userInfo}
                      isMobile={isMobile}
                      chatMessages={chatMessages}
                      chatLoading={chatLoading}
                      savedCriteria={savedCriteria}
                      criteriaEditMode={criteriaEditMode}
                      savedConfirm={savedConfirm}
                      onStartNewEval={startNewEval}
                      onOpenRun={openRun}
                      onSaveCriteria={handleSaveCriteria}
                      onSavedCriteriaChange={setSavedCriteria}
                      onCriteriaEditModeChange={setCriteriaEditMode}
                    />
                  )}
                  {canvasPage === "progress" && (
                    <ProgressPage
                      agentStatuses={agentStatuses}
                      isMobile={isMobile}
                      onCancel={handleCancelEval}
                    />
                  )}
                  {canvasPage === "results" && (
                    <ResultsPage
                      results={results}
                      activeRunId={activeRunId}
                      isMobile={isMobile}
                      onStartNewEval={startNewEval}
                    />
                  )}
                </div>
              )}

              {canvasPage === "confirm" && (
                <div style={{ animation: "meridian-canvas-enter 200ms ease-out" }}>
                  <ConfirmSetupPage
                    runId={confirmRunId!}
                    onConfirmed={() => {
                      setShellState("running");
                      setCanvasPage("progress");
                      setRightExpanded(true);
                      setRuns(prev => prev.map(r =>
                        r.run_id === confirmRunId ? { ...r, status: "running" } : r
                      ));
                    }}
                    onBack={() => setCanvasPage("upload-form")}
                    onAuth401={() => router.push("/login")}
                  />
                </div>
              )}
            </div>

            {/* Chat box — pinned bottom, hides when running */}
            <div style={{
              maxHeight: chatVisible ? 220 : 0,
              opacity: chatVisible ? 1 : 0,
              overflow: "hidden",
              transition: "max-height 300ms ease-out, opacity 200ms ease-out",
              flexShrink: 0,
            }}>
              <div style={{
                borderTop: "1px solid var(--color-border)",
                backgroundColor: "var(--color-background)",
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
                <form
                  onSubmit={handleChat}
                  onDragOver={e => { e.preventDefault(); setChatFileDragging(true); }}
                  onDragLeave={() => setChatFileDragging(false)}
                  onDrop={e => {
                    e.preventDefault(); setChatFileDragging(false);
                    const f = e.dataTransfer.files[0];
                    if (f) setChatFile(f);
                  }}
                  style={{
                    backgroundColor: chatFileDragging ? "var(--color-surface-hover)" : "var(--color-surface)",
                    borderRadius: 14,
                    boxShadow: chatFocused ? "var(--shadow-lg)" : "var(--shadow-md)",
                    borderTop: `1px solid ${chatFileDragging || chatFocused ? "var(--color-accent)" : "var(--color-border)"}`,
                    borderBottom: `1px solid ${chatFileDragging || chatFocused ? "var(--color-accent)" : "var(--color-border)"}`,
                    borderLeft: `1px solid ${chatFileDragging || chatFocused ? "var(--color-accent)" : "var(--color-border)"}`,
                    borderRight: `1px solid ${chatFileDragging || chatFocused ? "var(--color-accent)" : "var(--color-border)"}`,
                    transition: "border-color 150ms ease-out, box-shadow 150ms ease-out, background-color 150ms ease-out",
                  }}
                >
                  <label htmlFor="chat-textarea" style={{ position: "absolute", width: 1, height: 1, overflow: "hidden", clip: "rect(0,0,0,0)" }}>
                    Chat message
                  </label>
                  {chatFile && (
                    <div style={{ display: "flex", alignItems: "center", gap: 6, padding: "8px 16px 0" }}>
                      <div style={{
                        display: "inline-flex", alignItems: "center", gap: 6,
                        padding: "3px 8px 3px 10px",
                        backgroundColor: "var(--color-surface-hover)",
                        borderTop: "1px solid var(--color-border)",
                        borderBottom: "1px solid var(--color-border)",
                        borderLeft: "1px solid var(--color-border)",
                        borderRight: "1px solid var(--color-border)",
                        borderRadius: 6,
                      }}>
                        <span style={{ fontSize: 12 }}>📄</span>
                        <span style={{ fontFamily: FONT, fontSize: 12, color: "var(--color-text-primary)", maxWidth: 180, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                          {chatFile.name}
                        </span>
                        <button
                          type="button" onClick={() => setChatFile(null)} aria-label="Remove attached file"
                          style={{
                            background: "none", border: "none", cursor: "pointer",
                            color: "var(--color-text-muted)", fontSize: 14,
                            padding: "0 2px", lineHeight: 1, flexShrink: 0,
                          }}
                        >×</button>
                      </div>
                    </div>
                  )}
                  <textarea
                    id="chat-textarea"
                    rows={1}
                    value={chatInput}
                    onChange={e => setChatInput(e.target.value)}
                    onInput={e => {
                      const el = e.currentTarget;
                      el.style.height = "auto";
                      el.style.height = Math.min(el.scrollHeight, 120) + "px";
                    }}
                    onKeyDown={e => {
                      if (e.key === "Enter" && !e.shiftKey) {
                        e.preventDefault();
                        handleChat(e as unknown as React.FormEvent);
                      }
                    }}
                    onFocus={() => setChatFocused(true)}
                    onBlur={() => setChatFocused(false)}
                    placeholder={chatPlaceholder}
                    suppressHydrationWarning
                    style={{
                      display: "block", width: "100%",
                      minHeight: 44, maxHeight: 120,
                      padding: "12px 16px 0",
                      backgroundColor: "transparent",
                      borderTop: "none", borderBottom: "none",
                      borderLeft: "none", borderRight: "none",
                      borderRadius: "14px 14px 0 0",
                      fontFamily: FONT, fontSize: 14, lineHeight: 1.6,
                      color: "var(--color-text-primary)",
                      resize: "none", overflow: "auto", outline: "none",
                      boxSizing: "border-box",
                    }}
                  />
                  <div style={{
                    display: "flex", alignItems: "center", justifyContent: "space-between",
                    padding: "6px 10px 10px",
                  }}>
                    <button
                      type="button" aria-label="Attach file"
                      style={{
                        width: 28, height: 28, flexShrink: 0,
                        display: "flex", alignItems: "center", justifyContent: "center",
                        backgroundColor: "transparent",
                        borderTop: "none", borderBottom: "none",
                        borderLeft: "none", borderRight: "none",
                        borderRadius: 6, color: "var(--color-text-muted)",
                        cursor: "pointer",
                        transition: "color 150ms ease-out",
                      }}
                      onMouseEnter={e => { e.currentTarget.style.color = "var(--color-text-primary)"; }}
                      onMouseLeave={e => { e.currentTarget.style.color = "var(--color-text-muted)"; }}
                    >
                      <svg width="15" height="15" viewBox="0 0 24 24" fill="none">
                        <path d="M21.44 11.05l-9.19 9.19a6 6 0 01-8.49-8.49l9.19-9.19a4 4 0 015.66 5.66l-9.2 9.19a2 2 0 01-2.83-2.83l8.49-8.48" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
                      </svg>
                    </button>
                    {!isNarrow && bp === "desktop" && (
                      <span style={{ fontFamily: FONT, fontSize: 11, color: "var(--color-text-muted)", userSelect: "none" }}>
                        ⏎ send &nbsp;·&nbsp; ⇧⏎ new line
                      </span>
                    )}
                    <button
                      type="submit" disabled={!chatInput.trim()} aria-label="Send message"
                      style={{
                        width: 32, height: 32, flexShrink: 0,
                        display: "flex", alignItems: "center", justifyContent: "center",
                        backgroundColor: chatInput.trim() ? "var(--color-accent)" : "var(--color-surface-hover)",
                        borderTop: "none", borderBottom: "none",
                        borderLeft: "none", borderRight: "none",
                        borderRadius: "50%",
                        cursor: chatInput.trim() ? "pointer" : "default",
                        color: chatInput.trim() ? "var(--color-accent-foreground)" : "var(--color-text-muted)",
                        transition: "background-color 150ms ease-out",
                        opacity: chatInput.trim() ? 1 : 0.5,
                      }}
                    >
                      <svg width="15" height="15" viewBox="0 0 24 24" fill="none">
                        <path d="M12 19V5M5 12l7-7 7 7" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"/>
                      </svg>
                    </button>
                  </div>
                </form>
              </div>
            </div>
          </main>

          {/* ── Right Panel ────────────────────────────────────────── */}
          {!isNarrow && (
            <aside style={{
              width: rightExpanded ? 320 : 40, flexShrink: 0,
              display: "flex", flexDirection: "column",
              backgroundColor: "var(--color-surface)",
              borderLeft: "1px solid var(--color-border)",
              overflow: "hidden",
              transition: "width 250ms ease-out",
            }}>
              {rightExpanded ? (
                <div style={{ display: "flex", flexDirection: "column", height: "100%" }}>
                  <div style={{
                    display: "flex", alignItems: "center", justifyContent: "space-between",
                    padding: "10px 12px",
                    borderBottom: "1px solid var(--color-border)",
                    flexShrink: 0, gap: 8,
                  }}>
                    <div style={{ display: "flex", gap: 2 }}>
                      {(["agent", ...(isDevRole ? ["dev"] : [])] as ("agent" | "dev")[]).map(tab => (
                        <button
                          key={tab} type="button" onClick={() => setRightTab(tab)}
                          style={{
                            fontFamily: FONT, fontWeight: 600, fontSize: 10,
                            letterSpacing: "0.08em", textTransform: "uppercase",
                            padding: "3px 8px", borderRadius: "var(--radius)",
                            border: "none", cursor: "pointer",
                            backgroundColor: rightTab === tab ? "var(--color-surface-hover)" : "transparent",
                            color: rightTab === tab ? "var(--color-text-primary)" : "var(--color-text-muted)",
                            transition: "opacity 150ms ease-out",
                          }}
                        >
                          {tab === "agent" ? "Agent Log" : "Dev Log"}
                        </button>
                      ))}
                      {shellState === "running" && (
                        <div style={{ display: "flex", alignItems: "center", gap: 4, marginLeft: 4 }}>
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
                      type="button" onClick={() => setRightExpanded(false)} aria-label="Collapse agent log"
                      style={{
                        background: "none", border: "none", cursor: "pointer",
                        color: "var(--color-text-muted)", padding: 4, fontSize: 14,
                        transition: "color 150ms ease-out",
                      }}
                      onMouseEnter={e => { e.currentTarget.style.color = "var(--color-text-primary)"; }}
                      onMouseLeave={e => { e.currentTarget.style.color = "var(--color-text-muted)"; }}
                    >→</button>
                  </div>

                  {rightTab === "agent" && (
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
                            <p style={{ fontFamily: MONO, fontSize: 10, fontWeight: 600, color: "var(--color-text-secondary)", letterSpacing: "0.04em" }}>
                              {AGENT_LABELS[ev.agent] ?? ev.agent}
                            </p>
                            <p style={{ fontFamily: MONO, fontSize: 10, color: "var(--color-text-muted)", marginLeft: "auto" }}>
                              {ev.status}
                            </p>
                          </div>
                          <p style={{ fontFamily: FONT, fontSize: 11, color: "var(--color-text-muted)", lineHeight: 1.5, paddingLeft: 11 }}>
                            {ev.message}
                          </p>
                        </div>
                      ))}
                      <div ref={logEndRef} />
                    </div>
                  )}

                  {rightTab === "dev" && isDevRole && (
                    <DevLogPanel entries={devLogEntries} connected={devLogConnected} />
                  )}
                </div>
              ) : (
                <div
                  onClick={() => setRightExpanded(true)}
                  role="button" tabIndex={0}
                  onKeyDown={e => { if (e.key === "Enter" || e.key === " ") setRightExpanded(true); }}
                  aria-label="Expand agent log"
                  style={{
                    flex: 1, display: "flex", flexDirection: "column",
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
                    writingMode: "vertical-rl", textOrientation: "mixed",
                    transform: "rotate(180deg)", userSelect: "none",
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
