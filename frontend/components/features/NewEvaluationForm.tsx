"use client";

import { useState, useRef, useEffect } from "react";
import { FONT, DISPLAY } from "@/lib/theme";
import { useBreakpoint } from "@/lib/hooks";
import { api } from "@/lib/api";
import { FileDropZone } from "./FileDropZone";
import { MultiFileDropZone } from "./MultiFileDropZone";
import { VendorCard } from "./VendorCard";

// ── Types ─────────────────────────────────────────────────────────────────────

interface VendorSlot {
  id: string;
  name: string;
  file: File;
}

interface NewEvaluationFormProps {
  onBack: () => void;
  onSuccess: (runId: string, rfpTitle: string, vendorCount: number) => void;
  onAuth401: () => void;
}

// ── Constants ─────────────────────────────────────────────────────────────────

const DEPARTMENTS = ["Procurement", "Finance", "Legal", "IT", "Operations", "HR", "Marketing"];

const MAX_VENDORS = 10;

function mkId() { return Math.random().toString(36).slice(2, 8); }

function extractVendorName(filename: string): string {
  const base = filename.replace(/\.[^.]+$/, "");
  const first = base.split(/[_\-\s.]+/)[0] ?? base;
  return first.charAt(0).toUpperCase() + first.slice(1).toLowerCase();
}

// ── Shared styles ─────────────────────────────────────────────────────────────

const labelCss: React.CSSProperties = {
  display: "block",
  fontFamily: FONT,
  fontSize: 11, fontWeight: 600,
  letterSpacing: "0.07em", textTransform: "uppercase",
  color: "var(--color-text-muted)",
  marginBottom: 8,
};

const inputCss: React.CSSProperties = {
  width: "100%", boxSizing: "border-box",
  padding: "9px 12px",
  backgroundColor: "var(--color-background)",
  borderTop: "1px solid var(--color-border)",
  borderBottom: "1px solid var(--color-border)",
  borderLeft: "1px solid var(--color-border)",
  borderRight: "1px solid var(--color-border)",
  borderRadius: "var(--radius)",
  fontFamily: FONT, fontSize: 13,
  color: "var(--color-text-primary)",
  transition: "border-color 150ms ease-out",
};

// ── Component ─────────────────────────────────────────────────────────────────

