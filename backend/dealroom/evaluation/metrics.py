"""Metric functions. Pure, small and unit-tested."""

from __future__ import annotations

import math
from collections.abc import Sequence
from typing import Any

from dealroom.ingestion.models import Chunk
from dealroom.retrieval.text import numbers, tokens


def recall_at_k(ranked: Sequence[Chunk], evidence: Sequence[dict[str, Any]], k: int) -> float:
    if not evidence:
        return 0.0
    top = ranked[:k]
    return sum(any(c.covers(e) for c in top) for e in evidence) / len(evidence)


def reciprocal_rank(ranked: Sequence[Chunk], evidence: Sequence[dict[str, Any]]) -> float:
    for index, chunk in enumerate(ranked):
        if any(chunk.covers(e) for e in evidence):
            return 1.0 / (index + 1)
    return 0.0


def ndcg_at_k(ranked: Sequence[Chunk], evidence: Sequence[dict[str, Any]], k: int) -> float:
    """Binary relevance; a chunk is relevant when it covers an evidence item not yet covered higher up."""
    covered: set[int] = set()
    dcg = 0.0
    for index, chunk in enumerate(ranked[:k]):
        new = [i for i, e in enumerate(evidence) if i not in covered and chunk.covers(e)]
        if new:
            covered.update(new)
            dcg += 1.0 / math.log2(index + 2)
    ideal = sum(1.0 / math.log2(i + 2) for i in range(min(len(evidence), k)))
    return dcg / ideal if ideal else 0.0


def value_found(value: float, text: str) -> bool:
    """Accept 0.128 written as 12.8%, and 132.0 written as 132."""
    found = numbers(text)
    candidates = {f"{value:g}"}
    if abs(value) < 1:
        candidates.add(f"{value * 100:g}")
    return bool(candidates & found)


def grounded(sentence: str, evidence_texts: Sequence[str], threshold: float = 0.8) -> bool:
    """A sentence is grounded when most of its content words appear in the evidence it cites."""
    words = set(tokens(sentence))
    if not words:
        return True
    support: set[str] = set()
    for text in evidence_texts:
        support |= set(tokens(text))
    return len(words & support) / len(words) >= threshold


def levenshtein(a: str, b: str) -> int:
    previous = list(range(len(b) + 1))
    for i, ca in enumerate(a, start=1):
        current = [i]
        for j, cb in enumerate(b, start=1):
            current.append(min(previous[j] + 1, current[j - 1] + 1, previous[j - 1] + (ca != cb)))
        previous = current
    return previous[-1]


def character_accuracy(truth: str, ocr: str) -> float:
    truth_norm = " ".join(truth.split())
    ocr_norm = " ".join(ocr.split())
    if not truth_norm:
        return 1.0
    return max(0.0, 1.0 - levenshtein(truth_norm, ocr_norm) / len(truth_norm))


def mean(values: Sequence[float]) -> float:
    return sum(values) / len(values) if values else 0.0
