"""
PDF Report Generator — produces a formal procurement evaluation report.

Sections:
1. Cover page — org name, RFP title, date
2. Executive summary
3. Methodology note
4. Rejection notices — with failed checks, evidence citations, clause references
5. Ranked shortlist — per-criterion breakdown with scores
6. Limitations — ungrounded claims removed, critic flags
"""
from io import BytesIO
from datetime import datetime

from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.lib import colors
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    HRFlowable, PageBreak,
)
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT

# ── Colour palette ────────────────────────────────────────
_NAVY  = colors.HexColor("#1a2744")
_BLUE  = colors.HexColor("#2563eb")
_RED   = colors.HexColor("#dc2626")
_GREEN = colors.HexColor("#16a34a")
_AMBER = colors.HexColor("#d97706")
_LIGHT = colors.HexColor("#f1f5f9")
_GREY  = colors.HexColor("#64748b")

_PAGE_W, _PAGE_H = A4
_MARGIN = 2.0 * cm


def _styles():
    base = getSampleStyleSheet()
    return {
        "cover_title": ParagraphStyle(
            "cover_title", parent=base["Title"],
            fontSize=28, textColor=_NAVY, spaceAfter=12, alignment=TA_CENTER,
        ),
        "cover_sub": ParagraphStyle(
            "cover_sub", parent=base["Normal"],
            fontSize=14, textColor=_GREY, spaceAfter=6, alignment=TA_CENTER,
        ),
        "h1": ParagraphStyle(
            "h1", parent=base["Heading1"],
            fontSize=16, textColor=_NAVY, spaceBefore=18, spaceAfter=8,
            borderPad=4,
        ),
        "h2": ParagraphStyle(
            "h2", parent=base["Heading2"],
            fontSize=13, textColor=_BLUE, spaceBefore=12, spaceAfter=6,
        ),
        "body": ParagraphStyle(
            "body", parent=base["Normal"],
            fontSize=10, leading=15, spaceAfter=6,
        ),
        "small": ParagraphStyle(
            "small", parent=base["Normal"],
            fontSize=8, textColor=_GREY, leading=12, spaceAfter=4,
        ),
        "evidence": ParagraphStyle(
            "evidence", parent=base["Normal"],
            fontSize=9, textColor=colors.HexColor("#374151"),
            backColor=_LIGHT, leftIndent=12, rightIndent=12,
            spaceBefore=4, spaceAfter=4, leading=14,
            borderPad=6,
        ),
        "reject_header": ParagraphStyle(
            "reject_header", parent=base["Normal"],
            fontSize=12, textColor=_RED, fontName="Helvetica-Bold",
            spaceBefore=10, spaceAfter=4,
        ),
        "pass_header": ParagraphStyle(
            "pass_header", parent=base["Normal"],
            fontSize=12, textColor=_GREEN, fontName="Helvetica-Bold",
            spaceBefore=10, spaceAfter=4,
        ),
    }


def _hr():
    return HRFlowable(width="100%", thickness=0.5, color=_LIGHT, spaceAfter=8)


def _score_color(score: float) -> colors.Color:
    if score >= 7:
        return _GREEN
    if score >= 5:
        return _AMBER
    return _RED


