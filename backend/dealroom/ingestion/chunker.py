"""Layout-aware chunking.

Rules:
* a chunk never crosses a page (PDF) or a row block (spreadsheet), so every
  chunk has one exact citation;
* headings start a new chunk and are carried as section context;
* tables stay whole, with their caption, unless they are very long;
* spreadsheet rows are grouped into blocks separated by blank rows or sub-header
  rows, and every window repeats its block header;
* every chunk starts with a short context line (document and section), which
  helps both lexical and dense retrieval.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from dealroom.ingestion.models import Chunk, Element

SENTENCE_END = re.compile(r"(?<=[.!?])\s+")


@dataclass(frozen=True)
class ChunkSettings:
    max_chars: int = 900
    overlap_chars: int = 150
    rows_per_chunk: int = 12
    max_table_chars: int = 3600


def document_label(file: str) -> str:
    stem = file.rsplit(".", 1)[0]
    stem = re.sub(r"^\d+_", "", stem)
    return stem.replace("_", " ").strip().capitalize()


def _context(file: str, section: str | None) -> str:
    label = document_label(file)
    return f"[{label}" + (f" | {section}]" if section else "]")


def _tail(text: str, limit: int) -> str:
    if limit <= 0:
        return ""
    sentences = SENTENCE_END.split(text.strip())
    tail = sentences[-1] if sentences else ""
    return tail if len(tail) <= limit else ""


def _is_header_row(text: str) -> bool:
    cells = [c.strip() for c in text.split("|")]
    numeric = [c for c in cells if re.fullmatch(r"-?\d+(\.\d+)?", c)]
    return len(cells) > 1 and not numeric


class Chunker:
    def __init__(self, settings: ChunkSettings | None = None) -> None:
        self.settings = settings or ChunkSettings()

    def chunk(self, elements: list[Element]) -> list[Chunk]:
        spreadsheet = [e for e in elements if e.kind == "rows"]
        layout = [e for e in elements if e.kind != "rows"]
        return self._layout(layout) + self._rows(spreadsheet)

    # ------------------------------------------------------------------ PDFs and scans

    def _layout(self, elements: list[Element]) -> list[Chunk]:
        chunks: list[Chunk] = []
        buffer: list[str] = []
        state: dict[str, object] = {"file": None, "page": None, "section": None}
        carry = ""

        def flush() -> None:
            nonlocal buffer, carry
            if buffer:
                file, page, section = state["file"], state["page"], state["section"]
                assert isinstance(file, str)
                body = " ".join(buffer)
                text = f"{_context(file, section if isinstance(section, str) else None)}\n{body}"
                chunks.append(
                    Chunk(
                        file,
                        text,
                        "paragraph",
                        page=page if isinstance(page, int) else None,
                        section=section if isinstance(section, str) else None,
                    )
                )
                carry = _tail(body, self.settings.overlap_chars)
            buffer = []

        for element in elements:
            if element.file != state["file"]:
                flush()
                carry = ""
                state = {"file": element.file, "page": element.page, "section": None}
            if element.page != state["page"]:
                flush()
                carry = ""
                state["page"] = element.page
            if element.kind == "heading":
                flush()
                carry = ""
                state["section"] = element.text
                continue
            if element.kind == "table":
                flush()
                carry = ""
                chunks.extend(self._table(element, state["section"]))
                continue
            for piece in self._split(element.text):
                pending = len(" ".join(buffer)) + len(piece)
                if buffer and pending > self.settings.max_chars:
                    flush()
                if not buffer and carry:
                    buffer.append(carry)
                    carry = ""
                buffer.append(piece)
        flush()
        return chunks

    def _split(self, text: str) -> list[str]:
        text = " ".join(text.split())
        if len(text) <= self.settings.max_chars:
            return [text]
        pieces: list[str] = []
        current = ""
        for sentence in SENTENCE_END.split(text):
            if current and len(current) + len(sentence) + 1 > self.settings.max_chars:
                pieces.append(current)
                current = sentence
            else:
                current = f"{current} {sentence}".strip()
        if current:
            pieces.append(current)
        return pieces

    def _table(self, element: Element, section: object) -> list[Chunk]:
        section_name = section if isinstance(section, str) else None
        context = _context(element.file, section_name)
        if len(element.text) <= self.settings.max_table_chars:
            return [Chunk(element.file, f"{context}\n{element.text}", "table", page=element.page, section=section_name)]
        lines = element.text.split("\n")
        head, rows = lines[:2], lines[2:]
        out: list[Chunk] = []
        window: list[str] = []
        for row in rows:
            window.append(row)
            if len("\n".join(head + window)) > self.settings.max_table_chars:
                out.append(
                    Chunk(
                        element.file,
                        "\n".join([context, *head, *window[:-1]]),
                        "table",
                        page=element.page,
                        section=section_name,
                    )
                )
                window = [row]
        if window:
            out.append(
                Chunk(
                    element.file, "\n".join([context, *head, *window]), "table", page=element.page, section=section_name
                )
            )
        return out

    # ------------------------------------------------------------------ spreadsheets

    def _rows(self, elements: list[Element]) -> list[Chunk]:
        blocks: list[list[Element]] = []
        for element in elements:
            previous = blocks[-1][-1] if blocks else None
            new_block = (
                previous is None
                or previous.file != element.file
                or previous.sheet != element.sheet
                or (element.row_start or 0) > (previous.row_end or 0) + 1
                or _is_header_row(element.text)
            )
            if new_block:
                blocks.append([element])
            else:
                blocks[-1].append(element)
        chunks: list[Chunk] = []
        size = self.settings.rows_per_chunk
        for block in blocks:
            header = block[0] if _is_header_row(block[0].text) else None
            body = block[1:] if header else block
            if not body:
                body = block
                header = None
            for start in range(0, len(body), size):
                window = body[start : start + size]
                first = header if (header and start == 0) else window[0]
                lines = ([header.text] if header else []) + [e.text for e in window]
                context = f"[{document_label(block[0].file)} | sheet {block[0].sheet}]"
                chunks.append(
                    Chunk(
                        block[0].file,
                        "\n".join([context, *lines]),
                        "rows",
                        sheet=block[0].sheet,
                        row_start=first.row_start,
                        row_end=window[-1].row_end,
                        section=block[0].sheet,
                    )
                )
        return chunks
