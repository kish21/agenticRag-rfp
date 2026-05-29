"use client";

import { FONT, MONO } from "@/lib/theme";

export type AutonomyMode = "manual" | "auto_to_evaluate" | "auto_to_report";

interface AutonomyModePickerProps {
  value: AutonomyMode;
  onChange: (mode: AutonomyMode) => void;
}

interface ModeOption {
  id: AutonomyMode;
  label: string;
  subtitle: string;
  timeline: TimelineRow[];
  disabled?: boolean;
  disabledReason?: string;
}

interface TimelineRow {
  beat: string;          // T0, T1, T2 …
  text: string;
  system?: boolean;      // solid dot = automatic action under this mode
}

const MODES: ModeOption[] = [
  {
    id: "manual",
    label: "Manual",
    subtitle: "You stay in control. Click when ready.",
    timeline: [
      { beat: "T0", text: "RFP created" },
      { beat: "T1", text: "Files dropped" },
      { beat: "T2", text: "Deadline passes" },
      { beat: "·", text: "system waits" },
      { beat: "T3", text: "You click Evaluate" },
      { beat: "·", text: "Pipeline runs (~5 min)", system: true },
    ],
  },
  {
    id: "auto_to_evaluate",
    label: "Auto to Evaluate",
    subtitle: "Files process at the deadline. Your click is instant.",
    timeline: [
      { beat: "T0", text: "RFP created" },
      { beat: "T1", text: "Files dropped" },
      { beat: "T2", text: "Deadline passes" },
      { beat: "·", text: "Extraction runs", system: true },
      { beat: "T3", text: "You log in" },
      { beat: "·", text: "Report opens in ~30s", system: true },
    ],
  },
  {
    id: "auto_to_report",
    label: "Auto to Report",
    subtitle: "Coming in Phase 7 — PDF report by email.",
    disabled: true,
    disabledReason: "SOON",
    timeline: [
      { beat: "T0", text: "RFP created" },
      { beat: "T1", text: "Files dropped" },
      { beat: "T2", text: "Deadline passes" },
      { beat: "·", text: "Full pipeline runs", system: true },
      { beat: "T3", text: "—" },
      { beat: "·", text: "PDF sent to your inbox", system: true },
    ],
  },
];

export function AutonomyModePicker({ value, onChange }: AutonomyModePickerProps) {
  return (
    <div
      role="radiogroup"
      aria-label="Autonomy mode"
      className="grid gap-4 md:gap-5"
      style={{
        gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))",
      }}
    >
      {MODES.map((m) => {
        const selected = value === m.id;
        const interactive = !m.disabled;
        return (
          <button
            key={m.id}
            type="button"
            role="radio"
            aria-checked={selected}
            aria-disabled={m.disabled}
            disabled={m.disabled}
            onClick={interactive ? () => onChange(m.id) : undefined}
            className="text-left p-4 md:p-5"
            style={{
              minHeight: 280,
              cursor: interactive ? "pointer" : "not-allowed",
              opacity: m.disabled ? 0.55 : 1,
              background: selected
                ? "color-mix(in oklab, var(--color-accent) 6%, var(--color-surface))"
                : "var(--color-background)",
              borderTop: `${selected ? 2 : 1}px solid ${selected ? "var(--color-accent)" : "var(--color-border)"}`,
              borderBottom: `${selected ? 2 : 1}px solid ${selected ? "var(--color-accent)" : "var(--color-border)"}`,
              borderLeft: `${selected ? 2 : 1}px solid ${selected ? "var(--color-accent)" : "var(--color-border)"}`,
              borderRight: `${selected ? 2 : 1}px solid ${selected ? "var(--color-accent)" : "var(--color-border)"}`,
              borderRadius: "var(--radius)",
              transition: "transform var(--transition), opacity var(--transition)",
              outline: "none",
              position: "relative",
            }}
            onMouseEnter={(e) => {
              if (interactive) e.currentTarget.style.transform = "translateY(-1px)";
            }}
            onMouseLeave={(e) => {
              e.currentTarget.style.transform = "translateY(0)";
            }}
            onFocus={(e) => {
              e.currentTarget.style.boxShadow = "0 0 0 3px color-mix(in oklab, var(--color-accent) 30%, transparent)";
            }}
            onBlur={(e) => {
              e.currentTarget.style.boxShadow = "none";
            }}
          >
            <header className="mb-4 flex items-center gap-2.5">
              <RadioDot selected={selected} disabled={m.disabled} />
              <span
                style={{
                  fontFamily: MONO,
                  fontSize: 11,
                  fontWeight: 600,
                  letterSpacing: "0.16em",
                  textTransform: "uppercase",
                  color: selected ? "var(--color-text-primary)" : "var(--color-text-secondary)",
                }}
              >
                {m.label}
              </span>
              {m.disabledReason && (
                <span
                  className="ml-auto"
                  style={{
                    fontFamily: MONO,
                    fontSize: 9,
                    fontWeight: 700,
                    letterSpacing: "0.14em",
                    padding: "2px 6px",
                    borderRadius: "calc(var(--radius) - 4px)",
                    background: "color-mix(in oklab, var(--color-warning) 18%, var(--color-surface))",
                    color: "var(--color-warning)",
                  }}
                >
                  {m.disabledReason}
                </span>
              )}
            </header>

            <div
              style={{
                borderTop: "1px solid var(--color-border)",
                marginBottom: 12,
              }}
            />

            <ol className="space-y-1.5">
              {m.timeline.map((row, i) => (
                <li
                  key={i}
                  className="flex gap-2"
                  style={{
                    fontFamily: MONO,
                    fontSize: 10.5,
                    color: row.system
                      ? "var(--color-text-primary)"
                      : "var(--color-text-muted)",
                  }}
                >
                  <span
                    style={{
                      width: 18,
                      flexShrink: 0,
                      color: row.system
                        ? "var(--color-accent)"
                        : "var(--color-text-muted)",
                      fontWeight: row.system ? 700 : 400,
                    }}
                  >
                    {row.beat}
                  </span>
                  <span style={{ fontFamily: FONT, fontSize: 12.5, fontWeight: row.system ? 500 : 400 }}>
                    {row.text}
                  </span>
                </li>
              ))}
            </ol>

            <p
              className="mt-4"
              style={{
                fontFamily: FONT,
                fontSize: 12.5,
                fontStyle: "italic",
                fontWeight: 500,
                lineHeight: 1.5,
                color: "var(--color-text-secondary)",
              }}
            >
              {m.subtitle}
            </p>
          </button>
        );
      })}
    </div>
  );
}

function RadioDot({ selected, disabled }: { selected: boolean; disabled?: boolean }) {
  return (
    <span
      aria-hidden
      style={{
        width: 14,
        height: 14,
        borderRadius: "50%",
        flexShrink: 0,
        borderTop: `1.5px solid ${selected ? "var(--color-accent)" : "var(--color-border-strong)"}`,
        borderBottom: `1.5px solid ${selected ? "var(--color-accent)" : "var(--color-border-strong)"}`,
        borderLeft: `1.5px solid ${selected ? "var(--color-accent)" : "var(--color-border-strong)"}`,
        borderRight: `1.5px solid ${selected ? "var(--color-accent)" : "var(--color-border-strong)"}`,
        background: selected ? "var(--color-accent)" : "transparent",
        opacity: disabled ? 0.6 : 1,
        display: "inline-block",
      }}
    />
  );
}