def generate_evaluation_report(
    result: dict,
    org_name: str = "Organisation",
    rfp_title: str = "RFP Evaluation",
) -> bytes:
    """
    result dict keys:
      evaluated_vendors  int
      rejected_count     int
      ranked_count       int
      rejected_vendors   list[dict]  — vendor_id, rejection_reason, failed_checks, evidence_citations?
      ranked_vendors     list[dict]  — rank, vendor_id, total_score, criteria list[dict]
      executive_summary  str  (optional)
      methodology_note   str  (optional)
      limitations        list[str]  (optional)
      critic_flags       list[dict]  (optional)

    Returns raw PDF bytes.
    """
    buf = BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=_MARGIN,
        rightMargin=_MARGIN,
        topMargin=_MARGIN,
        bottomMargin=_MARGIN,
        title=f"{rfp_title} — Evaluation Report",
        author=org_name,
    )

    st = _styles()
    story = []

    # ── Cover ──────────────────────────────────────────────
    story.append(Spacer(1, 3 * cm))
    story.append(Paragraph(rfp_title, st["cover_title"]))
    story.append(Paragraph("Procurement Evaluation Report", st["cover_sub"]))
    story.append(Paragraph(org_name, st["cover_sub"]))
    story.append(Paragraph(
        datetime.utcnow().strftime("%d %B %Y"), st["cover_sub"]
    ))
    story.append(Spacer(1, 1 * cm))

    summary_data = [
        ["Vendors evaluated", str(result.get("evaluated_vendors", 0))],
        ["Rejected",          str(result.get("rejected_count", 0))],
        ["Shortlisted",       str(result.get("ranked_count", 0))],
    ]
    summary_table = Table(summary_data, colWidths=[8 * cm, 4 * cm])
    summary_table.setStyle(TableStyle([
        ("BACKGROUND",  (0, 0), (-1, -1), _LIGHT),
        ("FONTNAME",    (0, 0), (-1, -1), "Helvetica"),
        ("FONTSIZE",    (0, 0), (-1, -1), 11),
        ("ALIGN",       (1, 0), (1, -1), "CENTER"),
        ("ROWBACKGROUNDS", (0, 0), (-1, -1), [colors.white, _LIGHT]),
        ("GRID",        (0, 0), (-1, -1), 0.25, _GREY),
        ("TOPPADDING",  (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    story.append(summary_table)
    story.append(PageBreak())

    # ── Executive summary ──────────────────────────────────
    story.append(Paragraph("1. Executive Summary", st["h1"]))
    story.append(_hr())
    exec_summary = result.get(
        "executive_summary",
        f"This report presents the evaluation of "
        f"{result.get('evaluated_vendors', 0)} vendor response(s) against the "
        f"requirements of {rfp_title}. "
        f"{result.get('rejected_count', 0)} vendor(s) were rejected for failing "
        f"mandatory requirements. "
        f"{result.get('ranked_count', 0)} vendor(s) were shortlisted and scored."
    )
    story.append(Paragraph(exec_summary, st["body"]))

    # ── Methodology ────────────────────────────────────────
    story.append(Spacer(1, 0.5 * cm))
    story.append(Paragraph("2. Methodology", st["h1"]))
    story.append(_hr())
    methodology = result.get(
        "methodology_note",
        "This evaluation was conducted by an automated agentic AI pipeline. "
        "Every factual claim is grounded to a verbatim quote from the vendor submission. "
        "Mandatory compliance checks were evaluated against extracted structured facts. "
        "Scoring was performed against weighted criteria defined in the evaluation setup. "
        "Human review is recommended before final procurement decisions."
    )
    story.append(Paragraph(methodology, st["body"]))

    # ── Rejection notices ──────────────────────────────────
    rejected = result.get("rejected_vendors", [])
    if rejected:
        story.append(PageBreak())
        story.append(Paragraph("3. Rejection Notices", st["h1"]))
        story.append(_hr())
        story.append(Paragraph(
            f"{len(rejected)} vendor(s) failed mandatory compliance requirements "
            f"and have been excluded from scoring.",
            st["body"]
        ))

        for rej in rejected:
            vid = rej.get("vendor_id", "Unknown")
            story.append(Spacer(1, 0.3 * cm))
            story.append(Paragraph(f"REJECTED: {vid}", st["reject_header"]))

            reason = rej.get("rejection_reason", "")
            if reason:
                story.append(Paragraph(reason, st["body"]))

            failed_checks = rej.get("failed_checks", [])
            if failed_checks:
                story.append(Paragraph("Failed mandatory checks:", st["body"]))
                for check in failed_checks:
                    if isinstance(check, dict):
                        check_id   = check.get("check_id", "")
                        check_name = check.get("check_name", check_id)
                        reason_str = check.get("reason", "")
                        evidence   = check.get("evidence_quote", "")
                        story.append(Paragraph(
                            f"<b>{check_id}</b> — {check_name}: {reason_str}",
                            st["body"]
                        ))
                        if evidence:
                            story.append(Paragraph(
                                f'&ldquo;{evidence}&rdquo;', st["evidence"]
                            ))
                    else:
                        story.append(Paragraph(f"- {check}", st["body"]))

            evidence_citations = rej.get("evidence_citations", [])
            if evidence_citations:
                story.append(Paragraph("Evidence citations:", st["body"]))
                for cite in evidence_citations:
                    story.append(Paragraph(f'&ldquo;{cite}&rdquo;', st["evidence"]))

            clause_refs = rej.get("clause_references", [])
            if clause_refs:
                story.append(Paragraph(
                    f"Clause references: {', '.join(clause_refs)}", st["small"]
                ))

    # ── Ranked shortlist ───────────────────────────────────
    ranked = result.get("ranked_vendors", [])
    section_num = 4 if rejected else 3
    if ranked:
        story.append(PageBreak())
        story.append(Paragraph(f"{section_num}. Shortlisted Vendors", st["h1"]))
        story.append(_hr())
        story.append(Paragraph(
            f"{len(ranked)} vendor(s) passed all mandatory requirements and were scored.",
            st["body"]
        ))

        for vendor in ranked:
            rank       = vendor.get("rank", "?")
            vid        = vendor.get("vendor_id", "Unknown")
            score      = vendor.get("total_score", 0.0)
            rec        = vendor.get("recommendation", "")
            criteria   = vendor.get("criteria", [])

            story.append(Spacer(1, 0.3 * cm))
            story.append(Paragraph(
                f"#{rank} — {vid}  |  Score: {score:.1f}/10"
                + (f"  |  {rec.replace('_', ' ').title()}" if rec else ""),
                st["pass_header"]
            ))

            if criteria:
                crit_data = [["Criterion", "Score", "Evidence"]]
                for c in criteria:
                    c_name     = c.get("criterion_name", c.get("criterion_id", ""))
                    c_score    = c.get("raw_score", c.get("score", 0))
                    c_evidence = c.get("evidence_summary", c.get("score_rationale", ""))[:80]
                    crit_data.append([c_name, str(c_score), c_evidence])

                crit_table = Table(
                    crit_data,
                    colWidths=[5 * cm, 2 * cm, 9.5 * cm]
                )
                crit_table.setStyle(TableStyle([
                    ("BACKGROUND",    (0, 0), (-1, 0), _NAVY),
                    ("TEXTCOLOR",     (0, 0), (-1, 0), colors.white),
                    ("FONTNAME",      (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("FONTSIZE",      (0, 0), (-1, -1), 9),
                    ("ROWBACKGROUNDS",(0, 1), (-1, -1), [colors.white, _LIGHT]),
                    ("GRID",          (0, 0), (-1, -1), 0.25, _GREY),
                    ("ALIGN",         (1, 0), (1, -1), "CENTER"),
                    ("TOPPADDING",    (0, 0), (-1, -1), 5),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                    ("VALIGN",        (0, 0), (-1, -1), "TOP"),
                ]))
                story.append(crit_table)

            narrative = vendor.get("narrative", "")
            if narrative:
                story.append(Paragraph(narrative, st["body"]))

        section_num += 1

    # ── Limitations ────────────────────────────────────────
    limitations = result.get("limitations", [])
    critic_flags = result.get("critic_flags", [])
    if limitations or critic_flags:
        story.append(PageBreak())
        story.append(Paragraph(f"{section_num}. Limitations and Flags", st["h1"]))
        story.append(_hr())
        story.append(Paragraph(
            "The following limitations were identified during evaluation.", st["body"]
        ))
        for lim in limitations:
            story.append(Paragraph(f"- {lim}", st["body"]))
        for flag in critic_flags:
            severity = flag.get("severity", "")
            check    = flag.get("check_name", "")
            desc     = flag.get("description", "")
            color_map = {"hard": _RED, "soft": _AMBER, "log": _GREY}
            flag_color = color_map.get(severity.lower(), _GREY)
            story.append(Paragraph(
                f'<font color="#{flag_color.hexval()[1:]}">'
                f'[{severity.upper()}] {check}</font> — {desc}',
                st["body"]
            ))

    # ── Footer note ────────────────────────────────────────
    story.append(Spacer(1, 1 * cm))
    story.append(_hr())
    story.append(Paragraph(
        "This report was generated by the Enterprise Agentic AI Platform. "
        "All factual claims are grounded to verbatim source text. "
        "This document is confidential and intended for procurement use only.",
        st["small"]
    ))

    doc.build(story)
    return buf.getvalue()
