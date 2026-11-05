"""Investment committee memo: drafted section by section, every sentence cited.

Each section is driven by the questions an associate would answer to write it.
Answers come from the QA agent (so they carry citations or are left out), and a
section writer turns them into prose. With a real model the writer composes
prose from the cited answers; the verifier rejects any sentence without a valid
citation. With the stub, the section is the list of cited answers.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from dealroom.agents.qa import Answer, QAAgent
from dealroom.models.llm import LLM, Evidence, StubLLM, cited_numbers

SECTIONS: dict[str, tuple[str, ...]] = {
    "Investment thesis": (
        "What does the company supply and to which end markets?",
        "How large was the order backlog at 30 September 2025?",
        "How fast is the addressable market expected to grow?",
        "What share of automotive revenue comes from electric-vehicle drivetrain parts?",
    ),
    "Business overview": (
        "In which year was the company founded?",
        "How many people did the company employ at the end of FY2025?",
        "Where is the second plant located?",
        "Which certificates does the Thun plant hold?",
    ),
    "Financials": (
        "What was audited net revenue in FY2025?",
        "What was EBITDA in FY2025?",
        "What was net income in FY2025?",
        "How much cash did the company hold at 31 December 2025?",
        "What revenue does the model forecast for FY2026?",
    ),
    "Key risks": (
        "What share of FY2025 revenue came from Brenntal Automotive?",
        "What is the amount of the Ostara Pumps warranty claim?",
        "Is the company certified to ISO 27001?",
        "When does the Czech investment incentive expire?",
    ),
    "Valuation summary": (
        "What enterprise value does the LBO assume?",
        "What entry multiple does the LBO use?",
        "What is the size of the senior term loan B?",
        "How much equity does the sponsor contribute?",
    ),
    "Open diligence items": (
        "Has legal due diligence reviewed the change-of-control clause of the largest customer contract?",
        "Which agreements has legal due diligence not reviewed?",
    ),
}

WRITER_SYSTEM = (
    "You write one section of an investment committee memo for a private equity fund. Use only the numbered "
    "evidence. Every sentence must end with at least one citation such as [3]. Write short, factual sentences. "
    "Do not add opinions, forecasts or facts that are not in the evidence."
)


@dataclass
class Sentence:
    text: str
    citations: list[Evidence]


@dataclass
class Section:
    title: str
    sentences: list[Sentence] = field(default_factory=list)
    unanswered: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        return {
            "title": self.title,
            "sentences": [{"text": s.text, "citations": [c.__dict__ for c in s.citations]} for s in self.sentences],
            "unanswered": self.unanswered,
        }


@dataclass
class Memo:
    title: str
    sections: list[Section]

    def uncited_sentences(self) -> int:
        return sum(1 for section in self.sections for s in section.sentences if not s.citations)

    def to_dict(self) -> dict[str, object]:
        return {"title": self.title, "sections": [s.to_dict() for s in self.sections]}

    def to_markdown(self) -> str:
        lines = [f"# {self.title}", ""]
        for section in self.sections:
            lines += [f"## {section.title}", ""]
            for sentence in section.sentences:
                refs = "; ".join(c.citation for c in sentence.citations)
                lines.append(f"- {sentence.text} _({refs})_")
            for question in section.unanswered:
                lines.append(f"- Open: {question} (not found in the data room)")
            lines.append("")
        return "\n".join(lines)


SPLIT = re.compile(r"(?<=[.!?\]])\s+(?=[A-Z])")  # each sentence is checked for its own citation


class MemoDrafter:
    def __init__(self, qa: QAAgent, llm: LLM | None = None) -> None:
        self.qa = qa
        self.llm = llm or qa.llm

    def draft_section(self, title: str, questions: tuple[str, ...]) -> Section:
        section = Section(title)
        answers: list[Answer] = [self.qa.answer(q) for q in questions]
        evidence: list[Evidence] = []
        for answer in answers:
            if answer.abstained:
                section.unanswered.append(answer.question)
                continue
            for item in answer.citations:
                if all(item.text != e.text for e in evidence):
                    evidence.append(Evidence(len(evidence) + 1, item.chunk_id, item.citation, item.text))
        if not evidence:
            return section
        if isinstance(self.llm, StubLLM):
            for item in evidence:
                section.sentences.append(Sentence(item.text, [item]))
            return section
        raw = self.llm.complete(WRITER_SYSTEM, f"Section: {title}", evidence)
        by_number = {e.n: e for e in evidence}
        for sentence in SPLIT.split(raw.strip()):
            cited = [by_number[n] for n in dict.fromkeys(cited_numbers(sentence)) if n in by_number]
            if cited:  # uncited or wrongly cited sentences are dropped, never shown
                section.sentences.append(Sentence(re.sub(r"\s?\[\d+\]", "", sentence).strip(), cited))
        return section

    def draft(self, target: str = "Alpine Precision Components AG") -> Memo:
        return Memo(
            f"Investment committee memo - {target}",
            [self.draft_section(title, questions) for title, questions in SECTIONS.items()],
        )
