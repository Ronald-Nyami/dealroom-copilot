"""Run the full evaluation and write reports/results.json and reports/eval.md."""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from typing import Any

from dealroom.agents.challenger import Challenger
from dealroom.agents.qa import QAAgent
from dealroom.evaluation.metrics import (
    character_accuracy,
    grounded,
    mean,
    ndcg_at_k,
    recall_at_k,
    reciprocal_rank,
    value_found,
)
from dealroom.ingestion.anonymiser import Anonymiser, Vault
from dealroom.ingestion.extractors import TesseractOcr
from dealroom.ingestion.models import Chunk
from dealroom.models.llm import LLM, StubLLM
from dealroom.retrieval.retriever import MODES, Retriever, retriever_from_env
from dealroom.retrieval.text import tokens
from dealroom.synth.spec import PII


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def retrieval_metrics(retriever: Retriever, gold: list[dict[str, Any]]) -> dict[str, Any]:
    answerable = [g for g in gold if g["evidence"]]
    out: dict[str, Any] = {}
    for mode in MODES:
        r3, r5, r10, nd, mrr = [], [], [], [], []
        by_type: dict[str, list[float]] = defaultdict(list)
        for g in answerable:
            ranked = [h.chunk for h in retriever.search(g["question"], 10, mode)]
            r3.append(recall_at_k(ranked, g["evidence"], 3))
            r5.append(recall_at_k(ranked, g["evidence"], 5))
            r10.append(recall_at_k(ranked, g["evidence"], 10))
            nd.append(ndcg_at_k(ranked, g["evidence"], 10))
            mrr.append(reciprocal_rank(ranked, g["evidence"]))
            by_type[g["type"]].append(r5[-1])
        out[mode] = {
            "recall@3": mean(r3),
            "recall@5": mean(r5),
            "recall@10": mean(r10),
            "ndcg@10": mean(nd),
            "mrr": mean(mrr),
            "recall@5_by_type": {t: mean(v) for t, v in sorted(by_type.items())},
        }
    out["questions"] = len(answerable)
    return out


def answer_metrics(agent: QAAgent, gold: list[dict[str, Any]]) -> dict[str, Any]:
    by_id = {c.id: c for c in agent.retriever.chunks}
    citations_ok = citations_total = 0
    grounded_ok = grounded_total = 0
    numeric_ok = numeric_total = 0
    abstain = {"tp": 0, "fp": 0, "fn": 0, "tn": 0}
    rows = []
    for g in gold:
        answer = agent.answer(g["question"], multi=g["type"] == "cross_doc")
        unanswerable = g["type"] == "unanswerable"
        if unanswerable:
            abstain["tp" if answer.abstained else "fn"] += 1
        else:
            abstain["fp" if answer.abstained else "tn"] += 1
        if not answer.abstained:
            for citation in answer.citations:
                citations_total += 1
                if not unanswerable and any(by_id[citation.chunk_id].covers(e) for e in g["evidence"]):
                    citations_ok += 1
            grounded_total += 1
            grounded_ok += grounded(answer.text.replace("[", " ").replace("]", " "), [c.text for c in answer.citations])
        if not unanswerable and g["value"] is not None and g["type"] != "cross_doc":
            numeric_total += 1
            numeric_ok += (not answer.abstained) and value_found(float(g["value"]), answer.text)
        rows.append({"id": g["id"], "type": g["type"], **answer.to_dict()})
    total = len(gold)
    return {
        "citation_precision": citations_ok / max(citations_total, 1),
        "groundedness": grounded_ok / max(grounded_total, 1),
        "numeric_accuracy": numeric_ok / max(numeric_total, 1),
        "numeric_questions": numeric_total,
        "abstention_accuracy": (abstain["tp"] + abstain["tn"]) / max(total, 1),
        "abstention_precision": abstain["tp"] / max(abstain["tp"] + abstain["fp"], 1),
        "abstention_recall": abstain["tp"] / max(abstain["tp"] + abstain["fn"], 1),
        "abstention_counts": abstain,
        "answers": rows,
    }


