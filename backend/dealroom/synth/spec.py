"""Single source of truth for the synthetic data room.

Every company, person, figure and clause below is fictional. The gold set in
``gold.py`` points at passages in this module by an exact text needle, and the
generator resolves each needle to a file and page (or sheet and cell). Editing a
passage here therefore moves its evidence location automatically, and the build
fails loudly if a needle no longer matches exactly one place.

Amounts are in CHF million unless stated otherwise. Financial year = calendar year.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

# --------------------------------------------------------------------------- blocks


@dataclass(frozen=True)
class H:
    text: str


@dataclass(frozen=True)
class P:
    text: str


@dataclass(frozen=True)
class T:
    caption: str
    header: tuple[str, ...]
    rows: tuple[tuple[str, ...], ...]


Block = H | P | T
Page = tuple[Block, ...]


@dataclass(frozen=True)
class PdfDoc:
    filename: str
    title: str
    pages: tuple[Page, ...]
    kind: Literal["pdf"] = "pdf"


@dataclass(frozen=True)
class ScanDoc:
    """Image-only PDF. ``lines`` is also the OCR ground truth."""

    filename: str
    title: str
    lines: tuple[str, ...]
    style: Literal["typed", "handwritten"] = "typed"
    kind: Literal["scan"] = "scan"


@dataclass(frozen=True)
class Sheet:
    name: str
    rows: tuple[tuple[str | float | None, ...], ...]


@dataclass(frozen=True)
class XlsxDoc:
    filename: str
    title: str
    sheets: tuple[Sheet, ...]
    kind: Literal["xlsx"] = "xlsx"


Doc = PdfDoc | ScanDoc | XlsxDoc


@dataclass(frozen=True)
class Trap:
    id: str
    title: str
    description: str
    evidence: tuple[tuple[str, str], ...]  # (filename, needle)
    keywords: tuple[str, ...] = field(default_factory=tuple)


# ----------------------------------------------------------------- setting

FUND = "Northgate Capital Partners"
TARGET = "Alpine Precision Components AG"
TARGET_SHORT = "Alpine Precision"
SUBSIDIARY = "Alpine Precision CZ s.r.o."

# fictional people (masked by the anonymiser before anything leaves the trust boundary)
CEO = "Corinne Vasseli"
CFO = "Tobias Arnhold"
COO = "Lukas Imfeld"
CHAIR = "Reto Wyssbrod"

# --------------------------------------------------------------------------- documents

IM = PdfDoc(
    "01_information_memorandum.pdf",
    "Project Edelweiss - Information Memorandum",
    (
        (
            H("Project Edelweiss - Information Memorandum"),
            P(
                f"This Information Memorandum has been prepared on behalf of the shareholders of {TARGET} "
                f"(the Company) for a limited number of parties considering the acquisition of a majority "
                f"stake. The Company is owned by the Hosmatter family, who intend to sell 70% of the shares "
                f"and retain 30% alongside management."
            ),
            H("1. Investment highlights"),
            P(
                "The Company is a Swiss precision machining specialist founded in 1987 in Thun. It supplies "
                "machined housings, shafts and fluid-control parts to automotive, rail and medical technology "
                "customers in Europe."
            ),
            P(
                "Revenue reached CHF 148.6 million in FY2025, up from CHF 131.0 million in FY2024, "
                "with adjusted EBITDA of CHF 26.8 million."
            ),
            P(
                "Order backlog stood at CHF 96.4 million on 30 September 2025, equivalent to roughly eight "
                "months of revenue."
            ),
        ),
        (
            H("2. Business overview"),
            P(
                "The Company operates two plants: the headquarters plant in Thun, Switzerland, and a plant in "
                f"Brno, Czech Republic, held through {SUBSIDIARY}. The Brno plant opened in 2014 and focuses "
                "on high-volume turned parts."
            ),
            P("At the end of FY2025 the Company employed 612 people, of whom 418 work in Thun and 194 in Brno."),
            P(
                "End markets in FY2025 were automotive (58% of revenue), rail (19%), medical technology (14%) "
                "and general industry (9%). Electric-vehicle drivetrain parts represent 41% of automotive revenue."
            ),
            T(
                "Revenue by end market, FY2025 (share of revenue)",
                ("End market", "Share"),
                (("Automotive", "58%"), ("Rail", "19%"), ("Medical technology", "14%"), ("General industry", "9%")),
            ),
        ),
        (
            H("3. Customers"),
            P(
                "The Company serves around 140 active customers. The three largest are Brenntal Automotive GmbH, "
                "Nordwind Rail Systems AB and Valtrona Medical Systems SA. The relationship with Brenntal "
                "Automotive dates back to 2009."
            ),
            P(
                "Brenntal Automotive has nominated the Company as single source for the motor housing of its "
                "EV-7 electric drive platform, with start of production planned for Q2 2026."
            ),
            H("4. Operations"),
            P(
                "The Thun plant runs 74 CNC machining centres in a three-shift pattern. Overall equipment "
                "effectiveness was 78% in FY2025 and the scrap rate was 1.8%."
            ),
            P("A new five-axis machining line for EV-7 housings is planned for FY2027 at a cost of CHF 6.4 million."),
        ),
        (
            H("5. Management"),
            P(
                f"The Company is led by Chief Executive Officer {CEO}, who joined in 2016, Chief Financial "
                f"Officer {CFO}, who joined in 2019, and Chief Operating Officer {COO}, who joined in 2021. "
                f"The board is chaired by {CHAIR}."
            ),
            P(
                "Management intends to reinvest part of its proceeds and hold a combined 8% of the shares after "
                "closing."
            ),
            H("6. Process"),
            P(
                "Non-binding offers are requested by 14 November 2025. Selected bidders will receive access to "
                "the virtual data room and management sessions in Thun."
            ),
            P(
                "Enquiries should be addressed to the sell-side adviser at edelweiss@hosmatter-advisory.example "
                "or +41 31 555 02 40."
            ),
        ),
    ),
)

MGMT_PRES = PdfDoc(
    "02_management_presentation.pdf",
    "Management presentation - October 2025",
    (
        (
            H("Management presentation - October 2025"),
            P(
                "Our strategy for 2026 to 2028 rests on three priorities: winning EV drivetrain programmes, "
                "growing the medical technology line in Thun, and lifting Brno utilisation above 85%."
            ),
            P("Brno utilisation was 71% in FY2025."),
        ),
        (
            H("Budget FY2026"),
            P(
                "The board approved a FY2026 budget of CHF 151.0 million revenue and CHF 26.3 million EBITDA. "
                "The budget assumes EV-7 start of production in Q2 2026."
            ),
            T(
                "Budget FY2026 versus actual FY2025 (CHF million)",
                ("Line", "FY2025 actual", "FY2026 budget"),
                (("Revenue", "142.3", "151.0"), ("EBITDA", "25.1", "26.3"), ("Capex", "9.1", "9.8")),
            ),
        ),
        (
            H("Medical technology"),
            P(
                "The medical technology line in Thun is certified to ISO 13485 and produced parts for 23 customers "
                "in FY2025. Valtrona Medical Systems is the largest of them."
            ),
            P("Management targets medical technology revenue of CHF 26 million by FY2028."),
        ),
        (
            H("People"),
            P("Voluntary staff turnover was 6.4% in FY2025. The Company trains 38 apprentices across both sites."),
        ),
    ),
)


def _fs(
    year: int, is_rows: tuple[tuple[str, ...], ...], bs_rows: tuple[tuple[str, ...], ...], notes: tuple[Block, ...]
) -> PdfDoc:
    auditor = P(
        f"Birchwood & Partner Revision AG audited the consolidated financial statements of {TARGET} for the year "
        f"ended 31 December {year}, prepared in accordance with Swiss GAAP FER. In our opinion the financial "
        f"statements for FY{year} give a true and fair view. Our opinion on FY{year} is unqualified."
    )
    return PdfDoc(
        f"0{year - 2020}_audited_financial_statements_FY{year}.pdf",
        f"{TARGET} - Audited financial statements FY{year}",
        (
            (H(f"{TARGET} - Financial statements {year}"), H("Report of the statutory auditor"), auditor),
            (
                H(f"Income statement FY{year}"),
                T(
                    f"Income statement for the year ended 31 December {year} (CHF million)",
                    ("Line item", f"FY{year}"),
                    is_rows,
                ),
            ),
            (
                H(f"Balance sheet at 31 December {year}"),
                T(f"Balance sheet at 31 December {year} (CHF million)", ("Line item", f"31.12.{year}"), bs_rows),
                *notes,
            ),
        ),
    )


FS23 = _fs(
    2023,
    (
        ("Net revenue", "118.4"),
        ("Cost of goods sold", "-79.8"),
        ("Gross profit", "38.6"),
        ("Selling, general and administrative expenses", "-19.0"),
        ("EBITDA", "19.6"),
        ("Depreciation and amortisation", "-6.5"),
        ("EBIT", "13.1"),
        ("Net financial expense", "-1.9"),
        ("Profit before tax", "11.2"),
        ("Income taxes", "-2.5"),
        ("Net income", "8.7"),
    ),
    (
        ("Property, plant and equipment", "66.4"),
        ("Intangible assets", "10.2"),
        ("Inventories", "27.3"),
        ("Trade receivables", "23.1"),
        ("Other current assets", "10.4"),
        ("Cash and cash equivalents", "9.8"),
        ("Total assets", "147.2"),
        ("Shareholders' equity", "66.2"),
        ("Financial debt", "44.0"),
        ("Pension liabilities", "5.9"),
        ("Trade payables", "15.8"),
        ("Other liabilities", "15.3"),
        ("Total liabilities and equity", "147.2"),
    ),
    (P("Note 12: The Company paid a dividend of CHF 2.0 million to its shareholders in 2023."),),
)

FS24 = _fs(
    2024,
    (
        ("Net revenue", "131.0"),
        ("Cost of goods sold", "-87.6"),
        ("Gross profit", "43.4"),
        ("Selling, general and administrative expenses", "-20.5"),
        ("EBITDA", "22.9"),
        ("Depreciation and amortisation", "-7.1"),
        ("EBIT", "15.8"),
        ("Net financial expense", "-1.8"),
        ("Profit before tax", "14.0"),
        ("Income taxes", "-3.1"),
        ("Net income", "10.9"),
    ),
    (
        ("Property, plant and equipment", "69.1"),
        ("Intangible assets", "9.8"),
        ("Inventories", "29.0"),
        ("Trade receivables", "25.4"),
        ("Other current assets", "11.2"),
        ("Cash and cash equivalents", "11.6"),
        ("Total assets", "156.1"),
        ("Shareholders' equity", "74.1"),
        ("Financial debt", "41.0"),
        ("Pension liabilities", "6.1"),
        ("Trade payables", "17.2"),
        ("Other liabilities", "17.7"),
        ("Total liabilities and equity", "156.1"),
    ),
    (P("Note 12: The Company paid a dividend of CHF 2.6 million to its shareholders in 2024."),),
)

FS25 = _fs(
    2025,
    (
        ("Net revenue", "142.3"),
        ("Cost of goods sold", "-94.4"),
        ("Gross profit", "47.9"),
        ("Selling, general and administrative expenses", "-22.8"),
        ("EBITDA", "25.1"),
        ("Depreciation and amortisation", "-7.5"),
        ("EBIT", "17.6"),
        ("Net financial expense", "-1.7"),
        ("Profit before tax", "15.9"),
        ("Income taxes", "-3.5"),
        ("Net income", "12.4"),
    ),
    (
        ("Property, plant and equipment", "71.8"),
        ("Intangible assets", "9.3"),
        ("Inventories", "31.4"),
        ("Trade receivables", "27.9"),
        ("Other current assets", "12.9"),
        ("Cash and cash equivalents", "14.2"),
        ("Total assets", "167.5"),
        ("Shareholders' equity", "82.6"),
        ("Financial debt", "38.0"),
        ("Pension liabilities", "6.4"),
        ("Trade payables", "18.7"),
        ("Other liabilities", "21.8"),
        ("Total liabilities and equity", "167.5"),
    ),
    (
        P(
            "Note 9: Cash flow from operating activities was CHF 24.3 million and capital expenditure was "
            "CHF 9.1 million in FY2025."
        ),
        P("Note 12: The Company paid a dividend of CHF 3.1 million to its shareholders in 2025."),
    ),
)

BRENNTAL = PdfDoc(
    "06_customer_contract_brenntal_automotive.pdf",
    "Framework supply agreement - Brenntal Automotive GmbH",
    (
        (
            H("Framework supply agreement No. BA-2022-0147"),
            P(
                f"This framework supply agreement is made between Brenntal Automotive GmbH, Leipziger Ring 40, "
                f"04103 Leipzig, Germany (the Buyer) and {TARGET}, Industriestrasse 14, 3600 Thun, Switzerland "
                f"(the Supplier)."
            ),
            H("Clause 3. Term"),
            P("The agreement runs from 1 March 2022 until 31 December 2029 unless terminated earlier under clause 14."),
            H("Clause 6. Prices"),
            P(
                "Prices are fixed in euro. From 1 January 2026 the Supplier grants the Buyer an annual productivity "
                "reduction of 2.0% on all part prices."
            ),
        ),
        (
            H("Clause 9. Quality"),
            P("The Supplier shall maintain IATF 16949 certification for the duration of the agreement."),
            H("Clause 11. Liability"),
            P("The Supplier's aggregate liability under this agreement is capped at EUR 15 million per contract year."),
            H("Clause 14. Termination"),
            P(
                "14.1 Either party may terminate for material breach that is not remedied within 60 days of "
                "written notice."
            ),
            P(
                "14.2 If any third party acquires, directly or indirectly, more than 50% of the shares or voting "
                "rights in the Supplier without the Buyer's prior written consent, the Buyer may terminate this "
                "agreement with 90 days' written notice."
            ),
        ),
        (
            H("Clause 18. Governing law"),
            P("This agreement is governed by German law. The courts of Leipzig have exclusive jurisdiction."),
            P(
                f"Contact for notices to the Supplier: {CFO}, tobias.arnhold@alpine-precision.example, "
                "+41 33 555 01 12."
            ),
        ),
    ),
)

NORDWIND = PdfDoc(
    "07_customer_contract_nordwind_rail.pdf",
    "Supply agreement - Nordwind Rail Systems AB",
    (
        (
            H("Supply agreement - Nordwind Rail Systems AB"),
            P(
                f"Nordwind Rail Systems AB of Gothenburg, Sweden, purchases bogie and brake-system components "
                f"from {TARGET} under this agreement dated 15 June 2021. The agreement runs until 30 June 2027 "
                f"and renews automatically for two-year periods."
            ),
            P("Payment terms are 60 days from invoice."),
        ),
        (
            H("Clause 12. Change of control"),
            P(
                "The Supplier shall inform Nordwind in writing within 30 days after any change of control of the "
                "Supplier. A change of control does not by itself give either party a right to terminate."
            ),
        ),
    ),
)

VALTRONA = PdfDoc(
    "08_customer_contract_valtrona_medical.pdf",
    "Supply and quality agreement - Valtrona Medical Systems SA",
    (
        (
            H("Supply and quality agreement - Valtrona Medical Systems SA"),
            P(
                "Valtrona Medical Systems SA of Lausanne buys implant-grade titanium components produced on the "
                "ISO 13485 line in Thun. The agreement was signed on 2 November 2023 for a term of five years."
            ),
        ),
        (
            H("Clause 7. Audits"),
            P("Valtrona may audit the Supplier's medical technology line twice per year with 14 days' notice."),
            P("The agreement contains no change-of-control provision."),
        ),
    ),
)

LEASE = PdfDoc(
    "09_lease_agreement_thun.pdf",
    "Lease agreement - Thun production site",
    (
        (
            H("Lease agreement - Industriestrasse 14, Thun"),
            P(
                f"Aarefeld Immobilien AG (the Landlord) leases to {TARGET} (the Tenant) the production hall, "
                "offices and yard at Industriestrasse 14, 3600 Thun, with a floor area of 21,400 square metres."
            ),
            P("The annual base rent is CHF 2.85 million, payable quarterly in advance."),
        ),
        (
            P(
                "The lease term ends on 30 June 2033. The Tenant holds two options to extend the lease by five "
                "years each."
            ),
            P(
                "The lease may be assigned to an affiliate of the Tenant with the Landlord's consent, which may not "
                "be unreasonably withheld."
            ),
        ),
    ),
)

CVS = PdfDoc(
    "10_management_cvs.pdf",
    "Management CVs",
    (
        (
            H(f"{CEO} - Chief Executive Officer"),
            P(
                f"{CEO} has led the Company since 2016. Before that she spent eleven years at a German machine "
                "tool maker, latterly as head of the turned-parts division. She holds a master's degree in "
                "mechanical engineering. Email: corinne.vasseli@alpine-precision.example, phone +41 33 555 01 10."
            ),
            H(f"{CFO} - Chief Financial Officer"),
            P(
                f"{CFO} joined as CFO in 2019 from an industrial holding company where he ran group controlling. "
                "He is a Swiss certified expert in accounting and controlling."
            ),
        ),
        (
            H(f"{COO} - Chief Operating Officer"),
            P(
                f"{COO} joined in 2021 to run both plants. He previously managed a rail components plant and led "
                "the start-up of the Brno second shift. Private address: Seestrasse 7, 3700 Spiez. "
                "Salary account IBAN CH93 0076 2011 6238 5295 7."
            ),
        ),
    ),
)

LEGAL_DD = PdfDoc(
    "11_legal_due_diligence_summary.pdf",
    "Legal due diligence - summary report",
    (
        (
            H("Legal due diligence - summary report"),
            P("Prepared by Kaltbrunner Rechtsanwaelte for the bidders, version of 3 November 2025."),
            H("Litigation"),
            P(
                "Ostara Pumps has filed a warranty claim of CHF 1.2 million concerning valve bodies delivered in "
                "2024. The Company disputes the claim and has made no provision."
            ),
            H("Intellectual property"),
            P("The Company owns 14 registered patents and patent applications, mainly for clamping fixtures."),
        ),
        (
            H("Material contracts"),
            P(
                "We reviewed the change-of-control provisions of the Nordwind and Valtrona agreements. "
                "The Brenntal agreement was provided late and has not yet been reviewed."
            ),
            H("Real estate"),
            P("The Thun site is leased. The Brno plant and its land are owned by the Czech subsidiary."),
        ),
    ),
)

COMMERCIAL_DD = PdfDoc(
    "12_commercial_due_diligence_summary.pdf",
    "Commercial due diligence - summary",
    (
        (
            H("Commercial due diligence - summary"),
            P(
                "The addressable European market for precision machined drivetrain and fluid-control parts is "
                "estimated at EUR 4.1 billion, growing at 5.8% a year to 2030."
            ),
            P("Customer interviews rated the Company's delivery reliability at 96% on-time in FY2025."),
        ),
        (
            H("Pricing"),
            P(
                "Automotive customers typically require annual price reductions of 1.5% to 3.0%. Rail and medical "
                "customers accept cost pass-through clauses for raw materials."
            ),
        ),
    ),
)

TAX_DD = PdfDoc(
    "13_tax_due_diligence_summary.pdf",
    "Tax due diligence - summary",
    (
        (
            H("Tax due diligence - summary"),
            P("The group effective tax rate was 22.0% in FY2025. There are no open tax audits in Switzerland."),
            P("The Czech subsidiary benefits from an investment incentive that expires at the end of 2026."),
        ),
    ),
)

ENV = PdfDoc(
    "14_environmental_site_assessment.pdf",
    "Phase I environmental site assessment - Thun",
    (
        (
            H("Phase I environmental site assessment - Thun"),
            P(
                "Historical use of chlorinated solvents for degreasing was identified until 1998. The assessor rates "
                "the risk as low and estimates remediation, if ever required, at CHF 0.3 million."
            ),
        ),
    ),
)

INSURANCE = PdfDoc(
    "15_insurance_schedule.pdf",
    "Insurance schedule 2025",
    (
        (
            H("Insurance schedule 2025"),
            T(
                "Insurance programme",
                ("Policy", "Limit"),
                (
                    ("Product liability", "CHF 20 million"),
                    ("Property and business interruption", "CHF 95 million"),
                    ("Directors and officers", "CHF 10 million"),
                    ("Cyber", "CHF 5 million"),
                ),
            ),
        ),
    ),
)

HR = PdfDoc(
    "16_hr_and_pensions_summary.pdf",
    "HR and pensions summary",
    (
        (
            H("HR and pensions summary"),
            P(
                "Swiss employees are insured in a defined-contribution plan with a collective foundation. The Swiss "
                "GAAP FER pension liability was CHF 6.4 million at 31 December 2025."
            ),
            P("Employees in Brno are covered by a collective agreement that runs until 31 March 2027."),
        ),
    ),
)

IT = PdfDoc(
    "17_it_and_cybersecurity_review.pdf",
    "IT and cybersecurity review",
    (
        (
            H("IT and cybersecurity review"),
            P(
                "The ERP migration was completed in 2024. A ransomware incident in 2023 was contained within two days "
                "with no data loss."
            ),
            P("The Company is not certified to ISO 27001. A certification project is budgeted for 2026."),
        ),
    ),
)

QUALITY = PdfDoc(
    "18_quality_and_certifications.pdf",
    "Quality and certifications",
    (
        (
            H("Quality and certifications"),
            P(
                "The Thun plant holds ISO 9001, IATF 16949 and ISO 13485 certificates. Brno holds ISO 9001 and "
                "IATF 16949."
            ),
            P("Customer complaints fell from 41 in FY2024 to 29 in FY2025."),
        ),
    ),
)

BOARD_MINUTES = PdfDoc(
    "19_board_minutes_q2_2025.pdf",
    "Minutes of the board meeting of 24 June 2025",
    (
        (
            H("Minutes of the board meeting of 24 June 2025"),
            P(f"Present: {CHAIR} (chair), {CEO}, {CFO}, two non-executive directors."),
            P("The board approved the sale process and appointed a sell-side adviser."),
        ),
        (
            P(
                "Brenntal Automotive asked for an additional 2% price reduction from 2026. Management will reply "
                "after the EV-7 nomination is confirmed."
            ),
        ),
    ),
)

TERM_SHEET = PdfDoc(
    "20_senior_facilities_term_sheet.pdf",
    "Senior facilities - indicative term sheet",
    (
        (
            H("Senior facilities - indicative term sheet"),
            P(
                "Lead arranger: Lakeshore Credit Partners. Borrower: a newly formed acquisition company owned by "
                f"funds advised by {FUND}."
            ),
            T(
                "Facilities",
                ("Facility", "Amount", "Tenor", "Margin"),
                (
                    ("Senior term loan B", "CHF 132.0 million", "7 years", "SARON + 4.25%"),
                    ("Revolving credit facility", "CHF 20.0 million", "6 years", "SARON + 3.75%"),
                ),
            ),
        ),
        (
            H("Financial covenants"),
            P(
                "Net leverage (net debt to EBITDA) must not exceed 4.50x at 31 December 2026, 4.00x at "
                "31 December 2027 and 3.50x at 31 December 2028 and thereafter."
            ),
            P("Interest cover (EBITDA to net interest) must be at least 3.00x on each test date."),
            P("Covenants are tested annually on audited figures."),
        ),
    ),
)

SUPPLIERS = PdfDoc(
    "21_supplier_overview.pdf",
    "Supplier overview",
    (
        (
            H("Supplier overview"),
            P(
                "Steel and aluminium bar is sourced from three suppliers. The largest supplier accounted for 22% of "
                "purchases in FY2025."
            ),
            P("Titanium bar for the medical line is sourced from a single qualified supplier."),
        ),
    ),
)

STRUCTURE = PdfDoc(
    "22_corporate_structure.pdf",
    "Corporate structure",
    (
        (
            H("Corporate structure"),
            P(f"{TARGET}, Thun, owns 100% of {SUBSIDIARY}, Brno. There are no other subsidiaries or joint ventures."),
            P("The share capital of the Company is CHF 4.0 million, divided into 40,000 registered shares."),
        ),
    ),
)

# ------------------------------------------------------------------- spreadsheets

MODEL = XlsxDoc(
    "23_financial_model.xlsx",
    "Financial model",
    (
        Sheet(
            "P&L",
            (
                ("CHF million", "FY2023A", "FY2024A", "FY2025A", "FY2026E", "FY2027E", "FY2028E"),
                ("Revenue", 118.4, 131.0, 142.3, 151.0, 160.2, 168.9),
                ("EBITDA", 19.6, 22.9, 25.1, 26.3, 28.4, 30.6),
                ("EBITDA margin", 0.166, 0.175, 0.176, 0.174, 0.177, 0.181),
                ("Depreciation and amortisation", -6.5, -7.1, -7.5, -8.0, -8.6, -9.1),
                ("EBIT", 13.1, 15.8, 17.6, 18.3, 19.8, 21.5),
            ),
        ),
        Sheet(
            "Balance sheet",
            (
                ("CHF million", "FY2023A", "FY2024A", "FY2025A"),
                ("Total assets", 147.2, 156.1, 167.5),
                ("Shareholders' equity", 66.2, 74.1, 82.6),
                ("Financial debt", 44.0, 41.0, 38.0),
                ("Cash", 9.8, 11.6, 14.2),
                ("Net debt", 34.2, 29.4, 23.8),
            ),
        ),
        Sheet(
            "Cash flow",
            (
                ("CHF million", "FY2025A", "FY2026E", "FY2027E", "FY2028E"),
                ("Cash flow from operations", 24.3, 14.4, 24.9, 27.6),
                ("Net working capital build", None, -6.7, -1.9, -1.6),
                ("Capital expenditure", -9.1, -9.8, -11.2, -8.1),
                ("Free cash flow", 15.2, 4.6, 13.7, 19.5),
            ),
        ),
        Sheet(
            "LBO",
            (
                ("Sources and uses at closing", "CHF million"),
                ("Senior term loan B", 132.0),
                ("Sponsor equity", 84.9),
                ("Management rollover", 23.2),
                ("Total sources", 240.1),
                ("Purchase of shares", 202.1),
                ("Refinancing of existing net debt", 23.8),
                ("Transaction fees", 7.4),
                ("Cash to balance sheet", 6.8),
                ("Total uses", 240.1),
                ("Enterprise value", 225.9),
                ("Entry multiple (EV / FY2025 EBITDA)", 9.0),
                (None, None),
                ("Covenant test", "FY2026E", "FY2027E", "FY2028E"),
                ("Net debt", 115.2, 104.8, 92.3),
                ("EBITDA", 26.3, 28.4, 30.6),
                ("Net leverage", 4.38, 3.69, 3.02),
                ("Covenant maximum", 4.50, 4.00, 3.50),
                ("Headroom", 0.027, 0.078, 0.137),
                ("Net interest", 8.1, 7.6, 6.9),
                ("Interest cover", 3.25, 3.74, 4.43),
            ),
        ),
    ),
)

CONCENTRATION = XlsxDoc(
    "24_customer_concentration.xlsx",
    "Customer concentration FY2025",
    (
        Sheet(
            "FY2025",
            (
                ("Customer", "Revenue CHF m", "Share of revenue", "Segment"),
                ("Brenntal Automotive GmbH", 44.4, 0.312, "Automotive"),
                ("Nordwind Rail Systems AB", 18.2, 0.128, "Rail"),
                ("Valtrona Medical Systems SA", 13.7, 0.096, "Medical technology"),
                ("Ostara Pumps", 8.1, 0.057, "General industry"),
                ("Lindqvist Hydraulics", 6.9, 0.048, "General industry"),
                ("Ferrovia Componenti", 5.5, 0.039, "Rail"),
                ("All other customers", 45.5, 0.320, "Mixed"),
                ("Total", 142.3, 1.0, None),
            ),
        ),
    ),
)

CAPEX = XlsxDoc(
    "25_capex_plan.xlsx",
    "Capex plan FY2026-FY2028",
    (
        Sheet(
            "Capex",
            (
                ("CHF million", "FY2026E", "FY2027E", "FY2028E"),
                ("Maintenance capex", 5.1, 4.8, 5.3),
                ("Growth capex - EV-7 tooling", 4.7, None, None),
                ("Growth capex - five-axis line", None, 6.4, None),
                ("Growth capex - Brno automation", None, None, 2.8),
                ("Total capex", 9.8, 11.2, 8.1),
            ),
        ),
    ),
)

# --------------------------------------------------------------------------- scans

SCAN_BRENNTAL = ScanDoc(
    "26_scan_brenntal_signature_page.pdf",
    "Scanned signature page - Brenntal agreement",
    (
        "FRAMEWORK SUPPLY AGREEMENT No. BA-2022-0147",
        "Schedule 3 - Annual volume commitment",
        "The Buyer commits to purchase at least 1.2 million",
        "EV-7 motor housings per contract year from 2027.",
        "Signed in Leipzig on 4 February 2022",
        "for Brenntal Automotive GmbH",
        "for Alpine Precision Components AG",
    ),
)

SCAN_BOARD_NOTE = ScanDoc(
    "27_scan_handwritten_board_note.pdf",
    "Handwritten note from the chair, 18 September 2025",
    (
        "Note 18 Sept 2025",
        "Call with Brenntal purchasing today.",
        "EV-7 start of production moved",
        "from Q2 2026 to Q1 2027.",
        "Expect FY26 revenue about 4m below budget.",
        "Discuss with advisers before disclosure.",
    ),
    style="handwritten",
)

SCAN_LEASE_ADDENDUM = ScanDoc(
    "28_scan_lease_addendum.pdf",
    "Scanned lease addendum No. 1",
    (
        "ADDENDUM No. 1 TO THE LEASE AGREEMENT THUN",
        "The base rent is indexed to the Swiss consumer",
        "price index once a year. Any increase is capped",
        "at 2.0 percent per year.",
        "Signed in Thun on 12 March 2024",
    ),
)

SCAN_BANK_LETTER = ScanDoc(
    "29_scan_bank_confirmation_letter.pdf",
    "Scanned bank confirmation letter",
    (
        "Seeland Regionalbank AG",
        "Confirmation of balances at 31 December 2025",
        "Term loan outstanding: CHF 38.0 million",
        "The loan may be prepaid on any interest date",
        "without penalty.",
    ),
)

# ------------------------------------------------------------- distractors
# Realistic near-duplicates: unaudited monthly figures, similar clauses in other
# contracts, an older facility with a different covenant. They make retrieval
# harder in the way real data rooms are hard.

MONTHS = (
    "January",
    "February",
    "March",
    "April",
    "May",
    "June",
    "July",
    "August",
    "September",
    "October",
    "November",
    "December",
)
SEASON = (0.078, 0.080, 0.088, 0.084, 0.086, 0.087, 0.070, 0.062, 0.090, 0.092, 0.095, 0.088)


def _monthly(filename: str, year: int, revenue: float, ebitda: float, intake: float, headcount: int) -> PdfDoc:
    pages: list[Page] = []
    ytd_rev = ytd_ebitda = 0.0
    weights = [w / sum(SEASON) for w in SEASON]
    for index, month in enumerate(MONTHS):
        rev = round(revenue * weights[index], 1) if index < 11 else round(revenue - ytd_rev, 1)
        ebi = round(ebitda * weights[index], 1) if index < 11 else round(ebitda - ytd_ebitda, 1)
        ytd_rev = round(ytd_rev + rev, 1)
        ytd_ebitda = round(ytd_ebitda + ebi, 1)
        orders = round(intake * weights[(index + 2) % 12], 1)
        pages.append(
            (
                H(f"Management accounts {month} {year} (unaudited)"),
                T(
                    f"Key figures {month} {year} (CHF million, unaudited)",
                    ("Measure", f"{month} {year}", f"Year to date {year}"),
                    (
                        ("Revenue", f"{rev:.1f}", f"{ytd_rev:.1f}"),
                        ("EBITDA", f"{ebi:.1f}", f"{ytd_ebitda:.1f}"),
                        ("Order intake", f"{orders:.1f}", "-"),
                        ("Headcount", str(headcount - 11 + index), "-"),
                    ),
                ),
                P(
                    f"Commentary {month} {year}: figures are management estimates before audit adjustments and "
                    f"may differ from the audited financial statements."
                ),
            )
        )
    return PdfDoc(filename, f"Monthly management accounts FY{year}", tuple(pages))


MONTHLY25 = _monthly("30_monthly_management_accounts_FY2025.pdf", 2025, 142.9, 25.4, 139.5, 612)
MONTHLY24 = _monthly("31_monthly_management_accounts_FY2024.pdf", 2024, 131.3, 23.0, 128.2, 597)

OSTARA = PdfDoc(
    "32_customer_contract_ostara_pumps.pdf",
    "Supply agreement - Ostara Pumps",
    (
        (
            H("Supply agreement - Ostara Pumps"),
            P(
                f"Ostara Pumps buys valve bodies and pump housings from {TARGET} under this agreement dated "
                "9 January 2020. Payment terms are 45 days from invoice."
            ),
            H("Clause 10. Termination"),
            P(
                "Either party may terminate the agreement for convenience with twelve months' written notice. "
                "A change in the shareholding of either party has no effect on this agreement."
            ),
        ),
        (
            H("Clause 13. Warranty"),
            P("The Supplier warrants that parts are free from defects for 24 months after delivery."),
        ),
    ),
)

LINDQVIST = PdfDoc(
    "33_customer_contract_lindqvist_hydraulics.pdf",
    "Supply agreement - Lindqvist Hydraulics",
    (
        (
            H("Supply agreement - Lindqvist Hydraulics"),
            P(
                f"Lindqvist Hydraulics purchases hydraulic manifold blocks from {TARGET}. The agreement was signed "
                "on 1 April 2022 and runs until 31 March 2026."
            ),
            H("Clause 15. Change of control"),
            P(
                "If the Supplier undergoes a change of control, Lindqvist may ask to renegotiate prices within "
                "six months. The agreement otherwise continues on its terms."
            ),
        ),
    ),
)

BRNO_LEASE = PdfDoc(
    "34_lease_agreement_brno_warehouse.pdf",
    "Lease agreement - Brno warehouse",
    (
        (
            H("Lease agreement - Brno warehouse"),
            P(
                f"{SUBSIDIARY} leases a 3,200 square metre warehouse next to the Brno plant. The annual rent is "
                "CZK 4.9 million and the lease ends on 31 December 2028."
            ),
            P("The lease can be terminated by the tenant with six months' notice from 2027."),
        ),
    ),
)

BOARD_Q3 = PdfDoc(
    "35_board_minutes_q3_2025.pdf",
    "Minutes of the board meeting of 23 September 2025",
    (
        (
            H("Minutes of the board meeting of 23 September 2025"),
            P(f"Present: {CHAIR} (chair), {CEO}, {CFO}."),
            P(
                "The board reviewed the information memorandum and approved its release to bidders. Management "
                "reported that the year-to-date figures were in line with the FY2025 budget."
            ),
            P("The board approved the purchase of two used turning centres for Brno for CHF 0.9 million."),
        ),
    ),
)

BOARD_Q4_24 = PdfDoc(
    "36_board_minutes_q4_2024.pdf",
    "Minutes of the board meeting of 10 December 2024",
    (
        (
            H("Minutes of the board meeting of 10 December 2024"),
            P("The board approved the FY2025 budget of CHF 140.0 million revenue and CHF 24.5 million EBITDA."),
            P("The board approved a dividend proposal of CHF 3.1 million for the 2025 general meeting."),
        ),
    ),
)

OLD_FACILITY = PdfDoc(
    "37_existing_facility_agreement_2019.pdf",
    "Existing term loan agreement 2019",
    (
        (
            H("Term loan agreement of 30 September 2019"),
            P(
                f"Seeland Regionalbank AG granted {TARGET} a term loan of CHF 50.0 million, amortising by "
                "CHF 3.0 million a year, for the refinancing of the Brno plant."
            ),
        ),
        (
            H("Clause 21. Financial covenant"),
            P(
                "The ratio of net debt to EBITDA must not exceed 3.00x on any annual test date. On "
                "31 December 2025 the ratio was 0.95x."
            ),
            P("The loan becomes repayable on a change of control of the borrower."),
        ),
    ),
)

DOCS: tuple[Doc, ...] = (
    IM,
    MGMT_PRES,
    FS23,
    FS24,
    FS25,
    BRENNTAL,
    NORDWIND,
    VALTRONA,
    LEASE,
    CVS,
    LEGAL_DD,
    COMMERCIAL_DD,
    TAX_DD,
    ENV,
    INSURANCE,
    HR,
    IT,
    QUALITY,
    BOARD_MINUTES,
    TERM_SHEET,
    SUPPLIERS,
    STRUCTURE,
    MODEL,
    CONCENTRATION,
    CAPEX,
    SCAN_BRENNTAL,
    SCAN_BOARD_NOTE,
    SCAN_LEASE_ADDENDUM,
    SCAN_BANK_LETTER,
    MONTHLY25,
    MONTHLY24,
    OSTARA,
    LINDQVIST,
    BRNO_LEASE,
    BOARD_Q3,
    BOARD_Q4_24,
    OLD_FACILITY,
)

# Personal data that must never reach an index, a prompt or a cloud service.
PII: tuple[str, ...] = (
    CEO,
    CFO,
    COO,
    CHAIR,
    "corinne.vasseli@alpine-precision.example",
    "tobias.arnhold@alpine-precision.example",
    "+41 33 555 01 10",
    "+41 33 555 01 12",
    "Seestrasse 7, 3700 Spiez",
    "CH93 0076 2011 6238 5295 7",
)

# --------------------------------------------------------------------------- traps

TRAPS: tuple[Trap, ...] = (
    Trap(
        "revenue_mismatch",
        "FY2025 revenue in the IM does not match the audited accounts",
        "The information memorandum states FY2025 revenue of CHF 148.6 million; the audited income statement "
        "and the financial model show CHF 142.3 million. The CHF 6.3 million gap is not reconciled anywhere.",
        (
            (IM.filename, "Revenue reached CHF 148.6 million in FY2025"),
            (FS25.filename, "Income statement for the year ended 31 December 2025"),
        ),
        ("148.6", "142.3"),
    ),
    Trap(
        "change_of_control",
        "Largest customer can terminate on change of control",
        "Clause 14.2 of the Brenntal agreement lets the buyer terminate on 90 days' notice if a third party "
        "acquires more than 50% of the Supplier without consent. Brenntal is 31.2% of FY2025 revenue and the "
        "legal due diligence has not reviewed this agreement.",
        (
            (BRENNTAL.filename, "more than 50% of the shares or voting"),
            (CONCENTRATION.filename, "Brenntal Automotive GmbH"),
        ),
        ("14.2", "change of control", "terminate"),
    ),
    Trap(
        "covenant_headroom",
        "Net leverage covenant close to breach in FY2026",
        "The model shows FY2026 net leverage of 4.38x against a 4.50x covenant, a headroom of 2.7%. "
        "A revenue shortfall of the size flagged in the chair's note would push the covenant close to breach.",
        (
            (MODEL.filename, "Net leverage"),
            (TERM_SHEET.filename, "must not exceed 4.50x"),
        ),
        ("4.38", "4.50", "headroom"),
    ),
)
