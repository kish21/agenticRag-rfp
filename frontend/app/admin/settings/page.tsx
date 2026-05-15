"use client";

import { useState, useEffect } from "react";

type OrgSettings = {
  org_id: string;
  quality_tier: string;
  use_hyde: boolean;
  use_reranking: boolean;
  use_query_rewriting: boolean;
  use_hybrid_search: boolean;
  reranker_provider: string;
  retrieval_top_k: number;
  rerank_top_n: number;
  mandatory_check_use_llm_verify: boolean;
  confidence_retry_threshold: number;
  score_variance_threshold: number;
  rank_margin_threshold: number;
  llm_temperature: number;
  output_tone: string;
  output_language: string;
  citation_style: string;
  include_confidence_score: boolean;
  include_evidence_quotes: boolean;
  max_evidence_quote_chars: number;
  parallel_vendors: boolean;
};

const TIER_OPTIONS = ["fast", "balanced", "accurate"];

export default function OrgSettingsPage() {
  const [settings, setSettings] = useState<OrgSettings | null>(null);
  const [saving, setSaving] = useState(false);
  const [resetting, setResetting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    fetch("/api/v1/org/settings", { credentials: "include" })
      .then((r) => r.json())
      .then(setSettings)
      .catch(() => setError("Failed to load org settings"));
  }, []);

  const handleSave = async () => {
    if (!settings) return;
    setSaving(true);
    setError(null);
    setSaved(false);
    try {
      const { org_id, ...fields } = settings;
      const r = await fetch("/api/v1/org/settings", {
        method: "PATCH",
        credentials: "include",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ fields }),
      });
      if (!r.ok) {
        const d = await r.json();
        setError(d.detail ?? "Save failed");
      } else {
        setSettings(await r.json());
        setSaved(true);
        setTimeout(() => setSaved(false), 3000);
      }
    } catch {
      setError("Network error");
    } finally {
      setSaving(false);
    }
  };

  const handleReset = async () => {
    if (!confirm("Reset all settings to defaults?")) return;
    setResetting(true);
    setError(null);
    try {
      const r = await fetch("/api/v1/org/settings/reset", {
        method: "POST",
        credentials: "include",
      });
      if (!r.ok) {
        setError("Reset failed");
      } else {
        setSettings(await r.json());
        setSaved(true);
        setTimeout(() => setSaved(false), 3000);
      }
    } catch {
      setError("Network error");
    } finally {
      setResetting(false);
    }
  };

  const set = <K extends keyof OrgSettings>(key: K, val: OrgSettings[K]) =>
    setSettings((prev) => (prev ? { ...prev, [key]: val } : prev));

  if (!settings) {
    return (
      <div style={{ padding: "2rem", fontFamily: "var(--font-mono)", color: "var(--color-text-muted)" }}>
        {error ?? "Loading…"}
      </div>
    );
  }

  return (
    <div style={{ padding: "2rem", maxWidth: 720, fontFamily: "var(--font-sans)" }}>
      <h1 style={{ fontSize: "1.25rem", fontWeight: 700, marginBottom: "1.5rem" }}>
        Org Settings — {settings.org_id}
      </h1>

      <Section title="Quality Preset">
        <Row label="Tier">
          <select
            value={settings.quality_tier}
            onChange={(e) => set("quality_tier", e.target.value)}
            style={SELECT}
          >
            {TIER_OPTIONS.map((t) => (
              <option key={t} value={t}>{t}</option>
            ))}
          </select>
        </Row>
      </Section>

      <Section title="Retrieval">
        <BoolRow label="HyDE" val={settings.use_hyde} onChange={(v) => set("use_hyde", v)} />
        <BoolRow label="Reranking" val={settings.use_reranking} onChange={(v) => set("use_reranking", v)} />
        <BoolRow label="Query rewriting" val={settings.use_query_rewriting} onChange={(v) => set("use_query_rewriting", v)} />
        <BoolRow label="Hybrid search" val={settings.use_hybrid_search} onChange={(v) => set("use_hybrid_search", v)} />
        <Row label="Reranker provider">
          <input style={INPUT} value={settings.reranker_provider} onChange={(e) => set("reranker_provider", e.target.value)} />
        </Row>
        <Row label="Top-K candidates">
          <input style={INPUT} type="number" min={1} max={100} value={settings.retrieval_top_k} onChange={(e) => set("retrieval_top_k", Number(e.target.value))} />
        </Row>
        <Row label="Rerank top-N">
          <input style={INPUT} type="number" min={1} max={50} value={settings.rerank_top_n} onChange={(e) => set("rerank_top_n", Number(e.target.value))} />
        </Row>
      </Section>

      <Section title="Evaluation Thresholds">
        <BoolRow label="LLM verify mandatory checks" val={settings.mandatory_check_use_llm_verify} onChange={(v) => set("mandatory_check_use_llm_verify", v)} />
        <Row label="Confidence retry threshold">
          <input style={INPUT} type="number" step={0.01} min={0} max={1} value={settings.confidence_retry_threshold} onChange={(e) => set("confidence_retry_threshold", Number(e.target.value))} />
        </Row>
        <Row label="Score variance threshold">
          <input style={INPUT} type="number" step={0.01} min={0} max={1} value={settings.score_variance_threshold} onChange={(e) => set("score_variance_threshold", Number(e.target.value))} />
        </Row>
        <Row label="Rank margin threshold">
          <input style={INPUT} type="number" min={0} max={100} value={settings.rank_margin_threshold} onChange={(e) => set("rank_margin_threshold", Number(e.target.value))} />
        </Row>
        <Row label="LLM temperature">
          <input style={INPUT} type="number" step={0.1} min={0} max={2} value={settings.llm_temperature} onChange={(e) => set("llm_temperature", Number(e.target.value))} />
        </Row>
      </Section>

      <Section title="Output">
        <Row label="Tone">
          <input style={INPUT} value={settings.output_tone} onChange={(e) => set("output_tone", e.target.value)} />
        </Row>
        <Row label="Language">
          <input style={INPUT} value={settings.output_language} onChange={(e) => set("output_language", e.target.value)} />
        </Row>
        <Row label="Citation style">
          <input style={INPUT} value={settings.citation_style} onChange={(e) => set("citation_style", e.target.value)} />
        </Row>
        <BoolRow label="Include confidence score" val={settings.include_confidence_score} onChange={(v) => set("include_confidence_score", v)} />
        <BoolRow label="Include evidence quotes" val={settings.include_evidence_quotes} onChange={(v) => set("include_evidence_quotes", v)} />
        <Row label="Max evidence quote chars">
          <input style={INPUT} type="number" min={50} max={2000} value={settings.max_evidence_quote_chars} onChange={(e) => set("max_evidence_quote_chars", Number(e.target.value))} />
        </Row>
      </Section>

      <Section title="Pipeline">
        <BoolRow label="Parallel vendor evaluation" val={settings.parallel_vendors} onChange={(v) => set("parallel_vendors", v)} />
      </Section>

      {error && (
        <p style={{ color: "var(--color-error)", marginBottom: "1rem", fontSize: "0.875rem" }}>{error}</p>
      )}
      {saved && (
        <p style={{ color: "var(--color-success)", marginBottom: "1rem", fontSize: "0.875rem" }}>Saved.</p>
      )}

      <div style={{ display: "flex", gap: "0.75rem" }}>
        <button onClick={handleSave} disabled={saving} style={{ ...BTN, background: "var(--color-accent)", color: "var(--color-accent-foreground)" }}>
          {saving ? "Saving…" : "Save changes"}
        </button>
        <button onClick={handleReset} disabled={resetting} style={{ ...BTN, background: "var(--color-surface-hover)", color: "var(--color-text-secondary)" }}>
          {resetting ? "Resetting…" : "Reset to defaults"}
        </button>
      </div>
    </div>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div style={{ marginBottom: "1.5rem" }}>
      <h2 style={{ fontSize: "0.75rem", fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.08em", color: "var(--color-text-muted)", marginBottom: "0.5rem" }}>
        {title}
      </h2>
      <div style={{ background: "var(--color-surface)", borderRadius: 8, padding: "0.75rem 1rem", display: "flex", flexDirection: "column", gap: "0.5rem" }}>
        {children}
      </div>
    </div>
  );
}

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: "1rem" }}>
      <span style={{ fontSize: "0.875rem", color: "var(--color-text-secondary)", minWidth: 200 }}>{label}</span>
      {children}
    </div>
  );
}

function BoolRow({ label, val, onChange }: { label: string; val: boolean; onChange: (v: boolean) => void }) {
  return (
    <Row label={label}>
      <input type="checkbox" checked={val} onChange={(e) => onChange(e.target.checked)} style={{ width: 16, height: 16, accentColor: "var(--color-accent)" }} />
    </Row>
  );
}

const INPUT: React.CSSProperties = {
  border: "1px solid var(--color-border)",
  borderRadius: 6,
  padding: "0.25rem 0.5rem",
  fontSize: "0.875rem",
  width: 200,
  background: "#fff",
};

const SELECT: React.CSSProperties = { ...INPUT };

const BTN: React.CSSProperties = {
  padding: "0.5rem 1.25rem",
  borderRadius: 8,
  border: "none",
  cursor: "pointer",
  fontSize: "0.875rem",
  fontWeight: 600,
};
