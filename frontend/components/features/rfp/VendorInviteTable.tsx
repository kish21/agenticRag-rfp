"use client";

import { useMemo, useRef, useState } from "react";
import { FONT, MONO } from "@/lib/theme";

export interface VendorRow {
  rowKey: string;        // local UI key only
  vendor_id: string;
  vendor_name: string;
}

interface VendorInviteTableProps {
  rows: VendorRow[];
  onChange: (rows: VendorRow[]) => void;
  /** Regex from backend (settings.platform.ingestion.safe_id_pattern). */
  vendorIdPattern: RegExp;
}

function newKey() {
  return Math.random().toString(36).slice(2, 10);
}

export function VendorInviteTable({ rows, onChange, vendorIdPattern }: VendorInviteTableProps) {
  const [pasteOpen, setPasteOpen] = useState(false);
  const [pasteText, setPasteText] = useState("");
  const addRef = useRef<HTMLInputElement>(null);

  const validity = useMemo(() => {
    const seen = new Set<string>();
    return rows.map((r) => {
      const id = r.vendor_id.trim();
      if (!id) return { ok: true, reason: "" }; // empty = not yet entered
      if (!vendorIdPattern.test(id))
        return { ok: false, reason: "Invalid characters or too long" };
      if (seen.has(id)) return { ok: false, reason: "Duplicate vendor id" };
      seen.add(id);
      return { ok: true, reason: "" };
    });
  }, [rows, vendorIdPattern]);

  function update(rowKey: string, patch: Partial<VendorRow>) {
    onChange(rows.map((r) => (r.rowKey === rowKey ? { ...r, ...patch } : r)));
  }

  function remove(rowKey: string) {
    onChange(rows.filter((r) => r.rowKey !== rowKey));
  }

  function addEmpty() {
    onChange([...rows, { rowKey: newKey(), vendor_id: "", vendor_name: "" }]);
    setTimeout(() => addRef.current?.focus(), 0);
  }

  function importPaste() {
    const parsed: VendorRow[] = [];
    pasteText
      .split(/[\n,]+/)
      .map((s) => s.trim())
      .filter(Boolean)
      .forEach((token) => {
        const [id, ...nameParts] = token.split(":");
        const vid = id.trim();
        const name = nameParts.join(":").trim();
        if (vid) parsed.push({ rowKey: newKey(), vendor_id: vid, vendor_name: name });
      });
    if (parsed.length) onChange([...rows.filter((r) => r.vendor_id.trim()), ...parsed]);
    setPasteText("");
    setPasteOpen(false);
  }

  return (
    <div>
      <div role="table" aria-label="Invited vendors">
        <div
          role="row"
          className="hidden md:grid"
          style={{
            gridTemplateColumns: "minmax(160px, 1fr) minmax(180px, 1.4fr) 40px",
            gap: 12,
            paddingBottom: 8,
            borderBottom: "1px solid var(--color-border)",
          }}
        >
          <ColLabel>vendor_id</ColLabel>
          <ColLabel>vendor name (optional)</ColLabel>
          <span />
        </div>

        {rows.map((row, i) => {
          const v = validity[i];
          return (
            <div
              key={row.rowKey}
              role="row"
              className="grid"
              style={{
                gridTemplateColumns: "1fr",
                gap: 8,
                padding: "12px 0",
                borderBottom: "1px solid var(--color-border)",
              }}
            >
              <div
                className="grid"
                style={{
                  gridTemplateColumns: "1fr",
                  gap: 8,
                }}
              >
                <ResponsiveRow
                  vendorId={row.vendor_id}
                  vendorName={row.vendor_name}
                  ok={v.ok}
                  onIdChange={(s) => update(row.rowKey, { vendor_id: s })}
                  onNameChange={(s) => update(row.rowKey, { vendor_name: s })}
                  onRemove={() => remove(row.rowKey)}
                />
                {!v.ok && (
                  <span
                    role="alert"
                    style={{
                      fontFamily: FONT,
                      fontSize: 12,
                      color: "var(--color-error)",
                      paddingLeft: 2,
                    }}
                  >
                    {v.reason}
                  </span>
                )}
              </div>
            </div>
          );
        })}

        {rows.length === 0 && (
          <div
            className="py-6 text-center"
            style={{
              fontFamily: FONT,
              fontSize: 13,
              color: "var(--color-text-muted)",
            }}
          >
            No vendors yet — add at least one to continue.
          </div>
        )}
      </div>

      <div className="mt-3 flex flex-wrap items-center gap-3">
        <button
          type="button"
          onClick={addEmpty}
          className="flex items-center gap-1.5"
          style={{
            background: "transparent",
            borderTop: "1px solid var(--color-border)",
            borderBottom: "1px solid var(--color-border)",
            borderLeft: "1px solid var(--color-border)",
            borderRight: "1px solid var(--color-border)",
            borderRadius: "var(--radius)",
            padding: "8px 14px",
            minHeight: 44,
            fontFamily: FONT,
            fontSize: 13,
            fontWeight: 600,
            color: "var(--color-text-primary)",
            cursor: "pointer",
            transition: "opacity var(--transition)",
          }}
          onMouseEnter={(e) => { e.currentTarget.style.background = "var(--color-surface-hover)"; }}
          onMouseLeave={(e) => { e.currentTarget.style.background = "transparent"; }}
        >
          <span style={{ fontFamily: MONO, fontSize: 14, lineHeight: 1 }}>+</span>
          Add vendor
        </button>

        <button
          type="button"
          onClick={() => setPasteOpen((o) => !o)}
          style={{
            background: "transparent",
            border: "none",
            padding: "4px 2px",
            fontFamily: FONT,
            fontSize: 12,
            fontWeight: 500,
            color: "var(--color-text-secondary)",
            cursor: "pointer",
            textDecoration: "underline",
            textDecorationColor: "var(--color-border-strong)",
            textUnderlineOffset: 4,
            outline: "none",
            transition: "opacity var(--transition)",
          }}
          onMouseEnter={(e) => {
            e.currentTarget.style.color = "var(--color-text-primary)";
            e.currentTarget.style.textDecorationColor = "var(--color-accent)";
          }}
          onMouseLeave={(e) => {
            e.currentTarget.style.color = "var(--color-text-secondary)";
            e.currentTarget.style.textDecorationColor = "var(--color-border-strong)";
          }}
          onFocus={(e) => {
            e.currentTarget.style.boxShadow =
              "0 0 0 3px color-mix(in oklab, var(--color-accent) 30%, transparent)";
          }}
          onBlur={(e) => {
            e.currentTarget.style.boxShadow = "none";
          }}
        >
          paste vendor list {pasteOpen ? "˄" : "˅"}
        </button>
      </div>

      {pasteOpen && (
        <div className="mt-3">
          <textarea
            value={pasteText}
            onChange={(e) => setPasteText(e.target.value)}
            placeholder={"acme:Acme Corp\napex:Apex Ltd\nbravo"}
            rows={4}
            style={{
              width: "100%",
              boxSizing: "border-box",
              padding: 12,
              fontFamily: MONO,
              fontSize: 13,
              background: "var(--color-background)",
              borderTop: "1px solid var(--color-border)",
              borderBottom: "1px solid var(--color-border)",
              borderLeft: "1px solid var(--color-border)",
              borderRight: "1px solid var(--color-border)",
              borderRadius: "var(--radius)",
              color: "var(--color-text-primary)",
              resize: "vertical",
              outline: "none",
            }}
            onFocus={(e) => {
              e.currentTarget.style.boxShadow =
                "0 0 0 3px color-mix(in oklab, var(--color-accent) 30%, transparent)";
            }}
            onBlur={(e) => {
              e.currentTarget.style.boxShadow = "none";
            }}
          />
          <div className="mt-2 flex justify-end gap-2">
            <button
              type="button"
              onClick={() => {
                setPasteOpen(false);
                setPasteText("");
              }}
              style={{
                background: "transparent",
                border: "none",
                padding: "8px 12px",
                minHeight: 36,
                borderRadius: "var(--radius)",
                fontFamily: FONT,
                fontSize: 13,
                color: "var(--color-text-muted)",
                cursor: "pointer",
                outline: "none",
                transition: "opacity var(--transition)",
              }}
              onMouseEnter={(e) => {
                e.currentTarget.style.color = "var(--color-text-primary)";
              }}
              onMouseLeave={(e) => {
                e.currentTarget.style.color = "var(--color-text-muted)";
              }}
              onFocus={(e) => {
                e.currentTarget.style.boxShadow =
                  "0 0 0 3px color-mix(in oklab, var(--color-accent) 30%, transparent)";
              }}
              onBlur={(e) => {
                e.currentTarget.style.boxShadow = "none";
              }}
            >
              Cancel
            </button>
            <button
              type="button"
              onClick={importPaste}
              disabled={!pasteText.trim()}
              style={{
                background: "var(--color-accent)",
                color: "var(--color-accent-foreground)",
                borderTop: "1px solid var(--color-accent)",
                borderBottom: "1px solid var(--color-accent)",
                borderLeft: "1px solid var(--color-accent)",
                borderRight: "1px solid var(--color-accent)",
                borderRadius: "var(--radius)",
                padding: "8px 14px",
                fontFamily: FONT,
                fontSize: 13,
                fontWeight: 600,
                cursor: pasteText.trim() ? "pointer" : "not-allowed",
                opacity: pasteText.trim() ? 1 : 0.6,
                outline: "none",
                transition: "opacity var(--transition), transform var(--transition)",
              }}
              onMouseEnter={(e) => {
                if (pasteText.trim()) {
                  e.currentTarget.style.transform = "translateY(-1px)";
                  e.currentTarget.style.background =
                    "color-mix(in oklab, var(--color-accent) 88%, black)";
                }
              }}
              onMouseLeave={(e) => {
                e.currentTarget.style.transform = "translateY(0)";
                e.currentTarget.style.background = "var(--color-accent)";
              }}
              onFocus={(e) => {
                e.currentTarget.style.boxShadow =
                  "0 0 0 3px color-mix(in oklab, var(--color-accent) 30%, transparent)";
              }}
              onBlur={(e) => {
                e.currentTarget.style.boxShadow = "none";
              }}
            >
              Import
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

function ColLabel({ children }: { children: React.ReactNode }) {
  return (
    <span
      style={{
        fontFamily: MONO,
        fontSize: 10,
        fontWeight: 600,
        letterSpacing: "0.14em",
        textTransform: "uppercase",
        color: "var(--color-text-muted)",
      }}
    >
      {children}
    </span>
  );
}

function ResponsiveRow({
  vendorId,
  vendorName,
  ok,
  onIdChange,
  onNameChange,
  onRemove,
}: {
  vendorId: string;
  vendorName: string;
  ok: boolean;
  onIdChange: (s: string) => void;
  onNameChange: (s: string) => void;
  onRemove: () => void;
}) {
  const idStyle: React.CSSProperties = {
    width: "100%",
    boxSizing: "border-box",
    padding: "10px 12px",
    minHeight: 44,
    background: "var(--color-background)",
    borderTop: "1px solid var(--color-border)",
    borderBottom: ok
      ? "1px solid var(--color-border)"
      : "2px solid var(--color-error)",
    borderLeft: "1px solid var(--color-border)",
    borderRight: "1px solid var(--color-border)",
    borderRadius: "var(--radius)",
    fontFamily: MONO,
    fontSize: 13,
    color: "var(--color-text-primary)",
    outline: "none",
  };
  const nameStyle: React.CSSProperties = {
    ...idStyle,
    fontFamily: FONT,
    fontWeight: 500,
    borderBottom: "1px solid var(--color-border)",
  };

  return (
    <div
      className="grid items-center gap-2 md:gap-3"
      style={{
        gridTemplateColumns: "minmax(0, 1fr)",
      }}
    >
      <div
        className="grid items-center gap-2 md:gap-3"
        style={{
          gridTemplateColumns: "minmax(0, 1fr) minmax(0, 1.4fr) 40px",
        }}
      >
        <input
          type="text"
          aria-label="Vendor id"
          placeholder="acme"
          value={vendorId}
          onChange={(e) => onIdChange(e.target.value)}
          style={idStyle}
          onFocus={(e) => {
            e.currentTarget.style.boxShadow =
              "0 0 0 3px color-mix(in oklab, var(--color-accent) 30%, transparent)";
          }}
          onBlur={(e) => {
            e.currentTarget.style.boxShadow = "none";
          }}
        />
        <input
          type="text"
          aria-label="Vendor name"
          placeholder="optional display name"
          value={vendorName}
          onChange={(e) => onNameChange(e.target.value)}
          style={nameStyle}
          onFocus={(e) => {
            e.currentTarget.style.boxShadow =
              "0 0 0 3px color-mix(in oklab, var(--color-accent) 30%, transparent)";
          }}
          onBlur={(e) => {
            e.currentTarget.style.boxShadow = "none";
          }}
        />
        <button
          type="button"
          onClick={onRemove}
          aria-label="Remove vendor"
          style={{
            width: 40,
            height: 40,
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            background: "transparent",
            border: "none",
            color: "var(--color-text-muted)",
            cursor: "pointer",
            borderRadius: "var(--radius)",
            transition: "opacity var(--transition)",
            opacity: 0.5,
          }}
          onMouseEnter={(e) => {
            e.currentTarget.style.opacity = "1";
            e.currentTarget.style.color = "var(--color-error)";
          }}
          onMouseLeave={(e) => {
            e.currentTarget.style.opacity = "0.5";
            e.currentTarget.style.color = "var(--color-text-muted)";
          }}
        >
          ✕
        </button>
      </div>
    </div>
  );
}
