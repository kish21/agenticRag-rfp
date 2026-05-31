"""
Reusable reportlab wrapper for building synthetic benchmark PDFs.

Block-based API: a document is a list of blocks, each a small dataclass
(Heading, Para, Table, PageBreak, Filler). This keeps `build_scenarios` declarative
and lets one code path emit prose-heavy, table-heavy, long, and short documents.

reportlab is a dev/build-time dependency only — these PDFs are generated once and
committed, so nothing at runtime (or in CI) imports this module.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    PageBreak as _PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table as _Table,
    TableStyle,
)


@dataclass
class Heading:
    text: str
    level: int = 1


@dataclass
class Para:
    text: str


@dataclass
class Table:
    """A key/value or grid table. `rows` includes the header row if `header`."""
    rows: list[list[str]]
    header: bool = True


@dataclass
class PageBreak:
    pass


@dataclass
class Filler:
    """N paragraphs of innocuous boilerplate — used to bury facts in long docs."""
    paragraphs: int = 12
    seed_text: str = (
        "The vendor remains committed to a collaborative engagement model and "
        "continuous service improvement throughout the contract term, with regular "
        "governance reviews and transparent reporting to all stakeholders."
    )


Block = Heading | Para | Table | PageBreak | Filler


@dataclass
class Document:
    title: str
    blocks: list[Block] = field(default_factory=list)


def build_pdf(doc: Document, out_path: Path) -> None:
    """Render a Document to a PDF at out_path."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    styles = getSampleStyleSheet()
    story: list = []

    story.append(Paragraph(doc.title, styles["Title"]))
    story.append(Spacer(1, 6 * mm))

    for block in doc.blocks:
        if isinstance(block, Heading):
            style = styles["Heading1"] if block.level <= 1 else styles["Heading2"]
            story.append(Paragraph(block.text, style))
            story.append(Spacer(1, 2 * mm))
        elif isinstance(block, Para):
            story.append(Paragraph(block.text, styles["BodyText"]))
            story.append(Spacer(1, 2 * mm))
        elif isinstance(block, Table):
            t = _Table(block.rows, hAlign="LEFT")
            ts = [
                ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
            ]
            if block.header:
                ts += [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1A2540")),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ]
            t.setStyle(TableStyle(ts))
            story.append(t)
            story.append(Spacer(1, 4 * mm))
        elif isinstance(block, PageBreak):
            story.append(_PageBreak())
        elif isinstance(block, Filler):
            for i in range(block.paragraphs):
                story.append(Paragraph(f"{block.seed_text} (§{i + 1})", styles["BodyText"]))
                story.append(Spacer(1, 2 * mm))

    SimpleDocTemplate(
        str(out_path), pagesize=A4,
        title=doc.title, author="E3 Benchmark (synthetic)",
    ).build(story)
