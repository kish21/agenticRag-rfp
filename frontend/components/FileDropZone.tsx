"use client";

import { useRef, useState } from "react";
import { FONT, MONO } from "@/lib/theme";

interface FileDropZoneProps {
  file: File | null;
  onFile: (f: File) => void;
  placeholder: string;
  compact?: boolean;
}

export function FileDropZone({ file, onFile, placeholder, compact = false }: FileDropZoneProps) {
  const [dragging, setDragging] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  function handleDrop(e: React.DragEvent) {
    e.preventDefault();
    setDragging(false);
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