def challenger_metrics(retriever: Retriever, traps: list[dict[str, Any]]) -> dict[str, Any]:
    arguments = Challenger(retriever).run()
    by_id = {c.id: c for c in retriever.chunks}
    results = []
    for trap in traps:
        strict = lenient = None
        for argument in arguments:
            chunks = [by_id[c.chunk_id] for c in argument.citations]
            covered = [any(c.covers(e) for c in chunks) for e in trap["evidence"]]
            if all(covered) and strict is None:
                strict = argument.title
            if any(covered) and lenient is None:
                lenient = argument.title
        results.append(
            {
                "trap": trap["id"],
                "title": trap["title"],
                "found": strict is not None,
                "found_partial": lenient is not None,
                "argument": strict or lenient,
            }
        )
    supported = total = 0
    for argument in arguments:
        for citation in argument.citations:
            total += 1
            quote = set(tokens(citation.text))
            chunk = set(tokens(by_id[citation.chunk_id].text))
            supported += bool(quote) and len(quote & chunk) / len(quote) >= 0.9
    return {
        "trap_recall": sum(r["found"] for r in results) / max(len(results), 1),
        "traps": results,
        "argument_citation_precision": supported / max(total, 1),
        "arguments": [a.to_dict() for a in arguments],
    }


def ingestion_metrics(chunks: list[Chunk], dataroom: Path) -> dict[str, Any]:
    truth = json.loads((dataroom / "ground_truth.json").read_text())
    ocr = TesseractOcr()
    accuracy = {}
    import pymupdf

    for file, info in truth.items():
        if info["kind"] != "scan":
            continue
        page = pymupdf.open(dataroom / "files" / file)[0]
        text = ocr.text(page.get_pixmap(dpi=ocr.dpi).tobytes("png"))
        accuracy[file] = character_accuracy(info["scan_text"], text)
    leaked_index = sorted({p for p in PII for c in chunks if p in c.text})
    anonymiser = Anonymiser(Vault())
    leaked_redacted: set[str] = set()
    redacted_files = 0
    for file, info in truth.items():
        if info["kind"] != "pdf" or not any(p in page for p in PII for page in info["pages"]):
            continue
        redacted = anonymiser.redact_pdf((dataroom / "files" / file).read_bytes(), file=file)
        redacted_files += 1
        text = " ".join(" ".join(p.get_text().split()) for p in pymupdf.open(stream=redacted, filetype="pdf"))
        leaked_redacted |= {p for p in PII if p in text}
    return {
        "ocr_character_accuracy": accuracy,
        "ocr_mean": mean(list(accuracy.values())),
        "pii_strings": len(PII),
        "pii_leaked_into_index": leaked_index,
        "pdfs_with_pii": redacted_files,
        "pii_left_in_redacted_pdfs": sorted(leaked_redacted),
    }


def pct(value: float) -> str:
    return f"{value * 100:.1f}%"


