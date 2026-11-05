"""Ingestion pipeline: anonymise, extract, mask, chunk, persist.

Order matters. When the extractor is remote, the PDF is redacted *before* it is
sent, so the cloud service never receives personal data. Extracted text is then
masked again with the same vault, so the index and every model prompt contain
placeholders only. The vault and the masking log stay on the server.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path

from dealroom.ingestion.anonymiser import Anonymiser, Vault, jsonl_logger
from dealroom.ingestion.azure_auth import CertificateCredential
from dealroom.ingestion.chunker import Chunker, ChunkSettings
from dealroom.ingestion.extractors import AzureDocumentIntelligenceExtractor, Extractor, LocalExtractor, TesseractOcr
from dealroom.ingestion.models import Chunk

SUPPORTED = (".pdf", ".xlsx")


@dataclass
class IngestReport:
    files: int = 0
    chunks: int = 0
    masked: dict[str, int] = field(default_factory=dict)
    redacted_files: int = 0


def extractor_from_env() -> Extractor:
    """``DEALROOM_EXTRACTOR=azure`` switches to Document Intelligence; anything else stays local."""
    if os.environ.get("DEALROOM_EXTRACTOR", "local") != "azure":
        return LocalExtractor()
    credential = CertificateCredential.from_files(
        os.environ["AZURE_TENANT_ID"],
        os.environ["AZURE_CLIENT_ID"],
        Path(os.environ["AZURE_CLIENT_KEY_PATH"]),
        Path(os.environ["AZURE_CLIENT_CERT_PATH"]),
    )
    return AzureDocumentIntelligenceExtractor(os.environ["AZURE_DOCINTEL_ENDPOINT"], credential)


def ingest(
    files_dir: Path,
    out_dir: Path,
    extractor: Extractor | None = None,
    settings: ChunkSettings | None = None,
    redact_copies: bool = False,
) -> IngestReport:
    extractor = extractor or LocalExtractor()
    out_dir.mkdir(parents=True, exist_ok=True)
    log_path = out_dir / "anonymiser_log.jsonl"
    log_path.unlink(missing_ok=True)
    vault = Vault()
    report = IngestReport()

    write = jsonl_logger(log_path)

    def log(event: object) -> None:
        write(event)  # type: ignore[arg-type]
        kind = getattr(event, "type", "?")
        report.masked[kind] = report.masked.get(kind, 0) + 1

    anonymiser = Anonymiser(vault, log)
    chunker = Chunker(settings)
    ocr = TesseractOcr()
    remote = extractor.name != "local"
    chunks: list[Chunk] = []

    for path in sorted(p for p in files_dir.iterdir() if p.suffix.lower() in SUPPORTED):
        data = path.read_bytes()
        if path.suffix.lower() == ".pdf" and (remote or redact_copies):
            redacted = anonymiser.redact_pdf(data, file=path.name, ocr=ocr.words)
            report.redacted_files += 1
            if redact_copies:
                (out_dir / "redacted").mkdir(exist_ok=True)
                (out_dir / "redacted" / path.name).write_bytes(redacted)
            if remote:
                data = redacted  # only the redacted file ever crosses the trust boundary
        elements = extractor.extract(path.name, data)
        for element in elements:
            element.text = anonymiser.mask_text(element.text, file=path.name, page=element.page)
        chunks.extend(chunker.chunk(elements))
        report.files += 1

    report.chunks = len(chunks)
    save_chunks(chunks, out_dir / "chunks.jsonl")
    vault.save(out_dir / "vault.json")
    return report


def save_chunks(chunks: list[Chunk], path: Path) -> None:
    path.write_text("".join(json.dumps(c.to_dict(), ensure_ascii=False) + "\n" for c in chunks))


def load_chunks(path: Path) -> list[Chunk]:
    return [Chunk.from_dict(json.loads(line)) for line in path.read_text().splitlines() if line.strip()]
