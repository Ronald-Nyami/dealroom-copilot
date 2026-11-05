from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from dealroom.agents.challenger import Challenger, parse_table, source_kind
from dealroom.agents.graph import build_deal_graph, build_qa_graph, resume, start
from dealroom.agents.memo import Memo, MemoDrafter, Section, Sentence
from dealroom.agents.qa import QAAgent, _row_span, verify
from dealroom.agents.review import Review, ReviewError
from dealroom.ingestion.models import Chunk
from dealroom.models import llm as llm_module
from dealroom.models.llm import AzureOpenAIChat, Evidence, OpenAIChat, StubLLM, llm_from_env, render_evidence
from dealroom.retrieval.retriever import Retriever

# ------------------------------------------------------------------ QA


def test_answers_with_citation(qa: QAAgent) -> None:
    answer = qa.answer("What is the annual base rent for the Thun site?")
    assert not answer.abstained and "2.85" in answer.text
    assert answer.citations[0].citation == "09_lease_agreement_thun.pdf, p. 1"


def test_picks_the_column_named_in_the_question(qa: QAAgent) -> None:
    answer = qa.answer("What revenue does the model forecast for FY2027?")
    assert "160.2" in answer.text and "118.4" not in answer.text


def test_abstains_when_the_data_room_is_silent(qa: QAAgent) -> None:
    answer = qa.answer("What is the company's carbon footprint in tonnes of CO2?")
    assert answer.abstained and answer.citations == []


def test_verify_drops_invented_citations_and_uncited_answers() -> None:
    evidence = [Evidence(1, "abc", "a.pdf, p. 1", "Rent is CHF 2.85 million.")]
    assert verify("q", "Rent is CHF 2.85 million [1] [7]", evidence, 1.0).text == "Rent is CHF 2.85 million [1]"
    assert verify("q", "Rent is high.", evidence, 1.0).abstained
    assert verify("q", "INSUFFICIENT_EVIDENCE", evidence, 1.0).abstained


def test_row_span_rendering() -> None:
    columns = "CHF million | FY2025A | FY2026E"
    assert _row_span("Revenue | 142.3 | 151", columns, None, "revenue FY2026")[0] == "Revenue, FY2026E: 151"
    assert (
        _row_span("Revenue | 142.3 | 151", columns, "Cap", "revenue")[0]
        == "Cap: Revenue (FY2025A: 142.3, FY2026E: 151)"
    )
    assert _row_span("Revenue", None, None, "x") == ("Revenue", "Revenue")


