"""Guard: every tool call goes through policy, validation, approval and audit, in that order."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from pydantic import ValidationError

from dealroom_mcp.audit import AuditLog
from dealroom_mcp.policy import SIDE_EFFECTS, Approvals, PolicyError, check


@dataclass(frozen=True)
class Identity:
    """Comes from the authenticated session (OIDC token in production), never from the model."""

    user: str
    role: str


class Guard:
    def __init__(
        self,
        audit: AuditLog,
        handlers: dict[str, Callable[..., Any]],
        approvals: Approvals | None = None,
        mask: Callable[[str], str] | None = None,
    ) -> None:
        self.audit = audit
        self.handlers = handlers
        self.approvals = approvals or Approvals()
        self.mask = mask or (lambda text: text)

    def _masked(self, arguments: dict[str, Any]) -> dict[str, Any]:
        return {k: self.mask(v) if isinstance(v, str) else v for k, v in arguments.items()}

    def call(self, identity: Identity, tool: str, arguments: dict[str, Any]) -> dict[str, Any]:
        logged = self._masked(arguments)
        try:
            validated = check(identity.role, tool, arguments)
        except (PolicyError, ValidationError) as error:
            reason = str(error).splitlines()[0]
            self.audit.append(
                actor=identity.user, role=identity.role, tool=tool, arguments=logged, decision="denied", detail=reason
            )
            return {"status": "denied", "reason": reason}
        params = validated.model_dump()
        if tool in SIDE_EFFECTS:
            approval_id = params.pop("approval_id", None)
            if approval_id is None:
                approval = self.approvals.request(tool, identity.user, params)
                self.audit.append(
                    actor=identity.user,
                    role=identity.role,
                    tool=tool,
                    arguments=logged,
                    decision="approval_requested",
                    detail=approval.id,
                )
                return {"status": "approval_required", "approval_id": approval.id}
            try:
                approval = self.approvals.consume(approval_id, tool)
            except PolicyError as error:
                self.audit.append(
                    actor=identity.user,
                    role=identity.role,
                    tool=tool,
                    arguments=logged,
                    decision="denied",
                    detail=str(error),
                )
                return {"status": "denied", "reason": str(error)}
            detail = f"approved by {approval.approved_by}"
        else:
            detail = ""
        try:
            result = self.handlers[tool](**params)
        except Exception as error:  # the audit log records failures too
            self.audit.append(
                actor=identity.user,
                role=identity.role,
                tool=tool,
                arguments=logged,
                decision="error",
                detail=type(error).__name__,
            )
            return {"status": "error", "reason": type(error).__name__}
        self.audit.append(
            actor=identity.user, role=identity.role, tool=tool, arguments=logged, decision="allowed", detail=detail
        )
        return {"status": "ok", "result": result}

    def approve(self, approval_id: str, approver: Identity) -> dict[str, Any]:
        try:
            approval = self.approvals.approve(approval_id, approver.user, approver.role)
        except PolicyError as error:
            self.audit.append(
                actor=approver.user,
                role=approver.role,
                tool="approve",
                arguments={"id": approval_id},
                decision="denied",
                detail=str(error),
            )
            return {"status": "denied", "reason": str(error)}
        self.audit.append(
            actor=approver.user,
            role=approver.role,
            tool="approve",
            arguments={"id": approval_id},
            decision="allowed",
            detail=approval.tool,
        )
        return {"status": "approved", "approval_id": approval.id, "tool": approval.tool}
