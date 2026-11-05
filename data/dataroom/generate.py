"""Regenerate the synthetic data room, its ground truth, the gold set and the trap list.

Usage: python data/dataroom/generate.py
"""

from __future__ import annotations

from pathlib import Path

from dealroom.synth.gold import write_eval_files
from dealroom.synth.render import build

ROOT = Path(__file__).resolve().parents[2]


def main() -> None:
    truth = build(ROOT / "data" / "dataroom")
    questions = write_eval_files(ROOT / "data" / "eval")
    print(f"data room: {len(truth)} files; gold set: {questions} questions")


if __name__ == "__main__":
    main()
