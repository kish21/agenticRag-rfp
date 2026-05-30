"""
Phase 7 — customer-grade report rendering.

HTML-first (one template feeds the in-app view, the email body, and the PDF):

    run-row dict ──▶ build_report_context() ──▶ ReportContext
    ReportContext ──▶ build_report_html()  ──▶ HTML str   (in-app view / email body)
    HTML str      ──▶ render_pdf()          ──▶ PDF bytes  (download / email attachment)

`build_report_html()` uses jinja2 (pure-Python, always available) and is fully
unit-testable everywhere (golden snapshot). `render_pdf()` wraps weasyprint,
which needs native GTK libs — it is import-gated so importing this module never
fails, and the rest of the report path works without it. weasyprint runs in
production (Linux) and CI; on a Windows dev box, open the HTML in a browser
(Ctrl+P → Save as PDF) to preview.
"""
from __future__ import annotations

import functools
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from app.output.report_builder import build_report_context, ReportContext

_TEMPLATE_DIR = Path(__file__).parent
_TEMPLATE_NAME = "report_template.html"

PDF_MAGIC = b"%PDF"


@functools.lru_cache(maxsize=1)
def _env() -> Environment:
    return Environment(
        loader=FileSystemLoader(str(_TEMPLATE_DIR)),
        autoescape=select_autoescape(["html"]),   # escape vendor-supplied text
        trim_blocks=True,
        lstrip_blocks=True,
    )


def build_report_html(ctx: ReportContext) -> str:
    """Render the 12-section report to an HTML string. Pure-Python; no GTK."""
    return _env().get_template(_TEMPLATE_NAME).render(ctx=ctx)


def render_pdf(html: str) -> bytes:
    """Render an HTML string to PDF bytes via weasyprint.

    Raises a clear RuntimeError if weasyprint (and its native deps) is not
    importable — callers serving the HTML view never need to call this.
    """
    try:
        from weasyprint import HTML
    except (ImportError, OSError) as exc:  # OSError = missing native GTK libs
        raise RuntimeError(
            "PDF rendering needs weasyprint and its native libraries (cairo/pango). "
            "It is unavailable in this environment; the HTML report is still "
            "available. On Windows, preview by opening the HTML in a browser."
        ) from exc
    return HTML(string=html).write_pdf()


def build_report_html_for_run(run: dict, org_name: str = "Meridian Financial Services") -> str:
    """Convenience: run-row dict → HTML string (view / email body)."""
    return build_report_html(build_report_context(run, org_name=org_name))


def render_report_pdf_for_run(run: dict, org_name: str = "Meridian Financial Services") -> bytes:
    """Convenience: run-row dict → PDF bytes (download / email attachment)."""
    return render_pdf(build_report_html_for_run(run, org_name=org_name))
