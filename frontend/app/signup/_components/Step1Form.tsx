"use client";

import { FONT } from "@/lib/theme";
import { inputStyle, labelStyle, submitStyle } from "./signupStyles";
import { ErrorBanner } from "./ErrorBanner";

interface Step1FormProps {
  orgName: string;
  industry: string;
  error: string;
  focusedField: string | null;
  industries: string[];
  onOrgNameChange: (v: string) => void;
  onIndustryChange: (v: string) => void;
  onFocusChange: (field: string | null) => void;
  onContinue: (e: React.FormEvent) => void;
}

export default function Step1Form({
  orgName,
  industry,
  error,
  focusedField,
  industries,
  onOrgNameChange,
  onIndustryChange,
  onFocusChange,
  onContinue,
}: Step1FormProps) {
  return (
    <form onSubmit={onContinue}>
      <div style={{ marginBottom: 32 }}>
        <label style={labelStyle("orgName", focusedField)} htmlFor="orgName">Organisation name</label>
        <input
          id="orgName"
          type="text"
          required
          value={orgName}
          onChange={(e) => onOrgNameChange(e.target.value)}
          onFocus={() => onFocusChange("orgName")}
          onBlur={() => onFocusChange(null)}
          suppressHydrationWarning
          style={inputStyle("orgName", focusedField)}
          placeholder="Acme Financial Ltd"
        />
      </div>

      <div style={{ marginBottom: 40 }}>
        <label style={labelStyle("industry", focusedField)} htmlFor="industry">Industry</label>
        <select
          id="industry"
          required
          value={industry}
          onChange={(e) => onIndustryChange(e.target.value)}
          onFocus={() => onFocusChange("industry")}
          onBlur={() => onFocusChange(null)}
          style={{
            ...inputStyle("industry", focusedField),
            cursor: "pointer",
            appearance: "none",
            paddingRight: 24,
            color: industry ? "var(--color-text-primary)" : "var(--color-text-muted)",
          }}
        >
          <option value="" disabled>Select industry…</option>
          {industries.map((ind) => (
            <option key={ind} value={ind} style={{ backgroundColor: "var(--color-surface)", color: "var(--color-text-primary)" }}>
              {ind}
            </option>
          ))}
        </select>
      </div>

      {error && <ErrorBanner message={error} />}

      <button
        type="submit"
        onMouseEnter={(e) => { (e.currentTarget).style.opacity = "0.88"; (e.currentTarget).style.transform = "translateY(-1px)"; }}
        onMouseLeave={(e) => { (e.currentTarget).style.opacity = "1"; (e.currentTarget).style.transform = "translateY(0)"; }}
        onMouseDown={(e) => { (e.currentTarget).style.transform = "translateY(0) scale(0.98)"; }}
        onMouseUp={(e) => { (e.currentTarget).style.transform = "translateY(-1px)"; }}
        style={submitStyle}
      >
        Continue →
      </button>
    </form>
  );
}
