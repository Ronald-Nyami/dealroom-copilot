"""Append-only audit log with a hash chain.

Each record stores the SHA-256 of the previous record. Editing, deleting or
reordering any line breaks the chain, and ``verify`` reports the first broken
line. Arguments are logged after masking, so the log holds no personal data.
"""

from __future__ import annotations

import hashlib
import json
import threading
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

GENESIS = "0" * 64


def _canonical(record: dict[str, Any]) -> str:
    return json.dumps(record, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


@dataclass(frozen=True)
class Verification:
    ok: bool
    records: int
    broken_at: int | None = None
    reason: str = ""


class AuditLog:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    def _last_hash(self) -> str:
        if not self.path.exists():
            return GENESIS
        last = GENESIS
        with self.path.open(encoding="utf-8") as handle:
            for line in handle:
                if line.strip():
                    last = json.loads(line)["hash"]
        return last

    def append(
        self, *, actor: str, role: str, tool: str, arguments: dict[str, Any], decision: str, detail: str = ""
    ) -> dict[str, Any]:
        with self._lock:
            record = {
                "at": datetime.now(UTC).isoformat(),
                "actor": actor,
                "role": role,
                "tool": tool,
                "arguments": arguments,
                "decision": decision,
                "detail": detail,
                "prev": self._last_hash(),
            }
            record["hash"] = hashlib.sha256(_canonical(record).encode()).hexdigest()
            with self.path.open("a", encoding="utf-8") as handle:
                handle.write(_canonical(record) + "\n")
            return record

    def records(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        return [json.loads(line) for line in self.path.read_text(encoding="utf-8").splitlines() if line.strip()]

    def verify(self) -> Verification:
        previous = GENESIS
        records = self.records()
        for index, record in enumerate(records, start=1):
            stored = record.get("hash", "")
            body = {k: v for k, v in record.items() if k != "hash"}
            if body.get("prev") != previous:
                return Verification(False, len(records), index, "previous hash does not match")
            if hashlib.sha256(_canonical(body).encode()).hexdigest() != stored:
                return Verification(False, len(records), index, "record content was changed")
            previous = stored
        return Verification(True, len(records))
