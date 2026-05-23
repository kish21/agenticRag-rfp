"use client";

import { useRef, useState } from "react";
import { FONT } from "@/lib/theme";

interface MultiFileDropZoneProps {
  onFiles: (files: File[]) => void;
  disabled?: boolean;
}

export function MultiFileDropZone({ onFiles, disabled = false }: MultiFileDropZoneProps) {
  const [dragging, setDragging] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  function handleDrop(e: React.DragEvent) {
    e.preventDefault();
    setDragging(false);
    if (disabled) return;
    const valid = Array.from(e.dataTransfer.files).filter(
      f => f.type.includes("pdf") || f.name.endsWith(".docx")
    );
    if (valid.length) onFiles(valid);
  }

  function handleChange(e: React.ChangeEvent<HTMLInputElement>) {
    const valid = Array.from(e.target.files ?? []).filter(
      f => f.type.includes("pdf") || f.name.endsWith(".docx")
    );
    if (valid.length) onFiles(valid);
    e.target.value = "";
  }

  const borderStyle = dragging
    ? "1px solid var(--color-accent)"
    : "1px dashed var(--color-border)";

  return (
    <div
      onClick={() => !disabled && inputRef.current?.click()}
      onDragOver={e => { e.preventDefault(); if (!disabled) setDragging(true); }}
      onDragLeave={() => setDragging(false)}
      onDrop={handleDrop}
      role="button"
      tabIndex={disabled ? -1 : 0}
      aria-label="Drop all vendor proposals here"
      aria-disabled={disabled}
      onKeyDown={e => {
        if (!disabled && (e.key === "Enter" || e.key === " ")) inputRef.current?.click();
      }}
      className="w-full"
      style={{
        padding: "24px 20px",
        backgroundColor: dragging
          ? "var(--color-surface-hover)"
          : disabled
          ? "var(--color-surface)"
          : "var(--color-background)",
        borderTop: borderStyle, borderBottom: borderStyle,
        borderLeft: borderStyle, borderRight: borderStyle,
        borderRadius: "var(--radius)",
        cursor: disabled ? "not-allowed" : "pointer",
        textAlign: "center",
        opacity: disabled ? 0.5 : 1,
        transition: "background-color 150ms ease-out, border-color 150ms ease-out, opacity 150ms ease-out",
      }}
    >
      <div style={{ pointerEvents: "none" }}>
        <div style={{ fontSize: 24, marginBottom: 8, lineHeight: 1 }}>📂</div>
        <p style={{
          fontFamily: FONT, fontSize: 13, fontWeight: 500,
          color: dragging ? "var(--color-accent)" : "var(--color-text-muted)",
          lineHeight: 1.5, marginBottom: 4,
          transition: "color 150ms ease-out",
        }}>
          {dragging ? "Release to add vendors" : "Drop all vendor proposals here"}
        </p>
        <p style={{ fontFamily: FONT, fontSize: 11, color: "var(--color-text-muted)" }}>
          {disabled ? "Maximum 10 vendors reached" : "PDF or DOCX · multiple files at once · tap to browse"}
        </p>
      </div>
      <input
        ref={inputRef}
        type="file"
        accept=".pdf,.docx"
        multiple
        style={{ display: "none" }}
        onChange={handleChange}
      />
    </div>
  );
}