def test_chat_providers_send_evidence_and_parse_answers(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"choices": [{"message": {"content": " Rent is CHF 2.85 million [1] "}}]})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    evidence = [Evidence(1, "abc", "a.pdf, p. 1", "Rent is CHF 2.85 million.")]
    azure = AzureOpenAIChat("https://aoai.example/", "gpt", lambda: "tok", client=client)
    openai = OpenAIChat("sk-test", client=client)
    assert (
        azure.complete("sys", "q", evidence) == openai.complete("sys", "q", evidence) == "Rent is CHF 2.85 million [1]"
    )
    assert "/openai/deployments/gpt/chat/completions" in str(seen[0].url)
    assert json.loads(seen[1].content)["model"] == "gpt-4o-mini"
    assert "[1] (a.pdf, p. 1)" in render_evidence(evidence)
    assert StubLLM().complete("s", "q", []) == "INSUFFICIENT_EVIDENCE"
    monkeypatch.setenv("DEALROOM_LLM", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    assert llm_from_env().name == "openai"
    monkeypatch.setenv("DEALROOM_LLM", "stub")
    assert llm_from_env().name == "stub"


def test_llm_from_env_azure(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeCredential:
        @classmethod
        def from_files(cls, *args: object) -> FakeCredential:
            return cls()

        def __call__(self) -> str:
            return "t"

    import dealroom.ingestion.azure_auth as auth

    monkeypatch.setattr(auth, "CertificateCredential", FakeCredential)
    for name, value in {
        "DEALROOM_LLM": "azure",
        "AZURE_TENANT_ID": "t",
        "AZURE_CLIENT_ID": "c",
        "AZURE_CLIENT_KEY_PATH": "k",
        "AZURE_CLIENT_CERT_PATH": "c",
        "AZURE_OPENAI_ENDPOINT": "https://aoai.example",
        "AZURE_OPENAI_DEPLOYMENT": "gpt",
    }.items():
        monkeypatch.setenv(name, value)
    assert llm_module.llm_from_env().name == "azure-openai"


# ------------------------------------------------------------------ challenger


def test_challenger_finds_the_three_planted_issues(retriever: Retriever, root: Path) -> None:
    arguments = Challenger(retriever).run()
    by_id = {c.id: c for c in retriever.chunks}
    traps = json.loads((root / "data" / "eval" / "traps.json").read_text())
    for trap in traps:
        assert any(
            all(any(by_id[c.chunk_id].covers(e) for c in a.citations) for e in trap["evidence"]) for a in arguments
        ), trap["id"]
    for argument in arguments:
        cited = {int(n) for n in __import__("re").findall(r"\[(\d+)\]", argument.text)}
        assert cited <= {c.n for c in argument.citations}
    assert arguments[0].severity == "high"


def test_challenger_thresholds_can_silence_checks(retriever: Retriever) -> None:
    quiet = Challenger(retriever, headroom_threshold=0.0, mismatch_threshold=1.0, concentration_threshold=0.9)
    checks = {a.check for a in quiet.run()}
    assert "covenant_headroom" not in checks and "figure_consistency" not in checks and "concentration" not in checks


def test_challenger_helpers() -> None:
    table = parse_table(
        Chunk("m.xlsx", "[ctx]\nH | FY2026E\nNet debt | 115.2", "rows", sheet="LBO", row_start=1, row_end=2)
    )
    assert table is not None and table.rows["Net debt"] == ["115.2"]
    assert parse_table(Chunk("a.pdf", "[ctx]\ntext", "paragraph", page=1)) is None
    assert source_kind("05_audited_financial_statements_FY2025.pdf") == "audited"
    assert source_kind("02_management_presentation.pdf") == "marketing"
    assert source_kind("23_financial_model.xlsx") == "model"
    assert source_kind("09_lease.pdf") == "other"


# ------------------------------------------------------------------ memo and review


class ProseLLM:
    name = "prose"

    def complete(self, system: str, prompt: str, evidence: list[Evidence]) -> str:
        return "The company is a precision machining group [1]. This sentence has no citation. Bad ref [99]."


def test_memo_drafter_keeps_only_cited_sentences(qa: QAAgent) -> None:
    section = MemoDrafter(qa, ProseLLM()).draft_section(
        "Thesis", ("In which year was the company founded?", "What is the CEO's annual salary?")
    )
    assert [s.text for s in section.sentences] == ["The company is a precision machining group."]
    assert section.unanswered == ["What is the CEO's annual salary?"]


def test_memo_markdown_and_counts() -> None:
    evidence = Evidence(1, "abc", "a.pdf, p. 1", "x")
    memo = Memo("IC memo", [Section("A", [Sentence("Fact.", [evidence]), Sentence("Loose.", [])], ["Open?"])])
    assert memo.uncited_sentences() == 1
    markdown = memo.to_markdown()
    assert "- Fact. _(a.pdf, p. 1)_" in markdown and "- Open: Open?" in markdown
    assert memo.to_dict()["sections"][0]["unanswered"] == ["Open?"]


def test_review_state_machine_rules() -> None:
    review = Review()
    with pytest.raises(ReviewError):
        review.act("approve", "Pat", "partner")  # not in review yet
    with pytest.raises(ReviewError):
        review.act("submit", " ", "associate")
    with pytest.raises(ReviewError):
        review.act("submit", "Ana", "analyst")
    review.act("submit", "Sam", "associate")
    with pytest.raises(ReviewError):
        review.act("request_changes", "Pat", "partner")  # comment required
    with pytest.raises(ReviewError):
        review.act("approve", "Pat", "partner", uncited=2)
    with pytest.raises(ReviewError):
        review.act("approve", "Pat", "partner", high_arguments=["Covenant"])
    with pytest.raises(ReviewError):
        review.respond("Covenant", "", "Pat")
    review.respond("Covenant", "Equity cure negotiated", "Pat")
    assert review.act("approve", "Pat", "partner", high_arguments=["Covenant"]) == "approved"
    assert [e.action for e in review.history] == ["submit", "approve"]
    assert review.to_dict()["responses"]["Covenant"].endswith("(Pat)")


# ------------------------------------------------------------------ graphs


def test_qa_graph_answers_and_abstains(qa: QAAgent) -> None:
    graph = build_qa_graph(qa)
    assert not graph.invoke({"question": "When does the Thun lease end?"})["answer"].abstained
    assert graph.invoke({"question": "What is the carbon footprint in tonnes of CO2?"})["answer"].abstained
    assert not graph.invoke({"question": "Is the pension liability consistent?", "multi": True})["answer"].abstained


def test_deal_graph_loops_on_requested_changes(qa: QAAgent, retriever: Retriever) -> None:
    graph = build_deal_graph(MemoDrafter(qa), Challenger(retriever))
    state = start(graph, "thread-1")
    assert state["review"]["state"] == "in_review" and state["uncited"] == 0
    state = resume(graph, "thread-1", {"action": "request_changes", "actor": "Pat", "role": "partner"})
    assert "say what needs to change" in state["error"]
    state = resume(
        graph,
        "thread-1",
        {"action": "request_changes", "actor": "Pat", "role": "partner", "comment": "Use audited revenue throughout"},
    )
    assert state["review"]["state"] == "in_review"  # redrafted and resubmitted
    assert [e["action"] for e in state["review"]["history"]] == ["submit", "request_changes", "submit"]
    state = resume(graph, "thread-1", {"role": "partner"})
    assert "action" in state["error"]
