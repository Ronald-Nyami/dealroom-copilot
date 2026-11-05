"""Tool policy: who may call what, with which arguments, and what needs a human.

Deny by default. A tool that is not listed for a role is refused. Arguments are
validated with strict Pydantic models (unknown fields rejected, sizes bounded)
before any tool code runs. Tools with side effects return an approval request
first and run only after a named person with the right role approves it.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

Role = Literal["analyst", "associate", "partner"]


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class SearchArgs(_Strict):
    query: str = Field(min_length=3, max_length=300)
    k: int = Field(default=5, ge=1, le=20)


class ExcerptArgs(_Strict):
    chunk_id: str = Field(pattern=r"^[0-9a-f]{12}$")


class MetricArgs(_Strict):
    metric: Literal["revenue", "EBITDA", "net income", "net debt", "cash", "capex", "net leverage"]
    year: int = Field(ge=2015, le=2035)


class DiligenceItemArgs(_Strict):
    title: str = Field(min_length=5, max_length=160)
    description: str = Field(min_length=10, max_length=2000)
    severity: Literal["high", "medium", "low"]
    evidence_chunk_ids: list[str] = Field(min_length=1, max_length=10)


class ExportArgs(_Strict):
    format: Literal["markdown"] = "markdown"
    approval_id: str | None = Field(default=None, pattern=r"^[0-9a-f-]{36}$")


TOOLS: dict[str, type[_Strict]] = {
    "search_dataroom": SearchArgs,
    "get_document_excerpt": ExcerptArgs,
    "get_financial_metric": MetricArgs,
    "create_diligence_item": DiligenceItemArgs,
    "draft_memo": _Strict,
    "export_memo": ExportArgs,
}
READ = {"search_dataroom", "get_document_excerpt", "get_financial_metric"}
ALLOWED: dict[str, set[str]] = {
    "analyst": READ | {"create_diligence_item"},
    "associate": READ | {"create_diligence_item", "draft_memo"},
    "partner": READ | {"create_diligence_item", "draft_memo", "export_memo"},
}
SIDE_EFFECTS = {"export_memo"}
APPROVER_ROLE: dict[str, Role] = {"export_memo": "partner"}


class PolicyError(PermissionError):
    pass


def check(role: str, tool: str, arguments: dict[str, Any]) -> _Strict:
    if tool not in TOOLS:
        raise PolicyError(f"unknown tool {tool}")
    if tool not in ALLOWED.get(role, set()):
        raise PolicyError(f"role {role!r} may not call {tool}")
    return TOOLS[tool].model_validate(arguments)


@dataclass
class Approval:
    id: str
    tool: str
    requested_by: str
    arguments: dict[str, Any]
    created: str
    approved_by: str | None = None
    used: bool = False


@dataclass
class Approvals:
    """Pending approvals. One approval authorises one call, by its id."""

    items: dict[str, Approval] = field(default_factory=dict)

    def request(self, tool: str, actor: str, arguments: dict[str, Any]) -> Approval:
        approval = Approval(str(uuid.uuid4()), tool, actor, arguments, datetime.now(UTC).isoformat())
        self.items[approval.id] = approval
        return approval

    def approve(self, approval_id: str, approver: str, role: str) -> Approval:
        approval = self.items.get(approval_id)
        if approval is None:
            raise PolicyError("unknown approval")
        if role != APPROVER_ROLE.get(approval.tool):
            raise PolicyError(f"only a {APPROVER_ROLE.get(approval.tool)} can approve {approval.tool}")
        if not approver.strip():
            raise PolicyError("a named approver is required")
        approval.approved_by = approver
        return approval

    def consume(self, approval_id: str, tool: str) -> Approval:
        approval = self.items.get(approval_id)
        if approval is None or approval.tool != tool:
            raise PolicyError("unknown approval")
        if approval.approved_by is None:
            raise PolicyError("approval is still pending")
        if approval.used:
            raise PolicyError("approval already used")
        approval.used = True
        return approval

    def pending(self) -> list[Approval]:
        return [a for a in self.items.values() if a.approved_by is None]
