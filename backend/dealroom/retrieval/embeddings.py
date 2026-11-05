"""Embedding models.

``LsaEmbedder`` is a small local model: TF-IDF over words and character
n-grams, reduced with truncated SVD and L2-normalised. It is fitted on the
corpus, needs no network or GPU, and is deterministic, which is what CI needs.
``AzureOpenAIEmbedder`` calls an Azure OpenAI embedding deployment through the
private endpoint with an Entra ID token.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Protocol

import httpx
import numpy as np
from numpy.typing import NDArray
from scipy.sparse import hstack
from sklearn.decomposition import TruncatedSVD
from sklearn.feature_extraction.text import TfidfVectorizer

Matrix = NDArray[np.float32]


class Embedder(Protocol):
    name: str
    dimensions: int

    def fit(self, texts: list[str]) -> None: ...

    def embed(self, texts: list[str]) -> Matrix: ...


def _normalise(matrix: NDArray[np.float64]) -> Matrix:
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    normalised: Matrix = (matrix / norms).astype(np.float32)
    return normalised


class LsaEmbedder:
    name = "local-lsa"

    def __init__(self, dimensions: int = 96, seed: int = 7) -> None:
        self.dimensions = dimensions
        self.seed = seed
        self.words = TfidfVectorizer(sublinear_tf=True, ngram_range=(1, 2), min_df=1, stop_words="english")
        self.chars = TfidfVectorizer(sublinear_tf=True, analyzer="char_wb", ngram_range=(3, 5), min_df=1)
        self.svd: TruncatedSVD | None = None

    def fit(self, texts: list[str]) -> None:
        sparse = hstack([self.words.fit_transform(texts), self.chars.fit_transform(texts)]).tocsr()
        components = max(2, min(self.dimensions, sparse.shape[0] - 1, sparse.shape[1] - 1))
        self.svd = TruncatedSVD(n_components=components, random_state=self.seed)
        self.svd.fit(sparse)
        self.dimensions = components

    def embed(self, texts: list[str]) -> Matrix:
        if self.svd is None:
            raise RuntimeError("LsaEmbedder.fit must be called first")
        sparse = hstack([self.words.transform(texts), self.chars.transform(texts)]).tocsr()
        return _normalise(self.svd.transform(sparse))


class AzureOpenAIEmbedder:
    name = "azure-openai"

    def __init__(
        self,
        endpoint: str,
        deployment: str,
        token_provider: Callable[[], str],
        dimensions: int = 1536,
        api_version: str = "2024-10-21",
        client: httpx.Client | None = None,
        batch_size: int = 64,
    ) -> None:
        self.endpoint = endpoint.rstrip("/")
        self.deployment = deployment
        self.token_provider = token_provider
        self.dimensions = dimensions
        self.api_version = api_version
        self.client = client or httpx.Client(timeout=60)
        self.batch_size = batch_size

    def fit(self, texts: list[str]) -> None:
        return None  # pre-trained model

    def embed(self, texts: list[str]) -> Matrix:
        url = f"{self.endpoint}/openai/deployments/{self.deployment}/embeddings?api-version={self.api_version}"
        vectors: list[list[float]] = []
        for start in range(0, len(texts), self.batch_size):
            response = self.client.post(
                url,
                json={"input": texts[start : start + self.batch_size], "dimensions": self.dimensions},
                headers={"Authorization": f"Bearer {self.token_provider()}"},
            )
            response.raise_for_status()
            data = sorted(response.json()["data"], key=lambda item: item["index"])
            vectors.extend(item["embedding"] for item in data)
        return _normalise(np.asarray(vectors, dtype=np.float64))


class OnnxEmbedder:  # pragma: no cover - needs the optional model download (extra "onnx")
    """Pre-trained sentence embeddings (default BAAI/bge-small-en-v1.5) on CPU through ONNX Runtime."""

    name = "onnx-bge-small"

    def __init__(self, model: str = "BAAI/bge-small-en-v1.5") -> None:
        from fastembed import TextEmbedding

        self.model = TextEmbedding(model)
        self.dimensions = 384

    def fit(self, texts: list[str]) -> None:
        return None

    def embed(self, texts: list[str]) -> Matrix:
        return _normalise(np.asarray(list(self.model.embed(texts)), dtype=np.float64))
