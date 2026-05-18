"use client";

interface CardProps {
  children: React.ReactNode;
  /** Adds an accent top border */
  accent?: boolean;
  /** Highlight on hover */
  hoverable?: boolean;
  onClick?: () => void;
  style?: React.CSSProperties;
  padding?: string | number;
}

export function Card({
  children,
  accent = false,
  hoverable = false,
  onClick,
  style,
  padding = "20px 24px",
}: CardProps) {
  return (
    <div
      onClick={onClick}
      role={onClick ? "button" : undefined}
      tabIndex={onClick ? 0 : undefined}
      onKeyDown={onClick ? (e) => { if (e.key === "Enter" || e.key === " ") onClick(); } : undefined}
      style={{
        backgroundColor: "var(--color-surface)",
        borderTop: accent ? "2px solid var(--color-accent)" : "1px solid var(--color-border)",
        borderBottom: "1px solid var(--color-border)",
        borderLeft: "1px solid var(--color-border)",
        borderRight: "1px solid var(--color-border)",
        borderRadius: "var(--radius)",
        boxShadow: "var(--shadow-sm)",
        padding,
        cursor: onClick ? "pointer" : "default",
        transition: hoverable ? "background-color 150ms ease-out, box-shadow 150ms ease-out, transform 150ms ease-out" : "none",
        outline: "none",
        ...style,
      }}
      onMouseEnter={hoverable ? (e) => {
        e.currentTarget.style.backgroundColor = "var(--color-surface-hover)";
        e.currentTarget.style.boxShadow = "var(--shadow-md)";
        e.currentTarget.style.transform = "translateY(-1px)";
      } : undefined}
      onMouseLeave={hoverable ? (e) => {
        e.currentTarget.style.backgroundColor = "var(--color-surface)";
        e.currentTarget.style.boxShadow = "var(--shadow-sm)";
        e.currentTarget.style.transform = "translateY(0)";
      } : undefined}
    >
      {children}
    </div>
  );
}
