from __future__ import annotations

from docx import Document

from word_agent import WordAgent
from word_engine import EngineConfig, WordDocumentService
from word_ui.web_server import dispatch_api_post
from word_ui.workspace import WordUIWorkspace


def _new_workspace(tmp_path):
    service = WordDocumentService(config=EngineConfig(allowed_roots=[tmp_path]))
    return WordUIWorkspace(
        agent=WordAgent(service=service),
        allowed_roots=[tmp_path],
    )


def test_dispatch_api_post_enforces_api_key_for_protected_route(tmp_path):
    target = tmp_path / "target.docx"
    Document().save(str(target))
    workspace = _new_workspace(tmp_path)

    create_status, create_payload = dispatch_api_post(
        path="/api/sessions",
        payload={},
        headers={},
        workspace=workspace,
    )
    assert create_status.value == 200
    session_id = create_payload["session"]["session_id"]

    unauthorized_status, unauthorized_payload = dispatch_api_post(
        path=f"/api/sessions/{session_id}/targets/add",
        payload={"file_path": str(target)},
        headers={},
        workspace=workspace,
        api_key="secret",
    )
    assert unauthorized_status.value == 401
    assert unauthorized_payload["error_code"] == "AUTH_REQUIRED"

    ok_status, ok_payload = dispatch_api_post(
        path=f"/api/sessions/{session_id}/targets/add",
        payload={"file_path": str(target)},
        headers={"X-API-Key": "secret"},
        workspace=workspace,
        api_key="secret",
    )
    assert ok_status.value == 200
    assert ok_payload["status"] == "ok"


def test_dispatch_api_post_read_only_blocks_apply_route(tmp_path):
    workspace = _new_workspace(tmp_path)
    status, payload = dispatch_api_post(
        path="/api/sessions/any/plans/apply",
        payload={"plan_id": "abc"},
        headers={},
        workspace=workspace,
        read_only=True,
    )
    assert status.value == 403
    assert payload["error_code"] == "READ_ONLY"
