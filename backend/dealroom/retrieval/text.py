"""Tokenisation shared by BM25, the lexical reranker and the extractive answerer."""

from __future__ import annotations

import re
from itertools import pairwise

STOPWORDS = frozenset(
    [
        "a",
        "an",
        "and",
        "are",
        "as",
        "at",
        "be",
        "been",
        "by",
        "can",
        "could",
        "did",
        "do",
        "does",
        "for",
        "from",
        "had",
        "has",
        "have",
        "how",
        "in",
        "into",
        "is",
        "it",
        "its",
        "of",
        "on",
        "or",
        "our",
        "than",
        "that",
        "the",
        "their",
        "there",
        "these",
        "this",
        "to",
        "was",
        "were",
        "what",
        "when",
        "where",
        "which",
        "who",
        "whom",
        "why",
        "will",
        "with",
        "would",
        "company",
        "companys",
    ]
)
# Words that frame a question rather than carry its content. Ignored when measuring
# how much of a question the evidence covers (not when ranking).
QUESTION_WORDS = frozenset(
    [
        "many",
        "much",
        "long",
        "often",
        "since",
        "show",
        "shows",
        "hold",
        "generate",
        "contribute",
        "expect",
        "fast",
        "large",
        "size",
        "work",
        "happen",
        "assume",
        "amount",
        "according",
        "did",
        "does",
        "tell",
        "give",
        "list",
    ]
)
TOKEN = re.compile(r"[a-z0-9]+(?:[.,][0-9]+)*%?|\[[a-z]+_\d{3}\]")
NUMBER = re.compile(r"-?\d+(?:[.,]\d+)?")
YEAR = re.compile(r"\b(?:19|20)\d{2}\b")


def stem(token: str) -> str:
    if token[0].isdigit() or token.startswith("["):
        return token
    for suffix, minimum in (
        ("ations", 6),
        ("ation", 6),
        ("ings", 6),
        ("ing", 5),
        ("ies", 5),
        ("ied", 5),
        ("ed", 5),
        ("es", 5),
        ("ly", 5),
        ("s", 4),
        ("e", 5),
    ):
        if token.endswith(suffix) and len(token) >= minimum + len(suffix) - 2:
            base = token[: -len(suffix)]
            return base + ("y" if suffix in {"ies", "ied"} else "")
    return token


def normalise_number(token: str) -> str:
    token = token.replace(",", "")
    if re.fullmatch(r"-?\d+\.\d+", token):
        token = token.rstrip("0").rstrip(".")
    return token


FISCAL = re.compile(r"^fy(\d{2}|\d{4})[ae]?$")


def fiscal_year(token: str) -> str:
    """FY2027E, FY2027A, FY27 and FY2027 are the same year to an analyst."""
    match = FISCAL.match(token)
    if not match:
        return token
    year = match.group(1)
    return f"fy{'20' + year if len(year) == 2 else year}"


def tokens(text: str, *, keep_stopwords: bool = False) -> list[str]:
    out: list[str] = []
    for raw in TOKEN.findall(text.lower().replace("’", "'")):
        token = fiscal_year(raw.rstrip("%"))
        if not keep_stopwords and token in STOPWORDS:
            continue
        if len(token) == 1 and not token.isdigit():
            continue  # possessive "s", initials
        if token and token[0].isdigit():
            token = normalise_number(token)
        out.append(stem(token))
    return out


def numbers(text: str) -> set[str]:
    return {normalise_number(n.lstrip("-")) for n in NUMBER.findall(text.replace(",", ""))}


def bigrams(items: list[str]) -> set[tuple[str, str]]:
    return set(pairwise(items))
