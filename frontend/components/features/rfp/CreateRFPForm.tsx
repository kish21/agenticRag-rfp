"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { api, ApiError } from "@/lib/api";
import { DISPLAY, FONT, MONO } from "@/lib/theme";
import { useBreakpoint } from "@/lib/hooks";
import { SectionCard } from "./SectionCard";
import { AutonomyModePicker, type AutonomyMode } from "./AutonomyModePicker";
import { DeadlinePicker } from "./DeadlinePicker";
import { VendorInviteTable, type VendorRow } from "./VendorInviteTable";

// Mirrors backend platform.ingestion.safe_id_pattern. Keep in sync if backend changes.
const VENDOR_ID_PATTERN = /^[A-Za-z0-9._\-]{1,128}$/;
const DEFAULT_DEADLINE_DAYS = 14;

const DEPARTMENTS = ["IT", "Procurement", "Finance", "Legal", "Operations", "HR", "Marketing"];

interface CreateRFPResponse {
  rfp_id: string;
  submission_deadline: string;
  submission_status: string;
  autonomy_mode: AutonomyMode;
}

function defaultDeadline(): Date {
  const d = new Date();
  d.setDate(d.getDate() + DEFAULT_DEADLINE_DAYS);
  d.setHours(17, 0, 0, 0);
  return d;
}

function newRowKey() {
  return Math.random().toString(36).slice(2, 10);
}

