import { FONT, DISPLAY } from "@/lib/theme";

interface Props {
  title: string;
  description?: string;
  action?: React.ReactNode;
  icon?: React.ReactNode;
}

export function EmptyState({ title, description, action, icon }: Props) {
  return (
    <div style={{
      display: "flex", flexDirection: "column", alignItems: "center",
      justifyContent: "center", padding: "4rem 2rem", gap: "1rem",
      color: "var(--color-text-muted)", textAlign: "center",
    }}>
      {icon && <div style={{ opacity: 0.4, marginBottom: "0.5rem" }}>{icon}</div>}
      <p style={{
        fontFamily: DISPLAY, fontWeight: 700, fontSize: "1.125rem",
        letterSpacing: "-0.02em", color: "var(--color-text)", margin: 0,
      }}>
        {title}
      </p>
      {description && (
        <p style={{
          fontFamily: FONT, fontWeight: 400, fontSize: "0.875rem",
          lineHeight: 1.6, maxWidth: "24rem", margin: 0,
        }}>
          {description}
        </p>
      )}
      {action && <div style={{ marginTop: "0.5rem" }}>{action}</div>}
    </div>
  );
}
