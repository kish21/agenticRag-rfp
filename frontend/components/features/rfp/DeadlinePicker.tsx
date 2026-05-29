"use client";

import { useMemo, useState } from "react";
import { DISPLAY, FONT, MONO } from "@/lib/theme";

interface DeadlinePickerProps {
  value: Date;
  onChange: (next: Date) => void;
}

const WEEKDAY_HEAD = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];

function startOfMonth(d: Date): Date {
  return new Date(d.getFullYear(), d.getMonth(), 1);
}

function addMonths(d: Date, n: number): Date {
  return new Date(d.getFullYear(), d.getMonth() + n, 1);
}

function daysInMonth(year: number, month: number): number {
  return new Date(year, month + 1, 0).getDate();
}

/** Returns 0=Mon..6=Sun for the given date (Mon-first week). */
function dowMonFirst(d: Date): number {
  return (d.getDay() + 6) % 7;
}

function isSameDay(a: Date, b: Date): boolean {
  return (
    a.getFullYear() === b.getFullYear() &&
    a.getMonth() === b.getMonth() &&
    a.getDate() === b.getDate()
  );
}

function workingDaysBetween(from: Date, to: Date): number {
  if (to <= from) return 0;
  let n = 0;
  const cursor = new Date(from);
  cursor.setHours(0, 0, 0, 0);
  const end = new Date(to);
  end.setHours(0, 0, 0, 0);
  while (cursor < end) {
    cursor.setDate(cursor.getDate() + 1);
    const dow = cursor.getDay();
    if (dow !== 0 && dow !== 6) n++;
  }
  return n;
}

function formatLong(d: Date): string {
  return d.toLocaleString(undefined, {
    weekday: "long",
    day: "numeric",
    month: "long",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    timeZoneName: "short",
  });
}

function pad2(n: number): string {
  return n.toString().padStart(2, "0");
}

export function DeadlinePicker({ value, onChange }: DeadlinePickerProps) {
  const today = useMemo(() => {
    const t = new Date();
    t.setHours(0, 0, 0, 0);
    return t;
  }, []);

  const [anchor, setAnchor] = useState<Date>(() => startOfMonth(value));

  const months = useMemo(() => [anchor, addMonths(anchor, 1)], [anchor]);

  const diffDays = Math.max(0, Math.ceil((value.getTime() - today.getTime()) / 86400000));
  const workDays = workingDaysBetween(today, value);

  function pickDate(d: Date) {
    if (d < today) return;
    const next = new Date(value);
    next.setFullYear(d.getFullYear(), d.getMonth(), d.getDate());
    onChange(next);
  }

  function setTime(part: "hh" | "mm", n: number) {
    const next = new Date(value);
    if (part === "hh") next.setHours(n);
    else next.setMinutes(n);
    onChange(next);
  }

  return (
    <div>
      {/* Hero deadline summary */}
      <div className="mb-5">
        <div
          style={{
            fontFamily: DISPLAY,
            fontSize: 22,
            fontWeight: 700,
            letterSpacing: "-0.02em",
            lineHeight: 1.2,
            color: "var(--color-text-primary)",
          }}
        >
          {formatLong(value)}
        </div>
        <div
          className="mt-1"
          style={{
            fontFamily: FONT,
            fontSize: 13,
            color: "var(--color-text-muted)",
          }}
        >
          in {diffDays} day{diffDays === 1 ? "" : "s"} · {workDays} working day{workDays === 1 ? "" : "s"}
        </div>
      </div>

      {/* Calendar + time grid */}
      <div className="flex flex-col lg:flex-row gap-5">
        {/* Two months side by side on desktop, stacked on mobile */}
        <div className="grid gap-4 grid-cols-1 sm:grid-cols-2 flex-1">
          {months.map((m, idx) => (
            <MonthGrid
              key={m.toISOString()}
              month={m}
              today={today}
              selected={value}
              onPick={pickDate}
              onNav={idx === 0 ? (delta) => setAnchor(addMonths(anchor, delta)) : undefined}
            />
          ))}
        </div>

        {/* Time columns */}
        <div
          className="flex gap-2 self-start"
          style={{ minWidth: 144 }}
          role="group"
          aria-label="Time"
        >
          <ScrollColumn
            label="HH"
            values={Array.from({ length: 24 }, (_, i) => i)}
            current={value.getHours()}
            onPick={(n) => setTime("hh", n)}
          />
          <ScrollColumn
            label="MM"
            values={[0, 15, 30, 45]}
            current={value.getMinutes() - (value.getMinutes() % 15)}
            onPick={(n) => setTime("mm", n)}
          />
        </div>
      </div>

      <div
        className="mt-5 flex items-center gap-2 px-3 py-2.5"
        style={{
          background: "color-mix(in oklab, var(--color-info) 8%, var(--color-surface))",
          borderTop: "1px solid color-mix(in oklab, var(--color-info) 25%, var(--color-border))",
          borderBottom: "1px solid color-mix(in oklab, var(--color-info) 25%, var(--color-border))",
          borderLeft: "1px solid color-mix(in oklab, var(--color-info) 25%, var(--color-border))",
          borderRight: "1px solid color-mix(in oklab, var(--color-info) 25%, var(--color-border))",
          borderRadius: "var(--radius)",
        }}
      >
        <span aria-hidden style={{ fontSize: 14, lineHeight: 1, color: "var(--color-info)" }}>ⓘ</span>
        <span style={{ fontFamily: FONT, fontSize: 13, color: "var(--color-text-secondary)" }}>
          After this moment, vendor uploads are rejected.
        </span>
      </div>
    </div>
  );
}

