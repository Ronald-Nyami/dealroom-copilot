"""Real-data tracks on a miniature corpus built in the test, so no download is needed."""

from __future__ import annotations

import hashlib
import io
import json
import zipfile
from pathlib import Path
from typing import Any

import pymupdf
import pytest

from dealroom.cli import main
from dealroom.realdata import cuad, fetch, financebench, report

FILING_PAGES = [
    "Annual report on Form 10-K. Item 1. Business overview of the company and its segments.",
    "Consolidated statement of income. Net sales 1,577 million. Operating income 412 million.",
    "Capital expenditures were 8.7 million in fiscal 2022. Purchases of property and equipment.",
]
CONTRACTS = [
    ("A", "Either party may terminate this Agreement upon a change of control of the other party.", True),
    ("B", "This Agreement may not be assigned without consent, including on a change in ownership.", True),
    ("C", "The supplier shall deliver goods within 30 days. Payment terms are net 60.", False),
    ("D", "A change of control does not by itself give rise to any right. Notice is not required.", False),
    ("E", "Licensee shall pay royalties quarterly. Governing law is the State of New York.", True),
]


def _pdf(pages: list[str]) -> bytes:
    document = pymupdf.open()
    for text in pages:
        document.new_page().insert_text((72, 72), text, fontsize=10)
    data: bytes = document.tobytes()
    return data


def _questions() -> list[dict[str, Any]]:
    def q(qid: str, kind: str, question: str, answer: str, page: int) -> dict[str, Any]:
        return {
            "financebench_id": qid,
            "doc_name": "ACME_2022_10K",
            "question_type": kind,
            "question": question,
            "answer": answer,
            "evidence": [{"doc_name": "ACME_2022_10K", "evidence_page_num": page}],
        }

    return [
        q("q1", "metrics-generated", "What were net sales?", "$1577.00", 1),
        q("q2", "metrics-generated", "What were capital expenditures in fiscal 2022?", "8.70", 2),
        q("q3", "domain-relevant", "Describe the business segments.", "The company has segments.", 0),
    ]


def _cuad_json() -> bytes:
    data = []
    for title, text, label in CONTRACTS:
        answers = [{"text": text[:40], "answer_start": 0}] if label else []
        qas = [
            {"id": f"{title}__Parties", "answers": []},
            {"id": f"{title}__{cuad.LABEL}", "answers": answers},
        ]
        data.append({"title": title, "paragraphs": [{"context": text, "qas": qas}]})
    return json.dumps({"data": data}).encode()


@pytest.fixture()
def corpus(tmp_path: Path) -> dict[str, Any]:
    """URL -> bytes for a manifest that mirrors data/real/manifest.json."""
    archive = io.BytesIO()
    with zipfile.ZipFile(archive, "w") as zipped:
        zipped.writestr("test.json", _cuad_json())
    files = {
        "https://example.test/q.jsonl": "\n".join(json.dumps(q) for q in _questions()).encode(),
        "https://example.test/ACME_2022_10K.pdf": _pdf(FILING_PAGES),
        "https://example.test/data.zip": archive.getvalue(),
    }

    def entry(url: str) -> dict[str, str]:
        return {"url": url, "sha256": hashlib.sha256(files[url]).hexdigest()}

    manifest = {
        "financebench": {
            "questions": entry("https://example.test/q.jsonl"),
            "pdfs": {"ACME_2022_10K": entry("https://example.test/ACME_2022_10K.pdf")},
        },
        "cuad": {"archive": entry("https://example.test/data.zip")},
    }
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(manifest))
    return {"files": files, "manifest": path, "cache": tmp_path / "cache"}


