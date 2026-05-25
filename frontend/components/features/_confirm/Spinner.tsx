export function Spinner({ size = 12, color = "var(--color-text-muted)" }: { size?: number; color?: string }) {
  return (
    <div style={{
      width: size, height: size, flexShrink: 0,
      borderTop: `2px solid ${color}`,
      borderBottom: "2px solid transparent",
      borderLeft: "2px solid transparent",
      borderRight: "2px solid transparent",
      borderRadius: "50%",
      animation: "csp-spin 0.7s linear infinite",
    }} />
  );
}
