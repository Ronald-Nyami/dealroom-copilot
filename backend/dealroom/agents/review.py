"""Human review gate for the IC memo.

draft -> in_review -> approved
                   -> changes_requested -> in_review -> ...

Rules enforced here, not in the UI:
* only a named person can act; agents have no identity in this state machine;
* only a partner can approve;
* a memo with an uncited sentence cannot be approved;
* every high-severity challenger argument needs a written response before approval.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Literal

State = Literal["draft", "in_review", "approved", "changes_requested"]
Role = Literal["analyst", "associate", "partner"]
TRANSITIONS: dict[tuple[State, str], State] = {
    ("draft", "submit"): "in_review",
    ("changes_requested", "submit"): "in_review",
    ("in_review", "approve"): "approved",
    ("in_review", "request_changes"): "changes_requested",
}
ALLOWED_ROLES: dict[str, set[str]] = {
    "submit": {"associate", "partner"},
    "approve": {"partner"},
    "request_changes": {"associate", "partner"},
}


class ReviewError(ValueError):
    pass


@dataclass
class Event:
    action: str
    actor: str
    role: str
    state: State
    comment: str
    at: str


@dataclass
class Review:
    state: State = "draft"
    history: list[Event] = field(default_factory=list)
    responses: dict[str, str] = field(default_factory=dict)  # argument title -> reviewer response

    def act(
        self,
        action: str,
        actor: str,
        role: Role,
        *,
        comment: str = "",
        uncited: int = 0,
        high_arguments: list[str] | None = None,
    ) -> State:
        if not actor.strip():
            raise ReviewError("a named reviewer is required")
        if role not in ALLOWED_ROLES.get(action, set()):
            raise ReviewError(f"role {role} may not {action}")
        target = TRANSITIONS.get((self.state, action))
        if target is None:
            raise ReviewError(f"cannot {action} a memo in state {self.state}")
        if action == "approve":
            if uncited:
                raise ReviewError(f"{uncited} sentence(s) have no citation")
            missing = [title for title in (high_arguments or []) if not self.responses.get(title, "").strip()]
            if missing:
                raise ReviewError("respond to every high-severity challenger argument first: " + "; ".join(missing))
        if action == "request_changes" and not comment.strip():
            raise ReviewError("say what needs to change")
        self.state = target
        self.history.append(Event(action, actor, role, target, comment, datetime.now(UTC).isoformat()))
        return target

    def respond(self, argument_title: str, response: str, actor: str) -> None:
        if not actor.strip() or not response.strip():
            raise ReviewError("a named reviewer and a response are required")
        self.responses[argument_title] = f"{response} ({actor})"

    def to_dict(self) -> dict[str, object]:
        return {"state": self.state, "history": [e.__dict__ for e in self.history], "responses": self.responses}
