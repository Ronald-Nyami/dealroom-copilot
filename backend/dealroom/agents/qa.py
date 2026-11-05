"""Question answering over the data room, with citations or an explicit abstention.

Steps: retrieve -> select evidence spans -> abstain if the evidence does not
cover the question -> generate -> verify citations. The verifier drops any
citation the model invents and turns an uncited answer into an abstention, so
the rule "no claim without evidence" holds for any provider.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass, field

from dealroom.ingestion.models import Chunk
from dealroom.models.llm import LLM, Evidence, cited_numbers
from dealroom.retrieval.retriever import Retriever
from dealroom.retrieval.text import QUESTION_WORDS, YEAR, fiscal_year, tokens

QA_SYSTEM = (
    "You are a due-diligence analyst. Answer only from the numbered evidence. Put the evidence number in "
    "square brackets after every claim, for example [2]. If the evidence does not answer the question, reply "
    "exactly INSUFFICIENT_EVIDENCE. Do not use outside knowledge."
)
SENTENCE = re.compile(r"(?<=[.!?])\s+(?=[A-Z\[]|\d+\.\d+ )")  # also split before clause numbers


@dataclass(frozen=True)
class Span:
    chunk: Chunk
    text: str
    score: float
    key: str = ""  # the text that was scored (a table row without its caption)


@dataclass
class Answer:
    question: str
    text: str
    abstained: bool
    citations: list[Evidence] = field(default_factory=list)
    coverage: float = 0.0

    def to_dict(self) -> dict[str, object]:
        return {
            "question": self.question,
            "answer": self.text,
            "abstained": self.abstained,
            "coverage": round(self.coverage, 3),
            "citations": [e.__dict__ for e in self.citations],
        }


def _row_span(row: str, columns: str | None, caption: str | None, question: str) -> tuple[str, str]:
    """Render a table row as (display text, row label used for tie-breaking within a table).

    The column kept is the one whose header best matches the question (a year,
    "share", "budget"...). If no header matches, the whole row is shown.
    """
    cells = [c.strip() for c in row.split("|")]
    prefix = f"{caption}: " if caption else ""
    if not columns:
        return prefix + row, row
    heads = [c.strip() for c in columns.split("|")]
    label_terms = set(tokens(cells[0]))
    wanted = ({fiscal_year(t) for t in tokens(question)} | set(YEAR.findall(question))) - label_terms
    best, best_overlap = 0, 0
    for index, head in enumerate(heads[1:], start=1):
        if index >= len(cells) or not cells[index]:
            continue
        head_terms = {fiscal_year(t) for t in tokens(head)} | set(YEAR.findall(head))
        overlap = len(head_terms & wanted)
        if overlap > best_overlap:
            best, best_overlap = index, overlap
    if best:
        text = f"{cells[0]}, {heads[best]}: {cells[best]}"
        return prefix + text, text
    pairs = ", ".join(f"{h}: {c}" for h, c in zip(heads[1:], cells[1:], strict=False) if c)
    text = f"{cells[0]} ({pairs})" if pairs else cells[0]
    return prefix + text, text


class EvidenceSelector:
    """Splits retrieved chunks into sentences or table rows and scores them against the question."""

    def __init__(self, corpus: list[Chunk]) -> None:
        frequency: Counter[str] = Counter()
        for chunk in corpus:
            frequency.update(set(tokens(chunk.text)))
        n = max(len(corpus), 1)
        self.idf = {t: math.log(1 + n / (1 + df)) for t, df in frequency.items()}
        self.unknown = math.log(1 + n)

    def weight(self, term: str) -> float:
        return self.idf.get(term, self.unknown)

    @staticmethod
    def content_terms(question: str) -> set[str]:
        return {t for t in tokens(question) if t not in QUESTION_WORDS}

    def coverage(self, question: str, text: str) -> float:
        q = self.content_terms(question)
        if not q:
            return 0.0
        found = q & set(tokens(text))
        return sum(self.weight(t) for t in found) / sum(self.weight(t) for t in q)

    @staticmethod
    def spans(chunk: Chunk, question: str) -> list[tuple[str, str]]:
        _, _, body = chunk.text.partition("\n")
        if chunk.kind in {"table", "rows"}:
            lines = [line for line in body.split("\n") if line.strip()]
            caption = lines[0] if lines and "|" not in lines[0] else None
            columns = next((line for line in lines if "|" in line), None)
            rows = [line for line in lines if "|" in line and line != columns]
            return [_row_span(row, columns, caption, question) for row in rows] or [(body, body)]
        return [(s, s) for s in SENTENCE.split(" ".join(body.split())) if s]

    def select(self, question: str, chunks: list[Chunk], limit: int = 4) -> list[Span]:
        spans: list[Span] = []
        for rank, chunk in enumerate(chunks):
            context = chunk.text.split("\n", 1)[0]
            for text, label in self.spans(chunk, question):
                local = self.coverage(question, text)
                with_context = self.coverage(question, f"{context} {text}")
                own = self.coverage(question, label)  # separates rows of the same table
                score = 0.6 * local + 0.3 * with_context + 0.25 * own - 0.02 * rank
                spans.append(Span(chunk, text, score, f"{context} {text}"))
        spans.sort(key=lambda s: -s.score)
        seen: set[str] = set()
        out: list[Span] = []
        for span in spans:
            if span.text not in seen:
                out.append(span)
                seen.add(span.text)
            if len(out) == limit:
                break
        return out


class QAAgent:
    def __init__(self, retriever: Retriever, llm: LLM, min_coverage: float = 0.45, top_k: int = 6) -> None:
        self.retriever = retriever
        self.llm = llm
        self.selector = EvidenceSelector(retriever.chunks)
        self.min_coverage = min_coverage
        self.top_k = top_k

    def evidence(self, question: str, limit: int = 4) -> list[Span]:
        hits = self.retriever.search(question, self.top_k)
        return self.selector.select(question, [h.chunk for h in hits], limit)

    def answer(self, question: str, multi: bool = False) -> Answer:
        spans = self.evidence(question)
        numbered = [Evidence(i + 1, s.chunk.id, s.chunk.citation, s.text) for i, s in enumerate(spans)]
        coverage = self.selector.coverage(question, spans[0].key) if spans else 0.0
        if coverage < self.min_coverage:
            return Answer(question, "Not found in the data room.", True, [], coverage)
        system = QA_SYSTEM + (" MULTI: combine the evidence needed." if multi else "")
        raw = self.llm.complete(system, f"Question: {question}", numbered)
        return verify(question, raw, numbered, coverage)


def verify(question: str, raw: str, evidence: list[Evidence], coverage: float) -> Answer:
    """Keep only citations that point at evidence actually provided; no citation means no answer."""
    if raw.strip() == "INSUFFICIENT_EVIDENCE":
        return Answer(question, "Not found in the data room.", True, [], coverage)
    by_number = {e.n: e for e in evidence}
    numbers = cited_numbers(raw)
    cited = [by_number[n] for n in dict.fromkeys(numbers) if n in by_number]
    if not cited:
        return Answer(question, "Not found in the data room.", True, [], coverage)
    text = re.sub(r"\s?\[(\d+)\]", lambda m: m.group(0) if int(m.group(1)) in by_number else "", raw).strip()
    return Answer(question, text, False, cited, coverage)
