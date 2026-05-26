import { FONT, DISPLAY, MONO } from "@/lib/theme";

export default function LeftBrandPanel() {
  return (
    <div
      style={{
        width: "45%",
        minWidth: 380,
        backgroundColor: "#090E1A",
        display: "flex",
        flexDirection: "column",
        justifyContent: "space-between",
        padding: "48px 48px 40px",
        position: "relative",
        overflow: "hidden",
        flexShrink: 0,
      }}
    >
      <div
        aria-hidden
        style={{
          position: "absolute",
          inset: 0,
          backgroundImage:
            "linear-gradient(rgba(255,255,255,0.025) 1px, transparent 1px), linear-gradient(90deg, rgba(255,255,255,0.025) 1px, transparent 1px)",
          backgroundSize: "40px 40px",
          pointerEvents: "none",
        }}
      />
      <div
        aria-hidden
        style={{
          position: "absolute",
          top: -80,
          right: -80,
          width: 320,
          height: 320,
          borderRadius: "50%",
          background: "radial-gradient(circle, rgba(99,102,241,0.18) 0%, transparent 70%)",
          pointerEvents: "none",
        }}
      />

      {/* Wordmark */}
      <div style={{ position: "relative", zIndex: 1 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <div
            style={{
              width: 28, height: 28,
              border: "1.5px solid rgba(99,102,241,0.7)",
              borderRadius: 5,
              display: "flex", alignItems: "center", justifyContent: "center",
            }}
          >
            <div style={{ width: 10, height: 10, backgroundColor: "rgba(99,102,241,0.9)", borderRadius: 2 }} />
          </div>
          <span
            style={{
              fontFamily: DISPLAY, fontWeight: 700, fontSize: 14,
              letterSpacing: "0.12em", textTransform: "uppercase",
              color: "rgba(255,255,255,0.55)",
            }}
          >
            Meridian AI
          </span>
        </div>
      </div>

      {/* Hero text */}
      <div style={{ position: "relative", zIndex: 1, flex: 1, display: "flex", flexDirection: "column", justifyContent: "center" }}>
        <div style={{ overflow: "hidden", marginLeft: -4 }}>
          <div
            style={{
              fontFamily: DISPLAY, fontWeight: 800,
              fontSize: "clamp(64px, 9vw, 108px)",
              lineHeight: 0.9, letterSpacing: "-0.04em",
              color: "rgba(255,255,255,0.92)", whiteSpace: "nowrap",
            }}
          >
            Meridian
          </div>
        </div>
        <div style={{ width: 48, height: 2, backgroundColor: "rgba(99,102,241,0.8)", marginTop: 24, marginBottom: 20 }} />
        <p
          style={{
            fontFamily: FONT, fontWeight: 400, fontSize: 14,
            lineHeight: 1.7, color: "rgba(255,255,255,0.4)",
            maxWidth: 260, letterSpacing: "0.01em",
          }}
        >
          Enterprise vendor governance.
          <br />
          AI-evaluated. Audit-ready.
        </p>
      </div>

      {/* Footer */}
      <div style={{ position: "relative", zIndex: 1 }}>
        <p style={{ fontFamily: MONO, fontWeight: 400, fontSize: 10, letterSpacing: "0.08em", color: "rgba(255,255,255,0.2)", textTransform: "uppercase" }}>
          Meridian Financial Services
          <br />
          SOC 2 · ISO 27001 · GDPR
        </p>
      </div>
    </div>
  );
}
