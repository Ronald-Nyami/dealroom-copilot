"""FinanceBench: 150 questions on 84 real SEC filings, answers and evidence pages written by humans.

Setting: one index per filing (the paper's "single store" setting). A question is
searched only within its own filing. Retrieval is scored on whether a top-k chunk
sits on a gold evidence page; answers on whether they contain the gold figure.
Public filings are indexed without anonymisation, with the same chunker as the
synthetic data room but without cell-level table detection (too slow for 84 long
filings on small machines); table rows are kept as text lines.
"""

from __future__ import annotations

import json
import re
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from typing import Any

from dealroom.agents.qa import QAAgent
from dealroom.evaluation.metrics import mean
from dealroom.ingestion.chunker import Chunker
from dealroom.ingestion.extractors import LocalExtractor
from dealroom.ingestion.models import Chunk
from dealroom.ingestion.pipeline import load_chunks, save_chunks
from dealroom.models.llm import LLM, StubLLM
from dealroom.retrieval.retriever import MODES, Retriever

NUMBER = re.compile(r"-?\(?\$?\(?\d[\d,]*\.?\d*\)?%?")


def load_questions(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def _index_one(args: tuple[Path, Path]) -> tuple[str, int]:
    pdf, out = args
    target = out / f"{pdf.stem}.jsonl"
    if not target.exists():
        elements = LocalExtractor(detect_tables=False).extract(pdf.name, pdf.read_bytes())
        save_chunks(Chunker().chunk(elements), target)
    return pdf.stem, len(target.read_text().splitlines())


def build_indexes(pdf_dir: Path, out: Path, workers: int = 2) -> dict[str, int]:
    out.mkdir(parents=True, exist_ok=True)
    jobs = [(pdf, out) for pdf in sorted(pdf_dir.glob("*.pdf"))]
    if workers <= 1:
        return dict(map(_index_one, jobs))
    with ProcessPoolExecutor(max_workers=workers) as pool:  # pragma: no cover - exercised by the CLI
        return dict(pool.map(_index_one, jobs))


def gold_pages(question: dict[str, Any]) -> set[tuple[str, int]]:
    """FinanceBench page numbers are 0-based; chunk pages are 1-based."""
    return {(f"{e['doc_name']}.pdf", int(e["evidence_page_num"]) + 1) for e in question["evidence"]}


def parse_number(text: str) -> float | None:
    for raw in NUMBER.findall(text):
        cleaned = raw.replace("$", "").replace(",", "").replace("%", "")
        negative = cleaned.startswith("(") and cleaned.endswith(")")
        cleaned = cleaned.strip("()")
        try:
            value = float(cleaned)
        except ValueError:
            continue
        return -value if negative else value
    return None


FIGURE_ONLY = re.compile(r"^\s*-?\$?\(?\d[\d,]*\.?\d*\)?\s*(%|percent|million|billion|USD millions?)?\.?\s*$", re.I)


def is_figure(gold: str) -> bool:
    """Gold answers that are a single figure; narrative answers are not scored for figures."""
    return bool(FIGURE_ONLY.match(gold))


def contains_figure(answer: str, gold: str, tolerance: float = 0.01) -> bool:
    """True when the answer contains the gold figure (1% relative tolerance)."""
    target = parse_number(gold)
    if target is None:
        return False
    for raw in NUMBER.findall(answer):
        value = parse_number(raw)
        if value is not None and abs(value - target) <= max(abs(target) * tolerance, 0.005):
            return True
    return False


def evaluate(questions: list[dict[str, Any]], index_dir: Path, llm: LLM | None = None, k: int = 10) -> dict[str, Any]:
    llm = llm or StubLLM()
    by_doc: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for question in questions:
        by_doc[question["doc_name"]].append(question)
    hits: dict[str, dict[int, list[float]]] = {m: {1: [], 5: [], 10: []} for m in MODES}
    by_type: dict[str, list[float]] = defaultdict(list)
    figures: dict[str, list[float]] = defaultdict(list)
    rows: list[dict[str, Any]] = []
    for doc, items in sorted(by_doc.items()):
        chunks: list[Chunk] = load_chunks(index_dir / f"{doc}.jsonl")
        retriever = Retriever(chunks)
        agent = QAAgent(retriever, llm)
        for question in items:
            pages = gold_pages(question)
            for mode in MODES:
                ranked = retriever.search(question["question"], k, mode)
                for cutoff in hits[mode]:
                    found = any((h.chunk.file, h.chunk.page) in pages for h in ranked[:cutoff])
                    hits[mode][cutoff].append(float(found))
            by_type[question["question_type"]].append(hits["hybrid_rerank"][5][-1])
            answer = agent.answer(question["question"])
            if is_figure(question["answer"]):
                figures[question["question_type"]].append(float(contains_figure(answer.text, question["answer"])))
            rows.append(
                {
                    "id": question["financebench_id"],
                    "type": question["question_type"],
                    "question": question["question"],
                    "gold": question["answer"],
                    "answer": answer.text,
                    "abstained": answer.abstained,
                    "citations": [c.citation for c in answer.citations],
                }
            )
    return {
        "questions": len(questions),
        "filings": len(by_doc),
        "retrieval": {m: {f"page_hit@{c}": mean(v) for c, v in cuts.items()} for m, cuts in hits.items()},
        "page_hit@5_by_type": {t: mean(v) for t, v in sorted(by_type.items())},
        "figure_accuracy_by_type": {t: {"accuracy": mean(v), "questions": len(v)} for t, v in sorted(figures.items())},
        "abstained": sum(r["abstained"] for r in rows),
        "answers": rows,
    }
