"""Layout extraction behind one interface.

``LocalExtractor``  pymupdf (text layout, headings) + pdfplumber (tables) + openpyxl
                    (spreadsheets) + Tesseract (image-only pages). Used in CI and
                    whenever data may not leave the machine.
``AzureDocumentIntelligenceExtractor``  prebuilt-layout model behind a private
                    endpoint; spreadsheets still go through openpyxl because they
                    carry exact cell values already.
"""

from __future__ import annotations

import io
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any, Protocol

import httpx

from dealroom.ingestion.anonymiser import OcrWord
from dealroom.ingestion.models import Element, ElementKind

HEADING_MIN_SIZE = 12.5


class Extractor(Protocol):
    name: str

    def extract(self, file: str, data: bytes) -> list[Element]: ...


# --------------------------------------------------------------------------- OCR


class TesseractOcr:
    def __init__(self, dpi: int = 200, lang: str = "eng") -> None:
        self.dpi = dpi
        self.lang = lang

    def text(self, png: bytes) -> str:
        import pytesseract
        from PIL import Image

        return str(pytesseract.image_to_string(Image.open(io.BytesIO(png)), lang=self.lang))

    def words(self, png: bytes) -> list[OcrWord]:
        import pytesseract
        from PIL import Image

        data = pytesseract.image_to_data(
            Image.open(io.BytesIO(png)), lang=self.lang, output_type=pytesseract.Output.DICT
        )
        words: list[OcrWord] = []
        for i, word in enumerate(data["text"]):
            if word.strip():
                x, y, w, h = data["left"][i], data["top"][i], data["width"][i], data["height"][i]
                words.append(OcrWord(word, (float(x), float(y), float(x + w), float(y + h))))
        return words


# --------------------------------------------------------------------------- spreadsheets


def _fmt(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, float):
        return f"{value:g}"
    return str(value)


def extract_xlsx(file: str, data: bytes) -> list[Element]:
    from openpyxl import load_workbook

    workbook = load_workbook(io.BytesIO(data), data_only=True, read_only=True)
    elements: list[Element] = []
    for sheet in workbook.worksheets:
        for index, row in enumerate(sheet.iter_rows(values_only=True), start=1):
            cells = [_fmt(c) for c in row]
            if not any(cells):
                continue
            while cells and not cells[-1]:
                cells.pop()  # keep inner empty cells so values stay under their column header
            elements.append(
                Element(
                    file,
                    "rows",
                    " | ".join(cells),
                    sheet=sheet.title,
                    row_start=index,
                    row_end=index,
                    section=sheet.title,
                )
            )
    return elements


# --------------------------------------------------------------------------- local PDF


def _inside(inner: tuple[float, float, float, float], outer: tuple[float, float, float, float]) -> bool:
    cx, cy = (inner[0] + inner[2]) / 2, (inner[1] + inner[3]) / 2
    return outer[0] - 2 <= cx <= outer[2] + 2 and outer[1] - 2 <= cy <= outer[3] + 2


class LocalExtractor:
    name = "local"

    def __init__(self, ocr: TesseractOcr | None = None) -> None:
        self.ocr = ocr or TesseractOcr()

    def extract(self, file: str, data: bytes) -> list[Element]:
        if file.lower().endswith(".xlsx"):
            return extract_xlsx(file, data)
        return self._pdf(file, data)

    def _pdf(self, file: str, data: bytes) -> list[Element]:
        import pdfplumber
        import pymupdf

        elements: list[Element] = []
        document = pymupdf.open(stream=data, filetype="pdf")
        with pdfplumber.open(io.BytesIO(data)) as plumber:
            for index, page in enumerate(document):
                page_no = index + 1
                if not page.get_text().strip():
                    png = page.get_pixmap(dpi=self.ocr.dpi).tobytes("png")
                    text = self.ocr.text(png).strip()
                    if text:
                        elements.append(Element(file, "ocr", text, page=page_no))
                    continue
                tables = []
                for table in plumber.pages[index].find_tables():
                    rows = [" | ".join(c or "" for c in row) for row in table.extract()]
                    x0, top, x1, bottom = (float(v) for v in table.bbox)
                    tables.append(((x0, top, x1, bottom), "\n".join(rows)))
                elements.extend(self._page_elements(file, page_no, page, tables))
        return elements

    @staticmethod
    def _page_elements(
        file: str, page_no: int, page: Any, tables: list[tuple[tuple[float, float, float, float], str]]
    ) -> list[Element]:
        out: list[Element] = []
        pending_tables = sorted(tables, key=lambda t: t[0][1])
        caption: str | None = None
        for block in page.get_text("dict")["blocks"]:
            if block.get("type") != 0:
                continue
            bbox = tuple(block["bbox"])
            while pending_tables and pending_tables[0][0][1] <= bbox[1]:
                tbox, text = pending_tables.pop(0)
                body = f"{caption}\n{text}" if caption else text
                out.append(Element(file, "table", body, page=page_no, bbox=tbox))
                caption = None
            if any(_inside(bbox, t[0]) for t in tables):
                continue
            spans = [s for line in block["lines"] for s in line["spans"]]
            text = " ".join(" ".join(s["text"] for s in line["spans"]) for line in block["lines"]).strip()
            if not text:
                continue
            size = max(s["size"] for s in spans)
            italic = all("Oblique" in s["font"] or "Italic" in s["font"] for s in spans)
            if size >= HEADING_MIN_SIZE:
                out.append(Element(file, "heading", text, page=page_no, bbox=bbox))
            elif italic and pending_tables and pending_tables[0][0][1] - bbox[3] < 25:
                caption = text
            else:
                out.append(Element(file, "paragraph", text, page=page_no, bbox=bbox))
        for tbox, text in pending_tables:
            body = f"{caption}\n{text}" if caption else text
            out.append(Element(file, "table", body, page=page_no, bbox=tbox))
            caption = None
        return out


