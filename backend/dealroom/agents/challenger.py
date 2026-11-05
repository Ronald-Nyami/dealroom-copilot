"""IC challenger: builds the strongest case against the deal, every argument cited.

The challenger does not know where the problems are. It runs the checks a
sceptical investment committee member would run, using only retrieval over the
(masked) data room:

1. figure consistency   - full-year figures in marketing documents vs audited accounts
2. change of control    - termination rights in contracts, weighted by revenue share
3. covenant headroom    - model projections vs facility covenants, plus a downside case
4. timeline consistency - the same milestone dated differently in different documents
5. adjusted earnings    - adjusted EBITDA without a bridge to reported EBITDA
6. concentration        - dependence on a single customer
7. open diligence       - items an adviser says were not reviewed

Every argument carries verbatim evidence. A human must sign off on the memo
before it can be approved; the challenger can raise issues but never approve.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from dealroom.agents.qa import EvidenceSelector
from dealroom.ingestion.models import Chunk
from dealroom.models.llm import Evidence
from dealroom.retrieval.retriever import Retriever
from dealroom.retrieval.text import tokens

Severity = str  # "high" | "medium" | "low"
SEVERITY_ORDER = {"high": 0, "medium": 1, "low": 2}


@dataclass
class Argument:
    check: str
    title: str
    severity: Severity
    text: str
    citations: list[Evidence] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        return {
            "check": self.check,
            "title": self.title,
            "severity": self.severity,
            "text": self.text,
            "citations": [c.__dict__ for c in self.citations],
        }


@dataclass(frozen=True)
class Table:
    chunk: Chunk
    columns: list[str]
    rows: dict[str, list[str]]


def parse_table(chunk: Chunk) -> Table | None:
    lines = [line for line in chunk.text.split("\n")[1:] if "|" in line]
    if len(lines) < 2:
        return None
    columns = [c.strip() for c in lines[0].split("|")]
    rows = {}
    for line in lines[1:]:
        cells = [c.strip() for c in line.split("|")]
        rows[cells[0]] = cells[1:]
    return Table(chunk, columns, rows)


def _float(value: str) -> float | None:
    try:
        return float(value.replace(",", ""))
    except ValueError:
        return None


def _fy(label: str) -> str | None:
    match = re.search(r"FY(\d{4})", label)
    if match:
        return match.group(1)
    match = re.fullmatch(r"31\.12\.(\d{4})", label)
    return match.group(1) if match else None


def source_kind(file: str) -> str:
    if "audited_financial_statements" in file:
        return "audited"
    if "information_memorandum" in file or "management_presentation" in file:
        return "marketing"
    if "model" in file:
        return "model"
    return "other"


# Version 1 was written for the synthetic contracts. Version 2 was developed on CUAD's training
# split (408 real contracts) and is scored once on its test split; see reports/eval_real.md.
CHANGE_OF_CONTROL_V1 = re.compile(r"(change of control|more than 50% of the shares|voting rights)", re.I)
CHANGE_OF_CONTROL = re.compile(
    r"(change (of|in) (the )?(control|ownership)|change in the (general )?(management, )?(ownership|control)|"
    r"ownership change|controlling interest|more than (50|fifty) ?(%|percent)|acquired by (a|any) third party|"
    r"is acquired by)",
    re.I,
)
CONSEQUENCE = re.compile(r"(terminat|consent|notice|notify|assign|transfer|repayable)", re.I)
TERMINATION_RIGHT = re.compile(r"(may terminate|right to terminate|terminate this agreement|becomes repayable)", re.I)
NEGATED = re.compile(r"(does not by itself|has no effect|no change-of-control)", re.I)


def change_of_control_sentences(text: str, require_termination: bool = False, version: int = 2) -> list[str]:
    """Sentences that create a change-of-control provision (the challenger's own patterns)."""
    from dealroom.agents.qa import SENTENCE

    found = []
    for sentence in SENTENCE.split(" ".join(text.split())):
        if version == 1:
            if not CHANGE_OF_CONTROL_V1.search(sentence) or NEGATED.search(sentence):
                continue
        elif not (CHANGE_OF_CONTROL.search(sentence) and CONSEQUENCE.search(sentence)) or NEGATED.search(sentence):
            continue
        if require_termination and not TERMINATION_RIGHT.search(sentence):
            continue
        found.append(sentence)
    return found


class Challenger:
    def __init__(
        self,
        retriever: Retriever,
        headroom_threshold: float = 0.10,
        mismatch_threshold: float = 0.01,
        concentration_threshold: float = 0.25,
    ) -> None:
        self.retriever = retriever
        self.selector = EvidenceSelector(retriever.chunks)
        self.headroom_threshold = headroom_threshold
        self.mismatch_threshold = mismatch_threshold
        self.concentration_threshold = concentration_threshold
        self._n = 0

    # ------------------------------------------------------------------ helpers

    def _evidence(self, chunk: Chunk, quote: str) -> Evidence:
        self._n += 1
        return Evidence(self._n, chunk.id, chunk.citation, quote)

    def _search(self, query: str, k: int = 10) -> list[Chunk]:
        return [h.chunk for h in self.retriever.search(query, k)]

    def _sentences(self, query: str, pattern: str, k: int = 10) -> list[tuple[Chunk, str]]:
        regex = re.compile(pattern, re.IGNORECASE)
        found: list[tuple[Chunk, str]] = []
        for chunk in self._search(query, k):
            if chunk.kind in {"table", "rows"}:
                continue
            for sentence, _ in self.selector.spans(chunk, query):
                if regex.search(sentence):
                    found.append((chunk, sentence))
        return found

    def _tables(self, query: str, k: int = 10) -> list[Table]:
        out = []
        for chunk in self._search(query, k):
            if chunk.kind in {"table", "rows"}:
                table = parse_table(chunk)
                if table:
                    out.append(table)
        return out

    # ------------------------------------------------------------------ 1. figure consistency

    def figure_consistency(self) -> list[Argument]:
        arguments: list[Argument] = []
        for metric in ("revenue", "EBITDA", "net income"):
            for year in ("2023", "2024", "2025"):
                audited: tuple[float, Evidence] | None = None
                for table in self._tables(f"audited income statement {metric} FY{year}"):
                    if source_kind(table.chunk.file) != "audited":
                        continue
                    for label, cells in table.rows.items():
                        if set(tokens(metric)) <= set(tokens(label)) and _fy(table.columns[1] or "") == year:
                            value = _float(cells[0])
                            if value is not None:
                                audited = (value, self._evidence(table.chunk, f"{label}, FY{year}: {cells[0]}"))
                if audited is None:
                    continue
                pattern = rf"{metric}[^.]*?CHF ([\d.]+) million in FY{year}"
                for chunk, sentence in self._sentences(f"{metric} reached CHF million in FY{year}", pattern):
                    if source_kind(chunk.file) != "marketing":
                        continue
                    match = re.search(pattern, sentence, re.IGNORECASE)
                    claimed = float(match.group(1)) if match else None
                    if claimed is None:
                        continue
                    gap = (claimed - audited[0]) / audited[0]
                    if abs(gap) <= self.mismatch_threshold:
                        continue
                    claim = self._evidence(chunk, sentence)
                    arguments.append(
                        Argument(
                            "figure_consistency",
                            f"FY{year} {metric} in {chunk.file.split('_', 1)[1].rsplit('.', 1)[0].replace('_', ' ')} "
                            "does not match the audited accounts",
                            "high" if abs(gap) > 0.03 else "medium",
                            f"The marketing document states FY{year} {metric} of CHF {claimed:.1f} million "
                            f"[{claim.n}], "
                            f"but the audited accounts show CHF {audited[0]:.1f} million [{audited[1].n}], a gap of "
                            f"CHF {claimed - audited[0]:.1f} million ({gap:+.1%}). No reconciliation was found in the "
                            "data room; valuation and leverage must be based on the audited figure.",
                            [claim, audited[1]],
                        )
                    )
        return arguments

    # ------------------------------------------------------------------ 2. change of control

    def _customer_shares(self) -> dict[str, tuple[float, Evidence | None, Chunk]]:
        shares: dict[str, tuple[float, Evidence | None, Chunk]] = {}
        for table in self._tables("customer concentration share of revenue FY2025 by customer"):
            if "Share of revenue" not in table.columns:
                continue
            column = table.columns.index("Share of revenue") - 1
            for label, cells in table.rows.items():
                value = _float(cells[column]) if column < len(cells) else None
                if value is not None and label not in {"Total", "All other customers"}:
                    shares[label] = (value, None, table.chunk)
        return shares

    def change_of_control(self) -> list[Argument]:
        pattern = CHANGE_OF_CONTROL.pattern
        terminate, negated = TERMINATION_RIGHT, NEGATED
        shares = self._customer_shares()
        gaps = self._sentences(
            "change-of-control provisions agreement not yet been reviewed", r"not (yet )?been reviewed"
        )
        arguments: list[Argument] = []
        seen: set[str] = set()
        for chunk, sentence in self._sentences(
            "third party acquires shares change of control terminate agreement", pattern, k=12
        ):
            if not terminate.search(sentence) or negated.search(sentence) or chunk.file in seen:
                continue
            seen.add(chunk.file)
            clause = self._evidence(chunk, sentence)
            counterparty = next((name for name in shares if name.split()[0].lower() in chunk.file), None)
            if counterparty is None:
                if "facility" in chunk.file or "loan" in sentence.lower():
                    arguments.append(
                        Argument(
                            "change_of_control",
                            "Existing bank loan is repayable on change of control",
                            "low",
                            f"The existing term loan becomes repayable on a change of control [{clause.n}]. It is "
                            "refinanced at closing in the sources and uses, so this is a timing item, "
                            "not a value item.",
                            [clause],
                        )
                    )
                continue
            share, _, share_chunk = shares[counterparty]
            share_evidence = self._evidence(share_chunk, f"{counterparty}, Share of revenue: {share:g}")
            citations = [clause, share_evidence]
            text = (
                f"{counterparty} can terminate its agreement if a third party acquires control without its consent "
                f"[{clause.n}]. It accounts for {share:.1%} of FY2025 revenue [{share_evidence.n}], so the "
                "acquisition itself puts that revenue at risk unless consent is obtained before signing."
            )
            for gap_chunk, gap_sentence in gaps:
                if counterparty.split()[0] in gap_sentence:
                    gap = self._evidence(gap_chunk, gap_sentence)
                    citations.append(gap)
                    text += f" Legal due diligence has not reviewed this agreement [{gap.n}]."
            arguments.append(
                Argument(
                    "change_of_control",
                    f"{counterparty} can terminate on change of control",
                    "high" if share >= 0.10 else "medium",
                    text,
                    citations,
                )
            )
        return arguments

    # ------------------------------------------------------------------ 3. covenant headroom

    def covenant_headroom(self) -> list[Argument]:
        limits: dict[str, tuple[float, Evidence]] = {}
        for chunk, sentence in self._sentences(
            "financial covenants net leverage must not exceed", r"must not exceed [\d.]+x at 31 December"
        ):
            if "facility" in chunk.file and "existing" in chunk.file:
                continue  # covenant of the loan that is refinanced at closing
            evidence = self._evidence(chunk, sentence)
            for value, year in re.findall(r"([\d.]+)x at 31 December (\d{4})", sentence):
                limits.setdefault(year, (float(value), evidence))
        projections: dict[str, tuple[float, float, float, Evidence]] = {}
        for table in self._tables("covenant test net leverage net debt EBITDA projection"):
            rows = table.rows
            if "Net leverage" not in rows or "Net debt" not in rows or "EBITDA" not in rows:
                continue
            for index, column in enumerate(table.columns[1:]):
                year = _fy(column)
                leverage = _float(rows["Net leverage"][index]) if index < len(rows["Net leverage"]) else None
                if year and leverage is not None:
                    quote = f"Net leverage, {column}: {rows['Net leverage'][index]}"
                    projections[year] = (
                        leverage,
                        float(rows["Net debt"][index]),
                        float(rows["EBITDA"][index]),
                        self._evidence(table.chunk, quote),
                    )
        shortfall = None
        for chunk, sentence in self._sentences("expect revenue below budget", r"([\d.]+)\s?m(?:illion)? below budget"):
            match = re.search(r"([\d.]+)\s?m(?:illion)? below budget", sentence)
            if match:
                shortfall = (float(match.group(1)), self._evidence(chunk, sentence))
                break
        revenue = {}
        for table in self._tables("model revenue EBITDA FY2026 forecast P&L"):
            if "Revenue" in table.rows and "EBITDA" in table.rows:
                for index, column in enumerate(table.columns[1:]):
                    year = _fy(column)
                    if year and index < len(table.rows["Revenue"]):
                        revenue[year] = (_float(table.rows["Revenue"][index]), _float(table.rows["EBITDA"][index]))
        arguments = []
        for year in sorted(set(limits) & set(projections)):
            limit, limit_evidence = limits[year]
            leverage, net_debt, _, projection_evidence = projections[year]
            headroom = (limit - leverage) / limit
            if headroom >= self.headroom_threshold:
                continue
            citations = [projection_evidence, limit_evidence]
            text = (
                f"The model projects net leverage of {leverage:.2f}x at the end of FY{year} [{projection_evidence.n}] "
                f"against a covenant maximum of {limit:.2f}x [{limit_evidence.n}], a headroom of {headroom:.1%}."
            )
            if shortfall and year in revenue and revenue[year][0] and revenue[year][1]:
                rev, ebi = revenue[year]
                assert rev is not None and ebi is not None
                margin = ebi / rev
                stressed = net_debt / (ebi - shortfall[0] * margin)
                citations.append(shortfall[1])
                text += (
                    f" A revenue shortfall of CHF {shortfall[0]:.1f} million [{shortfall[1].n}] at the plan EBITDA "
                    f"margin of {margin:.1%} would lift leverage to {stressed:.2f}x with net debt unchanged"
                    + (", at or above the covenant." if stressed >= limit - 0.005 else ".")
                )
            arguments.append(
                Argument(
                    "covenant_headroom", f"FY{year} net leverage covenant headroom is thin", "high", text, citations
                )
            )
        return arguments

    # ------------------------------------------------------------------ 4. timeline consistency

    def timeline_consistency(self) -> list[Argument]:
        quarter = re.compile(r"Q[1-4] 20\d\d")
        mentions = self._sentences(
            "EV-7 start of production planned moved Q2 2026 Q1 2027", r"start of production", k=12
        )
        moved = [
            (c, s)
            for c, s in mentions
            if re.search(r"moved from Q[1-4] 20\d\d to Q[1-4] 20\d\d", s) or ("moved" in s and quarter.search(s))
        ]
        if not moved:
            # OCR text keeps line breaks between the clauses; read the whole note
            for chunk in self._search("start of production moved from to", 12):
                if chunk.kind == "ocr" and "moved" in chunk.text and quarter.search(chunk.text):
                    moved.append((chunk, " ".join(chunk.text.split("\n", 1)[1].split())))
        arguments = []
        for moved_chunk, moved_sentence in moved[:1]:
            match = re.search(r"from (Q[1-4] 20\d\d) to (Q[1-4] 20\d\d)", moved_sentence)
            if not match:
                continue
            old, new = match.groups()
            planned = [(c, s) for c, s in mentions if old in s and c.id != moved_chunk.id]
            if not planned:
                continue
            note = self._evidence(moved_chunk, moved_sentence)
            stated = [self._evidence(c, s) for c, s in planned[:2]]
            refs = ", ".join(f"[{e.n}]" for e in stated)
            arguments.append(
                Argument(
                    "timeline_consistency",
                    f"EV-7 start of production: {old} in the plan, {new} in the latest note",
                    "high",
                    f"The information memorandum and the budget assume start of production in {old} {refs}. A later "
                    f"handwritten note records that it moved to {new} and that revenue will fall below budget "
                    f"[{note.n}]. "
                    "The plan used for valuation and for the covenant test should be restated.",
                    [*stated, note],
                )
            )
        return arguments

    # ------------------------------------------------------------------ 5. adjusted earnings

    def adjusted_earnings(self) -> list[Argument]:
        found = self._sentences("adjusted EBITDA", r"adjusted EBITDA of CHF ([\d.]+) million")
        bridge = self._sentences(
            "EBITDA adjustments bridge reconciliation normalisation",
            r"(bridge|reconciliation|normalis|adjustments? (to|of) EBITDA)",
        )
        if not found or bridge:
            return []
        chunk, sentence = found[0]
        claim = self._evidence(chunk, sentence)
        return [
            Argument(
                "adjusted_earnings",
                "Adjusted EBITDA has no bridge to reported EBITDA",
                "medium",
                f"The information memorandum quotes adjusted EBITDA [{claim.n}] but the data room contains "
                "no bridge from reported to adjusted EBITDA. The entry multiple should be applied to "
                "reported EBITDA until each adjustment is evidenced.",
                [claim],
            )
        ]

    # ------------------------------------------------------------------ 6. concentration

    def concentration(self) -> list[Argument]:
        shares = self._customer_shares()
        if not shares:
            return []
        name, (share, _, chunk) = max(shares.items(), key=lambda item: item[1][0])
        if share < self.concentration_threshold:
            return []
        evidence = self._evidence(chunk, f"{name}, Share of revenue: {share:g}")
        return [
            Argument(
                "concentration",
                f"{name} is {share:.0%} of revenue",
                "medium",
                f"The largest customer, {name}, accounts for {share:.1%} of FY2025 revenue [{evidence.n}].",
                [evidence],
            )
        ]

    # ------------------------------------------------------------------ run

    def run(self) -> list[Argument]:
        self._n = 0
        arguments: list[Argument] = []
        for check in (
            self.figure_consistency,
            self.change_of_control,
            self.covenant_headroom,
            self.timeline_consistency,
            self.adjusted_earnings,
            self.concentration,
        ):
            arguments.extend(check())
        arguments.sort(key=lambda a: SEVERITY_ORDER.get(a.severity, 3))
        return [renumber(a) for a in arguments]


def renumber(argument: Argument) -> Argument:
    """Number citations [1], [2]... within each argument."""
    mapping = {c.n: i + 1 for i, c in enumerate(argument.citations)}
    text = re.sub(r"\[(\d+)\]", lambda m: f"[{mapping.get(int(m.group(1)), m.group(1))}]", argument.text)
    citations = [Evidence(mapping[c.n], c.chunk_id, c.citation, c.text) for c in argument.citations]
    return Argument(argument.check, argument.title, argument.severity, text, citations)
