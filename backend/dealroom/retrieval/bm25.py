"""Okapi BM25 over chunk text."""

from __future__ import annotations

import math
from collections import Counter

from dealroom.retrieval.text import tokens


class BM25:
    def __init__(self, documents: list[str], k1: float = 1.4, b: float = 0.75) -> None:
        self.k1 = k1
        self.b = b
        self.docs = [Counter(tokens(d)) for d in documents]
        self.lengths = [sum(d.values()) for d in self.docs]
        self.avg_length = sum(self.lengths) / max(len(self.lengths), 1)
        frequency: Counter[str] = Counter()
        for doc in self.docs:
            frequency.update(doc.keys())
        n = len(self.docs)
        self.idf = {term: math.log(1 + (n - df + 0.5) / (df + 0.5)) for term, df in frequency.items()}

    def scores(self, query: str) -> list[float]:
        terms = tokens(query)
        out: list[float] = []
        for doc, length in zip(self.docs, self.lengths, strict=True):
            score = 0.0
            for term in terms:
                tf = doc.get(term, 0)
                if tf:
                    norm = tf * (self.k1 + 1) / (tf + self.k1 * (1 - self.b + self.b * length / self.avg_length))
                    score += self.idf.get(term, 0.0) * norm
            out.append(score)
        return out