# --------------------------------------------------------------------------- Azure


class AzureDocumentIntelligenceExtractor:
    """prebuilt-layout over REST.

    Network path: the endpoint is the private endpoint's DNS name (public network
    access disabled on the resource). Identity: a bearer token from
    ``token_provider``, normally ``CertificateCredential`` (service principal that
    authenticates with a private key and an X.509 certificate). The document sent
    has already been through ``Anonymiser.redact_pdf``.
    """

    name = "azure-document-intelligence"
    api_version = "2024-11-30"

    def __init__(
        self,
        endpoint: str,
        token_provider: Callable[[], str],
        client: httpx.Client | None = None,
        poll_interval: float = 1.0,
        max_polls: int = 120,
    ) -> None:
        self.endpoint = endpoint.rstrip("/")
        self.token_provider = token_provider
        self.client = client or httpx.Client(timeout=60)
        self.poll_interval = poll_interval
        self.max_polls = max_polls

    def extract(self, file: str, data: bytes) -> list[Element]:
        if file.lower().endswith(".xlsx"):
            return extract_xlsx(file, data)
        result = self.analyze(data)
        return self.to_elements(file, result)

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.token_provider()}"}

    def analyze(self, data: bytes) -> dict[str, Any]:
        url = (
            f"{self.endpoint}/documentintelligence/documentModels/prebuilt-layout:analyze"
            f"?api-version={self.api_version}"
        )
        response = self.client.post(url, content=data, headers={**self._headers(), "Content-Type": "application/pdf"})
        response.raise_for_status()
        operation = response.headers["Operation-Location"]
        for _ in range(self.max_polls):
            poll = self.client.get(operation, headers=self._headers())
            poll.raise_for_status()
            body: dict[str, Any] = poll.json()
            status = body.get("status")
            if status == "succeeded":
                result: dict[str, Any] = body["analyzeResult"]
                return result
            if status == "failed":
                raise RuntimeError(f"Document Intelligence analysis failed: {body.get('error')}")
            time.sleep(self.poll_interval)
        raise TimeoutError("Document Intelligence analysis did not finish in time")

    @staticmethod
    def to_elements(file: str, result: dict[str, Any]) -> list[Element]:
        elements: list[Element] = []
        table_spans: set[int] = set()
        for table in result.get("tables", []):
            for span in table.get("spans", []):
                table_spans.update(range(span["offset"], span["offset"] + span["length"]))
        for paragraph in result.get("paragraphs", []):
            spans = paragraph.get("spans", [])
            if spans and spans[0]["offset"] in table_spans:
                continue
            region = (paragraph.get("boundingRegions") or [{}])[0]
            role = paragraph.get("role")
            kind: ElementKind = "heading" if role in {"title", "sectionHeading"} else "paragraph"
            elements.append(Element(file, kind, paragraph["content"], page=region.get("pageNumber")))
        for table in result.get("tables", []):
            grid: dict[int, dict[int, str]] = {}
            for cell in table.get("cells", []):
                grid.setdefault(cell["rowIndex"], {})[cell["columnIndex"]] = cell.get("content", "")
            rows = [" | ".join(row[c] for c in sorted(row)) for _, row in sorted(grid.items())]
            region = (table.get("boundingRegions") or [{}])[0]
            caption = (table.get("caption") or {}).get("content")
            text = "\n".join(([caption] if caption else []) + rows)
            elements.append(Element(file, "table", text, page=region.get("pageNumber")))
        elements.sort(key=lambda e: e.page or 0)
        return elements


def read_bytes(path: Path) -> bytes:
    return path.read_bytes()