def render_markdown(results: dict[str, Any]) -> str:
    r = results["retrieval"]
    a = results["answers"]
    c = results["challenger"]
    i = results["ingestion"]
    names = {"bm25": "BM25", "dense": "Dense (local LSA)", "hybrid": "Hybrid (RRF)", "hybrid_rerank": "Hybrid + rerank"}
    lines = [
        "# Evaluation report",
        "",
        f"Generated by `make eval`. Corpus: {results['config']['files']} synthetic files, "
        f"{results['config']['chunks']} chunks. Gold set: {results['config']['questions']} questions "
        f"({r['questions']} answerable). Model: `{results['config']['llm']}`. Embeddings: "
        f"`{results['config']['embedder']}`. Reranker: `{results['config']['reranker']}`.",
        "",
        "## Retrieval",
        "",
        "| Method | Recall@3 | Recall@5 | Recall@10 | nDCG@10 | MRR |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for mode in MODES:
        m = r[mode]
        lines.append(
            f"| {names[mode]} | {pct(m['recall@3'])} | {pct(m['recall@5'])} | {pct(m['recall@10'])} | "
            f"{m['ndcg@10']:.3f} | {m['mrr']:.3f} |"
        )
    base, best = r["bm25"], r["hybrid_rerank"]
    lines += [
        "",
        f"Lift from BM25 to hybrid + rerank: recall@3 {(best['recall@3'] - base['recall@3']) * 100:+.1f} pts, "
        f"recall@10 {(best['recall@10'] - base['recall@10']) * 100:+.1f} pts, "
        f"nDCG@10 {best['ndcg@10'] - base['ndcg@10']:+.3f}, MRR {best['mrr'] - base['mrr']:+.3f}.",
        "",
        "Recall@5 by question type (hybrid + rerank): "
        + ", ".join(f"{t} {pct(v)}" for t, v in best["recall@5_by_type"].items())
        + ".",
        "",
        "## Answers",
        "",
        "| Metric | Value |",
        "| --- | --- |",
        f"| Citation precision (cited chunk holds the gold evidence) | {pct(a['citation_precision'])} |",
        f"| Groundedness (answer words found in cited evidence) | {pct(a['groundedness'])} |",
        f"| Numeric accuracy ({a['numeric_questions']} questions with a figure) | {pct(a['numeric_accuracy'])} |",
        f"| Abstention accuracy (all questions) | {pct(a['abstention_accuracy'])} |",
        f"| Abstention precision / recall (unanswerable questions) | {pct(a['abstention_precision'])} / "
        f"{pct(a['abstention_recall'])} |",
        "",
        "## IC challenger",
        "",
        "| Planted issue | Found | Argument |",
        "| --- | --- | --- |",
    ]
    for trap in c["traps"]:
        lines.append(f"| {trap['title']} | {'yes' if trap['found'] else 'no'} | {trap['argument'] or '-'} |")
    lines += [
        "",
        f"Trap recall: {pct(c['trap_recall'])}. Argument citation precision (quoted evidence found verbatim "
        f"in the cited chunk): {pct(c['argument_citation_precision'])}. Arguments raised: {len(c['arguments'])}.",
        "",
        "## Ingestion and data protection",
        "",
        "| Metric | Value |",
        "| --- | --- |",
    ]
    for file, value in i["ocr_character_accuracy"].items():
        lines.append(f"| OCR character accuracy, {file} | {pct(value)} |")
    lines += [
        f"| Personal-data strings found in the search index | {len(i['pii_leaked_into_index'])} of "
        f"{i['pii_strings']} |",
        f"| Personal-data strings left in redacted PDFs ({i['pdfs_with_pii']} files) | "
        f"{len(i['pii_left_in_redacted_pdfs'])} of {i['pii_strings']} |",
        "",
        "## Limitations",
        "",
        "- The corpus is synthetic and small; absolute scores are higher than on a real data room.",
        "- Questions share vocabulary with the documents, which favours BM25 and limits the measurable lift.",
        "- Thresholds and the lexical reranker were developed against this same gold set; there is no held-out split.",
        "- With the stub model, answer metrics measure retrieval and evidence selection, not generation.",
        "",
    ]
    return "\n".join(lines)


def evaluate(
    index_dir: Path, data_dir: Path, reports_dir: Path, llm: LLM | None = None, name: str = "eval"
) -> dict[str, Any]:
    from dealroom.ingestion.pipeline import load_chunks

    chunks = load_chunks(index_dir / "chunks.jsonl")
    gold = load_jsonl(data_dir / "eval" / "gold.jsonl")
    traps = json.loads((data_dir / "eval" / "traps.json").read_text())
    retriever = retriever_from_env(chunks)
    llm = llm or StubLLM()
    results = {
        "config": {
            "files": len(list((data_dir / "dataroom" / "files").iterdir())),
            "chunks": len(chunks),
            "questions": len(gold),
            "llm": llm.name,
            "reranker": retriever.reranker.name,
            "embedder": retriever.embedder.name,
        },
        "retrieval": retrieval_metrics(retriever, gold),
        "answers": answer_metrics(QAAgent(retriever, llm), gold),
        "challenger": challenger_metrics(retriever, traps),
        "ingestion": ingestion_metrics(chunks, data_dir / "dataroom"),
    }
    reports_dir.mkdir(parents=True, exist_ok=True)
    suffix = "" if name == "eval" else name.removeprefix("eval")
    (reports_dir / f"results{suffix}.json").write_text(json.dumps(results, indent=2, ensure_ascii=False) + "\n")
    (reports_dir / f"{name}.md").write_text(render_markdown(results))
    return results
