"""Reversible anonymisation that runs before any document leaves the trust boundary.

Two entry points:

* ``redact_pdf`` rewrites a PDF so that personal data is replaced by placeholders
  *in the file itself*. This is what gets sent to Azure Document Intelligence.
  Text pages are redacted with PDF redaction annotations; image-only pages are
  OCR'd locally first, and matching word boxes are blacked out in the image.
* ``mask_text`` masks extracted text (chunks, questions, prompts) so the index and
  every model call only ever see placeholders.

Both share one ``Vault``, so "Corinne Vasseli" becomes the same ``[PERSON_001]``
in every document. The vault (placeholder to original) stays on the server; the
masking log records type, placeholder and a SHA-256 prefix, never the original.

Person detection uses a first-name lexicon plus a capitalised surname. It is
deliberately simple, measured in the evaluation report, and replaceable by an
NER model behind the same ``Detector`` interface.
"""

from __future__ import annotations

import hashlib
import io
import json
import re
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from pathlib import Path

FIRST_NAMES = frozenset(
    [
        "Adrian",
        "Alain",
        "Alexander",
        "Alexandra",
        "Andrea",
        "Andreas",
        "Anna",
        "Anne",
        "Antoine",
        "Barbara",
        "Beat",
        "Benjamin",
        "Bernhard",
        "Bruno",
        "Carla",
        "Carlo",
        "Caroline",
        "Christian",
        "Christine",
        "Christoph",
        "Claudia",
        "Corinne",
        "Daniel",
        "Daniela",
        "David",
        "Dominik",
        "Elena",
        "Elisabeth",
        "Emma",
        "Eric",
        "Erik",
        "Eva",
        "Fabian",
        "Felix",
        "Florian",
        "Francesca",
        "Franziska",
        "Gabriel",
        "Hans",
        "Heinz",
        "Helen",
        "Ines",
        "Isabelle",
        "Jakob",
        "Jan",
        "Jana",
        "Johanna",
        "Jonas",
        "Josef",
        "Julia",
        "Julien",
        "Karin",
        "Katarina",
        "Katharina",
        "Klaus",
        "Lara",
        "Laura",
        "Laurent",
        "Lea",
        "Lena",
        "Leon",
        "Lisa",
        "Lorenzo",
        "Luca",
        "Lucas",
        "Lukas",
        "Manuel",
        "Marc",
        "Marco",
        "Maria",
        "Marie",
        "Mario",
        "Markus",
        "Martin",
        "Martina",
        "Matthias",
        "Max",
        "Michael",
        "Michel",
        "Monika",
        "Nadia",
        "Nicolas",
        "Nina",
        "Olivier",
        "Pascal",
        "Patrick",
        "Paul",
        "Peter",
        "Petra",
        "Philipp",
        "Pierre",
        "Ralph",
        "Regula",
        "Reto",
        "Robert",
        "Roger",
        "Ruth",
        "Sabine",
        "Sandra",
        "Sara",
        "Sarah",
        "Simon",
        "Sofia",
        "Sophie",
        "Stefan",
        "Stefanie",
        "Stephan",
        "Susanne",
        "Thomas",
        "Tobias",
        "Ueli",
        "Urs",
        "Ursula",
        "Valentin",
        "Vera",
        "Viktor",
        "Werner",
        "Yves",
    ]
)

SURNAME = r"[A-Z][a-zäöüéèà]+(?:-[A-Z][a-zäöüéèà]+)?"
PATTERNS: dict[str, re.Pattern[str]] = {
    "EMAIL": re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+"),
    "IBAN": re.compile(r"\b[A-Z]{2}\d{2}(?: ?[A-Z0-9]{4}){3,7}(?: ?[A-Z0-9]{1,3})?\b"),
    "PHONE": re.compile(r"\+\d{2,3}(?: \d{2,4}){3,5}\b"),
    "ADDRESS": re.compile(
        r"\b(?:[A-Z][\w-]*(?:strasse|gasse|weg|platz|allee)|[A-Z][\w-]+ (?:Ring|Strasse|Weg|Platz|Allee))"
        r" \d+[a-z]?, \d{4,5} [A-Z][\w-]+"
    ),
    "PERSON": re.compile(r"\b(" + "|".join(sorted(FIRST_NAMES)) + r") (" + SURNAME + r")\b"),
}
ORDER = ("EMAIL", "IBAN", "PHONE", "ADDRESS", "PERSON")
PLACEHOLDER = re.compile(r"\[(EMAIL|IBAN|PHONE|ADDRESS|PERSON)_\d{3}\]")


@dataclass(frozen=True)
class Match:
    type: str
    start: int
    end: int
    value: str


@dataclass
class Vault:
    """Placeholder mapping. Lives server-side only; never sent to a model or a client."""

    forward: dict[str, str] = field(default_factory=dict)
    counters: dict[str, int] = field(default_factory=dict)

    def placeholder(self, kind: str, value: str) -> str:
        if value not in self.forward:
            self.counters[kind] = self.counters.get(kind, 0) + 1
            self.forward[value] = f"[{kind}_{self.counters[kind]:03d}]"
        return self.forward[value]

    @property
    def reverse(self) -> dict[str, str]:
        return {v: k for k, v in self.forward.items()}

    def surnames(self) -> dict[str, str]:
        """Surname of each masked person, so that later bare mentions ("Vasseli said") are masked too."""
        out: dict[str, str] = {}
        for value, token in self.forward.items():
            if token.startswith("[PERSON_"):
                out[value.split(" ", 1)[1]] = token
        return out

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"forward": self.forward, "counters": self.counters}, indent=2))

    @classmethod
    def load(cls, path: Path) -> Vault:
        if not path.exists():
            return cls()
        data = json.loads(path.read_text())
        return cls(forward=dict(data["forward"]), counters=dict(data["counters"]))