export function NewEvaluationForm({ onBack, onSuccess, onAuth401 }: NewEvaluationFormProps) {
  const bp = useBreakpoint();
  const isMobile = bp === "mobile";

  const [rfpTitle, setRfpTitle] = useState("");
  const [department, setDepartment] = useState("");
  const [contractValue, setContractValue] = useState("");
  const [currency, setCurrency] = useState("GBP");
  const [rfpFile, setRfpFile] = useState<File | null>(null);
  const [criteriaFile, setCriteriaFile] = useState<File | null>(null);
  const [vendors, setVendors] = useState<VendorSlot[]>([]);
  const [submitting, setSubmitting] = useState(false);
  const [formError, setFormError] = useState("");
  const errorRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (formError) errorRef.current?.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }, [formError]);

  function resetForm() {
    setRfpTitle("");
    setDepartment("");
    setContractValue("");
    setCurrency("GBP");
    setRfpFile(null);
    setCriteriaFile(null);
    setVendors([]);
    setFormError("");
  }

  function addVendorsFromFiles(files: File[]) {
    setVendors(prev => {
      const slots = files
        .slice(0, MAX_VENDORS - prev.length)
        .map(f => ({ id: mkId(), name: extractVendorName(f.name), file: f }));
      return [...prev, ...slots];
    });
  }

  function removeVendor(id: string) {
    setVendors(p => p.filter(v => v.id !== id));
  }

  function updateVendorName(id: string, name: string) {
    setVendors(p => p.map(v => v.id === id ? { ...v, name } : v));
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setFormError("");

    if (!rfpTitle.trim()) { setFormError("RFP title is required."); return; }
    if (!department) { setFormError("Department is required."); return; }
    if (!rfpFile) { setFormError("RFP document is required."); return; }
    if (vendors.length === 0) { setFormError("Drop at least one vendor proposal."); return; }
    if (vendors.some(v => !v.name.trim())) { setFormError("Each vendor must have a name."); return; }

    setSubmitting(true);
    const fd = new FormData();
    fd.append("rfp_title", rfpTitle.trim());
    fd.append("department", department);
    fd.append("contract_value", contractValue.replace(/,/g, "") || "0");
    fd.append("currency", currency);
    fd.append("rfp_file", rfpFile);
    if (criteriaFile) fd.append("criteria_sheet", criteriaFile);
    const vendorNamesObj: Record<string, string> = {};
    vendors.forEach(v => {
      const vid = v.file.name.replace(/\.[^.]+$/, "");
      vendorNamesObj[vid] = v.name.trim();
      fd.append("vendor_files", v.file);
    });
    fd.append("vendor_names", JSON.stringify(vendorNamesObj));

    try {
      const res = await api.post<{ run_id: string }>("/api/v1/evaluate/start", {
        body: fd,
        on401: onAuth401,
      });
      onSuccess(res.run_id, rfpTitle.trim(), vendors.length);
    } catch (err) {
      setFormError(err instanceof Error ? err.message : "Failed to start evaluation. Try again.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="w-full" style={{ maxWidth: 620 }}>
      {/* Back + Reset row */}
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 20 }}>
        <button
          type="button"
          onClick={onBack}
          style={{
            background: "none", border: "none", cursor: "pointer",
            fontFamily: FONT, fontSize: 12, color: "var(--color-text-muted)",
            padding: 0,
            display: "flex", alignItems: "center", gap: 4,
            transition: "color 150ms ease-out",
          }}
          onMouseEnter={e => { e.currentTarget.style.color = "var(--color-text-primary)"; }}
          onMouseLeave={e => { e.currentTarget.style.color = "var(--color-text-muted)"; }}
        >
          ← Back
        </button>

        {/* Only show reset if there's something to clear */}
        {(rfpTitle || rfpFile || vendors.length > 0 || criteriaFile) && (
          <button
            type="button"
            onClick={resetForm}
            style={{
              background: "none", border: "none", cursor: "pointer",
              fontFamily: FONT, fontSize: 12, color: "var(--color-text-muted)",
              padding: "4px 0",
              display: "flex", alignItems: "center", gap: 4,
              transition: "color 150ms ease-out",
            }}
            onMouseEnter={e => { e.currentTarget.style.color = "var(--color-error)"; }}
            onMouseLeave={e => { e.currentTarget.style.color = "var(--color-text-muted)"; }}
          >
            ↺ Clear all
          </button>
        )}
      </div>

      <h1 style={{
        fontFamily: DISPLAY, fontWeight: 800,
        fontSize: isMobile ? 24 : 32,
        letterSpacing: "-0.03em", lineHeight: 1.0,
        color: "var(--color-text-primary)", marginBottom: 8,
      }}>
        New RFP evaluation
      </h1>
      <p style={{ fontFamily: FONT, fontSize: 14, color: "var(--color-text-muted)", lineHeight: 1.65, marginBottom: 32 }}>
        Upload your RFP and vendor proposals. Nine specialised agents will evaluate and rank each vendor.
      </p>

      <style>{`@keyframes meridian-spin { to { transform: rotate(360deg); } }`}</style>
      <form onSubmit={handleSubmit} noValidate>
        {/* Error banner */}
        {formError && (
          <div ref={errorRef} role="alert" style={{
            marginBottom: 20, padding: "10px 14px",
            backgroundColor: "var(--color-surface)",
            borderTop: "1px solid var(--color-error)",
            borderBottom: "1px solid var(--color-error)",
            borderLeft: "3px solid var(--color-error)",
            borderRight: "1px solid var(--color-error)",
            borderRadius: "var(--radius)",
            fontFamily: FONT, fontSize: 13, color: "var(--color-error)",
          }}>
            {formError}
          </div>
        )}

        {/* Title + Department */}
        <div style={{
          display: "grid",
          gridTemplateColumns: isMobile ? "1fr" : "1fr 1fr",
          gap: 16, marginBottom: 20,
        }}>
          <div>
            <label htmlFor="rfp-title" style={labelCss}>RFP Title *</label>
            <input
              id="rfp-title" type="text" value={rfpTitle}
              onChange={e => setRfpTitle(e.target.value)}
              placeholder="e.g. Cloud Infrastructure 2026"
              required suppressHydrationWarning style={inputCss}
              onFocus={e => { e.currentTarget.style.borderTopColor = "var(--color-accent)"; e.currentTarget.style.borderBottomColor = "var(--color-accent)"; e.currentTarget.style.borderLeftColor = "var(--color-accent)"; e.currentTarget.style.borderRightColor = "var(--color-accent)"; }}
              onBlur={e => { e.currentTarget.style.borderTopColor = "var(--color-border)"; e.currentTarget.style.borderBottomColor = "var(--color-border)"; e.currentTarget.style.borderLeftColor = "var(--color-border)"; e.currentTarget.style.borderRightColor = "var(--color-border)"; }}
            />
          </div>
          <div>
            <label htmlFor="department" style={labelCss}>Department *</label>
            <select
              id="department" value={department}
              onChange={e => setDepartment(e.target.value)}
              required style={{ ...inputCss, cursor: "pointer" }}
              onFocus={e => { e.currentTarget.style.borderTopColor = "var(--color-accent)"; e.currentTarget.style.borderBottomColor = "var(--color-accent)"; e.currentTarget.style.borderLeftColor = "var(--color-accent)"; e.currentTarget.style.borderRightColor = "var(--color-accent)"; }}
              onBlur={e => { e.currentTarget.style.borderTopColor = "var(--color-border)"; e.currentTarget.style.borderBottomColor = "var(--color-border)"; e.currentTarget.style.borderLeftColor = "var(--color-border)"; e.currentTarget.style.borderRightColor = "var(--color-border)"; }}
            >
              <option value="">Select…</option>
              {DEPARTMENTS.map(d => <option key={d} value={d}>{d}</option>)}
            </select>
          </div>
        </div>

        {/* Contract value + Currency */}
        <div style={{
          display: "grid",
          gridTemplateColumns: isMobile ? "1fr" : "1fr auto",
          gap: 12, marginBottom: 20, alignItems: "end",
        }}>
          <div>
            <label htmlFor="contract-value" style={labelCss}>Contract Value</label>
            <input
              id="contract-value" type="text" inputMode="numeric"
              value={contractValue}
              onChange={e => setContractValue(e.target.value.replace(/[^0-9,.]/g, ""))}
              placeholder="e.g. 2,400,000"
              suppressHydrationWarning style={inputCss}
              onFocus={e => { e.currentTarget.style.borderTopColor = "var(--color-accent)"; e.currentTarget.style.borderBottomColor = "var(--color-accent)"; e.currentTarget.style.borderLeftColor = "var(--color-accent)"; e.currentTarget.style.borderRightColor = "var(--color-accent)"; }}
              onBlur={e => { e.currentTarget.style.borderTopColor = "var(--color-border)"; e.currentTarget.style.borderBottomColor = "var(--color-border)"; e.currentTarget.style.borderLeftColor = "var(--color-border)"; e.currentTarget.style.borderRightColor = "var(--color-border)"; }}
            />
          </div>
          <div style={{ minWidth: 120 }}>
            <label htmlFor="currency" style={labelCss}>Currency</label>
            <select
              id="currency" value={currency}
              onChange={e => setCurrency(e.target.value)}
              style={{ ...inputCss, cursor: "pointer" }}
              onFocus={e => { e.currentTarget.style.borderTopColor = "var(--color-accent)"; e.currentTarget.style.borderBottomColor = "var(--color-accent)"; e.currentTarget.style.borderLeftColor = "var(--color-accent)"; e.currentTarget.style.borderRightColor = "var(--color-accent)"; }}
              onBlur={e => { e.currentTarget.style.borderTopColor = "var(--color-border)"; e.currentTarget.style.borderBottomColor = "var(--color-border)"; e.currentTarget.style.borderLeftColor = "var(--color-border)"; e.currentTarget.style.borderRightColor = "var(--color-border)"; }}
            >
              {["GBP","USD","EUR","AUD","CAD","SGD","AED","INR","JPY","CHF"].map(c => (
                <option key={c} value={c}>{c}</option>
              ))}
            </select>
          </div>
        </div>

        {/* RFP document */}
        <div style={{ marginBottom: 24 }}>
          <label style={labelCss}>RFP Document *</label>
          <FileDropZone
            file={rfpFile}
            onFile={setRfpFile}
            onClear={() => setRfpFile(null)}
            placeholder="Drop RFP PDF or DOCX here, or click to browse"
          />
        </div>

        {/* Criteria sheet — optional */}
        <div style={{ marginBottom: 24 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 8 }}>
            <label style={labelCss}>Your Criteria Sheet</label>
            <span style={{
              fontFamily: FONT, fontSize: 10, fontWeight: 500,
              letterSpacing: "0.06em", textTransform: "uppercase",
              color: "var(--color-text-muted)",
              padding: "1px 6px",
              borderTop: "1px solid var(--color-border)",
              borderBottom: "1px solid var(--color-border)",
              borderLeft: "1px solid var(--color-border)",
              borderRight: "1px solid var(--color-border)",
              borderRadius: 3,
            }}>optional</span>
          </div>
          <FileDropZone
            file={criteriaFile}
            onFile={setCriteriaFile}
            onClear={() => setCriteriaFile(null)}
            accept=".csv,.xlsx,.xls,.pdf,.docx"
            placeholder="Drop your scoring sheet — CSV, Excel, or PDF"
          />
          {criteriaFile && (
            <p style={{
              fontFamily: FONT, fontSize: 11, color: "var(--color-warning)",
              marginTop: 6,
            }}>
              Your criteria will be added as a 4th source — overrides RFP-extracted, not org/dept templates.
            </p>
          )}
        </div>

        {/* Vendor proposals */}
        <div style={{ marginBottom: 28 }}>
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 12 }}>
            <p style={labelCss}>Vendor Proposals *</p>
            {vendors.length > 0 && (
              <span style={{ fontFamily: FONT, fontSize: 11, color: "var(--color-text-muted)" }}>
                {vendors.length}/{MAX_VENDORS}
              </span>
            )}
          </div>

          {/* Multi-file drop zone */}
          <div style={{ marginBottom: vendors.length > 0 ? 12 : 0 }}>
            <MultiFileDropZone
              onFiles={addVendorsFromFiles}
              disabled={vendors.length >= MAX_VENDORS}
            />
          </div>

          {/* Vendor cards */}
          {vendors.length > 0 && (
            <div
              className="w-full"
              style={{ display: "flex", flexDirection: "column", gap: 10 }}
            >
              {vendors.map((vendor, idx) => (
                <VendorCard
                  key={vendor.id}
                  id={vendor.id}
                  index={idx}
                  name={vendor.name}
                  file={vendor.file}
                  canRemove={true}
                  onRemove={() => removeVendor(vendor.id)}
                  onNameChange={name => updateVendorName(vendor.id, name)}
                />
              ))}
            </div>
          )}
        </div>

        {/* Submit */}
        <button
          type="submit"
          disabled={submitting}
          style={{
            width: "100%", padding: "12px 24px",
            backgroundColor: submitting ? "var(--color-surface)" : "var(--color-accent)",
            color: submitting ? "var(--color-text-muted)" : "var(--color-accent-foreground)",
            borderTop: "1px solid var(--color-border)",
            borderBottom: "1px solid var(--color-border)",
            borderLeft: "1px solid var(--color-border)",
            borderRight: "1px solid var(--color-border)",
            borderRadius: "var(--radius)",
            fontFamily: FONT, fontWeight: 600, fontSize: 14,
            cursor: submitting ? "not-allowed" : "pointer",
            transition: "opacity 150ms ease-out",
            display: "flex", alignItems: "center", justifyContent: "center", gap: 8,
          }}
          onMouseEnter={e => { if (!submitting) e.currentTarget.style.opacity = "0.88"; }}
          onMouseLeave={e => { e.currentTarget.style.opacity = "1"; }}
        >
          {submitting && (
            <div style={{
              width: 14, height: 14,
              borderTop: "2px solid var(--color-text-muted)",
              borderBottom: "2px solid transparent",
              borderLeft: "2px solid transparent",
              borderRight: "2px solid transparent",
              borderRadius: "50%",
              animation: "meridian-spin 0.7s linear infinite",
            }} />
          )}
          {submitting ? "Starting evaluation…" : "Start evaluation →"}
        </button>
      </form>
    </div>
  );
}
