from __future__ import annotations

import base64
import datetime as dt
import io
import json
from pathlib import Path
from typing import Any

import httpx
import pymupdf
import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.x509.oid import NameOID
from PIL import Image, ImageDraw, ImageFont

from dealroom.ingestion import pipeline
from dealroom.ingestion.anonymiser import Anonymiser, MaskEvent, Vault, detect, jsonl_logger, placeholders_in
from dealroom.ingestion.azure_auth import CertificateCredential, pem_block
from dealroom.ingestion.chunker import Chunker, ChunkSettings, document_label
from dealroom.ingestion.extractors import AzureDocumentIntelligenceExtractor, LocalExtractor, TesseractOcr, extract_xlsx
from dealroom.ingestion.models import Chunk, Element
from dealroom.synth import spec

FILES = Path(__file__).resolve().parents[1] / "data" / "dataroom" / "files"

# ------------------------------------------------------------------ anonymiser


def test_detects_each_kind_of_personal_data() -> None:
    text = (
        "Corinne Vasseli (corinne.vasseli@alpine-precision.example, +41 33 555 01 10) lives at "
        "Seestrasse 7, 3700 Spiez; IBAN CH93 0076 2011 6238 5295 7."
    )
    kinds = {m.type for m in detect(text)}
    assert kinds == {"PERSON", "EMAIL", "PHONE", "ADDRESS", "IBAN"}


def test_mask_is_consistent_reversible_and_logged() -> None:
    events: list[MaskEvent] = []
    anonymiser = Anonymiser(Vault(), events.append)
    first = anonymiser.mask_text("Tobias Arnhold joined in 2019.", file="a.pdf", page=1)
    second = anonymiser.mask_text("Later Arnhold signed the contract.", file="b.pdf", page=2)
    assert first == "[PERSON_001] joined in 2019."
    assert second == "Later [PERSON_001] signed the contract."
    assert anonymiser.unmask(second) == "Later Tobias Arnhold signed the contract."
    assert all("Arnhold" not in e.to_json() for e in events)
    assert placeholders_in([first, second]) == {"[PERSON_001]"}


def test_vault_round_trip_and_logger(tmp_path: Path) -> None:
    vault = Vault()
    vault.placeholder("EMAIL", "x@y.example")
    vault.save(tmp_path / "vault.json")
    assert Vault.load(tmp_path / "vault.json").forward == {"x@y.example": "[EMAIL_001]"}
    assert Vault.load(tmp_path / "none.json").forward == {}
    log = jsonl_logger(tmp_path / "log.jsonl")
    log(MaskEvent("f", 1, "EMAIL", "[EMAIL_001]", "abc"))
    assert json.loads((tmp_path / "log.jsonl").read_text())["placeholder"] == "[EMAIL_001]"


def test_redacted_pdf_holds_no_personal_data() -> None:
    redacted = Anonymiser().redact_pdf((FILES / spec.CVS.filename).read_bytes(), file=spec.CVS.filename)
    text = " ".join(" ".join(p.get_text().split()) for p in pymupdf.open(stream=redacted, filetype="pdf"))
    for value in spec.PII:
        assert value not in text
    assert "[PERSON_001]" in text


def test_scanned_page_is_redacted_from_local_ocr(tmp_path: Path) -> None:
    image = Image.new("L", (1654, 600), 255)
    font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf", 40)
    ImageDraw.Draw(image).text((100, 200), "Contact jane.doe@example.org today", fill=0, font=font)
    buffer = io.BytesIO()
    image.save(buffer, "PDF", resolution=200.0)
    events: list[MaskEvent] = []
    redacted = Anonymiser(Vault(), events.append).redact_pdf(
        buffer.getvalue(), file="scan.pdf", ocr=TesseractOcr().words
    )
    page = pymupdf.open(stream=redacted, filetype="pdf")[0]
    assert "jane.doe" not in TesseractOcr().text(page.get_pixmap(dpi=200).tobytes("png"))
    assert [e.type for e in events] == ["EMAIL"]


