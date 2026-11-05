"""FastAPI backend for the analyst workspace.

Identity: ``X-User`` and ``X-Role`` headers. In the AKS deployment these are set
by the authenticating ingress (OAuth2 proxy in front of Entra ID) and stripped
from client requests; locally they come from the role switcher in the UI.
Every state-changing route goes through the same ``Guard`` as the MCP tools.
"""

from __future__ import annotations

import asyncio
import json
import os
from collections.abc import AsyncIterator
from functools import lru_cache
from pathlib import Path
from typing import Annotated, Any, Literal

from fastapi import Depends, FastAPI, Header, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from dealroom.service import Workspace
from dealroom_mcp.guard import Identity

Role = Literal["analyst", "associate", "partner"]


@lru_cache(maxsize=1)
def workspace() -> Workspace:
    return Workspace.load(Path(os.environ.get("DEALROOM_ROOT", Path.cwd())))


def identity(
    x_user: Annotated[str, Header()] = "local-analyst", x_role: Annotated[Role, Header()] = "analyst"
) -> Identity:
    return Identity(x_user, x_role)


class AskBody(BaseModel):
    question: str = Field(min_length=3, max_length=500)
    multi: bool = False


class ReviewBody(BaseModel):
    action: Literal["approve", "request_changes"]
    comment: str = ""
    responses: dict[str, str] = Field(default_factory=dict)


class ItemBody(BaseModel):
    title: str
    description: str
    severity: Literal["high", "medium", "low"]
    evidence_chunk_ids: list[str]


class ExportBody(BaseModel):
    approval_id: str | None = None


app = FastAPI(title="dealroom-copilot", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.environ.get("DEALROOM_CORS", "http://localhost:3000").split(","),
    allow_methods=["*"],
    allow_headers=["*"],
)

WS = Annotated[Workspace, Depends(workspace)]
ID = Annotated[Identity, Depends(identity)]


def _guarded(ws: Workspace, who: Identity, tool: str, arguments: dict[str, Any]) -> Any:
    outcome = ws.guard.call(who, tool, arguments)
    if outcome["status"] == "denied":
        raise HTTPException(403, outcome["reason"])
    if outcome["status"] == "error":
        raise HTTPException(409, outcome["reason"])
    return outcome.get("result", outcome)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/documents")
def documents(ws: WS) -> list[dict[str, Any]]:
    return ws.documents()


@app.get("/api/documents/{file}/chunks")
def document_chunks(file: str, ws: WS) -> list[dict[str, Any]]:
    try:
        return ws.document_chunks(file)
    except KeyError as error:
        raise HTTPException(404, "unknown document") from error


@app.get("/api/chunks/{chunk_id}")
def chunk(chunk_id: str, ws: WS, who: ID) -> Any:
    return _guarded(ws, who, "get_document_excerpt", {"chunk_id": chunk_id})


@app.post("/api/ask")
def ask(body: AskBody, ws: WS, who: ID) -> dict[str, Any]:
    _guarded(ws, who, "search_dataroom", {"query": body.question, "k": 6})
    return ws.ask(body.question, body.multi)


@app.get("/api/ask/stream")
async def ask_stream(ws: WS, who: ID, q: Annotated[str, Query(min_length=3, max_length=500)]) -> StreamingResponse:
    """Server-sent events: one ``citations`` event, then ``token`` events, then ``done``."""
    _guarded(ws, who, "search_dataroom", {"query": q, "k": 6})
    answer = await asyncio.to_thread(ws.ask, q)

    async def events() -> AsyncIterator[str]:
        yield f"event: citations\ndata: {json.dumps(answer['citations'])}\n\n"
        for word in str(answer["answer"]).split(" "):
            yield f"event: token\ndata: {json.dumps(word + ' ')}\n\n"
            await asyncio.sleep(0)
        yield f"event: done\ndata: {json.dumps({'abstained': answer['abstained']})}\n\n"

    return StreamingResponse(events(), media_type="text/event-stream")


@app.post("/api/memos")
def draft_memo(ws: WS, who: ID) -> Any:
    return _guarded(ws, who, "draft_memo", {})


@app.get("/api/memos")
def memos(ws: WS) -> list[dict[str, Any]]:
    out = []
    for memo_id in ws.memo_threads:
        state = ws.memo_state(memo_id)
        out.append({"memo_id": memo_id, "state": state.get("review", {}).get("state")})
    return out


@app.get("/api/memos/{memo_id}")
def memo(memo_id: str, ws: WS) -> dict[str, Any]:
    if memo_id not in ws.memo_threads:
        raise HTTPException(404, "unknown memo")
    return ws.memo_state(memo_id)


@app.post("/api/memos/{memo_id}/review")
def review(memo_id: str, body: ReviewBody, ws: WS, who: ID) -> dict[str, Any]:
    if memo_id not in ws.memo_threads:
        raise HTTPException(404, "unknown memo")
    decision = {
        "action": body.action,
        "actor": who.user,
        "role": who.role,
        "comment": body.comment,
        "responses": body.responses,
    }
    state = ws.review(memo_id, decision)
    ws.guard.audit.append(
        actor=who.user,
        role=who.role,
        tool="review_memo",
        arguments={"memo_id": memo_id, "action": body.action},
        decision="denied" if state.get("error") else "allowed",
        detail=state.get("error", ""),
    )
    if state.get("error"):
        raise HTTPException(409, state["error"])
    return state


@app.get("/api/items")
def items(ws: WS) -> list[dict[str, Any]]:
    return ws.items


@app.post("/api/items")
def create_item(body: ItemBody, ws: WS, who: ID) -> Any:
    return _guarded(ws, who, "create_diligence_item", body.model_dump())


@app.post("/api/export")
def export(body: ExportBody, ws: WS, who: ID) -> Any:
    arguments: dict[str, Any] = {"format": "markdown"}
    if body.approval_id:
        arguments["approval_id"] = body.approval_id
    return _guarded(ws, who, "export_memo", arguments)


@app.post("/api/approvals/{approval_id}")
def approve(approval_id: str, ws: WS, who: ID) -> dict[str, Any]:
    outcome = ws.guard.approve(approval_id, who)
    if outcome["status"] != "approved":
        raise HTTPException(403, outcome["reason"])
    return outcome


@app.get("/api/approvals")
def approvals(ws: WS) -> list[dict[str, Any]]:
    return [a.__dict__ for a in ws.guard.approvals.pending()]


@app.get("/api/audit")
def audit(ws: WS) -> dict[str, Any]:
    check = ws.guard.audit.verify()
    return {"verified": check.ok, "broken_at": check.broken_at, "records": ws.guard.audit.records()[-200:]}
