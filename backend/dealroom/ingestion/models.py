"""Data structures shared by extraction, chunking and retrieval."""

from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass, field
from typing import Any, Literal

ElementKind = Literal["heading", "paragraph", "table", "rows", "ocr"]


@dataclass
class Element:
    """One layout unit extracted from a document, with the coordinates needed to cite it."""

    file: str
    kind: ElementKind
    text: str
    page: int | None = None
    sheet: str | None = None
    row_start: int | None = None
    row_end: int | None = None
    section: str | None = None
    bbox: tuple[float, float, float, float] | None = None


@dataclass
class Chunk:
    """A retrievable passage. ``citation`` is what users see next to an answer."""

    file: str
    text: str
    kind: ElementKind
    page: int | None = None
    sheet: str | None = None
    row_start: int | None = None
    row_end: int | None = None
    section: str | None = None
    id: str = field(default="")

    def __post_init__(self) -> None:
        if not self.id:
            digest = hashlib.sha1(
                f"{self.file}|{self.page}|{self.sheet}|{self.row_start}|{self.text}".encode()
            ).hexdigest()
            self.id = digest[:12]

    @property
    def citation(self) -> str:
        if self.sheet is not None:
            rows = f"A{self.row_start}" if self.row_start == self.row_end else f"A{self.row_start}:A{self.row_end}"
            return f"{self.file}, sheet {self.sheet}, rows {rows}"
        return f"{self.file}, p. {self.page}"

    def covers(self, location: dict[str, Any]) -> bool:
        """True when this chunk contains a gold evidence location (or one of its accepted alternatives)."""
        if "any_of" in location:
            return any(self.covers(option) for option in location["any_of"])
        if location.get("file") != self.file:
            return False
        if "sheet" in location:
            row = int(location["row"])
            return (
                self.sheet == location["sheet"]
                and self.row_start is not None
                and self.row_end is not None
                and self.row_start <= row <= self.row_end
            )
        return self.page == location.get("page")

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["citation"] = self.citation
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Chunk:
        keys = {"file", "text", "kind", "page", "sheet", "row_start", "row_end", "section", "id"}
        return cls(**{k: v for k, v in data.items() if k in keys})