# ------------------------------------------------------------------ extractors


def test_local_extractor_keeps_tables_and_headings() -> None:
    elements = LocalExtractor().extract(spec.FS25.filename, (FILES / spec.FS25.filename).read_bytes())
    tables = [e for e in elements if e.kind == "table"]
    assert any("Net revenue | 142.3" in t.text and t.text.startswith("Income statement") for t in tables)
    assert any(e.kind == "heading" and e.page == 2 for e in elements)


def test_local_extractor_ocrs_image_only_pages() -> None:
    elements = LocalExtractor().extract(
        spec.SCAN_BANK_LETTER.filename, (FILES / spec.SCAN_BANK_LETTER.filename).read_bytes()
    )
    assert elements[0].kind == "ocr" and "38.0 million" in elements[0].text


def test_xlsx_keeps_empty_cells_in_place() -> None:
    rows = extract_xlsx(spec.MODEL.filename, (FILES / spec.MODEL.filename).read_bytes())
    nwc = next(e for e in rows if e.text.startswith("Net working capital build"))
    assert nwc.text.split(" | ")[1:3] == ["", "-6.7"]
    assert nwc.sheet == "Cash flow" and nwc.row_start == 3


def _di_transport(calls: list[str]) -> httpx.MockTransport:
    result = {
        "status": "succeeded",
        "analyzeResult": {
            "paragraphs": [
                {
                    "content": "Lease agreement",
                    "role": "title",
                    "boundingRegions": [{"pageNumber": 1}],
                    "spans": [{"offset": 0, "length": 15}],
                },
                {
                    "content": "Rent is CHF 2.85 million.",
                    "boundingRegions": [{"pageNumber": 1}],
                    "spans": [{"offset": 16, "length": 25}],
                },
                {"content": "Line", "spans": [{"offset": 50, "length": 4}]},
            ],
            "tables": [
                {
                    "spans": [{"offset": 50, "length": 20}],
                    "boundingRegions": [{"pageNumber": 2}],
                    "caption": {"content": "Rent schedule"},
                    "cells": [
                        {"rowIndex": 0, "columnIndex": 0, "content": "Line"},
                        {"rowIndex": 0, "columnIndex": 1, "content": "CHF m"},
                        {"rowIndex": 1, "columnIndex": 0, "content": "Rent"},
                        {"rowIndex": 1, "columnIndex": 1, "content": "2.85"},
                    ],
                }
            ],
        },
    }
    polls = iter([{"status": "running"}, result])

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(f"{request.method} {request.url.path} {request.headers.get('Authorization')}")
        if request.method == "POST":
            return httpx.Response(202, headers={"Operation-Location": "https://di.example/ops/1"})
        return httpx.Response(200, json=next(polls))

    return httpx.MockTransport(handler)


def test_document_intelligence_adapter_maps_layout() -> None:
    calls: list[str] = []
    extractor = AzureDocumentIntelligenceExtractor(
        "https://di.example/", lambda: "token-1", httpx.Client(transport=_di_transport(calls)), poll_interval=0
    )
    elements = extractor.extract("lease.pdf", b"%PDF-1.4")
    assert [e.kind for e in elements] == ["heading", "paragraph", "table"]
    assert elements[2].text == "Rent schedule\nLine | CHF m\nRent | 2.85" and elements[2].page == 2
    assert calls[0].startswith("POST /documentintelligence/documentModels/prebuilt-layout:analyze")
    assert all(c.endswith("Bearer token-1") for c in calls)
    assert extractor.extract(spec.CAPEX.filename, (FILES / spec.CAPEX.filename).read_bytes())[0].kind == "rows"


