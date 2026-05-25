import { FONT } from "@/lib/theme";

export function ErrorBanner({ message }: { message: string }) {
  return (
    <div
      role="alert"
      style={{
        marginBottom: 20,
        padding: "10px 14px",
        backgroundColor: "color-mix(in srgb, var(--color-error) 10%, transparent)",
        borderTop: "none",
        borderBottom: "none",
        borderRight: "none",
        borderLeft: "2px solid var(--color-error)",
        borderRadius: "0 4px 4px 0",
        fontFamily: FONT,
        fontWeight: 500,
        fontSize: 13,
        color: "var(--color-error)",
        lineHeight: 1.5,
      }}
    >
      {message}
    </div>
  );
}
