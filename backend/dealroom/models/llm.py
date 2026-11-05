"""Model layer: Azure OpenAI, OpenAI, and a deterministic stub for CI.

Agents never depend on a provider directly. They send a system prompt, a user
prompt and the numbered evidence; providers return text. Every provider output is
checked afterwards by the citation verifier, so a model that cites evidence it
was not given, or answers without a citation, is caught regardless of provider.
"""

from __future__ import annotations

import os
import re
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

import httpx


@dataclass(frozen=True)
class Evidence:
    """A verbatim span from a chunk, numbered for citation as [n]."""

    n: int
    chunk_id: str
    citation: str
    text: str


class LLM(Protocol):
    name: str

    def complete(self, system: str, prompt: str, evidence: list[Evidence]) -> str: ...


def render_evidence(evidence: list[Evidence]) -> str:
    return "\n".join(f"[{e.n}] ({e.citation}) {e.text}" for e in evidence)


class _ChatCompletions:
    name = "chat"

    def __init__(
        self,
        url: str,
        headers: Callable[[], dict[str, str]],
        model: str | None,
        client: httpx.Client | None,
        temperature: float = 0.0,
    ) -> None:
        self.url = url
        self.headers = headers
        self.model = model
        self.client = client or httpx.Client(timeout=120)
        self.temperature = temperature

    def complete(self, system: str, prompt: str, evidence: list[Evidence]) -> str:
        body: dict[str, object] = {
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": f"{prompt}\n\nEvidence:\n{render_evidence(evidence)}"},
            ],
            "temperature": self.temperature,
        }
        if self.model:
            body["model"] = self.model
        response = self.client.post(self.url, json=body, headers=self.headers())
        response.raise_for_status()
        return str(response.json()["choices"][0]["message"]["content"]).strip()


class AzureOpenAIChat(_ChatCompletions):
    name = "azure-openai"

    def __init__(
        self,
        endpoint: str,
        deployment: str,
        token_provider: Callable[[], str],
        api_version: str = "2024-10-21",
        client: httpx.Client | None = None,
    ) -> None:
        url = f"{endpoint.rstrip('/')}/openai/deployments/{deployment}/chat/completions?api-version={api_version}"
        super().__init__(url, lambda: {"Authorization": f"Bearer {token_provider()}"}, None, client)


class OpenAIChat(_ChatCompletions):
    name = "openai"

    def __init__(
        self,
        api_key: str,
        model: str = "gpt-4o-mini",
        client: httpx.Client | None = None,
        base_url: str = "https://api.openai.com/v1",
    ) -> None:
        super().__init__(f"{base_url}/chat/completions", lambda: {"Authorization": f"Bearer {api_key}"}, model, client)


class StubLLM:
    """Deterministic extractive model used in CI and the offline demo.

    It answers with the highest-ranked evidence span and cites it, which is
    exactly what the verifier expects from a real model. Numbers produced with the
    stub therefore measure retrieval and evidence selection, not generation.
    """

    name = "stub"

    def complete(self, system: str, prompt: str, evidence: list[Evidence]) -> str:
        if not evidence:
            return "INSUFFICIENT_EVIDENCE"
        chosen = evidence[:2] if "MULTI" in system else evidence[:1]
        return " ".join(f"{item.text} [{item.n}]" for item in chosen)


CITATION = re.compile(r"\[(\d+)\]")


def cited_numbers(text: str) -> list[int]:
    return [int(n) for n in CITATION.findall(text)]


def llm_from_env() -> LLM:
    provider = os.environ.get("DEALROOM_LLM", "stub")
    if provider == "azure":
        from dealroom.ingestion.azure_auth import CertificateCredential

        credential = CertificateCredential.from_files(
            os.environ["AZURE_TENANT_ID"],
            os.environ["AZURE_CLIENT_ID"],
            Path(os.environ["AZURE_CLIENT_KEY_PATH"]),
            Path(os.environ["AZURE_CLIENT_CERT_PATH"]),
        )
        return AzureOpenAIChat(os.environ["AZURE_OPENAI_ENDPOINT"], os.environ["AZURE_OPENAI_DEPLOYMENT"], credential)
    if provider == "openai":
        return OpenAIChat(os.environ["OPENAI_API_KEY"], os.environ.get("OPENAI_MODEL", "gpt-4o-mini"))
    return StubLLM()
