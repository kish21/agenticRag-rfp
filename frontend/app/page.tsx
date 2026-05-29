"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { FONT, DISPLAY, MONO } from "@/lib/theme";
import { useThemeContext } from "@/components/layout/ThemeProvider";
import { useBreakpoint } from "@/lib/hooks";
import { api, getUserInfo, clearUserInfo, isLoggedIn, type UserInfo } from "@/lib/api";
import { type EvalRun, type AgentEvent, type EvalResults, type ChatMessage, type ChatSession } from "@/lib/types";
import { ROLE_DISPLAY } from "@/lib/constants";
import { WelcomePage } from "@/components/features/WelcomePage";
import { ProgressPage } from "@/components/features/ProgressPage";
import { ResultsPage } from "@/components/features/ResultsPage";
import { NewEvaluationForm } from "@/components/features/NewEvaluationForm";
import { ConfirmSetupPage } from "@/components/features/ConfirmSetupPage";
import { type DevLogEntry } from "@/components/features/DevLogPanel";
import { AppSidebar } from "./_components/AppSidebar";
import { AgentLogPanel } from "./_components/AgentLogPanel";
import { ChatBox } from "./_components/ChatBox";

// ── Shell types ───────────────────────────────────────────────────────────────

type ShellState = "idle" | "running" | "completed";
type CanvasPage = "welcome" | "upload-form" | "confirm" | "progress" | "results";

// ── Main shell ────────────────────────────────────────────────────────────────

export default function HomePage() {
  const router = useRouter();
  useThemeContext();
  const bp       = useBreakpoint();
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
  const [rightTab, setRightTab]         = useState<"agent" | "dev">("agent");

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
  const esRef    = useRef<EventSource | null>(null);
  const devEsRef = useRef<EventSource | null>(null);

  const chatVisible = shellState !== "running" && canvasPage !== "confirm";

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
    // Mount-only auth + initial data load. setState fires synchronously
    // for user info (read from localStorage); subsequent setState calls
    // come from resolved promises (fetched data). The set-state-in-effect
    // lint warning is intentional for client-only "load on mount" pages —
    // useSyncExternalStore would need a subscribe callback localStorage
    // does not provide.
    if (!isLoggedIn()) { router.push("/login"); return; }
    const info = getUserInfo();
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setUserInfo(info);
    if (info?.email) {
      // eslint-disable-next-line react-hooks/set-state-in-effect
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
          backgroundColor: "var(--color-surface)",
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

          {/* ── Sidebar ──────────────────────────────────────────── */}
          <AppSidebar
            userInfo={userInfo}
            runs={runs}
            loading={loading}
            chatSessions={chatSessions}
            activeRunId={activeRunId}
            chatSessionId={chatSessionId}
            shellState={shellState}
            hoveredRunId={hoveredRunId}
            deletingRunId={deletingRunId}
            isNarrow={isNarrow}
            sidebarOpen={sidebarOpen}
            onStartNewEval={startNewEval}
            onNewChatSession={newChatSession}
            onLoadChatSession={loadChatSession}
            onOpenRun={openRun}
            onDeleteRun={deleteRun}
            onGoHome={goHome}
            onSignOut={signOut}
            onSetHoveredRunId={setHoveredRunId}
            onCloseSidebar={() => setSidebarOpen(false)}
          />

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

            {/* Chat */}
            <ChatBox
              chatInput={chatInput}
              chatFile={chatFile}
              chatFocused={chatFocused}
              chatFileDragging={chatFileDragging}
              chatLoading={chatLoading}
              chatVisible={chatVisible}
              chatMessages={chatMessages}
              chatPlaceholder={chatPlaceholder}
              bp={bp}
              isNarrow={isNarrow}
              onSubmit={handleChat}
              onInputChange={setChatInput}
              onFileChange={setChatFile}
              onFocusChange={setChatFocused}
              onDraggingChange={setChatFileDragging}
              onDrop={file => setChatFile(file)}
            />
          </main>

          {/* ── Right Panel ────────────────────────────────────────── */}
          {!isNarrow && (
            <AgentLogPanel
              rightExpanded={rightExpanded}
              rightTab={rightTab}
              shellState={shellState}
              agentEvents={agentEvents}
              devLogEntries={devLogEntries}
              devLogConnected={devLogConnected}
              isDevRole={isDevRole}
              onSetExpanded={setRightExpanded}
              onTabChange={setRightTab}
            />
          )}
        </div>
      </div>
    </>
  );
}
