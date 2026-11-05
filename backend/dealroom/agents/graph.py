"""LangGraph orchestration.

QA graph:    retrieve -> gate -(abstain)-> END
                           \\-> generate -> verify -> END
Deal graph:  draft_memo -> challenge -> human_review (interrupt) -> apply_review
                  ^                                                    |
                  +------------------- changes requested --------------+
             approved -> END

The deal graph pauses at ``human_review`` with LangGraph's ``interrupt`` and
resumes only with a decision from a named person. Nothing reaches "approved"
without passing through ``Review.act``.
"""

from __future__ import annotations

from typing import Any, TypedDict

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt

from dealroom.agents.challenger import Challenger
from dealroom.agents.memo import Memo, MemoDrafter
from dealroom.agents.qa import QA_SYSTEM, Answer, QAAgent, verify
from dealroom.agents.review import Review, ReviewError
from dealroom.models.llm import Evidence

# ----------------------------------------------------------------------------- QA


class QAState(TypedDict, total=False):
    question: str
    multi: bool
    evidence: list[Evidence]
    coverage: float
    raw: str
    answer: Answer


def build_qa_graph(agent: QAAgent) -> Any:
    def retrieve(state: QAState) -> QAState:
        spans = agent.evidence(state["question"])
        evidence = [Evidence(i + 1, s.chunk.id, s.chunk.citation, s.text) for i, s in enumerate(spans)]
        coverage = agent.selector.coverage(state["question"], spans[0].key) if spans else 0.0
        return {"evidence": evidence, "coverage": coverage}

    def gate(state: QAState) -> str:
        return "generate" if state["coverage"] >= agent.min_coverage else "abstain"

    def abstain(state: QAState) -> QAState:
        return {"answer": Answer(state["question"], "Not found in the data room.", True, [], state["coverage"])}

    def generate(state: QAState) -> QAState:
        system = QA_SYSTEM + (" MULTI: combine the evidence needed." if state.get("multi") else "")
        return {"raw": agent.llm.complete(system, f"Question: {state['question']}", state["evidence"])}

    def check(state: QAState) -> QAState:
        return {"answer": verify(state["question"], state["raw"], state["evidence"], state["coverage"])}

    graph = StateGraph(QAState)
    graph.add_node("retrieve", retrieve)
    graph.add_node("abstain", abstain)
    graph.add_node("generate", generate)
    graph.add_node("verify", check)
    graph.add_edge(START, "retrieve")
    graph.add_conditional_edges("retrieve", gate, {"generate": "generate", "abstain": "abstain"})
    graph.add_edge("generate", "verify")
    graph.add_edge("verify", END)
    graph.add_edge("abstain", END)
    return graph.compile()


# --------------------------------------------------------------------------- deal


class DealState(TypedDict, total=False):
    memo: dict[str, Any]
    uncited: int
    arguments: list[dict[str, Any]]
    review: dict[str, Any]
    error: str
    comments: list[str]


def _review_from(state: DealState) -> Review:
    data = state.get("review") or {}
    review = Review(state=data.get("state", "draft"), responses=dict(data.get("responses", {})))
    from dealroom.agents.review import Event

    review.history = [Event(**e) for e in data.get("history", [])]
    return review


def build_deal_graph(drafter: MemoDrafter, challenger: Challenger, checkpointer: Any | None = None) -> Any:
    def draft_memo(state: DealState) -> DealState:
        memo: Memo = drafter.draft()
        review = _review_from(state)
        if review.state in {"draft", "changes_requested"}:
            review.act(
                "submit", "dealroom-copilot workflow", "associate", comment="draft generated; awaiting human review"
            )
        return {"memo": memo.to_dict(), "uncited": memo.uncited_sentences(), "review": review.to_dict(), "error": ""}

    def challenge(state: DealState) -> DealState:
        return {"arguments": [a.to_dict() for a in challenger.run()]}

    def human_review(state: DealState) -> DealState:
        decision: dict[str, Any] = interrupt(
            {
                "memo": state["memo"],
                "arguments": state["arguments"],
                "review": state["review"],
                "error": state.get("error", ""),
            }
        )
        review = _review_from(state)
        try:
            for title, response in (decision.get("responses") or {}).items():
                review.respond(title, response, decision.get("actor", ""))
            high = [a["title"] for a in state["arguments"] if a["severity"] == "high"]
            review.act(
                decision["action"],
                decision.get("actor", ""),
                decision.get("role", "analyst"),
                comment=decision.get("comment", ""),
                uncited=state.get("uncited", 0),
                high_arguments=high,
            )
        except (ReviewError, KeyError) as error:
            return {"review": review.to_dict(), "error": str(error)}
        comments = [*state.get("comments", []), decision.get("comment", "")]
        return {"review": review.to_dict(), "error": "", "comments": comments}

    def route(state: DealState) -> str:
        if state.get("error"):
            return "human_review"
        return {"approved": "end", "changes_requested": "draft_memo"}.get(state["review"]["state"], "human_review")

    graph = StateGraph(DealState)
    graph.add_node("draft_memo", draft_memo)
    graph.add_node("challenge", challenge)
    graph.add_node("human_review", human_review)
    graph.add_edge(START, "draft_memo")
    graph.add_edge("draft_memo", "challenge")
    graph.add_edge("challenge", "human_review")
    graph.add_conditional_edges(
        "human_review", route, {"end": END, "draft_memo": "draft_memo", "human_review": "human_review"}
    )
    return graph.compile(checkpointer=checkpointer or InMemorySaver())


def resume(graph: Any, thread_id: str, decision: dict[str, Any]) -> dict[str, Any]:
    config = {"configurable": {"thread_id": thread_id}}
    graph.invoke(Command(resume=decision), config)
    return dict(graph.get_state(config).values)


def start(graph: Any, thread_id: str) -> dict[str, Any]:
    config = {"configurable": {"thread_id": thread_id}}
    graph.invoke({"comments": []}, config)
    return dict(graph.get_state(config).values)
