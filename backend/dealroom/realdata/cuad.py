"""CUAD: does the challenger's change-of-control detector agree with lawyers?

CUAD labels, for each of 510 real contracts, whether it contains a change-of-control
provision (termination right, consent or notice when a party changes control). The
detector is the same pattern set the challenger uses. It is scored on CUAD's test
split only (102 contracts); the patterns were written before looking at CUAD.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from dealroom.agents.challenger import change_of_control_sentences

LABEL = "Change Of Control"


def load_contracts(path: Path) -> list[dict[str, Any]]:
    contracts = []
    for item in json.loads(path.read_text())["data"]:
        paragraph = item["paragraphs"][0]
        question = next(q for q in paragraph["qas"] if q["id"].endswith(f"__{LABEL}"))
        contracts.append(
            {
                "title": item["title"],
                "text": paragraph["context"],
                "label": bool(question["answers"]),
                "spans": [a["text"] for a in question["answers"]],
            }
        )
    return contracts


def evaluate(contracts: list[dict[str, Any]], require_termination: bool = False, version: int = 2) -> dict[str, Any]:
    """``require_termination`` scores the challenger's full rule (a termination right), which is
    narrower than CUAD's label (termination, consent or notice); recall is expected to drop."""
    tp = fp = fn = tn = 0
    errors: list[dict[str, Any]] = []
    for contract in contracts:
        found = change_of_control_sentences(contract["text"], require_termination, version)
        predicted = bool(found)
        if predicted and contract["label"]:
            tp += 1
        elif predicted:
            fp += 1
            errors.append({"title": contract["title"], "error": "false positive", "detected": found[0][:300]})
        elif contract["label"]:
            fn += 1
            errors.append({"title": contract["title"], "error": "missed", "lawyer_span": contract["spans"][0][:300]})
        else:
            tn += 1
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {
        "contracts": len(contracts),
        "with_provision": tp + fn,
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "counts": {"tp": tp, "fp": fp, "fn": fn, "tn": tn},
        "errors": errors,
    }
