"""Gold questions for the synthetic data room.

Each question names its evidence by (filename, needle). ``resolve`` turns a
needle into a page (PDF and scan) or a sheet and row (XLSX) using ``spec.py``,
and raises if a needle matches zero or several places. Unanswerable questions
have no evidence: the right behaviour is to abstain.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from dealroom.synth import spec as s

QType = Literal["fact", "numeric", "cross_doc", "unanswerable", "ocr"]


class AnyOf(tuple[tuple[str, str], ...]):
    """One evidence item that several documents state equally well."""


def any_of(*pairs: tuple[str, str]) -> AnyOf:
    return AnyOf(pairs)


Evidence = tuple[str, str] | AnyOf


@dataclass(frozen=True)
class Gold:
    id: str
    question: str
    type: QType
    answer: str
    evidence: tuple[Evidence, ...] = ()
    value: float | None = None


IM, FS23, FS24, FS25 = s.IM.filename, s.FS23.filename, s.FS24.filename, s.FS25.filename
MP, BR, NW, VA, LE = (
    s.MGMT_PRES.filename,
    s.BRENNTAL.filename,
    s.NORDWIND.filename,
    s.VALTRONA.filename,
    s.LEASE.filename,
)
CV, LDD, CDD, TDD = s.CVS.filename, s.LEGAL_DD.filename, s.COMMERCIAL_DD.filename, s.TAX_DD.filename
ENV, INS, HR, IT, QA = s.ENV.filename, s.INSURANCE.filename, s.HR.filename, s.IT.filename, s.QUALITY.filename
BM, TS, SUP, ST = s.BOARD_MINUTES.filename, s.TERM_SHEET.filename, s.SUPPLIERS.filename, s.STRUCTURE.filename
MOD, CON, CAP = s.MODEL.filename, s.CONCENTRATION.filename, s.CAPEX.filename
SC_BR, SC_NOTE = s.SCAN_BRENNTAL.filename, s.SCAN_BOARD_NOTE.filename
SC_LEASE, SC_BANK = s.SCAN_LEASE_ADDENDUM.filename, s.SCAN_BANK_LETTER.filename

AUDITOR = any_of(*((f, f"Our opinion on FY{y} is unqualified") for f, y in ((FS23, 2023), (FS24, 2024), (FS25, 2025))))

_RAW: list[tuple[str, QType, str, tuple[Evidence, ...], float | None]] = [
    # ------------------------------------------------------------------ facts (text passages)
    ("In which year was the company founded?", "fact", "1987", ((IM, "founded in 1987 in Thun"),), 1987),
    (
        "What share of the company do the Hosmatter family intend to sell?",
        "fact",
        "70%",
        ((IM, "intend to sell 70% of the shares"),),
        70,
    ),
    (
        "Where is the second plant located?",
        "fact",
        "Brno, Czech Republic",
        (any_of((IM, "Brno plant opened in 2014"), (ST, "owns 100% of")),),
        None,
    ),
    ("When did the Brno plant open?", "fact", "2014", ((IM, "Brno plant opened in 2014"),), 2014),
    (
        "How many people did the company employ at the end of FY2025?",
        "fact",
        "612",
        ((IM, "employed 612 people"),),
        612,
    ),
    ("How many employees work in Brno?", "fact", "194", ((IM, "194 in Brno"),), 194),
    (
        "What share of FY2025 revenue came from rail customers?",
        "fact",
        "19%",
        ((IM, "End markets in FY2025 were automotive"),),
        19,
    ),
    (
        "What share of automotive revenue comes from electric-vehicle drivetrain parts?",
        "fact",
        "41%",
        ((IM, "represent 41% of automotive revenue"),),
        41,
    ),
    (
        "How large was the order backlog at 30 September 2025?",
        "fact",
        "CHF 96.4 million",
        ((IM, "Order backlog stood at CHF 96.4 million"),),
        96.4,
    ),
    (
        "Since when has the company worked with Brenntal Automotive?",
        "fact",
        "2009",
        ((IM, "dates back to 2009"),),
        2009,
    ),
    (
        "When is start of production of the EV-7 platform planned according to the information memorandum?",
        "fact",
        "Q2 2026",
        ((IM, "start of production planned for Q2 2026"),),
        None,
    ),
    (
        "How many CNC machining centres does the Thun plant run?",
        "fact",
        "74",
        ((IM, "runs 74 CNC machining centres"),),
        74,
    ),
    ("What was the scrap rate in FY2025?", "fact", "1.8%", ((IM, "the scrap rate was 1.8%"),), 1.8),
    (
        "What was overall equipment effectiveness in Thun in FY2025?",
        "fact",
        "78%",
        ((IM, "Overall equipment effectiveness was 78%"),),
        78,
    ),
    ("When did the chief executive officer join the company?", "fact", "2016", ((IM, "who joined in 2016"),), 2016),
    ("What stake will management hold after closing?", "fact", "8%", ((IM, "hold a combined 8% of the shares"),), 8),
    (
        "By when are non-binding offers due?",
        "fact",
        "14 November 2025",
        ((IM, "Non-binding offers are requested by 14 November 2025"),),
        None,
    ),
    ("What was Brno utilisation in FY2025?", "fact", "71%", ((MP, "Brno utilisation was 71% in FY2025"),), 71),
    (
        "What medical technology revenue does management target for FY2028?",
        "fact",
        "CHF 26 million",
        ((MP, "medical technology revenue of CHF 26 million by FY2028"),),
        26,
    ),
    ("How many apprentices does the company train?", "fact", "38", ((MP, "trains 38 apprentices"),), 38),
    ("What was voluntary staff turnover in FY2025?", "fact", "6.4%", ((MP, "Voluntary staff turnover was 6.4%"),), 6.4),
    (
        "Under which accounting framework are the financial statements prepared?",
        "fact",
        "Swiss GAAP FER",
        (AUDITOR,),
        None,
    ),
    (
        "Who audited the FY2025 financial statements?",
        "fact",
        "Birchwood & Partner Revision AG",
        ((FS25, "Our opinion on FY2025 is unqualified"),),
        None,
    ),
    (
        "When does the Brenntal framework agreement expire?",
        "fact",
        "31 December 2029",
        ((BR, "until 31 December 2029"),),
        None,
    ),
    (
        "What annual price reduction does the company grant Brenntal from 2026?",
        "fact",
        "2.0%",
        ((BR, "annual productivity reduction of 2.0%"),),
        2.0,
    ),
    (
        "What is the liability cap in the Brenntal agreement?",
        "fact",
        "EUR 15 million per contract year",
        ((BR, "capped at EUR 15 million per contract year"),),
        15,
    ),
    ("Which law governs the Brenntal agreement?", "fact", "German law", ((BR, "governed by German law"),), None),
    (
        "What are the payment terms in the Nordwind agreement?",
        "fact",
        "60 days from invoice",
        ((NW, "Payment terms are 60 days from invoice"),),
        60,
    ),
    (
        "Does a change of control allow Nordwind to terminate its agreement?",
        "fact",
        "No, the company must only notify Nordwind within 30 days",
        ((NW, "does not by itself give either party a right to terminate"),),
        None,
    ),
    (
        "How often may Valtrona audit the medical technology line?",
        "fact",
        "Twice per year",
        ((VA, "twice per year with 14 days' notice"),),
        None,
    ),
    (
        "What is the annual base rent for the Thun site?",
        "fact",
        "CHF 2.85 million",
        ((LE, "annual base rent is CHF 2.85 million"),),
        2.85,
    ),
    ("When does the Thun lease end?", "fact", "30 June 2033", ((LE, "lease term ends on 30 June 2033"),), None),
    (
        "What is the floor area of the Thun site?",
        "fact",
        "21,400 square metres",
        ((LE, "floor area of 21,400 square metres"),),
        21400,
    ),
    (
        "What is the amount of the Ostara Pumps warranty claim?",
        "fact",
        "CHF 1.2 million",
        ((LDD, "warranty claim of CHF 1.2 million"),),
        1.2,
    ),
    (
        "How many patents and patent applications does the company own?",
        "fact",
        "14",
        ((LDD, "owns 14 registered patents"),),
        14,
    ),
    (
        "How fast is the addressable market expected to grow?",
        "fact",
        "5.8% a year to 2030",
        ((CDD, "growing at 5.8% a year to 2030"),),
        5.8,
    ),
    ("What on-time delivery rate did customers report for FY2025?", "fact", "96%", ((CDD, "96% on-time"),), 96),
    (
        "What was the group effective tax rate in FY2025?",
        "fact",
        "22.0%",
        ((TDD, "effective tax rate was 22.0%"),),
        22.0,
    ),
    (
        "When does the Czech investment incentive expire?",
        "fact",
        "End of 2026",
        ((TDD, "expires at the end of 2026"),),
        None,
    ),
    (
        "What is the estimated environmental remediation cost at Thun?",
        "fact",
        "CHF 0.3 million",
        ((ENV, "remediation, if ever required, at CHF 0.3 million"),),
        0.3,
    ),
    (
        "Is the company certified to ISO 27001?",
        "fact",
        "No, a certification project is budgeted for 2026",
        ((IT, "not certified to ISO 27001"),),
        None,
    ),
    (
        "How many customer complaints were recorded in FY2025?",
        "fact",
        "29",
        ((QA, "Customer complaints fell from 41 in FY2024 to 29"),),
        29,
    ),
    (
        "What share of purchases did the largest raw-material supplier account for?",
        "fact",
        "22%",
        ((SUP, "accounted for 22% of purchases"),),
        22,
    ),
    (
        "What is the share capital of the company?",
        "fact",
        "CHF 4.0 million",
        ((ST, "share capital of the Company is CHF 4.0 million"),),
        4.0,
    ),
    (
        "Until when does the Brno collective agreement run?",
        "fact",
        "31 March 2027",
        ((HR, "runs until 31 March 2027"),),
        None,
    ),
    (
        "What is the interest cover covenant?",
        "fact",
        "At least 3.00x on each test date",
        ((TS, "must be at least 3.00x"),),
        3.0,
    ),
    (
        "Who is the lead arranger of the senior facilities?",
        "fact",
        "Lakeshore Credit Partners",
        ((TS, "Lead arranger: Lakeshore Credit Partners"),),
        None,
    ),
    (
        "Can Ostara Pumps terminate its supply agreement for convenience?",
        "fact",
        "Yes, with twelve months' notice",
        ((s.OSTARA.filename, "terminate the agreement for convenience"),),
        None,
    ),
    (
        "What can Lindqvist Hydraulics do if the company changes control?",
        "fact",
        "Ask to renegotiate prices within six months",
        ((s.LINDQVIST.filename, "may ask to renegotiate prices"),),
        None,
    ),
    (
        "What is the annual rent of the Brno warehouse?",
        "fact",
        "CZK 4.9 million",
        ((s.BRNO_LEASE.filename, "annual rent is CZK 4.9 million"),),
        4.9,
    ),
    (
        "What happens to the existing bank loan on a change of control?",
        "fact",
        "It becomes repayable",
        ((s.OLD_FACILITY.filename, "repayable on a change of control"),),
        None,
    ),
    (
        "What FY2025 budget did the board approve in December 2024?",
        "fact",
        "CHF 140.0 million revenue and CHF 24.5 million EBITDA",
        ((s.BOARD_Q4_24.filename, "approved the FY2025 budget of CHF 140.0 million"),),
        140.0,
    ),
    (
        "What headcount did the management accounts show for March 2025?",
        "numeric",
        "603",
        ((s.MONTHLY25.filename, "Key figures March 2025 (CHF million, unaudited)"),),
        603,
    ),
    # ------------------------------------------------------------------ numeric (tables and spreadsheets)
    (
        "What was audited net revenue in FY2025?",
        "numeric",
        "CHF 142.3 million",
        ((FS25, "Income statement for the year ended 31 December 2025"),),
        142.3,
    ),
    (
        "What was audited net revenue in FY2024?",
        "numeric",
        "CHF 131.0 million",
        ((FS24, "Income statement for the year ended 31 December 2024"),),
        131.0,
    ),
    (
        "What was net revenue in FY2023?",
        "numeric",
        "CHF 118.4 million",
        (any_of((FS23, "Income statement for the year ended 31 December 2023"), (MOD, "P&L!Revenue")),),
        118.4,
    ),
    (
        "What was EBITDA in FY2025?",
        "numeric",
        "CHF 25.1 million",
        (
            any_of(
                (FS25, "Income statement for the year ended 31 December 2025"),
                (MOD, "P&L!EBITDA"),
                (MP, "Budget FY2026 versus actual FY2025 (CHF million)"),
            ),
        ),
        25.1,
    ),
    (
        "What was net income in FY2024?",
        "numeric",
        "CHF 10.9 million",
        ((FS24, "Income statement for the year ended 31 December 2024"),),
        10.9,
    ),
    (
        "What was EBIT in FY2023?",
        "numeric",
        "CHF 13.1 million",
        (any_of((FS23, "Income statement for the year ended 31 December 2023"), (MOD, "P&L!EBIT")),),
        13.1,
    ),
    (
        "How much cash did the company hold at 31 December 2025?",
        "numeric",
        "CHF 14.2 million",
        (any_of((FS25, "Balance sheet at 31 December 2025 (CHF million)"), (MOD, "Balance sheet!Cash")),),
        14.2,
    ),
    (
        "What were total assets at 31 December 2024?",
        "numeric",
        "CHF 156.1 million",
        (any_of((FS24, "Balance sheet at 31 December 2024 (CHF million)"), (MOD, "Total assets")),),
        156.1,
    ),
    (
        "What were inventories at 31 December 2025?",
        "numeric",
        "CHF 31.4 million",
        ((FS25, "Balance sheet at 31 December 2025 (CHF million)"),),
        31.4,
    ),
    (
        "What was financial debt at 31 December 2023?",
        "numeric",
        "CHF 44.0 million",
        (any_of((FS23, "Balance sheet at 31 December 2023 (CHF million)"), (MOD, "Balance sheet!Financial debt")),),
        44.0,
    ),
    (
        "How large was the dividend paid in 2025?",
        "numeric",
        "CHF 3.1 million",
        ((FS25, "dividend of CHF 3.1 million"),),
        3.1,
    ),
    (
        "What was cash flow from operating activities in FY2025?",
        "numeric",
        "CHF 24.3 million",
        (
            any_of(
                (FS25, "Cash flow from operating activities was CHF 24.3 million"), (MOD, "Cash flow from operations")
            ),
        ),
        24.3,
    ),
    (
        "What revenue does the model forecast for FY2027?",
        "numeric",
        "CHF 160.2 million",
        ((MOD, "P&L!Revenue"),),
        160.2,
    ),
    ("What EBITDA margin does the model show for FY2028?", "numeric", "18.1%", ((MOD, "EBITDA margin"),), 0.181),
    (
        "What EBITDA does the budget assume for FY2026?",
        "numeric",
        "CHF 26.3 million",
        ((MP, "Budget FY2026 versus actual FY2025 (CHF million)"),),
        26.3,
    ),
    (
        "What is the size of the senior term loan B?",
        "numeric",
        "CHF 132.0 million",
        (any_of((MOD, "LBO!Senior term loan B"), (TS, "Senior term loan B | CHF 132.0 million")),),
        132.0,
    ),
    ("How much equity does the sponsor contribute?", "numeric", "CHF 84.9 million", ((MOD, "Sponsor equity"),), 84.9),
    ("What is the management rollover amount?", "numeric", "CHF 23.2 million", ((MOD, "Management rollover"),), 23.2),
    ("What enterprise value does the LBO assume?", "numeric", "CHF 225.9 million", ((MOD, "Enterprise value"),), 225.9),
    (
        "What entry multiple does the LBO use?",
        "numeric",
        "9.0x FY2025 EBITDA",
        ((MOD, "Entry multiple (EV / FY2025 EBITDA)"),),
        9.0,
    ),
    (
        "How much are transaction fees in the sources and uses?",
        "numeric",
        "CHF 7.4 million",
        ((MOD, "Transaction fees"),),
        7.4,
    ),
    (
        "What net debt does the model project for FY2027?",
        "numeric",
        "CHF 104.8 million",
        ((MOD, "LBO!Net debt"),),
        104.8,
    ),
    ("What interest cover does the model show for FY2026?", "numeric", "3.25x", ((MOD, "Interest cover"),), 3.25),
    (
        "What free cash flow does the model forecast for FY2026?",
        "numeric",
        "CHF 4.6 million",
        ((MOD, "Free cash flow"),),
        4.6,
    ),
    (
        "What working-capital build does the model assume for FY2026?",
        "numeric",
        "CHF 6.7 million",
        ((MOD, "Net working capital build"),),
        6.7,
    ),
    (
        "How much revenue did Brenntal Automotive generate in FY2025?",
        "numeric",
        "CHF 44.4 million",
        ((CON, "Brenntal Automotive GmbH"),),
        44.4,
    ),
    (
        "What share of FY2025 revenue came from Nordwind Rail Systems?",
        "numeric",
        "12.8%",
        ((CON, "Nordwind Rail Systems AB"),),
        0.128,
    ),
    (
        "How much revenue came from Valtrona Medical Systems in FY2025?",
        "numeric",
        "CHF 13.7 million",
        ((CON, "Valtrona Medical Systems SA"),),
        13.7,
    ),
    ("What is total capex planned for FY2027?", "numeric", "CHF 11.2 million", ((CAP, "Total capex"),), 11.2),
    (
        "How much does the five-axis line cost?",
        "numeric",
        "CHF 6.4 million",
        (any_of((CAP, "Growth capex - five-axis line"), (IM, "five-axis machining line for EV-7 housings")),),
        6.4,
    ),
    ("What maintenance capex is planned for FY2028?", "numeric", "CHF 5.3 million", ((CAP, "Maintenance capex"),), 5.3),
    (
        "What is the product liability insurance limit?",
        "numeric",
        "CHF 20 million",
        ((INS, "Product liability | CHF 20 million"),),
        20,
    ),
    (
        "What is the limit of the cyber insurance policy?",
        "numeric",
        "CHF 5 million",
        ((INS, "Cyber | CHF 5 million"),),
        5,
    ),
    (
        "What is the size of the revolving credit facility?",
        "numeric",
        "CHF 20.0 million",
        ((TS, "Revolving credit facility | CHF 20.0 million"),),
        20.0,
    ),
    # ------------------------------------------------------------------ cross-document checks
    (
        "Does FY2025 revenue in the information memorandum match the audited accounts?",
        "cross_doc",
        "No: the IM states CHF 148.6 million, the audited accounts CHF 142.3 million",
        (
            (IM, "Revenue reached CHF 148.6 million in FY2025"),
            (FS25, "Income statement for the year ended 31 December 2025"),
        ),
        142.3,
    ),
    (
        "Can the largest customer terminate its contract if Northgate acquires a majority stake?",
        "cross_doc",
        "Yes: clause 14.2 lets Brenntal terminate with 90 days' notice; Brenntal is 31.2% of revenue",
        ((BR, "more than 50% of the shares or voting"), (CON, "Brenntal Automotive GmbH")),
        None,
    ),
    (
        "How much headroom is there on the FY2026 net leverage covenant?",
        "cross_doc",
        "2.7%: model net leverage 4.38x against a 4.50x maximum",
        ((MOD, "Headroom"), (TS, "must not exceed 4.50x")),
        0.027,
    ),
    (
        "Has legal due diligence reviewed the change-of-control clause of the largest customer contract?",
        "cross_doc",
        "No: the Brenntal agreement has not been reviewed, and it contains a termination right in clause 14.2",
        ((LDD, "has not yet been reviewed"), (BR, "more than 50% of the shares or voting")),
        None,
    ),
    (
        "Does the EV-7 start of production in the budget match the latest information from Brenntal?",
        "cross_doc",
        "No: the budget assumes Q2 2026, the chair's note of 18 September 2025 says Q1 2027",
        ((MP, "The budget assumes EV-7 start of production in Q2 2026"), (SC_NOTE, "from Q2 2026 to Q1 2027.")),
        None,
    ),
    (
        "Does the bank confirmation agree with financial debt in the FY2025 balance sheet?",
        "cross_doc",
        "Yes: both show CHF 38.0 million",
        (
            (SC_BANK, "Term loan outstanding: CHF 38.0 million"),
            (FS25, "Balance sheet at 31 December 2025 (CHF million)"),
        ),
        38.0,
    ),
    (
        "Do revenues by customer add up to audited FY2025 revenue?",
        "cross_doc",
        "Yes: CHF 142.3 million",
        ((CON, "Total"), (FS25, "Income statement for the year ended 31 December 2025")),
        142.3,
    ),
    (
        "Is the five-axis line cost consistent between the information memorandum and the capex plan?",
        "cross_doc",
        "Yes: CHF 6.4 million in both",
        ((IM, "five-axis machining line for EV-7 housings"), (CAP, "Growth capex - five-axis line")),
        6.4,
    ),
    (
        "Is the pension liability in the HR summary consistent with the balance sheet?",
        "cross_doc",
        "Yes: CHF 6.4 million in both",
        ((HR, "pension liability was CHF 6.4 million"), (FS25, "Balance sheet at 31 December 2025 (CHF million)")),
        6.4,
    ),
    (
        "Does the lease addendum cap rent increases, and what is the current rent?",
        "cross_doc",
        "Yes, increases are capped at 2.0% a year; base rent is CHF 2.85 million",
        ((SC_LEASE, "at 2.0 percent per year."), (LE, "annual base rent is CHF 2.85 million")),
        2.0,
    ),
    (
        "How much additional price reduction did Brenntal request on top of the contractual reduction?",
        "cross_doc",
        "An additional 2%, on top of the contractual 2.0% a year",
        ((BM, "asked for an additional 2% price reduction"), (BR, "annual productivity reduction of 2.0%")),
        2.0,
    ),
    (
        "Is the FY2026 revenue in the model the same as in the budget?",
        "cross_doc",
        "Yes: CHF 151.0 million",
        ((MOD, "P&L!Revenue"), (MP, "Budget FY2026 versus actual FY2025 (CHF million)")),
        151.0,
    ),
    # ------------------------------------------------------------------ OCR (scanned documents)
    (
        "What annual volume does Brenntal commit to in Schedule 3?",
        "ocr",
        "At least 1.2 million EV-7 motor housings",
        ((SC_BR, "The Buyer commits to purchase at least 1.2 million"),),
        1.2,
    ),
    (
        "When was the Brenntal agreement signed?",
        "ocr",
        "4 February 2022",
        ((SC_BR, "Signed in Leipzig on 4 February 2022"),),
        None,
    ),
    (
        "By how much does the chair expect FY2026 revenue to fall short of budget?",
        "ocr",
        "About CHF 4 million",
        ((SC_NOTE, "Expect FY26 revenue about 4m below budget."),),
        4,
    ),
    (
        "When was the lease addendum signed?",
        "ocr",
        "12 March 2024",
        ((SC_LEASE, "Signed in Thun on 12 March 2024"),),
        None,
    ),
    (
        "Can the existing bank loan be prepaid without penalty?",
        "ocr",
        "Yes, on any interest date",
        ((SC_BANK, "The loan may be prepaid on any interest date"),),
        None,
    ),
    (
        "Which bank provided the balance confirmation?",
        "ocr",
        "Seeland Regionalbank AG",
        ((SC_BANK, "Seeland Regionalbank AG"),),
        None,
    ),
    # ------------------------------------------------------------------ unanswerable
    ("What is the CEO's annual salary?", "unanswerable", "", (), None),
    ("What was the company's revenue in FY2019?", "unanswerable", "", (), None),
    ("How many patents does Brenntal Automotive hold?", "unanswerable", "", (), None),
    ("What is the purchase price offered by competing bidders?", "unanswerable", "", (), None),
    ("What is the company's carbon footprint in tonnes of CO2?", "unanswerable", "", (), None),
    ("Which software vendor supplied the new ERP system?", "unanswerable", "", (), None),
    ("What is the Brno plant's annual energy cost?", "unanswerable", "", (), None),
    ("How many shares does the CFO own?", "unanswerable", "", (), None),
    ("What order intake does management target for FY2027?", "unanswerable", "", (), None),
    ("What credit rating does the company have?", "unanswerable", "", (), None),
    ("What is the warranty provision at 31 December 2025?", "unanswerable", "", (), None),
    ("What is the expected closing date of the transaction?", "unanswerable", "", (), None),
]


def gold_set() -> list[Gold]:
    return [
        Gold(f"q{index:03d}", question, qtype, answer, evidence, value)
        for index, (question, qtype, answer, evidence, value) in enumerate(_RAW, start=1)
    ]


# ------------------------------------------------------------------------ resolution


def _pdf_locations(doc: s.PdfDoc, needle: str) -> list[dict[str, object]]:
    from dealroom.synth.render import page_texts

    return [{"file": doc.filename, "page": i + 1} for i, text in enumerate(page_texts(doc)) if needle in text]


def _xlsx_locations(doc: s.XlsxDoc, needle: str) -> list[dict[str, object]]:
    sheet_name, _, label = needle.rpartition("!")
    hits: list[dict[str, object]] = []
    for sheet in doc.sheets:
        if sheet_name and sheet.name != sheet_name:
            continue
        for row_index, row in enumerate(sheet.rows, start=1):
            if row and row[0] == label:
                hits.append({"file": doc.filename, "sheet": sheet.name, "row": row_index, "cell": f"A{row_index}"})
    return hits


def resolve(filename: str, needle: str) -> dict[str, object]:
    doc = next((d for d in s.DOCS if d.filename == filename), None)
    if doc is None:
        raise KeyError(f"unknown document {filename}")
    if isinstance(doc, s.PdfDoc):
        hits = _pdf_locations(doc, needle)
    elif isinstance(doc, s.XlsxDoc):
        hits = _xlsx_locations(doc, needle)
    else:
        hits = [{"file": filename, "page": 1}] if any(needle in line for line in doc.lines) else []
    if len(hits) != 1:
        raise ValueError(f"needle {needle!r} in {filename} matched {len(hits)} locations")
    return hits[0]


def _resolve_item(item: Evidence) -> dict[str, object]:
    if isinstance(item, AnyOf):
        return {"any_of": [resolve(f, n) | {"needle": n} for f, n in item]}
    file, needle = item
    return resolve(file, needle) | {"needle": needle}


def write_eval_files(eval_dir: Path) -> int:
    eval_dir.mkdir(parents=True, exist_ok=True)
    rows = []
    for gold in gold_set():
        rows.append(
            {
                "id": gold.id,
                "question": gold.question,
                "type": gold.type,
                "answer": gold.answer,
                "value": gold.value,
                "evidence": [_resolve_item(item) for item in gold.evidence],
            }
        )
    (eval_dir / "gold.jsonl").write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows))
    traps = [
        {
            "id": t.id,
            "title": t.title,
            "description": t.description,
            "keywords": list(t.keywords),
            "evidence": [resolve(f, n) | {"needle": n} for f, n in t.evidence],
        }
        for t in s.TRAPS
    ]
    (eval_dir / "traps.json").write_text(json.dumps(traps, indent=2, ensure_ascii=False) + "\n")
    return len(rows)