def test_fetch_verifies_checksums_and_skips_present_files(corpus: dict[str, Any]) -> None:
    calls: list[str] = []

    def download(url: str) -> bytes:
        calls.append(url)
        data: bytes = corpus["files"][url]
        return data

    assert fetch.fetch(corpus["manifest"], corpus["cache"], download) == 3
    assert (corpus["cache"] / "cuad" / "test.json").exists()
    assert fetch.fetch(corpus["manifest"], corpus["cache"], download) == 0
    assert len(calls) == 3
    (corpus["cache"] / "financebench" / "questions.jsonl").write_text("tampered")
    with pytest.raises(fetch.ChecksumError):
        fetch.fetch(corpus["manifest"], corpus["cache"], lambda url: b"wrong")


def test_financebench_index_and_evaluate(corpus: dict[str, Any]) -> None:
    fetch.fetch(corpus["manifest"], corpus["cache"], lambda url: corpus["files"][url])
    fb = corpus["cache"] / "financebench"
    built = financebench.build_indexes(fb / "pdfs", fb / "index", workers=1)
    assert built["ACME_2022_10K"] > 0
    results = financebench.evaluate(financebench.load_questions(fb / "questions.jsonl"), fb / "index")
    assert results["questions"] == 3 and results["filings"] == 1
    assert results["retrieval"]["bm25"]["page_hit@10"] == 1.0
    assert results["figure_accuracy_by_type"]["metrics-generated"]["questions"] == 2
    assert "domain-relevant" not in results["figure_accuracy_by_type"]
    assert len(results["answers"]) == 3


def test_figure_helpers() -> None:
    assert financebench.parse_number("($1,234.5)") == -1234.5
    assert financebench.parse_number("no figure") is None
    assert financebench.is_figure("$1577.00") and financebench.is_figure("65.4%")
    assert not financebench.is_figure("Yes, it grew by 3%.")
    assert financebench.contains_figure("Capex was $1,580 million", "$1577.00")
    assert not financebench.contains_figure("Capex was $1,700 million", "$1577.00")
    assert not financebench.contains_figure("anything", "not a number")
    assert financebench.gold_pages(_questions()[0]) == {("ACME_2022_10K.pdf", 2)}


def test_cuad_scoring(corpus: dict[str, Any]) -> None:
    fetch.fetch(corpus["manifest"], corpus["cache"], lambda url: corpus["files"][url])
    contracts = cuad.load_contracts(corpus["cache"] / "cuad" / "test.json")
    assert [c["label"] for c in contracts] == [c[2] for c in CONTRACTS]
    broad = cuad.evaluate(contracts)
    assert broad["counts"] == {"tp": 2, "fp": 0, "fn": 1, "tn": 2}
    assert broad["recall"] == pytest.approx(2 / 3)
    strict = cuad.evaluate(contracts, require_termination=True)
    assert strict["counts"]["tp"] == 1 and strict["precision"] == 1.0
    assert {e["error"] for e in broad["errors"]} == {"missed"}
    assert cuad.evaluate([])["f1"] == 0.0


def test_report_and_cli(
    corpus: dict[str, Any], tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    root = tmp_path / "project"
    (root / "data" / "real").mkdir(parents=True)
    (root / "data" / "real" / "manifest.json").write_text(corpus["manifest"].read_text())
    monkeypatch.setenv("DEALROOM_ROOT", str(root))
    monkeypatch.delenv("DEALROOM_LLM", raising=False)
    real_fetch = fetch.fetch
    monkeypatch.setattr(fetch, "fetch", lambda m, out: real_fetch(m, out, lambda url: corpus["files"][url]))
    main(["real", "all", "--workers", "1"])
    out = capsys.readouterr().out
    assert "fetched 3 files" in out and "indexed 1 filings" in out and "CUAD v2 F1" in out
    markdown = (root / "reports" / "eval_real.md").read_text()
    assert "| BM25 | " in markdown and "v2, provision present" in markdown
    saved = json.loads((root / "reports" / "results_real.json").read_text())
    assert saved["llm"] == "stub"
    assert set(saved["cuad"]) == {"v1_provision", "v1_termination", "v2_provision", "v2_termination"}
    assert report.pct(0.4267) == "42.7%"