def test_document_intelligence_adapter_reports_failure_and_timeout() -> None:
    failed = httpx.MockTransport(
        lambda r: (
            httpx.Response(202, headers={"Operation-Location": "https://x/o"})
            if r.method == "POST"
            else httpx.Response(200, json={"status": "failed", "error": "bad"})
        )
    )
    with pytest.raises(RuntimeError):
        AzureDocumentIntelligenceExtractor("https://x", lambda: "t", httpx.Client(transport=failed)).analyze(b"")
    running = httpx.MockTransport(
        lambda r: (
            httpx.Response(202, headers={"Operation-Location": "https://x/o"})
            if r.method == "POST"
            else httpx.Response(200, json={"status": "running"})
        )
    )
    with pytest.raises(TimeoutError):
        AzureDocumentIntelligenceExtractor(
            "https://x", lambda: "t", httpx.Client(transport=running), poll_interval=0, max_polls=2
        ).analyze(b"")


# ------------------------------------------------------------------ certificate credential


def _key_and_cert() -> tuple[bytes, bytes, rsa.RSAPrivateKey]:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "dealroom-copilot-test")])
    now = dt.datetime.now(dt.UTC)
    cert = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(1)
        .not_valid_before(now)
        .not_valid_after(now + dt.timedelta(days=1))
        .sign(key, hashes.SHA256())
    )
    key_pem = key.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
    )
    return key_pem, cert.public_bytes(serialization.Encoding.PEM), key


def _b64decode(part: str) -> bytes:
    return base64.urlsafe_b64decode(part + "=" * (-len(part) % 4))


