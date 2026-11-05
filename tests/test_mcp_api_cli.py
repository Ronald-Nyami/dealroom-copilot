from __future__ import annotations

import asyncio
import json
import shutil
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from dealroom import cli
from dealroom.api import app as api
from dealroom.service import Workspace, identity_from_env
from dealroom_mcp.audit import AuditLog
from dealroom_mcp.guard import Guard, Identity
from dealroom_mcp.policy import Approvals, PolicyError, check
from dealroom_mcp.server import build

ANALYST = Identity("ana", "analyst")
PARTNER = Identity("pat", "partner")


@pytest.fixture(scope="module")
def workspace(root: Path, tmp_path_factory: pytest.TempPathFactory) -> Workspace:
    base = tmp_path_factory.mktemp("ws")
    shutil.copytree(root / "data", base / "data")
    shutil.copytree(root / ".cache", base / ".cache")
    return Workspace.load(base)


# ------------------------------------------------------------------ audit and policy


def test_audit_chain_detects_tampering(tmp_path: Path) -> None:
    log = AuditLog(tmp_path / "audit.jsonl")
    for i in range(3):
        log.append(actor="a", role="analyst", tool="t", arguments={"i": i}, decision="allowed")
    assert log.verify().ok and log.verify().records == 3
    lines = (tmp_path / "audit.jsonl").read_text().splitlines()
    edited = json.loads(lines[1])
    edited["decision"] = "denied"
    (tmp_path / "audit.jsonl").write_text("\n".join([lines[0], json.dumps(edited), lines[2]]) + "\n")
    assert log.verify().broken_at == 2 and "changed" in log.verify().reason
    (tmp_path / "audit.jsonl").write_text("\n".join([lines[0], lines[2]]) + "\n")
    assert log.verify().reason == "previous hash does not match"
    assert AuditLog(tmp_path / "empty.jsonl").records() == []


def test_policy_denies_by_default_and_validates() -> None:
    with pytest.raises(PolicyError):
        check("analyst", "rm_rf", {})
    with pytest.raises(PolicyError):
        check("intern", "search_dataroom", {"query": "rent"})
    assert check("partner", "export_memo", {}).model_dump() == {"format": "markdown", "approval_id": None}
    approvals = Approvals()
    pending = approvals.request("export_memo", "pat", {})
    with pytest.raises(PolicyError):
        approvals.consume(pending.id, "export_memo")
    with pytest.raises(PolicyError):
        approvals.approve("nope", "pat", "partner")
    with pytest.raises(PolicyError):
        approvals.approve(pending.id, " ", "partner")
    with pytest.raises(PolicyError):
        approvals.consume("nope", "export_memo")
    assert approvals.pending() == [pending]


def test_guard_records_handler_errors(tmp_path: Path) -> None:
    def boom(**_: object) -> None:
        raise LookupError("no memo")

    guard = Guard(AuditLog(tmp_path / "a.jsonl"), {"search_dataroom": boom})
    assert guard.call(ANALYST, "search_dataroom", {"query": "rent"}) == {"status": "error", "reason": "LookupError"}
    assert guard.audit.records()[-1]["decision"] == "error"


# ------------------------------------------------------------------ workspace and MCP


def test_full_tool_flow_with_approval(workspace: Workspace) -> None:
    guard = workspace.guard
    search = guard.call(ANALYST, "search_dataroom", {"query": "Corinne Vasseli career", "k": 3})
    assert search["status"] == "ok" and search["result"][0]["citation"].startswith("10_management_cvs.pdf")
    chunk_id = search["result"][0]["chunk_id"]
    assert guard.call(ANALYST, "get_document_excerpt", {"chunk_id": chunk_id})["result"]["chunk_id"] == chunk_id
    metric = guard.call(ANALYST, "get_financial_metric", {"metric": "revenue", "year": 2024})
    assert "131" in metric["result"]["answer"]
    item = guard.call(
        ANALYST,
        "create_diligence_item",
        {"title": "Revenue gap", "description": "IM vs audited", "severity": "high", "evidence_chunk_ids": [chunk_id]},
    )
    assert item["result"]["evidence"][0]["chunk_id"] == chunk_id
    bad = guard.call(
        ANALYST,
        "create_diligence_item",
        {
            "title": "Revenue gap",
            "description": "IM vs audited",
            "severity": "high",
            "evidence_chunk_ids": ["000000000000"],
        },
    )
    assert bad["status"] == "error"
    assert guard.call(ANALYST, "draft_memo", {})["status"] == "denied"
    early = guard.call(PARTNER, "export_memo", {})
    approved_early = guard.approve(early["approval_id"], PARTNER)
    assert approved_early["status"] == "approved"
    assert guard.call(PARTNER, "export_memo", {"approval_id": early["approval_id"]})["status"] == "error"
    memo = guard.call(PARTNER, "draft_memo", {})["result"]
    responses = {a["title"]: "Addressed" for a in memo["arguments"] if a["severity"] == "high"}
    workspace.review(memo["memo_id"], {"action": "approve", "actor": "pat", "role": "partner", "responses": responses})
    request = guard.call(PARTNER, "export_memo", {})
    assert guard.approve(request["approval_id"], ANALYST)["status"] == "denied"
    guard.approve(request["approval_id"], PARTNER)
    exported = guard.call(PARTNER, "export_memo", {"approval_id": request["approval_id"]})
    assert (workspace.root / exported["result"]["path"]).read_text().startswith("# Investment committee memo")
    assert guard.call(PARTNER, "export_memo", {"approval_id": request["approval_id"]})["status"] == "denied"
    assert guard.audit.verify().ok
    assert "Vasseli" not in (workspace.root / ".cache" / "audit.jsonl").read_text()


