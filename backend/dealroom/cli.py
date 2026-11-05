"""Command line: dealroom generate | ingest | eval | ask | demo."""

from __future__ import annotations

import argparse
import json
import os
import uuid
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from dealroom.retrieval.retriever import Retriever


def root() -> Path:
    return Path(os.environ.get("DEALROOM_ROOT", Path.cwd()))


def index_dir() -> Path:
    return root() / ".cache" / "index"


def _retriever() -> Retriever:
    from dealroom.ingestion.pipeline import load_chunks
    from dealroom.retrieval.retriever import retriever_from_env

    if not (index_dir() / "chunks.jsonl").exists():
        cmd_ingest(argparse.Namespace(redact_copies=False))
    return retriever_from_env(load_chunks(index_dir() / "chunks.jsonl"))


def cmd_generate(_: argparse.Namespace) -> None:
    from dealroom.synth.gold import write_eval_files
    from dealroom.synth.render import build

    truth = build(root() / "data" / "dataroom")
    print(f"data room: {len(truth)} files; gold set: {write_eval_files(root() / 'data' / 'eval')} questions")


def cmd_ingest(args: argparse.Namespace) -> None:
    from dealroom.ingestion.pipeline import extractor_from_env, ingest

    report = ingest(
        root() / "data" / "dataroom" / "files", index_dir(), extractor_from_env(), redact_copies=args.redact_copies
    )
    print(f"ingested {report.files} files into {report.chunks} chunks; masked {report.masked}")


def cmd_eval(_: argparse.Namespace) -> None:
    from dealroom.evaluation.run import evaluate
    from dealroom.models.llm import llm_from_env

    if not (index_dir() / "chunks.jsonl").exists():
        cmd_ingest(argparse.Namespace(redact_copies=False))
    name = "eval_onnx" if os.environ.get("DEALROOM_RETRIEVAL") == "onnx" else "eval"
    results = evaluate(index_dir(), root() / "data", root() / "reports", llm_from_env(), name=name)
    best = results["retrieval"]["hybrid_rerank"]
    print(
        f"recall@10 {best['recall@10']:.3f}  ndcg@10 {best['ndcg@10']:.3f}  "
        f"trap recall {results['challenger']['trap_recall']:.0%}  -> reports/{name}.md"
    )


def cmd_ask(args: argparse.Namespace) -> None:
    from dealroom.agents.qa import QAAgent
    from dealroom.models.llm import llm_from_env

    print(json.dumps(QAAgent(_retriever(), llm_from_env()).answer(args.question).to_dict(), indent=2))


def cmd_demo(_: argparse.Namespace) -> None:
    """Offline walk-through: question -> cited answer -> memo -> challenger -> review -> approval."""
    from dealroom.agents.challenger import Challenger
    from dealroom.agents.graph import build_deal_graph, resume, start
    from dealroom.agents.memo import Memo, MemoDrafter, Section, Sentence
    from dealroom.agents.qa import QAAgent
    from dealroom.models.llm import Evidence, llm_from_env

    retriever = _retriever()
    qa = QAAgent(retriever, llm_from_env())
    for question in ("What was audited net revenue in FY2025?", "What is the CEO's annual salary?"):
        answer = qa.answer(question)
        refs = "; ".join(c.citation for c in answer.citations) or "-"
        print(f"Q: {question}\nA: {answer.text}\n   sources: {refs}\n")
    graph = build_deal_graph(MemoDrafter(qa), Challenger(retriever))
    thread = str(uuid.uuid4())
    state = start(graph, thread)
    print(f"Memo drafted ({len(state['memo']['sections'])} sections), state: {state['review']['state']}")
    print("Challenger:")
    for argument in state["arguments"]:
        print(f"  [{argument['severity']}] {argument['title']}")
    state = resume(graph, thread, {"action": "approve", "actor": "Demo Partner", "role": "partner"})
    print(f"Approval without responses -> refused: {state['error'][:80]}...")
    responses = {
        a["title"]: "Accepted; condition precedent added to the term sheet."
        for a in state["arguments"]
        if a["severity"] == "high"
    }
    state = resume(
        graph, thread, {"action": "approve", "actor": "Demo Partner", "role": "partner", "responses": responses}
    )
    print(f"After responses -> {state['review']['state']} by Demo Partner")
    memo = Memo(
        state["memo"]["title"],
        [
            Section(
                s["title"],
                [Sentence(x["text"], [Evidence(**c) for c in x["citations"]]) for x in s["sentences"]],
                s["unanswered"],
            )
            for s in state["memo"]["sections"]
        ],
    )
    out = root() / "reports" / "demo_memo.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(memo.to_markdown())
    print(f"Memo written to {out.relative_to(root())}")


def cmd_real(args: argparse.Namespace) -> None:
    """Real public data: fetch the pinned sources, index the filings, evaluate both tracks."""
    from dealroom.models.llm import llm_from_env
    from dealroom.realdata import fetch, financebench, report

    cache = root() / ".cache" / "real"
    if args.step in {"fetch", "all"}:
        print(f"fetched {fetch.fetch(root() / 'data' / 'real' / 'manifest.json', cache)} files")
    if args.step in {"index", "all"}:
        built = financebench.build_indexes(
            cache / "financebench" / "pdfs", cache / "financebench" / "index", workers=args.workers
        )
        print(f"indexed {len(built)} filings into {sum(built.values())} chunks")
    if args.step in {"eval", "all"}:
        results = report.run(cache, root() / "reports", llm_from_env())
        best = results["financebench"]["retrieval"]["hybrid_rerank"]
        print(
            f"FinanceBench page hit@10 {best['page_hit@10']:.3f}; CUAD v2 F1 "
            f"{results['cuad']['v2_provision']['f1']:.3f} -> reports/eval_real.md"
        )


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="dealroom")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("generate").set_defaults(func=cmd_generate)
    ingest = sub.add_parser("ingest")
    ingest.add_argument("--redact-copies", action="store_true", help="also write redacted PDFs for inspection")
    ingest.set_defaults(func=cmd_ingest)
    sub.add_parser("eval").set_defaults(func=cmd_eval)
    ask = sub.add_parser("ask")
    ask.add_argument("question")
    ask.set_defaults(func=cmd_ask)
    sub.add_parser("demo").set_defaults(func=cmd_demo)
    real = sub.add_parser("real", help="evaluation on real public data (FinanceBench, CUAD)")
    real.add_argument("step", choices=["fetch", "index", "eval", "all"])
    real.add_argument("--workers", type=int, default=2)
    real.set_defaults(func=cmd_real)
    args = parser.parse_args(argv)
    args.func(args)


if __name__ == "__main__":  # pragma: no cover
    main()
