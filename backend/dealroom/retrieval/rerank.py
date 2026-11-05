"""Second-stage rerankers.

``LexicalCrossScorer`` scores each (question, passage) pair jointly with
features a first-stage ranker does not use: IDF-weighted term coverage, bigram
overlap, matching numbers and years, and whether a table row label matches the
question. It is deterministic and runs in CI. ``CrossEncoderReranker`` wraps a
sentence-transformers cross-encoder (optional extra ``crossencoder``) for cloud
mode. Both implement ``Reranker``.
"""

from __future__ import annotations

import math
from collections import Counter
from typing import Protocol

from dealroom.ingestion.models import Chunk
from dealroom.retrieval.text import YEAR, bigrams, numbers, tokens


class Reranker(Protocol):
    name: str

    def score(self, query: str, chunks: list[Chunk]) -> list[float]: ...


class LexicalCrossScorer:
    name = "lexical-cross-scorer"

    def __init__(self, corpus: list[Chunk]) -> None:
        frequency: Counter[str] = Counter()
        for chunk in corpus:
            frequency.update(set(tokens(chunk.text)))
        n = max(len(corpus), 1)
        self.idf = {t: math.log(1 + n / (1 + df)) for t, df in frequency.items()}
        self.default_idf = math.log(1 + n)

    def _weight(self, term: str) -> float:
        return self.idf.get(term, self.default_idf)

    def score(self, query: str, chunks: list[Chunk]) -> list[float]:
        q_terms = tokens(query)
        q_set = set(q_terms)
        q_bigrams = bigrams(q_terms)
        q_numbers = {n for n in numbers(query) if not YEAR.fullmatch(n)}
        q_years = set(YEAR.findall(query))
        q_fy = {t for t in q_terms if t.startswith("fy")}
        total = sum(self._weight(t) for t in q_set) or 1.0
        out: list[float] = []
        for chunk in chunks:
            body = chunk.text.split("\n", 1)[-1]
            c_terms = tokens(chunk.text)
            c_set = set(c_terms)
            coverage = sum(self._weight(t) for t in q_set & c_set) / total
            pairs = len(q_bigrams & bigrams(c_terms)) / max(len(q_bigrams), 1)
            nums = len(q_numbers & numbers(body)) / max(len(q_numbers), 1) if q_numbers else 0.0
            years = len(q_years & set(YEAR.findall(chunk.text))) / max(len(q_years), 1) if q_years else 0.0
            fy = len(q_fy & c_set) / max(len(q_fy), 1) if q_fy else 0.0
            label = 0.0
            if chunk.kind in {"table", "rows"}:
                for line in body.split("\n")[1:]:
                    head = set(tokens(line.split("|", 1)[0]))
                    if not head:
                        continue
                    weight = sum(self._weight(t) for t in head)
                    overlap = sum(self._weight(t) for t in head & q_set) / weight
                    if overlap >= 0.5:
                        label = max(label, overlap * min(1.0, len(head & q_set) / 2))
            out.append(2.0 * coverage + 0.8 * pairs + 0.6 * nums + 0.5 * years + 0.5 * fy + 0.7 * label)
        return out


class CrossEncoderReranker:  # pragma: no cover - needs the optional model download (extra "onnx")
    """ms-marco MiniLM cross-encoder on CPU through ONNX Runtime."""

    name = "onnx-cross-encoder"

    def __init__(self, model: str = "Xenova/ms-marco-MiniLM-L-6-v2") -> None:
        from fastembed.rerank.cross_encoder import TextCrossEncoder

        self.model = TextCrossEncoder(model)

    def score(self, query: str, chunks: list[Chunk]) -> list[float]:
        return [float(s) for s in self.model.rerank(query, [c.text for c in chunks])]
