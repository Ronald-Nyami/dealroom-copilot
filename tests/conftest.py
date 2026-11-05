from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from dealroom.agents.qa import QAAgent
from dealroom.ingestion.models import Chunk
from dealroom.ingestion.pipeline import ingest, load_chunks
from dealroom.models.llm import StubLLM
from dealroom.retrieval.retriever import Retriever

REPO = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="session")
def root(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """A disposable project root with the committed data room and a fresh index."""
    base = tmp_path_factory.mktemp("workspace")
    shutil.copytree(REPO / "data", base / "data")
    ingest(base / "data" / "dataroom" / "files", base / ".cache" / "index")
    return base


@pytest.fixture(scope="session")
def chunks(root: Path) -> list[Chunk]:
    return load_chunks(root / ".cache" / "index" / "chunks.jsonl")


@pytest.fixture(scope="session")
def retriever(chunks: list[Chunk]) -> Retriever:
    return Retriever(chunks)


@pytest.fixture(scope="session")
def qa(retriever: Retriever) -> QAAgent:
    return QAAgent(retriever, StubLLM())