function MonthGrid({
  month,
  today,
  selected,
  onPick,
  onNav,
}: {
  month: Date;
  today: Date;
  selected: Date;
  onPick: (d: Date) => void;
  onNav?: (delta: number) => void;
}) {
  const year = month.getFullYear();
  const m = month.getMonth();
  const total = daysInMonth(year, m);
  const leadOffset = dowMonFirst(month);
  const cells: Array<Date | null> = [];
  for (let i = 0; i < leadOffset; i++) cells.push(null);
  for (let d = 1; d <= total; d++) cells.push(new Date(year, m, d));

  return (
    <div>
      <header className="mb-2 flex items-center justify-between">
        <span style={{ fontFamily: MONO, fontSize: 11, fontWeight: 600, letterSpacing: "0.14em", textTransform: "uppercase", color: "var(--color-text-secondary)" }}>
          {month.toLocaleString(undefined, { month: "long", year: "numeric" })}
        </span>
        {onNav && (
          <div className="flex gap-1">
            <NavBtn label="‹" onClick={() => onNav(-1)} aria="Previous month" />
            <NavBtn label="›" onClick={() => onNav(1)} aria="Next month" />
          </div>
        )}
      </header>

      <div className="grid grid-cols-7 gap-0.5 mb-1">
        {WEEKDAY_HEAD.map((w) => (
          <span
            key={w}
            style={{
              fontFamily: MONO, fontSize: 9.5, fontWeight: 500,
              letterSpacing: "0.1em", textTransform: "uppercase",
              color: "var(--color-text-muted)",
              textAlign: "center", padding: "4px 0",
            }}
          >
            {w.slice(0, 1)}
          </span>
        ))}
      </div>

      <div className="grid grid-cols-7 gap-0.5">
        {cells.map((d, i) => {
          if (!d) return <div key={i} />;
          const isPast = d < today;
          const isToday = isSameDay(d, today);
          const isSelected = isSameDay(d, selected);
          return (
            <button
              key={i}
              type="button"
              onClick={() => onPick(d)}
              disabled={isPast}
              aria-label={d.toDateString()}
              aria-pressed={isSelected}
              className="flex items-center justify-center"
              style={{
                minHeight: 36,
                width: "100%",
                fontFamily: MONO,
                fontSize: 13,
                fontWeight: isSelected ? 700 : 500,
                color: isSelected
                  ? "var(--color-accent-foreground)"
                  : isPast
                  ? "var(--color-text-muted)"
                  : "var(--color-text-primary)",
                background: isSelected
                  ? "var(--color-accent)"
                  : "transparent",
                borderTop: isToday && !isSelected ? "1px solid var(--color-info)" : "1px solid transparent",
                borderBottom: isToday && !isSelected ? "1px solid var(--color-info)" : "1px solid transparent",
                borderLeft: isToday && !isSelected ? "1px solid var(--color-info)" : "1px solid transparent",
                borderRight: isToday && !isSelected ? "1px solid var(--color-info)" : "1px solid transparent",
                borderRadius: "calc(var(--radius) - 4px)",
                opacity: isPast ? 0.3 : 1,
                cursor: isPast ? "not-allowed" : "pointer",
                transition: "opacity var(--transition)",
              }}
              onMouseEnter={(e) => {
                if (!isPast && !isSelected) e.currentTarget.style.background = "var(--color-surface-hover)";
              }}
              onMouseLeave={(e) => {
                if (!isSelected) e.currentTarget.style.background = "transparent";
              }}
            >
              {d.getDate()}
            </button>
          );
        })}
      </div>
    </div>
  );
}

