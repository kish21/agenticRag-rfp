"use client";

import React from "react";
import { FONT } from "@/lib/theme";
import { type ChatMessage } from "@/lib/types";
import { type Breakpoint } from "@/lib/hooks";

interface ChatBoxProps {
  chatInput: string;
  chatFile: File | null;
  chatFocused: boolean;
  chatFileDragging: boolean;
  chatLoading: boolean;
  chatVisible: boolean;
  chatMessages: ChatMessage[];
  chatPlaceholder: string;
  bp: Breakpoint;
  isNarrow: boolean;
  onSubmit: (e: React.FormEvent) => void;
  onInputChange: (value: string) => void;
  onFileChange: (file: File | null) => void;
  onFocusChange: (focused: boolean) => void;
  onDraggingChange: (dragging: boolean) => void;
  onDrop: (file: File) => void;
}

export function ChatBox({
  chatInput, chatFile, chatFocused, chatFileDragging,
  chatVisible, chatMessages, chatPlaceholder, bp, isNarrow,
  onSubmit, onInputChange, onFileChange, onFocusChange, onDraggingChange, onDrop,
}: ChatBoxProps) {
  return (
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
          onSubmit={onSubmit}
          onDragOver={e => { e.preventDefault(); onDraggingChange(true); }}
          onDragLeave={() => onDraggingChange(false)}
          onDrop={e => {
            e.preventDefault(); onDraggingChange(false);
            const f = e.dataTransfer.files[0];
            if (f) onDrop(f);
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
                  type="button" onClick={() => onFileChange(null)} aria-label="Remove attached file"
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
            onChange={e => onInputChange(e.target.value)}
            onInput={e => {
              const el = e.currentTarget;
              el.style.height = "auto";
              el.style.height = Math.min(el.scrollHeight, 120) + "px";
            }}
            onKeyDown={e => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                onSubmit(e as unknown as React.FormEvent);
              }
            }}
            onFocus={() => onFocusChange(true)}
            onBlur={() => onFocusChange(false)}
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
  );
}
