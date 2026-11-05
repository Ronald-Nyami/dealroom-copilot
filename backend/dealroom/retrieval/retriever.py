"""Hybrid retrieval: BM25 and dense, fused with reciprocal rank fusion, then reranked."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import numpy as np

from dealroom.ingestion.models import Chunk
from dealroom.retrieval.bm25 import BM25
from dealroom.retrieval.embeddings import Embedder, LsaEmbedder
from dealroom.retrieval.rerank import LexicalCrossScorer, Reranker
from dealroom.retrieval.store import InMemoryVectorStore, VectorStore

Mode = Literal["bm25", "dense", "hybrid", "hybrid_rerank"]
MODES: tuple[Mode, ...] = ("bm25", "dense", "hybrid", "hybrid_rerank")


@dataclass(frozen=True)
class Hit:
    chunk: Chunk
    score: float
    rank: int


class Retriever:
    def __init__(
        self,
        chunks: list[Chunk],
        embedder: Embedder | None = None,
        store: VectorStore | None = None,
        reranker: Reranker | None = None,
        rrf_k: int = 60,
        candidates: int = 30,
    ) -> None:
        self.chunks = chunks
        self.by_id = {c.id: c for c in chunks}
        self.bm25 = BM25([c.text for c in chunks])
        self.embedder = embedder or LsaEmbedder()
        self.embedder.fit([c.text for c in chunks])
        self.store = store or InMemoryVectorStore()
        self.store.upsert(chunks, self.embedder.embed([c.text for c in chunks]))
        self.reranker = reranker or LexicalCrossScorer(chunks)
        self.rrf_k = rrf_k
        self.candidates = candidates

    def _bm25(self, query: str, k: int) -> list[tuple[str, float]]:
        scores = self.bm25.scores(query)
        order = np.argsort(-np.asarray(scores), kind="stable")[:k]
        return [(self.chunks[i].id, float(scores[i])) for i in order]

    def _dense(self, query: str, k: int) -> list[tuple[str, float]]:
        return self.store.search(self.embedder.embed([query])[0], k)

    def _fuse(self, *rankings: list[tuple[str, float]]) -> list[tuple[str, float]]:
        fused: dict[str, float] = {}
        for ranking in rankings:
            for rank, (chunk_id, _) in enumerate(ranking):
                fused[chunk_id] = fused.get(chunk_id, 0.0) + 1.0 / (self.rrf_k + rank + 1)
        return sorted(fused.items(), key=lambda item: (-item[1], item[0]))

    def search(self, query: str, k: int = 10, mode: Mode = "hybrid_rerank") -> list[Hit]:
        if mode == "bm25":
            ranked = self._bm25(query, k)
        elif mode == "dense":
            ranked = self._dense(query, k)
        else:
            pool = max(self.candidates, k)
            ranked = self._fuse(self._bm25(query, pool), self._dense(query, pool))[:pool]
            if mode == "hybrid_rerank":
                candidates = [self.by_id[i] for i, _ in ranked]
                scores = self.reranker.score(query, candidates)
                fused = {i: s for i, s in ranked}
                top = max(fused.values()) if fused else 1.0
                ranked = sorted(
                    ((c.id, s + 0.5 * fused[c.id] / top) for c, s in zip(candidates, scores, strict=True)),
                    key=lambda item: (-item[1], item[0]),
                )
            ranked = ranked[:k]
        return [Hit(self.by_id[i], s, r + 1) for r, (i, s) in enumerate(ranked)]


def retriever_from_env(chunks: list[Chunk]) -> Retriever:
    """Pick models and store from the environment.

    ``DEALROOM_RETRIEVAL=onnx`` uses pre-trained ONNX models (default: offline LSA and lexical reranker).
    ``DATABASE_URL`` stores vectors in Postgres + pgvector (default: in memory).
    """
    import os

    embedder: Embedder
    reranker: Reranker | None = None
    if os.environ.get("DEALROOM_RETRIEVAL", "local") == "onnx":  # pragma: no cover - needs model download
        from dealroom.retrieval.embeddings import OnnxEmbedder
        from dealroom.retrieval.rerank import CrossEncoderReranker

        embedder, reranker = OnnxEmbedder(), CrossEncoderReranker()
    else:
        embedder = LsaEmbedder()
    store: VectorStore | None = None
    dsn = os.environ.get("DATABASE_URL")
    if dsn:  # pragma: no cover - exercised by the postgres CI job
        from dealroom.retrieval.store import PgVectorStore

        embedder.fit([c.text for c in chunks])
        store = PgVectorStore(dsn, embedder.dimensions)
    return Retriever(chunks, embedder=embedder, store=store, reranker=reranker)