@dataclass(frozen=True)
class MaskEvent:
    file: str
    page: int | None
    type: str
    placeholder: str
    sha256: str

    def to_json(self) -> str:
        return json.dumps(self.__dict__)


def detect(text: str, vault: Vault | None = None) -> list[Match]:
    """Find personal data, longest and earliest first, without overlaps."""
    found: list[Match] = []
    for kind in ORDER:
        for m in PATTERNS[kind].finditer(text):
            found.append(Match(kind, m.start(), m.end(), m.group(0)))
    if vault is not None:
        for surname in vault.surnames():
            for m in re.finditer(rf"\b{re.escape(surname)}\b", text):
                found.append(Match("PERSON_SURNAME", m.start(), m.end(), m.group(0)))
    found.sort(key=lambda m: (m.start, -(m.end - m.start)))
    result: list[Match] = []
    last_end = -1
    for match in found:
        if match.start >= last_end:
            result.append(match)
            last_end = match.end
    return result


class Anonymiser:
    def __init__(self, vault: Vault | None = None, log: Callable[[MaskEvent], None] | None = None) -> None:
        self.vault = vault or Vault()
        self._log = log or (lambda event: None)

    def _token(self, match: Match) -> str:
        if match.type == "PERSON_SURNAME":
            return self.vault.surnames()[match.value]
        return self.vault.placeholder(match.type, match.value)

    def _emit(self, file: str, page: int | None, match: Match, token: str) -> None:
        digest = hashlib.sha256(match.value.encode()).hexdigest()[:16]
        self._log(MaskEvent(file, page, match.type.replace("_SURNAME", ""), token, digest))

    def mask_text(self, text: str, *, file: str = "", page: int | None = None, log: bool = True) -> str:
        # full names first, so that surnames learnt from them are masked in the same pass
        for name in PATTERNS["PERSON"].finditer(text):
            self.vault.placeholder("PERSON", name.group(0))
        out: list[str] = []
        cursor = 0
        for match in detect(text, self.vault):
            token = self._token(match)
            out.append(text[cursor : match.start])
            out.append(token)
            cursor = match.end
            if log:
                self._emit(file, page, match, token)
        out.append(text[cursor:])
        return "".join(out)

    def unmask(self, text: str) -> str:
        reverse = self.vault.reverse
        return PLACEHOLDER.sub(lambda m: reverse.get(m.group(0), m.group(0)), text)

    # ---------------------------------------------------------------- PDF redaction

    def redact_pdf(self, data: bytes, *, file: str, ocr: Callable[[bytes], list[OcrWord]] | None = None) -> bytes:
        """Return a copy of the PDF with personal data replaced in the file itself."""
        import pymupdf

        document = pymupdf.open(stream=data, filetype="pdf")
        for page_index, page in enumerate(document):
            page_no = page_index + 1
            text = " ".join(page.get_text().split())  # values wrapped over two lines are matched as one
            if text.strip():
                self.mask_text(text, file=file, page=page_no, log=False)  # learn names first
                for match in detect(text, self.vault):
                    token = self._token(match)
                    for rect in page.search_for(match.value):
                        inset = rect.height * 0.3  # keep neighbouring lines out of the redaction box
                        box = pymupdf.Rect(rect.x0, rect.y0 + inset, rect.x1, rect.y1 - inset)
                        page.add_redact_annot(box, text=token, fontsize=6, fill=(1, 1, 1))
                    self._emit(file, page_no, match, token)
                page.apply_redactions()
            elif ocr is not None:
                pix = page.get_pixmap(dpi=200)
                png = pix.tobytes("png")
                boxes = self._redaction_boxes(ocr(png), file=file, page=page_no)
                if boxes:
                    scale = 72.0 / 200.0
                    for x0, y0, x1, y1 in boxes:
                        rect = pymupdf.Rect(x0 * scale, y0 * scale, x1 * scale, y1 * scale)
                        page.add_redact_annot(rect, fill=(0, 0, 0))
                    page.apply_redactions(images=pymupdf.PDF_REDACT_IMAGE_PIXELS)
        buffer = io.BytesIO()
        document.save(buffer, garbage=3, deflate=True)
        return buffer.getvalue()

    def _redaction_boxes(
        self, words: list[OcrWord], *, file: str, page: int
    ) -> list[tuple[float, float, float, float]]:
        text = " ".join(w.text for w in words)
        offsets: list[tuple[int, int, OcrWord]] = []
        cursor = 0
        for word in words:
            offsets.append((cursor, cursor + len(word.text), word))
            cursor += len(word.text) + 1
        boxes: list[tuple[float, float, float, float]] = []
        self.mask_text(text, file=file, page=page, log=False)
        for match in detect(text, self.vault):
            self._emit(file, page, match, self._token(match))
            for start, end, word in offsets:
                if start < match.end and end > match.start:
                    boxes.append(word.box)
        return boxes


@dataclass(frozen=True)
class OcrWord:
    text: str
    box: tuple[float, float, float, float]  # pixel coordinates x0, y0, x1, y1


def jsonl_logger(path: Path) -> Callable[[MaskEvent], None]:
    path.parent.mkdir(parents=True, exist_ok=True)

    def write(event: MaskEvent) -> None:
        with path.open("a", encoding="utf-8") as handle:
            handle.write(event.to_json() + "\n")

    return write


def placeholders_in(texts: Iterable[str]) -> set[str]:
    found: set[str] = set()
    for text in texts:
        found.update(m.group(0) for m in PLACEHOLDER.finditer(text))
    return found