function NavBtn({ label, onClick, aria }: { label: string; onClick: () => void; aria: string }) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-label={aria}
      style={{
        width: 28, height: 28,
        display: "flex", alignItems: "center", justifyContent: "center",
        background: "transparent",
        borderTop: "1px solid var(--color-border)",
        borderBottom: "1px solid var(--color-border)",
        borderLeft: "1px solid var(--color-border)",
        borderRight: "1px solid var(--color-border)",
        borderRadius: "calc(var(--radius) - 4px)",
        color: "var(--color-text-secondary)",
        fontFamily: MONO, fontSize: 13, lineHeight: 1,
        cursor: "pointer",
        outline: "none",
        transition: "opacity var(--transition), transform var(--transition)",
      }}
      onMouseEnter={(e) => {
        e.currentTarget.style.background = "var(--color-surface-hover)";
        e.currentTarget.style.color = "var(--color-text-primary)";
      }}
      onMouseLeave={(e) => {
        e.currentTarget.style.background = "transparent";
        e.currentTarget.style.color = "var(--color-text-secondary)";
      }}
      onFocus={(e) => {
        e.currentTarget.style.boxShadow =
          "0 0 0 3px color-mix(in oklab, var(--color-accent) 30%, transparent)";
      }}
      onBlur={(e) => {
        e.currentTarget.style.boxShadow = "none";
      }}
    >
      {label}
    </button>
  );
}

function ScrollColumn({
  label,
  values,
  current,
  onPick,
}: {
  label: string;
  values: number[];
  current: number;
  onPick: (n: number) => void;
}) {
  return (
    <div className="flex flex-col" style={{ minWidth: 60 }}>
      <span
        className="mb-1"
        style={{
          fontFamily: MONO, fontSize: 10, fontWeight: 600,
          letterSpacing: "0.16em", textTransform: "uppercase",
          color: "var(--color-text-muted)",
          textAlign: "center",
        }}
      >
        {label}
      </span>
      <div
        className="overflow-y-auto"
        style={{
          maxHeight: 200,
          borderTop: "1px solid var(--color-border)",
          borderBottom: "1px solid var(--color-border)",
          borderLeft: "1px solid var(--color-border)",
          borderRight: "1px solid var(--color-border)",
          borderRadius: "var(--radius)",
          background: "var(--color-background)",
        }}
      >
        {values.map((n) => {
          const selected = n === current;
          return (
            <button
              key={n}
              type="button"
              onClick={() => onPick(n)}
              className="w-full"
              style={{
                padding: "8px 12px",
                fontFamily: MONO,
                fontVariantNumeric: "tabular-nums",
                fontSize: 14,
                fontWeight: selected ? 700 : 500,
                color: selected ? "var(--color-accent-foreground)" : "var(--color-text-primary)",
                background: selected ? "var(--color-accent)" : "transparent",
                borderTop: "1px solid transparent",
                borderBottom: "1px solid transparent",
                borderLeft: "1px solid transparent",
                borderRight: "1px solid transparent",
                textAlign: "center",
                cursor: "pointer",
                transition: "opacity var(--transition)",
              }}
              onMouseEnter={(e) => {
                if (!selected) e.currentTarget.style.background = "var(--color-surface-hover)";
              }}
              onMouseLeave={(e) => {
                if (!selected) e.currentTarget.style.background = "transparent";
              }}
            >
              {pad2(n)}
            </button>
          );
        })}
      </div>
    </div>
  );
}
