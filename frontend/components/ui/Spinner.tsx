"use client";

interface SpinnerProps {
  size?: number;
  /** Uses currentColor by default — set to override */
  color?: string;
  style?: React.CSSProperties;
}

export function Spinner({ size = 20, color, style }: SpinnerProps) {
  return (
    <span
      role="status"
      aria-label="Loading"
      style={{
        display: "inline-block",
        width: size,
        height: size,
        borderRadius: "50%",
        borderTop: `2px solid ${color ?? "var(--color-accent)"}`,
        borderRight: "2px solid transparent",
        borderBottom: "2px solid transparent",
        borderLeft: "2px solid transparent",
        animation: "spin 0.7s linear infinite",
        flexShrink: 0,
        ...style,
      }}
    />
  );
}
