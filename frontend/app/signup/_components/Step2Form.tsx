"use client";

import { FONT } from "@/lib/theme";
import { inputStyle, labelStyle, submitStyle } from "./signupStyles";
import { ErrorBanner } from "./ErrorBanner";

interface Step2FormProps {
  email: string;
  password: string;
  confirmPassword: string;
  error: string;
  loading: boolean;
  focusedField: string | null;
  onEmailChange: (v: string) => void;
  onPasswordChange: (v: string) => void;
  onConfirmPasswordChange: (v: string) => void;
  onFocusChange: (field: string | null) => void;
  onBack: () => void;
  onSubmit: (e: React.FormEvent) => void;
}

export default function Step2Form({
  email,
  password,
  confirmPassword,
  error,
  loading,
  focusedField,
  onEmailChange,
  onPasswordChange,
  onConfirmPasswordChange,
  onFocusChange,
  onBack,
  onSubmit,
}: Step2FormProps) {
  return (
    <form onSubmit={onSubmit}>
      <div style={{ marginBottom: 32 }}>
        <label style={labelStyle("email", focusedField)} htmlFor="email">Work email</label>
        <input
          id="email"
          type="email"
          autoComplete="email"
          required
          value={email}
          onChange={(e) => onEmailChange(e.target.value)}
          onFocus={() => onFocusChange("email")}
          onBlur={() => onFocusChange(null)}
          suppressHydrationWarning
          style={inputStyle("email", focusedField)}
          placeholder="you@company.com"
        />
      </div>

      <div style={{ marginBottom: 32 }}>
        <label style={labelStyle("password", focusedField)} htmlFor="password">Password</label>
        <input
          id="password"
          type="password"
          autoComplete="new-password"
          required
          value={password}
          onChange={(e) => onPasswordChange(e.target.value)}
          onFocus={() => onFocusChange("password")}
          onBlur={() => onFocusChange(null)}
          suppressHydrationWarning
          style={inputStyle("password", focusedField)}
          placeholder="Min. 8 characters"
        />
      </div>

      <div style={{ marginBottom: 40 }}>
        <label style={labelStyle("confirm", focusedField)} htmlFor="confirm">Confirm password</label>
        <input
          id="confirm"
          type="password"
          autoComplete="new-password"
          required
          value={confirmPassword}
          onChange={(e) => onConfirmPasswordChange(e.target.value)}
          onFocus={() => onFocusChange("confirm")}
          onBlur={() => onFocusChange(null)}
          suppressHydrationWarning
          style={{
            ...inputStyle("confirm", focusedField),
            borderBottom: confirmPassword && confirmPassword !== password
              ? "1.5px solid var(--color-error)"
              : inputStyle("confirm", focusedField).borderBottom,
          }}
          placeholder="Repeat password"
        />
        {confirmPassword && confirmPassword !== password && (
          <p style={{ fontFamily: FONT, fontSize: 12, color: "var(--color-error)", marginTop: 6 }}>
            Passwords do not match
          </p>
        )}
      </div>

      {error && <ErrorBanner message={error} />}

      <div style={{ display: "flex", gap: 12 }}>
        <button
          type="button"
          onClick={onBack}
          onMouseEnter={(e) => { (e.currentTarget).style.backgroundColor = "var(--color-surface-hover)"; }}
          onMouseLeave={(e) => { (e.currentTarget).style.backgroundColor = "transparent"; }}
          style={{
            flex: "0 0 auto",
            padding: "14px 20px",
            backgroundColor: "transparent",
            color: "var(--color-text-secondary)",
            borderTop: "1px solid var(--color-border)",
            borderBottom: "1px solid var(--color-border)",
            borderLeft: "1px solid var(--color-border)",
            borderRight: "1px solid var(--color-border)",
            borderRadius: "var(--radius)",
            fontFamily: FONT,
            fontWeight: 500,
            fontSize: 14,
            cursor: "pointer",
            transition: "background-color 150ms ease-out",
          }}
        >
          ← Back
        </button>
        <button
          type="submit"
          disabled={loading}
          onMouseEnter={(e) => { if (!loading) { (e.currentTarget).style.opacity = "0.88"; (e.currentTarget).style.transform = "translateY(-1px)"; } }}
          onMouseLeave={(e) => { (e.currentTarget).style.opacity = "1"; (e.currentTarget).style.transform = "translateY(0)"; }}
          onMouseDown={(e) => { if (!loading) (e.currentTarget).style.transform = "translateY(0) scale(0.98)"; }}
          onMouseUp={(e) => { if (!loading) (e.currentTarget).style.transform = "translateY(-1px)"; }}
          style={{ ...submitStyle, flex: 1, opacity: loading ? 0.6 : 1, cursor: loading ? "not-allowed" : "pointer" }}
        >
          {loading ? "Creating account…" : "Create account"}
        </button>
      </div>
    </form>
  );
}
