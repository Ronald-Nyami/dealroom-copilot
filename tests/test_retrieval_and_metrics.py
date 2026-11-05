from __future__ import annotations

import json
from pathlib import Path

import httpx
import numpy as np
import pytest

from dealroom.evaluation import metrics
from dealroom.ingestion.models import Chunk
from dealroom.retrieval.bm25 import BM25
from dealroom.retrieval.embeddings import AzureOpenAIEmbedder, LsaEmbedder
from dealroom.retrieval.rerank import LexicalCrossScorer
from dealroom.retrieval.retriever import MODES, Retriever, retriever_from_env
from dealroom.retrieval.store import InMemoryVectorStore
from dealroom.retrieval.text import fiscal_year, numbers, stem, tokens


def test_tokenizer_normalises_years_numbers_and_possessives() -> None:
    assert fiscal_year("fy2027e") == "fy2027" and fiscal_year("fy26") == "fy2026" and fiscal_year("rent") == "rent"
    assert tokens("The CEO's FY2027E revenue of 1,200.50") == ["ceo", "fy2027", "revenu", "1200.5"]
    assert stem("expires") == stem("expire") == "expir"
    assert numbers("CHF 2.85 million, -6.7 and 21,400") == {"2.85", "6.7", "21400"}


def test_bm25_ranks_the_matching_document_first() -> None:
    scores = BM25(["annual rent CHF 2.85 million", "customer contract", "rent of the warehouse"]).scores("annual rent")
    assert int(np.argmax(scores)) == 0 and scores[1] == 0


def test_lsa_embedder_requires_fit() -> None:
    with pytest.raises(RuntimeError):
        LsaEmbedder().embed(["x"])


def test_in_memory_store_empty_and_filled() -> None:
    store = InMemoryVectorStore()
    assert store.search(np.ones(2, dtype=np.float32), 3) == []
    chunks = [Chunk("a", "a", "paragraph", page=1), Chunk("b", "b", "paragraph", page=1)]
    store.upsert(chunks, np.eye(2, dtype=np.float32))
    assert store.search(np.array([0, 1], dtype=np.float32), 1)[0][0] == chunks[1].id


def test_azure_embedder_batches_and_normalises() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        texts = json.loads(request.content)["input"]
        return httpx.Response(200, json={"data": [{"index": i, "embedding": [3.0, 4.0]} for i in range(len(texts))]})

    embedder = AzureOpenAIEmbedder(
        "https://aoai.example",
        "emb",
        lambda: "t",
        dimensions=2,
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        batch_size=2,
    )
    embedder.fit(["ignored"])
    vectors = embedder.embed(["a", "b", "c"])
    assert vectors.shape == (3, 2) and np.allclose(vectors[0], [0.6, 0.8])


def test_all_modes_return_ranked_hits(retriever: Retriever) -> None:
    for mode in MODES:
        hits = retriever.search("annual base rent Thun lease", 5, mode)
        assert len(hits) == 5 and hits[0].rank == 1
        assert any("lease_agreement_thun" in h.chunk.file for h in hits[:3])


def test_reranker_prefers_the_matching_table_row(chunks: list[Chunk]) -> None:
    scorer = LexicalCrossScorer(chunks)
    model = next(c for c in chunks if c.sheet == "LBO" and c.row_start == 14)
    other = next(c for c in chunks if c.file.startswith("14_"))
    scores = scorer.score("FY2026 net leverage covenant", [other, model])
    assert scores[1] > scores[0]


def test_retriever_from_env_defaults_to_offline(chunks: list[Chunk], monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DEALROOM_RETRIEVAL", raising=False)
    assert retriever_from_env(chunks[:20]).embedder.name == "local-lsa"


def test_retrieval_metrics() -> None:
    a = Chunk("a.pdf", "x", "paragraph", page=1)
    b = Chunk("b.pdf", "y", "paragraph", page=2)
    evidence = [{"file": "b.pdf", "page": 2}, {"file": "c.pdf", "page": 1}]
    assert metrics.recall_at_k([a, b], evidence, 1) == 0.0
    assert metrics.recall_at_k([a, b], evidence, 2) == 0.5
    assert metrics.recall_at_k([a], [], 2) == 0.0
    assert metrics.reciprocal_rank([a, b], evidence) == 0.5
    assert metrics.reciprocal_rank([a], evidence) == 0.0
    assert metrics.ndcg_at_k([b, a], evidence[:1], 10) == pytest.approx(1.0)
    assert metrics.ndcg_at_k([a], [], 10) == 0.0


def test_answer_metrics() -> None:
    assert metrics.value_found(0.128, "Share of revenue: 12.8%")
    assert metrics.value_found(132.0, "Senior term loan B | 132")
    assert not metrics.value_found(4.38, "4.50x")
    assert metrics.grounded("Rent is CHF 2.85 million", ["The annual base rent is CHF 2.85 million"])
    assert metrics.grounded("", [])
    assert not metrics.grounded("Revenue fell sharply", ["Rent is CHF 2.85 million"])
    assert metrics.levenshtein("kitten", "sitting") == 3
    assert metrics.character_accuracy("abc", "abd") == pytest.approx(2 / 3)
    assert metrics.character_accuracy("", "x") == 1.0
    assert metrics.mean([]) == 0.0


@pytest.mark.postgres
def test_pgvector_store_round_trip(chunks: list[Chunk]) -> None:  # pragma: no cover - needs DATABASE_URL
    import os

    dsn = os.environ.get("DATABASE_URL")
    if not dsn:
        pytest.skip("DATABASE_URL not set")
    from dealroom.retrieval.store import PgVectorStore

    embedder = LsaEmbedder()
    embedder.fit([c.text for c in chunks])
    store = PgVectorStore(dsn, embedder.dimensions, table="test_chunks")
    store.upsert(chunks, embedder.embed([c.text for c in chunks]))
    target = next(c for c in chunks if "lease_agreement_thun" in c.file)
    assert store.search(embedder.embed([target.text])[0], 1)[0][0] == target.id


def test_eval_files_exist() -> None:
    root = Path(__file__).resolve().parents[1]
    assert (root / "data" / "eval" / "gold.jsonl").exists()