def test_mcp_server_exposes_guarded_tools(workspace: Workspace, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DEALROOM_ROLE", "analyst")
    server = build(workspace)
    names = sorted(t.name for t in asyncio.run(server.list_tools()))
    assert names == [
        "create_diligence_item",
        "draft_memo",
        "export_memo",
        "get_document_excerpt",
        "get_financial_metric",
        "search_dataroom",
    ]
    result = asyncio.run(server.call_tool("export_memo", {}))
    assert "denied" in json.dumps(result, default=str)
    result = asyncio.run(server.call_tool("search_dataroom", {"query": "annual base rent", "k": 1}))
    assert "lease_agreement_thun" in json.dumps(result, default=str)
    for tool, args in [
        ("get_document_excerpt", {"chunk_id": "x"}),
        ("get_financial_metric", {"metric": "cash", "year": 2025}),
        ("create_diligence_item", {"title": "t", "description": "d", "severity": "low", "evidence_chunk_ids": []}),
        ("draft_memo", {}),
    ]:
        asyncio.run(server.call_tool(tool, args))
    assert identity_from_env().role == "analyst"


# ------------------------------------------------------------------ HTTP API


def test_api_end_to_end(workspace: Workspace) -> None:
    api.app.dependency_overrides[api.workspace] = lambda: workspace
    client = TestClient(api.app)
    partner = {"X-User": "pat", "X-Role": "partner"}
    try:
        assert client.get("/health").json() == {"status": "ok"}
        docs = client.get("/api/documents").json()
        assert len(docs) == 37 and docs[0]["chunks"] > 0
        chunks = client.get("/api/documents/09_lease_agreement_thun.pdf/chunks").json()
        assert chunks and client.get("/api/documents/..%2Fsecret/chunks").status_code == 404
        assert client.get(f"/api/chunks/{chunks[0]['id']}").json()["chunk_id"] == chunks[0]["id"]
        answer = client.post("/api/ask", json={"question": "When does the Thun lease end?"}).json()
        assert "2033" in answer["answer"]
        stream = client.get("/api/ask/stream", params={"q": "When does the Thun lease end?"}).text
        assert stream.startswith("event: citations") and "event: done" in stream
        assert client.post("/api/memos").status_code == 403
        memo = client.post("/api/memos", headers=partner).json()
        memo_id = memo["memo_id"]
        assert client.get("/api/memos").json()[-1]["memo_id"] == memo_id
        assert client.get(f"/api/memos/{memo_id}").json()["review"]["state"] == "in_review"
        assert client.get("/api/memos/unknown").status_code == 404
        refused = client.post(f"/api/memos/{memo_id}/review", headers=partner, json={"action": "approve"})
        assert refused.status_code == 409
        assert client.post("/api/memos/unknown/review", headers=partner, json={"action": "approve"}).status_code == 404
        responses = {a["title"]: "Addressed in SPA" for a in memo["arguments"] if a["severity"] == "high"}
        done = client.post(
            f"/api/memos/{memo_id}/review", headers=partner, json={"action": "approve", "responses": responses}
        ).json()
        assert done["review"]["state"] == "approved"
        item = client.post(
            "/api/items",
            json={
                "title": "Covenant",
                "description": "Headroom 2.7% in FY2026",
                "severity": "high",
                "evidence_chunk_ids": [chunks[0]["id"]],
            },
        )
        assert item.status_code == 200 and client.get("/api/items").json()
        request = client.post("/api/export", headers=partner, json={}).json()
        assert client.get("/api/approvals").json()[0]["id"] == request["approval_id"]
        assert client.post(f"/api/approvals/{request['approval_id']}").status_code == 403
        assert client.post(f"/api/approvals/{request['approval_id']}", headers=partner).status_code == 200
        exported = client.post("/api/export", headers=partner, json={"approval_id": request["approval_id"]}).json()
        assert exported["path"].startswith("reports/ic_memo_")
        audit = client.get("/api/audit").json()
        assert audit["verified"] and audit["records"]
    finally:
        api.app.dependency_overrides.clear()


# ------------------------------------------------------------------ CLI


def test_cli_commands(
    root: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    shutil.copytree(root / "data", tmp_path / "data")
    monkeypatch.setenv("DEALROOM_ROOT", str(tmp_path))
    monkeypatch.delenv("DEALROOM_RETRIEVAL", raising=False)
    cli.main(["generate"])
    cli.main(["ask", "When does the Thun lease end?"])
    assert "2033" in capsys.readouterr().out
    cli.main(["ingest", "--redact-copies"])
    cli.main(["eval"])
    report = (tmp_path / "reports" / "eval.md").read_text()
    assert "Trap recall: 100.0%" in report and "| 0 of 10 |" in report
    cli.main(["demo"])
    out = capsys.readouterr().out
    assert "refused" in out and "approved by Demo Partner" in out
    assert (tmp_path / "reports" / "demo_memo.md").exists()
    shutil.rmtree(tmp_path / ".cache")
    cli.main(["eval"])
    shutil.rmtree(tmp_path / ".cache")
    monkeypatch.setattr(api, "workspace", lambda: Workspace.load(tmp_path))
    assert api.workspace().retriever.chunks
