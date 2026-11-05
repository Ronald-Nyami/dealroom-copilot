"""Vector stores: in-memory (CI, tests) and Postgres + pgvector (docker-compose, AKS)."""

from __future__ import annotations

import json
from typing import Any, Protocol

import numpy as np

from dealroom.ingestion.models import Chunk
from dealroom.retrieval.embeddings import Matrix


class VectorStore(Protocol):
    def upsert(self, chunks: list[Chunk], vectors: Matrix) -> None: ...

    def search(self, vector: Matrix, k: int) -> list[tuple[str, float]]: ...


class InMemoryVectorStore:
    def __init__(self) -> None:
        self.ids: list[str] = []
        self.matrix: Matrix = np.zeros((0, 0), dtype=np.float32)

    def upsert(self, chunks: list[Chunk], vectors: Matrix) -> None:
        self.ids = [c.id for c in chunks]
        self.matrix = vectors

    def search(self, vector: Matrix, k: int) -> list[tuple[str, float]]:
        if not self.ids:
            return []
        scores = self.matrix @ vector.reshape(-1)
        order = np.argsort(-scores, kind="stable")[:k]
        return [(self.ids[i], float(scores[i])) for i in order]


class PgVectorStore:
    """Chunks and embeddings in Postgres with an HNSW cosine index."""

    def __init__(self, dsn: str, dimensions: int, table: str = "chunks") -> None:
        import psycopg
        from pgvector.psycopg import register_vector

        self.table = table
        self.dimensions = dimensions
        self.conn: Any = psycopg.connect(dsn, autocommit=True)
        self.conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
        register_vector(self.conn)
        self.conn.execute(
            f"""
            CREATE TABLE IF NOT EXISTS {table} (
                id TEXT PRIMARY KEY,
                file TEXT NOT NULL,
                meta JSONB NOT NULL,
                text TEXT NOT NULL,
                embedding vector({dimensions}) NOT NULL
            )
            """
        )
        self.conn.execute(
            f"CREATE INDEX IF NOT EXISTS {table}_embedding_hnsw ON {table} USING hnsw (embedding vector_cosine_ops)"
        )

    def upsert(self, chunks: list[Chunk], vectors: Matrix) -> None:
        with self.conn.cursor() as cursor:
            cursor.execute(f"TRUNCATE {self.table}")
            for chunk, vector in zip(chunks, vectors, strict=True):
                meta = {k: v for k, v in chunk.to_dict().items() if k not in {"text", "id"}}
                cursor.execute(
                    f"INSERT INTO {self.table} (id, file, meta, text, embedding) VALUES (%s, %s, %s, %s, %s)",
                    (chunk.id, chunk.file, json.dumps(meta), chunk.text, vector),
                )

    def search(self, vector: Matrix, k: int) -> list[tuple[str, float]]:
        rows = self.conn.execute(
            f"SELECT id, 1 - (embedding <=> %s) AS score FROM {self.table} ORDER BY embedding <=> %s LIMIT %s",
            (vector.reshape(-1), vector.reshape(-1), k),
        ).fetchall()
        return [(str(r[0]), float(r[1])) for r in rows]