export function CreateRFPForm() {
  const router = useRouter();
  const bp = useBreakpoint();
  const isMobile = bp === "mobile";

  const [title, setTitle] = useState("");
  const [department, setDepartment] = useState("IT");
  const [deadline, setDeadline] = useState<Date>(defaultDeadline);
  const [mode, setMode] = useState<AutonomyMode>("auto_to_evaluate");
  const [vendors, setVendors] = useState<VendorRow[]>([
    { rowKey: newRowKey(), vendor_id: "", vendor_name: "" },
  ]);

  const [submitting, setSubmitting] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const errorRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (formError) errorRef.current?.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }, [formError]);

  const validVendors = useMemo(
    () =>
      vendors.filter(
        (v) => v.vendor_id.trim() && VENDOR_ID_PATTERN.test(v.vendor_id.trim()),
      ),
    [vendors],
  );

  const hasDuplicates = useMemo(() => {
    const ids = validVendors.map((v) => v.vendor_id.trim());
    return new Set(ids).size !== ids.length;
  }, [validVendors]);

  const canSubmit =
    title.trim().length > 0 &&
    deadline > new Date() &&
    validVendors.length > 0 &&
    !hasDuplicates &&
    !submitting;

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setFormError(null);

    if (!title.trim()) {
      setFormError("RFP title is required.");
      return;
    }
    if (deadline <= new Date()) {
      setFormError("Deadline must be in the future.");
      return;
    }
    if (validVendors.length === 0) {
      setFormError("Add at least one vendor.");
      return;
    }
    if (hasDuplicates) {
      setFormError("Vendor ids must be unique.");
      return;
    }

    setSubmitting(true);
    try {
      const created = await api.post<CreateRFPResponse>("/api/v1/rfps", {
        body: {
          title: title.trim(),
          department,
          submission_deadline: deadline.toISOString(),
          autonomy_mode: mode,
        },
      });

      // Invite vendors sequentially — failures are reported but do not roll back the RFP.
      const failed: string[] = [];
      for (const v of validVendors) {
        try {
          await api.post(`/api/v1/rfps/${created.rfp_id}/vendors`, {
            body: {
              vendor_id: v.vendor_id.trim(),
              vendor_name: v.vendor_name.trim() || null,
            },
          });
        } catch (err) {
          failed.push(v.vendor_id.trim());
          // eslint-disable-next-line no-console
          console.error("Vendor invite failed", v.vendor_id, err);
        }
      }

      if (failed.length) {
        setFormError(
          `RFP created (${created.rfp_id}). ${failed.length} vendor invite${failed.length === 1 ? "" : "s"} failed: ${failed.join(", ")}. Retry from the RFP detail page.`,
        );
      }

      // Detail page is built in a later PR; for now, navigate to its planned route.
      router.push(`/procurement/rfps/${created.rfp_id}`);
    } catch (err) {
      const msg =
        err instanceof ApiError
          ? err.message
          : "Could not create RFP. Try again.";
      setFormError(msg);
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <form onSubmit={handleSubmit} noValidate>
      {/* Hero */}
      <div className="mb-8 md:mb-10">
        <div
          style={{
            fontFamily: MONO,
            fontSize: 11,
            fontWeight: 600,
            letterSpacing: "0.2em",
            textTransform: "uppercase",
            color: "var(--color-text-muted)",
            marginBottom: 12,
          }}
        >
          New evaluation
        </div>
        <h1
          style={{
            fontFamily: DISPLAY,
            fontSize: isMobile ? 28 : 36,
            fontWeight: 800,
            letterSpacing: "-0.03em",
            lineHeight: 1.05,
            color: "var(--color-text-primary)",
            margin: 0,
          }}
        >
          Create RFP
        </h1>
        <p
          className="mt-3"
          style={{
            fontFamily: FONT,
            fontSize: 15,
            fontWeight: 400,
            lineHeight: 1.55,
            color: "var(--color-text-secondary)",
            maxWidth: 520,
          }}
        >
          Define the rubric, set the deadline, invite the vendors.
        </p>
      </div>

      {formError && (
        <div
          ref={errorRef}
          role="alert"
          className="mb-6 px-4 py-3"
          style={{
            background: "color-mix(in oklab, var(--color-error) 8%, var(--color-surface))",
            borderTop: "1px solid color-mix(in oklab, var(--color-error) 40%, var(--color-border))",
            borderBottom: "1px solid color-mix(in oklab, var(--color-error) 40%, var(--color-border))",
            borderLeft: "3px solid var(--color-error)",
            borderRight: "1px solid color-mix(in oklab, var(--color-error) 40%, var(--color-border))",
            borderRadius: "var(--radius)",
            fontFamily: FONT,
            fontSize: 13,
            color: "var(--color-text-primary)",
          }}
        >
          {formError}
        </div>
      )}

      <div className="space-y-6 md:space-y-8">
        <SectionCard index="01" label="Identity">
          <div className="space-y-4">
            <FieldGroup>
              <Label htmlFor="rfp_title">RFP title *</Label>
              <input
                id="rfp_title"
                type="text"
                value={title}
                onChange={(e) => setTitle(e.target.value)}
                maxLength={512}
                placeholder="Managed IT services 2026"
                required
                style={inputStyle}
                onFocus={applyFocusRing}
                onBlur={clearFocusRing}
              />
            </FieldGroup>

            <FieldGroup>
              <Label htmlFor="department">Department</Label>
              <select
                id="department"
                value={department}
                onChange={(e) => setDepartment(e.target.value)}
                style={inputStyle}
                onFocus={applyFocusRing}
                onBlur={clearFocusRing}
              >
                {DEPARTMENTS.map((d) => (
                  <option key={d} value={d}>
                    {d}
                  </option>
                ))}
              </select>
            </FieldGroup>
          </div>
        </SectionCard>

        <SectionCard index="02" label="Deadline">
          <DeadlinePicker value={deadline} onChange={setDeadline} />
        </SectionCard>

        <SectionCard
          index="03"
          label="Autonomy mode"
          subtitle="How much of the evaluation should run on its own after the deadline?"
        >
          <AutonomyModePicker value={mode} onChange={setMode} />
        </SectionCard>

        <SectionCard
          index="04"
          label="Invited vendors"
          subtitle="Each vendor gets a drop folder. Files outside the list go to the attribution queue."
        >
          <VendorInviteTable
            rows={vendors}
            onChange={setVendors}
            vendorIdPattern={VENDOR_ID_PATTERN}
          />
        </SectionCard>
      </div>

      {/* CTA bar */}
      <div
        className="mt-8 md:mt-10 flex flex-col-reverse md:flex-row md:items-center md:justify-end gap-3"
      >
        <button
          type="button"
          onClick={() => router.back()}
          style={{
            minHeight: 44,
            padding: "10px 18px",
            background: "transparent",
            borderTop: "1px solid var(--color-border)",
            borderBottom: "1px solid var(--color-border)",
            borderLeft: "1px solid var(--color-border)",
            borderRight: "1px solid var(--color-border)",
            borderRadius: "var(--radius)",
            fontFamily: FONT,
            fontSize: 14,
            fontWeight: 600,
            color: "var(--color-text-secondary)",
            cursor: "pointer",
            outline: "none",
            transition: "opacity var(--transition), transform var(--transition)",
          }}
          onMouseEnter={(e) => {
            e.currentTarget.style.background = "var(--color-surface-hover)";
          }}
          onMouseLeave={(e) => {
            e.currentTarget.style.background = "transparent";
          }}
          onFocus={applyFocusRing}
          onBlur={clearFocusRing}
        >
          Cancel
        </button>
        <button
          type="submit"
          disabled={!canSubmit}
          style={{
            minHeight: 44,
            padding: "10px 22px",
            background: canSubmit ? "var(--color-accent)" : "var(--color-surface-hover)",
            color: canSubmit ? "var(--color-accent-foreground)" : "var(--color-text-muted)",
            borderTop: "1px solid var(--color-accent)",
            borderBottom: "1px solid var(--color-accent)",
            borderLeft: "1px solid var(--color-accent)",
            borderRight: "1px solid var(--color-accent)",
            borderRadius: "var(--radius)",
            fontFamily: FONT,
            fontSize: 14,
            fontWeight: 700,
            letterSpacing: "-0.005em",
            cursor: canSubmit ? "pointer" : "not-allowed",
            opacity: canSubmit ? 1 : 0.7,
            outline: "none",
            transition: "opacity var(--transition), transform var(--transition)",
          }}
          onMouseEnter={(e) => {
            if (canSubmit) {
              e.currentTarget.style.transform = "translateY(-1px)";
              e.currentTarget.style.background =
                "color-mix(in oklab, var(--color-accent) 88%, black)";
            }
          }}
          onMouseLeave={(e) => {
            e.currentTarget.style.transform = "translateY(0)";
            if (canSubmit) e.currentTarget.style.background = "var(--color-accent)";
          }}
          onFocus={applyFocusRing}
          onBlur={clearFocusRing}
        >
          {submitting
            ? "Creating…"
            : validVendors.length === 0
            ? "Create RFP"
            : `Create & invite ${validVendors.length} vendor${validVendors.length === 1 ? "" : "s"}`}
        </button>
      </div>
    </form>
  );
}

