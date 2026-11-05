"""Workspace: one object that owns the index, the agents, the deal graph and the guard.

The FastAPI app and the MCP server both call ``Workspace.guard.call`` so that a
human clicking in the web app and an agent calling an MCP tool are subject to the
same policy and land in the same audit log.
"""

from __future__ import annotations

import json
import os
import re
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from dealroom.agents.challenger import Challenger
from dealroom.agents.graph import build_deal_graph, resume, start
from dealroom.agents.memo import MemoDrafter
from dealroom.agents.qa import QAAgent
from dealroom.ingestion.anonymiser import Anonymiser, Vault
from dealroom.ingestion.pipeline import ingest, load_chunks
from dealroom.models.llm import LLM, llm_from_env
from dealroom.retrieval.retriever import Retriever, retriever_from_env
from dealroom_mcp.audit import AuditLog
from dealroom_mcp.guard import Guard, Identity

METRIC_QUESTIONS = {
    "revenue": "What was net revenue in FY{year}?",
    "EBITDA": "What was EBITDA in FY{year}?",
    "net income": "What was net income in FY{year}?",
    "net debt": "What net debt does the model show for FY{year}?",
    "cash": "How much cash did the company hold at 31 December {year}?",
    "capex": "What is total capex planned for FY{year}?",
    "net leverage": "What net leverage does the model show for FY{year}?",
}


@dataclass
class Workspace:
    root: Path
    llm: LLM
    retriever: Retriever
    anonymiser: Anonymiser
    guard: Guard = field(init=False)
    items: list[dict[str, Any]] = field(default_factory=list)
    memo_threads: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.qa = QAAgent(self.retriever, self.llm)
        self.challenger = Challenger(self.retriever)
        self.drafter = MemoDrafter(self.qa)
        self.graph = build_deal_graph(self.drafter, self.challenger)
        self.by_id = {c.id: c for c in self.retriever.chunks}
        self.guard = Guard(
            AuditLog(self.root / ".cache" / "audit.jsonl"),
            {
                "search_dataroom": self.search,
                "get_document_excerpt": self.excerpt,
                "get_financial_metric": self.metric,
                "create_diligence_item": self.create_item,
                "draft_memo": self.draft_memo,
                "export_memo": self.export_memo,
            },
            mask=lambda text: self.anonymiser.mask_text(text, log=False),
        )

    # ------------------------------------------------------------------ construction

    @classmethod
    def load(cls, root: Path, llm: LLM | None = None) -> Workspace:
        index = root / ".cache" / "index"
        if not (index / "chunks.jsonl").exists():
            ingest(root / "data" / "dataroom" / "files", index)
        chunks = load_chunks(index / "chunks.jsonl")
        vault = Vault.load(index / "vault.json")
        return cls(root, llm or llm_from_env(), retriever_from_env(chunks), Anonymiser(vault))

    # ------------------------------------------------------------------ tool handlers

    def search(self, query: str, k: int = 5) -> list[dict[str, Any]]:
        masked = self.anonymiser.mask_text(query, log=False)
        return [
            {
                "chunk_id": h.chunk.id,
                "citation": h.chunk.citation,
                "score": round(h.score, 4),
                "text": h.chunk.text[:600],
            }
            for h in self.retriever.search(masked, k)
        ]

    def excerpt(self, chunk_id: str) -> dict[str, Any]:
        chunk = self.by_id[chunk_id]
        return {"chunk_id": chunk.id, "citation": chunk.citation, "text": chunk.text}

    def metric(self, metric: str, year: int) -> dict[str, Any]:
        answer = self.qa.answer(METRIC_QUESTIONS[metric].format(year=year))
        return answer.to_dict()

    def ask(self, question: str, multi: bool = False) -> dict[str, Any]:
        masked = self.anonymiser.mask_text(question, log=False)
        return self.qa.answer(masked, multi=multi).to_dict()

    def create_item(self, title: str, description: str, severity: str, evidence_chunk_ids: list[str]) -> dict[str, Any]:
        unknown = [c for c in evidence_chunk_ids if c not in self.by_id]
        if unknown:
            raise KeyError(f"unknown evidence {unknown}")
        item = {
            "id": str(uuid.uuid4()),
            "title": title,
            "description": description,
            "severity": severity,
            "evidence": [{"chunk_id": c, "citation": self.by_id[c].citation} for c in evidence_chunk_ids],
        }
        self.items.append(item)
        return item

    def draft_memo(self) -> dict[str, Any]:
        thread = str(uuid.uuid4())
        state = start(self.graph, thread)
        self.memo_threads.append(thread)
        return {"memo_id": thread, **state}

    def memo_state(self, memo_id: str) -> dict[str, Any]:
        config = {"configurable": {"thread_id": memo_id}}
        return {"memo_id": memo_id, **dict(self.graph.get_state(config).values)}

    def review(self, memo_id: str, decision: dict[str, Any]) -> dict[str, Any]:
        return {"memo_id": memo_id, **resume(self.graph, memo_id, decision)}

    def export_memo(self, format: str = "markdown") -> dict[str, Any]:
        approved = [
            m for m in (self.memo_state(t) for t in self.memo_threads) if m.get("review", {}).get("state") == "approved"
        ]
        if not approved:
            raise LookupError("no approved memo to export")
        memo = approved[-1]
        lines = [f"# {memo['memo']['title']}", ""]
        for section in memo["memo"]["sections"]:
            lines += [f"## {section['title']}", ""]
            lines += [
                f"- {s['text']} ({'; '.join(c['citation'] for c in s['citations'])})" for s in section["sentences"]
            ]
            lines.append("")
        out = self.root / "reports" / f"ic_memo_{memo['memo_id'][:8]}.md"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text("\n".join(lines))
        return {"path": str(out.relative_to(self.root)), "memo_id": memo["memo_id"]}

    # ------------------------------------------------------------------ helpers for the API

    def documents(self) -> list[dict[str, Any]]:
        truth = json.loads((self.root / "data" / "dataroom" / "ground_truth.json").read_text())
        counts: dict[str, int] = {}
        for chunk in self.retriever.chunks:
            counts[chunk.file] = counts.get(chunk.file, 0) + 1
        return [
            {"file": f, "title": v["title"], "kind": v["kind"], "chunks": counts.get(f, 0)}
            for f, v in sorted(truth.items())
        ]

    def document_chunks(self, file: str) -> list[dict[str, Any]]:
        if not re.fullmatch(r"[\w.-]+", file):
            raise KeyError(file)
        return [c.to_dict() for c in self.retriever.chunks if c.file == file]


def identity_from_env() -> Identity:
    return Identity(os.environ.get("DEALROOM_USER", "local-analyst"), os.environ.get("DEALROOM_ROLE", "analyst"))
