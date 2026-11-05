from __future__ import annotations

import json
from pathlib import Path

import pytest

from dealroom.synth import gold, spec
from dealroom.synth.render import render_pdf, render_scan, render_xlsx


def test_gold_set_size_and_types(root: Path) -> None:
    rows = [json.loads(line) for line in (root / "data" / "eval" / "gold.jsonl").read_text().splitlines()]
    assert 80 <= len(rows) <= 120
    assert {r["type"] for r in rows} == {"fact", "numeric", "cross_doc", "unanswerable", "ocr"}
    assert all(r["evidence"] for r in rows if r["type"] != "unanswerable")
    assert not any(r["evidence"] for r in rows if r["type"] == "unanswerable")


def test_every_needle_resolves_to_one_place() -> None:
    assert gold.resolve(spec.IM.filename, "Revenue reached CHF 148.6 million in FY2025") == {
        "file": spec.IM.filename,
        "page": 1,
    }
    assert gold.resolve(spec.MODEL.filename, "Net leverage")["sheet"] == "LBO"
    assert gold.resolve(spec.SCAN_BOARD_NOTE.filename, "below budget")["page"] == 1


@pytest.mark.parametrize(
    ("filename", "needle", "error"),
    [
        ("missing.pdf", "x", KeyError),
        (spec.MODEL.filename, "EBITDA", ValueError),
        (spec.IM.filename, "zzz", ValueError),
    ],
)
def test_bad_needles_fail_loudly(filename: str, needle: str, error: type[Exception]) -> None:
    with pytest.raises(error):
        gold.resolve(filename, needle)


def test_generated_files_are_deterministic(tmp_path: Path) -> None:
    render_pdf(spec.TAX_DD, tmp_path / "a.pdf")
    render_pdf(spec.TAX_DD, tmp_path / "b.pdf")
    assert (tmp_path / "a.pdf").read_bytes() == (tmp_path / "b.pdf").read_bytes()
    render_scan(spec.SCAN_LEASE_ADDENDUM, tmp_path / "s1.pdf", seed=3)
    render_scan(spec.SCAN_LEASE_ADDENDUM, tmp_path / "s2.pdf", seed=3)
    assert (tmp_path / "s1.pdf").read_bytes() == (tmp_path / "s2.pdf").read_bytes()
    render_xlsx(spec.CAPEX, tmp_path / "c.xlsx")
    assert (tmp_path / "c.xlsx").stat().st_size > 0


def test_traps_are_written(root: Path) -> None:
    traps = json.loads((root / "data" / "eval" / "traps.json").read_text())
    assert [t["id"] for t in traps] == ["revenue_mismatch", "change_of_control", "covenant_headroom"]
    assert all(len(t["evidence"]) == 2 for t in traps)
