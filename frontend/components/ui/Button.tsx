"use client";

import { FONT } from "@/lib/theme";

type Variant = "primary" | "secondary" | "ghost" | "danger";
type Size    = "sm" | "md" | "lg";

interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
  size?: Size;
  loading?: boolean;
  children: React.ReactNode;
}

const VARIANT_STYLES: Record<Variant, React.CSSProperties> = {
  primary: {
    backgroundColor: "var(--color-accent)",
    color: "var(--color-accent-foreground)",
    borderTop: "1px solid transparent",
    borderBottom: "1px solid transparent",
    borderLeft: "1px solid transparent",
    borderRight: "1px solid transparent",
  },
  secondary: {
    backgroundColor: "var(--color-surface)",
    color: "var(--color-text-primary)",
    borderTop: "1px solid var(--color-border-strong)",
    borderBottom: "1px solid var(--color-border-strong)",
    borderLeft: "1px solid var(--color-border-strong)",
    borderRight: "1px solid var(--color-border-strong)",
  },
  ghost: {
    backgroundColor: "transparent",
    color: "var(--color-text-secondary)",
    borderTop: "1px solid transparent",
    borderBottom: "1px solid transparent",
    borderLeft: "1px solid transparent",
    borderRight: "1px solid transparent",
  },
  danger: {
    backgroundColor: "var(--color-error)",
    color: "#ffffff",
    borderTop: "1px solid transparent",
    borderBottom: "1px solid transparent",
    borderLeft: "1px solid transparent",
    borderRight: "1px solid transparent",
  },
};

const SIZE_STYLES: Record<Size, React.CSSProperties> = {
  sm: { fontSize: 12, fontWeight: 500, padding: "6px 12px", height: 30 },
  md: { fontSize: 13, fontWeight: 600, padding: "8px 18px", height: 36 },
  lg: { fontSize: 14, fontWeight: 600, padding: "11px 24px", height: 44 },
};

export function Button({
  variant = "primary",
  size = "md",
  loading = false,
  disabled,
  children,
  style,
  onMouseEnter,
  onMouseLeave,
  ...props
}: ButtonProps) {
  const isDisabled = disabled || loading;

  return (
    <button
      disabled={isDisabled}
      style={{
        display: "inline-flex",
        alignItems: "center",
        justifyContent: "center",
        gap: 8,
        borderRadius: "var(--radius)",
        fontFamily: FONT,
        cursor: isDisabled ? "not-allowed" : "pointer",
        opacity: isDisabled ? 0.55 : 1,
        transition: "opacity 150ms ease-out, transform 150ms ease-out, background-color 150ms ease-out",
        boxShadow: variant === "primary" ? "var(--shadow-sm)" : "none",
        lineHeight: 1,
        whiteSpace: "nowrap",
        ...VARIANT_STYLES[variant],
        ...SIZE_STYLES[size],
        ...style,
      }}
      onMouseEnter={(e) => {
        if (!isDisabled) {
          e.currentTarget.style.opacity = "0.88";
          e.currentTarget.style.transform = "translateY(-1px)";
        }
        onMouseEnter?.(e);
      }}
      onMouseLeave={(e) => {
        e.currentTarget.style.opacity = isDisabled ? "0.55" : "1";
        e.currentTarget.style.transform = "translateY(0)";
        onMouseLeave?.(e);
      }}
      {...props}
    >
      {loading && <Spinner size={size === "lg" ? 16 : 14} />}
      {children}
    </button>
  );
}

// Inline spinner to avoid circular import
function Spinner({ size = 14 }: { size?: number }) {
  return (
    <span
      style={{
        width: size, height: size,
        borderRadius: "50%",
        borderTop: "2px solid currentColor",
        borderRight: "2px solid transparent",
        borderBottom: "2px solid transparent",
        borderLeft: "2px solid transparent",
        display: "inline-block",
        animation: "spin 0.7s linear infinite",
        flexShrink: 0,
      }}
    />
  );
}
