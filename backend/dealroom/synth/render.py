"""Render the synthetic data room from ``spec.py``.

Outputs are deterministic: fixed PDF metadata, a seeded random generator for the
scan noise, and fixed workbook properties, so ``git diff`` stays empty when the
generator runs twice.
"""

from __future__ import annotations

import datetime as dt
import json
import random
from pathlib import Path

from openpyxl import Workbook
from PIL import Image, ImageDraw, ImageFilter, ImageFont
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from dealroom.synth.spec import DOCS, H, P, PdfDoc, ScanDoc, T, XlsxDoc

FIXED_DATE = dt.datetime(2025, 11, 3, 9, 0, 0)
FONT_CANDIDATES = {
    "typed": ("/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf", "DejaVuSerif.ttf"),
    "handwritten": ("/usr/share/fonts/truetype/dejavu/DejaVuSans-Oblique.ttf", "DejaVuSans-Oblique.ttf"),
}


def _font(style: str, size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for candidate in FONT_CANDIDATES[style]:
        try:
            return ImageFont.truetype(candidate, size)
        except OSError:
            continue
    return ImageFont.load_default(size=size)  # pragma: no cover - only without DejaVu fonts


def render_pdf(doc: PdfDoc, out: Path) -> None:
    styles = getSampleStyleSheet()
    story: list[object] = []
    for index, page in enumerate(doc.pages):
        if index:
            story.append(PageBreak())
        for block in page:
            if isinstance(block, H):
                story.append(Paragraph(block.text, styles["Heading2"]))
            elif isinstance(block, P):
                story.append(Paragraph(block.text.replace("&", "&amp;"), styles["BodyText"]))
                story.append(Spacer(1, 2 * mm))
            elif isinstance(block, T):
                story.append(Paragraph(block.caption, styles["Italic"]))
                table = Table([list(block.header), *[list(r) for r in block.rows]], hAlign="LEFT")
                table.setStyle(
                    TableStyle(
                        [
                            ("GRID", (0, 0), (-1, -1), 0.4, colors.grey),
                            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#E8E2D4")),
                            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                            ("ALIGN", (1, 1), (-1, -1), "RIGHT"),
                        ]
                    )
                )
                story.append(table)
                story.append(Spacer(1, 3 * mm))
    template = SimpleDocTemplate(
        str(out),
        pagesize=A4,
        title=doc.title,
        author="Synthetic data room",
        creator="dealroom-copilot",
        invariant=1,
    )
    template.build(story)


def render_scan(doc: ScanDoc, out: Path, seed: int) -> None:
    rng = random.Random(seed)
    width, height = 1654, 2339  # A4 at 200 dpi
    image = Image.new("L", (width, height), 250)
    draw = ImageDraw.Draw(image)
    size = 46 if doc.style == "handwritten" else 40
    font = _font(doc.style, size)
    y = 220
    for line in doc.lines:
        x = 170 + rng.randint(-8, 8)
        if doc.style == "handwritten":
            for word in line.split(" "):
                draw.text((x, y + rng.randint(-5, 5)), word, fill=rng.randint(20, 60), font=font)
                x += int(draw.textlength(word + " ", font=font)) + rng.randint(0, 6)
        else:
            draw.text((x, y), line, fill=25, font=font)
        y += int(size * 2.1)
    if doc.style == "typed":
        draw.line((170, y + 80, 700, y + 80), fill=60, width=3)  # signature line
        draw.line((900, y + 80, 1430, y + 80), fill=60, width=3)
    for _ in range(2500):  # scanner dust
        draw.point((rng.randrange(width), rng.randrange(height)), fill=rng.randint(120, 200))
    image = image.rotate(rng.uniform(-0.8, 0.8), resample=Image.Resampling.BICUBIC, fillcolor=250)
    image = image.filter(ImageFilter.GaussianBlur(0.6))
    image.save(
        out,
        "PDF",
        resolution=200.0,
        title=doc.title,
        creationDate=FIXED_DATE.timetuple(),
        modDate=FIXED_DATE.timetuple(),
    )


def render_xlsx(doc: XlsxDoc, out: Path) -> None:
    workbook = Workbook()
    default = workbook.active
    if default is not None:
        workbook.remove(default)
    for sheet_spec in doc.sheets:
        sheet = workbook.create_sheet(sheet_spec.name)
        for row in sheet_spec.rows:
            sheet.append(list(row))
        sheet.column_dimensions["A"].width = 42
    workbook.properties.creator = "Synthetic data room"
    workbook.properties.title = doc.title
    workbook.properties.created = FIXED_DATE
    workbook.properties.modified = FIXED_DATE
    workbook.save(out)
    _fix_zip_timestamps(out)


def _fix_zip_timestamps(path: Path) -> None:
    """An .xlsx is a zip; pin entry timestamps and the save time openpyxl writes, so the file is reproducible."""
    import re
    import zipfile

    stamp = FIXED_DATE.strftime("%Y-%m-%dT%H:%M:%SZ").encode()
    with zipfile.ZipFile(path) as source:
        entries = [(info.filename, source.read(info.filename)) for info in source.infolist()]
    entries = [
        (
            name,
            re.sub(rb"(<dcterms:modified[^>]*>)[^<]+", rb"\g<1>" + stamp, data)
            if name == "docProps/core.xml"
            else data,
        )
        for name, data in entries
    ]
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as target:
        for name, data in entries:
            info = zipfile.ZipInfo(name, date_time=FIXED_DATE.timetuple()[:6])
            info.compress_type = zipfile.ZIP_DEFLATED
            target.writestr(info, data)


def page_texts(doc: PdfDoc) -> list[str]:
    texts: list[str] = []
    for page in doc.pages:
        parts: list[str] = []
        for block in page:
            if isinstance(block, (H, P)):
                parts.append(block.text)
            else:
                parts.append(block.caption)
                parts.append(" | ".join(block.header))
                parts.extend(" | ".join(r) for r in block.rows)
        texts.append("\n".join(parts))
    return texts


def build(out_dir: Path) -> dict[str, object]:
    """Render every document into ``out_dir/files`` and write ``ground_truth.json``."""
    files_dir = out_dir / "files"
    files_dir.mkdir(parents=True, exist_ok=True)
    truth: dict[str, object] = {}
    for seed, doc in enumerate(DOCS):
        target = files_dir / doc.filename
        if isinstance(doc, PdfDoc):
            render_pdf(doc, target)
            truth[doc.filename] = {"kind": "pdf", "title": doc.title, "pages": page_texts(doc)}
        elif isinstance(doc, ScanDoc):
            render_scan(doc, target, seed)
            truth[doc.filename] = {"kind": "scan", "title": doc.title, "scan_text": "\n".join(doc.lines)}
        else:
            render_xlsx(doc, target)
            truth[doc.filename] = {
                "kind": "xlsx",
                "title": doc.title,
                "sheets": {s.name: [[c for c in r] for r in s.rows] for s in doc.sheets},
            }
    (out_dir / "ground_truth.json").write_text(json.dumps(truth, indent=2, ensure_ascii=False) + "\n")
    return truth