function FieldGroup({ children }: { children: React.ReactNode }) {
  return <div>{children}</div>;
}

function Label({ htmlFor, children }: { htmlFor: string; children: React.ReactNode }) {
  return (
    <label
      htmlFor={htmlFor}
      style={{
        display: "block",
        fontFamily: FONT,
        fontSize: 11,
        fontWeight: 600,
        letterSpacing: "0.08em",
        textTransform: "uppercase",
        color: "var(--color-text-muted)",
        marginBottom: 8,
      }}
    >
      {children}
    </label>
  );
}

/** Focus-ring helpers — applied via onFocus/onBlur to every input/button that
 *  strips outline. Matches the visible focus state on the autonomy picker. */
function applyFocusRing(e: React.FocusEvent<HTMLElement>) {
  e.currentTarget.style.boxShadow =
    "0 0 0 3px color-mix(in oklab, var(--color-accent) 30%, transparent)";
}
function clearFocusRing(e: React.FocusEvent<HTMLElement>) {
  e.currentTarget.style.boxShadow = "none";
}

const inputStyle: React.CSSProperties = {
  width: "100%",
  boxSizing: "border-box",
  padding: "10px 12px",
  minHeight: 44,
  background: "var(--color-background)",
  borderTop: "1px solid var(--color-border)",
  borderBottom: "1px solid var(--color-border)",
  borderLeft: "1px solid var(--color-border)",
  borderRight: "1px solid var(--color-border)",
  borderRadius: "var(--radius)",
  fontFamily: FONT,
  fontSize: 14,
  color: "var(--color-text-primary)",
  outline: "none",
};
