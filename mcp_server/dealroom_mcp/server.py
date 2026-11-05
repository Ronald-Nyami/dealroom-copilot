"""MCP server exposing the data room to agents.

Identity is taken from the environment the server is started in
(``DEALROOM_USER``, ``DEALROOM_ROLE``), which in a deployment is set from the
authenticated session, never from the model. Every call goes through ``Guard``:
deny by default, validated arguments, human approval for ``export_memo``, and a
hash-chained audit log.

Run: ``dealroom-mcp`` (stdio) or ``dealroom-mcp --http`` (streamable HTTP).
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

from mcp.server import MCPServer

from dealroom.service import Workspace, identity_from_env


def build(workspace: Workspace) -> MCPServer:
    server = MCPServer(
        name="dealroom",
        instructions=(
            "Tools over a synthetic private-equity data room. Every answer must cite a chunk id. "
            "export_memo needs a partner's approval: call it once to get an approval id, wait for the human "
            "approval, then call it again with that id."
        ),
    )
    identity = identity_from_env()

    def call(tool: str, **arguments: Any) -> dict[str, Any]:
        return workspace.guard.call(identity, tool, {k: v for k, v in arguments.items() if v is not None})

    @server.tool(description="Hybrid search over the data room. Returns chunk ids, citations and text.")
    def search_dataroom(query: str, k: int = 5) -> dict[str, Any]:
        return call("search_dataroom", query=query, k=k)

    @server.tool(description="Full text of one chunk, by chunk id.")
    def get_document_excerpt(chunk_id: str) -> dict[str, Any]:
        return call("get_document_excerpt", chunk_id=chunk_id)

    @server.tool(description="A financial figure for a year, answered from the data room with citations.")
    def get_financial_metric(metric: str, year: int) -> dict[str, Any]:
        return call("get_financial_metric", metric=metric, year=year)

    @server.tool(description="Record a diligence item backed by one or more chunk ids.")
    def create_diligence_item(
        title: str, description: str, severity: str, evidence_chunk_ids: list[str]
    ) -> dict[str, Any]:
        return call(
            "create_diligence_item",
            title=title,
            description=description,
            severity=severity,
            evidence_chunk_ids=evidence_chunk_ids,
        )

    @server.tool(description="Draft the IC memo and run the challenger. The memo then waits for human review.")
    def draft_memo() -> dict[str, Any]:
        return call("draft_memo")

    @server.tool(description="Export the approved IC memo. Side effect: needs a partner's approval id.")
    def export_memo(format: str = "markdown", approval_id: str | None = None) -> dict[str, Any]:
        return call("export_memo", format=format, approval_id=approval_id)

    return server


def main() -> None:  # pragma: no cover - process entry point
    workspace = Workspace.load(Path(os.environ.get("DEALROOM_ROOT", Path.cwd())))
    server = build(workspace)
    server.run("streamable-http" if "--http" in sys.argv else "stdio")
