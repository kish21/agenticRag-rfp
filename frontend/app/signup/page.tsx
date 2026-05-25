"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { FONT, DISPLAY } from "@/lib/theme";
import { useThemeContext } from "@/components/layout/ThemeProvider";
import { useBreakpoint } from "@/lib/hooks";
import { api, setUserInfo } from "@/lib/api";
import LeftBrandPanel from "@/components/auth/LeftBrandPanel";
import Step1Form from "./_components/Step1Form";
import Step2Form from "./_components/Step2Form";

const INDUSTRIES = [
  "Financial Services",
  "Banking",
  "Insurance",
  "Asset Management",
  "Healthcare",
  "Technology",
  "Government",
  "Manufacturing",
  "Energy & Utilities",
  "Professional Services",
  "Other",
];

type Step = 1 | 2;

export default function SignupPage() {
  const router = useRouter();
  const { isDark } = useThemeContext();
  const bp = useBreakpoint();
  const isDesktop = bp === "desktop";

  const [step, setStep] = useState<Step>(1);
  const [orgName, setOrgName] = useState("");
  const [industry, setIndustry] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [focusedField, setFocusedField] = useState<string | null>(null);

  function handleStep1(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    if (!orgName.trim()) { setError("Organisation name is required."); return; }
    if (!industry) { setError("Please select your industry."); return; }
    setStep(2);
  }

  async function handleStep2(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    if (password.length < 8) { setError("Password must be at least 8 characters."); return; }
    if (password !== confirmPassword) { setError("Passwords do not match."); return; }

    setLoading(true);
    try {
      const data = await api.post<{ role: string; org_id: string }>(
        "/api/v1/auth/signup",
        { body: { org_name: orgName, industry, email, password } }
      );
      setUserInfo({ email, role: data.role, org_id: data.org_id });
      router.push("/");
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Registration failed. Please try again.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div style={{ minHeight: "100vh", display: "flex", fontFamily: FONT }}>

      {isDesktop && <LeftBrandPanel />}

      <div
        style={{
          flex: 1, display: "flex", flexDirection: "column",
          justifyContent: "center", alignItems: "center",
          background: "var(--bg-gradient)",
          padding: isDesktop ? "48px 32px" : bp === "tablet" ? "32px 24px" : "24px 20px",
        }}
      >
        <div style={{ width: "100%", maxWidth: isDesktop ? 380 : 440 }}>

          {/* Compact logo — mobile/tablet only */}
          {!isDesktop && (
            <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 40 }}>
              <div
                style={{
                  width: 28, height: 28,
                  border: "1.5px solid var(--color-accent)",
                  borderRadius: 5,
                  display: "flex", alignItems: "center", justifyContent: "center",
                }}
              >
                <div style={{ width: 10, height: 10, backgroundColor: "var(--color-accent)", borderRadius: 2 }} />
              </div>
              <span style={{ fontFamily: DISPLAY, fontWeight: 700, fontSize: 14, letterSpacing: "0.12em", textTransform: "uppercase", color: "var(--color-text-primary)" }}>
                Meridian AI
              </span>
            </div>
          )}

          {/* Step indicator */}
          <div style={{ display: "flex", gap: 6, marginBottom: 32 }}>
            {([1, 2] as Step[]).map((s) => (
              <div
                key={s}
                style={{
                  flex: 1, height: 2,
                  backgroundColor: s <= step ? "var(--color-accent)" : "var(--color-border)",
                  borderRadius: 2,
                  transition: "background-color 300ms ease-out",
                }}
              />
            ))}
          </div>

          <p
            style={{
              fontFamily: FONT, fontWeight: 600, fontSize: 11,
              letterSpacing: "0.1em", textTransform: "uppercase",
              color: "var(--color-text-muted)", marginBottom: 12,
            }}
          >
            {step === 1 ? "Step 1 of 2" : "Step 2 of 2"}
          </p>

          <h1
            style={{
              fontFamily: DISPLAY, fontWeight: 800, fontSize: 28,
              lineHeight: 1.1, letterSpacing: "-0.03em",
              color: "var(--color-text-primary)", marginBottom: 8,
            }}
          >
            {step === 1 ? "Your organisation" : "Your account"}
          </h1>
          <p
            style={{
              fontFamily: FONT, fontWeight: 400, fontSize: 14,
              color: "var(--color-text-secondary)", marginBottom: 36, lineHeight: 1.6,
            }}
          >
            {step === 1
              ? "Tell us about your organisation so we can configure your workspace."
              : "Create your administrator account for this workspace."}
          </p>

          {step === 1 && (
            <Step1Form
              orgName={orgName}
              industry={industry}
              error={error}
              focusedField={focusedField}
              industries={INDUSTRIES}
              onOrgNameChange={setOrgName}
              onIndustryChange={setIndustry}
              onFocusChange={setFocusedField}
              onContinue={handleStep1}
            />
          )}

          {step === 2 && (
            <Step2Form
              email={email}
              password={password}
              confirmPassword={confirmPassword}
              error={error}
              loading={loading}
              focusedField={focusedField}
              onEmailChange={setEmail}
              onPasswordChange={setPassword}
              onConfirmPasswordChange={setConfirmPassword}
              onFocusChange={setFocusedField}
              onBack={() => { setStep(1); setError(""); }}
              onSubmit={handleStep2}
            />
          )}

          <div style={{ display: "flex", alignItems: "center", gap: 12, margin: "28px 0" }}>
            <div style={{ flex: 1, height: 1, backgroundColor: "var(--color-border)" }} />
            <span style={{ fontFamily: FONT, fontWeight: 400, fontSize: 12, color: "var(--color-text-muted)" }}>
              Already have an account?
            </span>
            <div style={{ flex: 1, height: 1, backgroundColor: "var(--color-border)" }} />
          </div>

          <Link
            href="/login"
            style={{
              display: "block", width: "100%", padding: "13px 0",
              backgroundColor: "transparent",
              color: "var(--color-text-primary)",
              borderTop: "1px solid var(--color-border)",
              borderBottom: "1px solid var(--color-border)",
              borderLeft: "1px solid var(--color-border)",
              borderRight: "1px solid var(--color-border)",
              borderRadius: "var(--radius)",
              fontFamily: FONT, fontWeight: 500, fontSize: 14,
              textAlign: "center", textDecoration: "none",
              transition: "background-color 150ms ease-out",
              boxSizing: "border-box",
            }}
            onMouseEnter={(e) => { (e.currentTarget as HTMLAnchorElement).style.backgroundColor = "var(--color-surface-hover)"; }}
            onMouseLeave={(e) => { (e.currentTarget as HTMLAnchorElement).style.backgroundColor = "transparent"; }}
          >
            Sign in instead
          </Link>
        </div>
      </div>
    </div>
  );
}
