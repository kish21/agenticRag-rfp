"use client";

import { useEffect, useRef, useState } from "react";
import { FONT, MONO } from "@/lib/theme";

export interface DevLogEntry {
  type: "dev";
  ts: string;
  level: "DEBUG" | "INFO" | "WARN" | "ERROR" | "SUCCESS" | "AGENT" | "RAG" | "LLM" | "CRITIC";
  agent: string;
  message: string;
  data?: Record<string, unknown>;
  run_id?: string;
  org_id?: string;
  elapsed_ms?: number;
}

const LEVEL_COLOR: Record<string, string> = {
  DEBUG:   "var(--color-text-muted)",
  INFO:    "var(--color-info)",
  WARN:    "var(--color-warning)",
  ERROR:   "var(--color-error)",
  SUCCESS: "var(--color-success)",
  AGENT:   "var(--color-accent)",
  RAG:     "var(--color-info)",
  LLM:     "var(--color-info)",
  CRITIC:  "var(--color-warning)",
};

interface Props {
  entries: DevLogEntry[];
  connected: boolean;
}

export function DevLogPanel({ entries, connected }: Props) {
  const bottomRef    = useRef<HTMLDivElement>(null);
  const [filter, setFilter] = useState<string>("ALL");

  const levels = ["ALL", "AGENT", "LLM", "RAG", "CRITIC", "ERROR"];

  const visible = filter === "ALL"
    ? entries
    : entries.filter(e => e.level === filter);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [visible.length]);

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100%" }}>
      {/* Header */}
      <div style={{
        display: "flex", alignItems: "center", justifyContent: "space-between",
        padding: "10px 12px", borderBottom: "1px solid var(--color-border)",
        flexShrink: 0, gap: 8,
      }}>
        <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
          <div style={{
            width: 5, height: 5, borderRadius: "50%",
            backgroundColor: connected ? "var(--color-warning)" : "var(--color-text-muted)",
            animation: connected ? "meridian-dot-pulse 1.5s ease-in-out infinite" : "none",
          }} />
          <p style={{
            fontFamily: FONT, fontWeight: 600, fontSize: 10,
            letterSpacing: "0.08em", textTransform: "uppercase",
            color: connected ? "var(--color-warning)" : "var(--color-text-muted)",
          }}>
            Dev Log
          </p>
        </div>
        <p style={{ fontFamily: MONO, fontSize: 10, color: "var(--color-text-muted)" }}>
          {entries.length} entries
        </p>
      </div>

      {/* Level filter */}
      <div style={{
        display: "flex", gap: 4, padding: "6px 12px",
        borderBottom: "1px solid var(--color-border)",
        flexShrink: 0, overflowX: "auto",
      }}>
        {levels.map(l => (
          <button
            key={l}
            type="button"
            onClick={() => setFilter(l)}
            style={{
              fontFamily: MONO, fontSize: 9, fontWeight: 600,
              letterSpacing: "0.06em", textTransform: "uppercase",
              padding: "2px 7px", borderRadius: "var(--radius)",
              border: "none", cursor: "pointer",
              backgroundColor: filter === l ? "var(--color-accent)" : "transparent",
              color: filter === l ? "var(--color-accent-foreground)" : "var(--color-text-muted)",
              transition: "opacity 150ms ease-out",
              whiteSpace: "nowrap",
            }}
          >
            {l}
          </button>
        ))}
      </div>

      {/* Log rows */}
      <div style={{ flex: 1, overflowY: "auto", padding: "6px 0" }}>
        {visible.length === 0 && (
          <p style={{
            fontFamily: FONT, fontSize: 11, color: "var(--color-text-muted)",
            padding: "12px 12px", lineHeight: 1.6,
          }}>
            {connected ? "Waiting for events…" : "No events recorded."}
          </p>
        )}
        {visible.map((e, i) => (
          <DevRow key={i} entry={e} />
        ))}
        <div ref={bottomRef} />
      </div>
    </div>
  );
}

function DevRow({ entry: e }: { entry: DevLogEntry }) {
  const [expanded, setExpanded] = useState(false);
  const hasData = e.data && Object.keys(e.data).length > 0;

  return (
    <div
      onClick={() => hasData && setExpanded(v => !v)}
      style={{
        padding: "3px 12px",
        cursor: hasData ? "pointer" : "default",
        backgroundColor: expanded ? "var(--color-surface-hover)" : "transparent",
        transition: "background-color 100ms ease-out",
        borderLeft: `2px solid ${e.level === "ERROR" ? "var(--color-error)" : "transparent"}`,
      }}
    >
      <div style={{ display: "flex", alignItems: "baseline", gap: 6, flexWrap: "nowrap" }}>
        {/* Timestamp */}
        <span style={{
          fontFamily: MONO, fontSize: 9, color: "var(--color-text-muted)",
          flexShrink: 0, letterSpacing: "0.02em",
        }}>
          {e.ts.slice(11, 23)}
        </span>

        {/* Elapsed */}
        {e.elapsed_ms != null && (
          <span style={{
            fontFamily: MONO, fontSize: 9, color: "var(--color-text-muted)",
            flexShrink: 0, minWidth: 48, textAlign: "right",
          }}>
            +{e.elapsed_ms}ms
          </span>
        )}

        {/* Level */}
        <span style={{
          fontFamily: MONO, fontSize: 9, fontWeight: 700,
          letterSpacing: "0.06em", flexShrink: 0, minWidth: 44,
          color: LEVEL_COLOR[e.level] ?? "var(--color-text-muted)",
        }}>
          {e.level}
        </span>

        {/* Agent */}
        <span style={{
          fontFamily: MONO, fontSize: 9, color: "var(--color-accent)",
          flexShrink: 0, minWidth: 60, overflow: "hidden", textOverflow: "ellipsis",
        }}>
          {e.agent}
        </span>

        {/* Message */}
        <span style={{
          fontFamily: FONT, fontSize: 11, color: "var(--color-text-secondary)",
          flex: 1, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap",
        }}>
          {e.message}
        </span>

        {hasData && (
          <span style={{
            fontFamily: MONO, fontSize: 9, color: "var(--color-text-muted)",
            flexShrink: 0,
          }}>
            {expanded ? "▲" : "▼"}
          </span>
        )}
      </div>

      {expanded && hasData && (
        <pre style={{
          fontFamily: MONO, fontSize: 9, color: "var(--color-text-muted)",
          backgroundColor: "var(--color-surface)",
          borderTop: "1px solid var(--color-border)",
          borderBottom: "1px solid var(--color-border)",
          borderLeft: "1px solid var(--color-border)",
          borderRight: "1px solid var(--color-border)",
          borderRadius: "var(--radius)",
          padding: "6px 8px", marginTop: 4,
          overflowX: "auto", whiteSpace: "pre-wrap", wordBreak: "break-all",
          lineHeight: 1.6,
        }}>
          {JSON.stringify(e.data, null, 2)}
        </pre>
      )}
    </div>
  );
}