def test_certificate_credential_signs_a_valid_assertion_and_caches_token(tmp_path: Path) -> None:
    key_pem, cert_pem, key = _key_and_cert()
    (tmp_path / "k.pem").write_bytes(key_pem)
    (tmp_path / "c.pem").write_bytes(cert_pem)
    seen: list[dict[str, Any]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        form = dict(x.split("=", 1) for x in request.content.decode().split("&"))
        seen.append(form)
        return httpx.Response(200, json={"access_token": "abc", "expires_in": 3600})

    credential = CertificateCredential.from_files(
        "tenant",
        "client",
        tmp_path / "k.pem",
        tmp_path / "c.pem",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    assert credential() == "abc" and credential() == "abc"
    assert len(seen) == 1 and seen[0]["grant_type"] == "client_credentials"
    header, claims, signature = credential.client_assertion(now=1_700_000_000).split(".")
    assert json.loads(_b64decode(header))["alg"] == "PS256"
    assert json.loads(_b64decode(claims))["aud"].endswith("/tenant/oauth2/v2.0/token")
    key.public_key().verify(
        _b64decode(signature),
        f"{header}.{claims}".encode(),
        padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.DIGEST_LENGTH),
        hashes.SHA256(),
    )


# ------------------------------------------------------------------ chunker and pipeline


def test_chunker_splits_long_text_with_overlap_and_long_tables() -> None:
    sentence = "The plant produced many parts this year. "
    elements = [
        Element("f.pdf", "heading", "Section A", page=1),
        Element("f.pdf", "paragraph", sentence * 40, page=1),
        Element("f.pdf", "table", "Caption\nA | B\n" + "\n".join(f"row {i} | {i}" for i in range(400)), page=2),
    ]
    chunks = Chunker(ChunkSettings(max_chars=300, overlap_chars=80, max_table_chars=800)).chunk(elements)
    paragraphs = [c for c in chunks if c.kind == "paragraph"]
    tables = [c for c in chunks if c.kind == "table"]
    assert len(paragraphs) > 3 and all(c.section == "Section A" for c in paragraphs)
    assert paragraphs[1].text.split("\n", 1)[1].startswith("The plant produced")
    assert len(tables) > 1 and all("Caption\nA | B" in t.text for t in tables)
    assert document_label("01_information_memorandum.pdf") == "Information memorandum"


def test_rows_are_grouped_into_blocks_with_their_header() -> None:
    elements = [
        Element("m.xlsx", "rows", text, sheet="S", row_start=i, row_end=i)
        for i, text in [(1, "Head | FY1"), (2, "A | 1"), (3, "B | 2"), (5, "Other | FY2"), (6, "C | 3")]
    ]
    chunks = Chunker(ChunkSettings(rows_per_chunk=1)).chunk(elements)
    assert [(c.row_start, c.row_end) for c in chunks] == [(1, 2), (3, 3), (5, 6)]
    assert chunks[1].text.splitlines()[1] == "Head | FY1"


def test_chunk_citation_and_coverage() -> None:
    rows = Chunk("m.xlsx", "x", "rows", sheet="LBO", row_start=14, row_end=21)
    page = Chunk("a.pdf", "y", "paragraph", page=2)
    assert rows.citation == "m.xlsx, sheet LBO, rows A14:A21"
    assert rows.covers({"file": "m.xlsx", "sheet": "LBO", "row": 17})
    assert not rows.covers({"file": "m.xlsx", "sheet": "LBO", "row": 3})
    assert page.covers({"any_of": [{"file": "z.pdf", "page": 2}, {"file": "a.pdf", "page": 2}]})
    assert Chunk.from_dict(page.to_dict()) == page


class RecordingExtractor:
    name = "remote-test"

    def __init__(self) -> None:
        self.received: dict[str, bytes] = {}

    def extract(self, file: str, data: bytes) -> list[Element]:
        self.received[file] = data
        return [Element(file, "paragraph", "Reto Wyssbrod chaired the meeting.", page=1)]


def test_remote_extractor_only_receives_redacted_files(tmp_path: Path) -> None:
    source = tmp_path / "files"
    source.mkdir()
    (source / spec.CVS.filename).write_bytes((FILES / spec.CVS.filename).read_bytes())
    extractor = RecordingExtractor()
    report = pipeline.ingest(source, tmp_path / "out", extractor, redact_copies=True)
    sent = extractor.received[spec.CVS.filename]
    text = " ".join(p.get_text() for p in pymupdf.open(stream=sent, filetype="pdf"))
    assert spec.CEO not in text and report.redacted_files == 1
    assert (tmp_path / "out" / "redacted" / spec.CVS.filename).exists()
    assert "Wyssbrod" not in (tmp_path / "out" / "chunks.jsonl").read_text()


def test_credential_reads_a_single_pem_bundle(tmp_path: Path) -> None:
    key_pem, cert_pem, _ = _key_and_cert()
    (tmp_path / "bundle.pem").write_bytes(key_pem + cert_pem)
    credential = CertificateCredential.from_files("t", "c", tmp_path / "bundle.pem", tmp_path / "bundle.pem")
    assert b"PRIVATE" in credential.private_key_pem.splitlines()[0]
    assert credential.certificate_pem.startswith(b"-----BEGIN CERTIFICATE-----")
    assert credential.client_assertion().count(".") == 2
    with pytest.raises(ValueError):
        pem_block(b"nothing here", "CERTIFICATE")


def test_extractor_from_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.delenv("DEALROOM_EXTRACTOR", raising=False)
    assert pipeline.extractor_from_env().name == "local"
    key_pem, cert_pem, _ = _key_and_cert()
    (tmp_path / "k").write_bytes(key_pem)
    (tmp_path / "c").write_bytes(cert_pem)
    for name, value in {
        "DEALROOM_EXTRACTOR": "azure",
        "AZURE_TENANT_ID": "t",
        "AZURE_CLIENT_ID": "c",
        "AZURE_CLIENT_KEY_PATH": str(tmp_path / "k"),
        "AZURE_CLIENT_CERT_PATH": str(tmp_path / "c"),
        "AZURE_DOCINTEL_ENDPOINT": "https://di.private.example",
    }.items():
        monkeypatch.setenv(name, value)
    assert pipeline.extractor_from_env().name == "azure-document-intelligence"
