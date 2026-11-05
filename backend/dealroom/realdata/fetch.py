"""Download the pinned public datasets into ``.cache/real`` and verify their checksums."""

from __future__ import annotations

import hashlib
import json
import zipfile
from collections.abc import Callable, Iterator
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

import httpx

Downloader = Callable[[str], bytes]


def http_get(url: str) -> bytes:  # pragma: no cover - network
    response = httpx.get(url, timeout=300, follow_redirects=True)
    response.raise_for_status()
    return response.content


class ChecksumError(ValueError):
    pass


def _items(manifest: dict[str, Any]) -> Iterator[tuple[str, str, str]]:
    fb = manifest["financebench"]
    yield fb["questions"]["url"], fb["questions"]["sha256"], "financebench/questions.jsonl"
    for name, item in fb["pdfs"].items():
        yield item["url"], item["sha256"], f"financebench/pdfs/{name}.pdf"
    archive = manifest["cuad"]["archive"]
    yield archive["url"], archive["sha256"], "cuad/data.zip"


def fetch(manifest_path: Path, out: Path, download: Downloader = http_get, workers: int = 6) -> int:
    """Download every pinned file that is missing or corrupt. Returns the number of files fetched."""
    manifest = json.loads(manifest_path.read_text())

    def one(item: tuple[str, str, str]) -> int:
        url, expected, relative = item
        target = out / relative
        if target.exists() and hashlib.sha256(target.read_bytes()).hexdigest() == expected:
            return 0
        data = download(url)
        if hashlib.sha256(data).hexdigest() != expected:
            raise ChecksumError(f"checksum mismatch for {url}")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        return 1

    with ThreadPoolExecutor(max_workers=workers) as pool:
        fetched = sum(pool.map(one, list(_items(manifest))))
    archive = out / "cuad" / "data.zip"
    if not (out / "cuad" / "test.json").exists():
        with zipfile.ZipFile(archive) as zipped:
            for member in ("CUADv1.json", "test.json", "train_separate_questions.json"):
                if member in zipped.namelist():
                    (out / "cuad" / member).write_bytes(zipped.read(member))
    return fetched
