"use client";

import { useState, useRef, useCallback, useEffect, Suspense } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { TopBar, useTheme } from "@/components/TopBar";
import { PALETTE, PALETTE_LIGHT, FONT, MONO, TOKENS } from "@/lib/theme";

const API         = process.env.NEXT_PUBLIC_API_URL ?? "";
const ACCEPTED    = [".pdf", ".docx"];

function getToken() {
  return typeof window !== "undefined" ? (localStorage.getItem("access_token") ?? "") : "";
}

function fmtSize(bytes: number) {
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function validFile(f: File) {
  return ACCEPTED.some(ext => f.name.toLowerCase().endsWith(ext));
}

// ── Drop zone ──────────────────────────────────────────────────────────────────

function DropZone({ label, hint, multiple, files, onAdd, onRemove, isDark, accent }: {
  label: string; hint: string; multiple: boolean;
  files: File[]; onAdd: (f: File[]) => void; onRemove: (i: number) => void;
  isDark: boolean; accent: string;
}) {
  const P     = isDark ? PALETTE : PALETTE_LIGHT;
  const [over, setOver] = useState(false);
  const ref   = useRef<HTMLInputElement>(null);

  const handle = useCallback((list: FileList | null) => {
    if (!list) return;
    const bad = Array.from(list).filter(f => !validFile(f));
    if (bad.length) alert(`Rejected: ${bad.map(f => f.name).join(", ")}\nOnly PDF and DOCX are accepted. Extract ZIPs before uploading.`);
    const good = Array.from(list).filter(validFile);
    if (good.length) onAdd(multiple ? good : [good[0]]);
  }, [multiple, onAdd]);

  return (
    <div>
      <div style={{ fontSize: 12, fontWeight: 600, color: P.text.secondary, marginBottom: 8, fontFamily: FONT }}>{label}</div>
      <div
        onDragOver={e => { e.preventDefault(); setOver(true); }}
        onDragLeave={() => setOver(false)}
        onDrop={e => { e.preventDefault(); setOver(false); handle(e.dataTransfer.files); }}
        onClick={() => ref.current?.click()}
        style={{
          border: `2px dashed ${over ? accent : P.border.mid}`,
          borderRadius: TOKENS.radius.card, padding: "26px 20px",
          textAlign: "center", cursor: "pointer",
          background: over ? accent + "0D" : P.bg.surface,
          transition: "all 140ms",
        }}
      >
        <div style={{ fontSize: 24, marginBottom: 6, opacity: 0.5 }}>⬆</div>
        <div style={{ fontSize: 13, color: P.text.secondary, fontFamily: FONT, marginBottom: 3 }}>
          Drop here or <span style={{ color: accent, fontWeight: 500 }}>browse</span>
        </div>
        <div style={{ fontSize: 11, color: P.text.muted, fontFamily: FONT }}>{hint}</div>
        <input ref={ref} type="file" accept={ACCEPTED.join(",")} multiple={multiple}
          style={{ display: "none" }} onChange={e => handle(e.target.files)} />
      </div>

      {files.length > 0 && (
        <div style={{ marginTop: 10, display: "flex", flexDirection: "column", gap: 6 }}>
          {files.map((f, i) => (
            <div key={i} style={{
              display: "flex", alignItems: "center", gap: 10,
              background: P.bg.elevated, borderRadius: 8,
              padding: "8px 12px", border: `1px solid ${P.border.dim}`,
            }}>
              <span style={{ fontSize: 15 }}>{f.name.endsWith(".pdf") ? "📄" : "📝"}</span>
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ fontSize: 12, fontWeight: 500, color: P.text.primary, fontFamily: FONT, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{f.name}</div>
                <div style={{ fontSize: 11, color: P.text.muted, fontFamily: MONO }}>{fmtSize(f.size)}</div>
              </div>
              <button onClick={e => { e.stopPropagation(); onRemove(i); }} style={{ background: "none", border: "none", cursor: "pointer", color: P.text.muted, fontSize: 15, padding: 2 }}>✕</button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

// ── Page ───────────────────────────────────────────────────────────────────────

export default function UploadPage() {
  return (
    <Suspense>
      <UploadPageInner />
    </Suspense>
  );
}

function UploadPageInner() {
  const { isDark, toggle } = useTheme();
  const P            = isDark ? PALETTE : PALETTE_LIGHT;
  const router       = useRouter();
  const searchParams = useSearchParams();

  const [rfp,           setRfp]           = useState<File[]>([]);
  const [vendors,       setVendors]       = useState<File[]>([]);
  const [dept,          setDept]          = useState("");
  const [rfpTitle,      setRfpTitle]      = useState("");

  // Pre-fill department from ?department= query param (set by home page agent card)
  useEffect(() => {
    const d = searchParams.get("department");
    if (d) setDept(d);
  }, [searchParams]);
  const [contractValue, setContractValue] = useState("");
  const [loading,       setLoading]       = useState(false);
  const [error,         setError]         = useState("");

  const BG = isDark
    ? "radial-gradient(ellipse 90% 60% at 50% 0%, #111828 0%, #090C14 65%)"
    : "linear-gradient(160deg, #ede9e0 0%, #fafaf9 55%)";

  const ready = rfp.length === 1 && vendors.length >= 1 && dept.trim().length > 0 && rfpTitle.trim().length > 0;
  const TEAL  = "#00D4AA";

  async function submit() {
    if (!ready || loading) return;
    setLoading(true);
    setError("");
    try {
      const body = new FormData();
      body.append("rfp_file", rfp[0]);
      body.append("rfp_title", rfpTitle.trim());
      body.append("department", dept.trim());
      body.append("contract_value", contractValue.trim() || "0");
      body.append("vendor_ids", "[]");  // derived from filenames server-side
      vendors.forEach(v => body.append("vendor_files", v));
      const res = await fetch(`${API}/api/v1/evaluate/start`, {
        method: "POST",
        headers: { Authorization: `Bearer ${getToken()}` },
        body,
      });
      if (!res.ok) {
        const d = await res.json().catch(() => ({}));
        throw new Error(d.detail ?? `Upload failed (${res.status})`);
      }
      const { run_id } = await res.json();
      router.push(`/${run_id}/confirm`);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Upload failed. Please try again.");
      setLoading(false);
    }
  }

  const FORMAT_ROWS = [
    { ok: true,  label: "PDF (.pdf)",    note: "Up to 200 MB. Scanned PDFs supported via OCR." },
    { ok: true,  label: "Word (.docx)",  note: "Up to 50 MB." },
    { ok: false, label: "ZIP archives",  note: "Extract files first, then upload individually." },
    { ok: false, label: "Excel / CSV",   note: "Embed pricing data inside the main document." },
    { ok: false, label: "Images",        note: "Embed inside a PDF or DOCX instead." },
  ];

  return (
    <div style={{ minHeight: "100vh", background: BG, fontFamily: FONT }}>
      <TopBar isDark={isDark} onToggle={toggle}
        crumbs={[{ label: "Procurement", href: "/" }, { label: "New evaluation" }]} />

      <main style={{ maxWidth: 920, margin: "0 auto", padding: "36px 28px 80px" }}>
        <div style={{ marginBottom: 28 }}>
          <h1 style={{ fontSize: 22, fontWeight: 700, color: P.text.primary, margin: "0 0 6px", fontFamily: FONT }}>
            New RFP evaluation
          </h1>
          <p style={{ fontSize: 13, color: P.text.muted, margin: 0 }}>
            Upload the RFP and each vendor&apos;s response. The system evaluates all vendors simultaneously in parallel.
          </p>
        </div>

        <div style={{ display: "grid", gridTemplateColumns: "1fr 270px", gap: 24, alignItems: "start" }}>
          {/* Left: form */}
          <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>

            {/* RFP Title */}
            <div>
              <label style={{ fontSize: 12, fontWeight: 600, color: P.text.secondary, display: "block", marginBottom: 8, fontFamily: FONT }}>
                RFP Title
              </label>
              <input
                value={rfpTitle} onChange={e => setRfpTitle(e.target.value)}
                placeholder="e.g. IT Managed Services 2026"
                suppressHydrationWarning
                style={{
                  width: "100%", fontFamily: FONT, fontSize: 13,
                  padding: "10px 14px", borderRadius: TOKENS.radius.btn,
                  border: `1px solid ${P.border.mid}`,
                  background: P.bg.surface, color: P.text.primary, outline: "none",
                  boxSizing: "border-box",
                }}
              />
            </div>

            {/* Department + Contract value */}
            <div style={{ display: "grid", gridTemplateColumns: "1fr 160px", gap: 12 }}>
              <div>
                <label style={{ fontSize: 12, fontWeight: 600, color: P.text.secondary, display: "block", marginBottom: 8, fontFamily: FONT }}>
                  Department
                </label>
                <input
                  value={dept} onChange={e => setDept(e.target.value)}
                  placeholder="e.g. IT Procurement"
                  suppressHydrationWarning
                  style={{
                    width: "100%", fontFamily: FONT, fontSize: 13,
                    padding: "10px 14px", borderRadius: TOKENS.radius.btn,
                    border: `1px solid ${P.border.mid}`,
                    background: P.bg.surface, color: P.text.primary, outline: "none",
                    boxSizing: "border-box",
                  }}
                />
              </div>
              <div>
                <label style={{ fontSize: 12, fontWeight: 600, color: P.text.secondary, display: "block", marginBottom: 8, fontFamily: FONT }}>
                  Est. contract value (£)
                </label>
                <input
                  value={contractValue} onChange={e => setContractValue(e.target.value)}
                  placeholder="e.g. 250000"
                  suppressHydrationWarning
                  style={{
                    width: "100%", fontFamily: FONT, fontSize: 13,
                    padding: "10px 14px", borderRadius: TOKENS.radius.btn,
                    border: `1px solid ${P.border.mid}`,
                    background: P.bg.surface, color: P.text.primary, outline: "none",
                    boxSizing: "border-box",
                  }}
                />
              </div>
            </div>

            <DropZone label="RFP Document (1 file)" hint="The original RFP issued to vendors — PDF or DOCX"
              multiple={false} files={rfp}
              onAdd={f => setRfp(f)} onRemove={i => setRfp(fs => fs.filter((_, j) => j !== i))}
              isDark={isDark} accent={TEAL} />

            <DropZone label="Vendor Responses (one or more)" hint="One file per vendor. File name = vendor name."
              multiple files={vendors}
              onAdd={f => setVendors(v => [...v, ...f])} onRemove={i => setVendors(v => v.filter((_, j) => j !== i))}
              isDark={isDark} accent="#8B5CF6" />

            {error && (
              <div style={{
                background: "#EF444414", border: "1px solid #EF4444",
                borderRadius: TOKENS.radius.btn, padding: "10px 14px",
                fontSize: 13, color: "#EF4444", fontFamily: FONT,
              }}>{error}</div>
            )}

            <div style={{ display: "flex", alignItems: "center", gap: 14 }}>
              <button onClick={submit} disabled={!ready || loading} style={{
                background: ready && !loading ? TEAL : P.border.mid,
                color: ready && !loading ? "#071510" : P.text.muted,
                border: "none", borderRadius: TOKENS.radius.btn,
                padding: "11px 28px", fontSize: 13, fontFamily: FONT, fontWeight: 600,
                cursor: ready && !loading ? "pointer" : "not-allowed",
                transition: "background 160ms",
              }}>
                {loading ? "Uploading…" : "Start evaluation →"}
              </button>
              {!ready && !loading && (
                <span style={{ fontSize: 11, color: P.text.muted }}>
                  {!rfpTitle.trim() ? "Enter an RFP title" : !dept.trim() ? "Enter a department name" : !rfp.length ? "Upload the RFP file" : "Add at least one vendor response"}
                </span>
              )}
            </div>
          </div>

          {/* Right: format guide + how it works */}
          <div style={{ display: "flex", flexDirection: "column", gap: 14, position: "sticky", top: 76 }}>
            <div style={{ background: P.bg.elevated, borderRadius: TOKENS.radius.card, border: `1px solid ${P.border.dim}`, padding: "16px 18px" }}>
              <div style={{ fontSize: 10, fontWeight: 700, color: P.text.muted, letterSpacing: "0.07em", textTransform: "uppercase", marginBottom: 12, fontFamily: FONT }}>
                Accepted formats
              </div>
              {FORMAT_ROWS.map((r, i) => (
                <div key={i} style={{ display: "flex", gap: 9, marginBottom: 9, alignItems: "flex-start" }}>
                  <span style={{ fontSize: 12, flexShrink: 0, marginTop: 1 }}>{r.ok ? "✅" : "❌"}</span>
                  <div>
                    <span style={{ fontSize: 12, fontWeight: 600, color: P.text.secondary, fontFamily: FONT }}>{r.label}</span>
                    <span style={{ fontSize: 12, color: P.text.muted, fontFamily: FONT }}> — {r.note}</span>
                  </div>
                </div>
              ))}
            </div>

            <div style={{ background: P.bg.elevated, borderRadius: TOKENS.radius.card, border: `1px solid ${P.border.dim}`, padding: "16px 18px" }}>
              <div style={{ fontSize: 10, fontWeight: 700, color: P.text.muted, letterSpacing: "0.07em", textTransform: "uppercase", marginBottom: 12, fontFamily: FONT }}>
                How it works
              </div>
              {[
                ["01", "Upload — system parses and indexes all documents"],
                ["02", "Confirm — verify RFP identity and scoring rubric"],
                ["03", "Evaluate — 9 agents run in parallel across all vendors"],
                ["04", "Results — ranked shortlist, every score evidenced"],
              ].map(([n, s], i) => (
                <div key={i} style={{ display: "flex", gap: 10, marginBottom: 9 }}>
                  <span style={{ fontFamily: MONO, fontSize: 11, color: TEAL, flexShrink: 0 }}>{n}</span>
                  <span style={{ fontSize: 12, color: P.text.secondary, fontFamily: FONT }}>{s}</span>
                </div>
              ))}
            </div>
          </div>
        </div>
      </main>
    </div>
  );
}
