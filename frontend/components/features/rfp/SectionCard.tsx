"use client";

import { FONT, MONO } from "@/lib/theme";

interface SectionCardProps {
  index: string;          // "01"
  label: string;          // "IDENTITY"
  subtitle?: string;
  children: React.ReactNode;
}

/**
 * Editorial-style section container used by every block on the RFP creation
 * page. The mono "01 · IDENTITY" header is the design's structural signature.
 */
export function SectionCard({ index, label, subtitle, children }: SectionCardProps) {
  return (
    <section
      className="p-6 md:p-8"
      style={{
        background: "var(--color-surface)",
        borderTop: "1px solid var(--color-border)",
        borderBottom: "1px solid var(--color-border)",
        borderLeft: "1px solid var(--color-border)",
        borderRight: "1px solid var(--color-border)",
        borderRadius: "var(--radius)",
        boxShadow: "var(--shadow-sm)",
      }}
    >
      <header className="mb-5 flex items-baseline gap-3">
        <span
          style={{
            fontFamily: MONO,
            fontSize: 11,
            fontWeight: 500,
            letterSpacing: "0.18em",
            color: "var(--color-text-muted)",
          }}
        >
          {index}
        </span>
        <span
          style={{
            fontFamily: MONO,
            fontSize: 11,
            fontWeight: 600,
            letterSpacing: "0.18em",
            textTransform: "uppercase",
            color: "var(--color-text-secondary)",
          }}
        >
          {label}
        </span>
      </header>
      {subtitle && (
        <p
          className="mb-5"
          style={{
            fontFamily: FONT,
            fontSize: 14,
            fontWeight: 400,
            lineHeight: 1.6,
            color: "var(--color-text-muted)",
            maxWidth: 520,
          }}
        >
          {subtitle}
        </p>
      )}
      {children}
    </section>
  );
}
