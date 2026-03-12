from __future__ import annotations

import json
import threading
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from docx import Document
import pytest

from word_agent import WordAgent
from word_engine import EngineConfig, WordDocumentService
from word_ui.web_server import create_server
from word_ui.workspace import WordUIWorkspace


def _request_json(
    base_url: str,
    path: str,
    method: str = "GET",
    payload: dict | None = None,
    headers: dict[str, str] | None = None,
):
    data = None
    combined_headers: dict[str, str] = dict(headers or {})
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        combined_headers["Content-Type"] = "application/json"
    request = Request(f"{base_url}{path}", data=data, method=method, headers=combined_headers)
    try:
        with urlopen(request, timeout=3) as response:
            return response.status, json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        return exc.code, json.loads(exc.read().decode("utf-8"))


def _make_workspace(root):
    service = WordDocumentService(config=EngineConfig(allowed_roots=[root]))
    return WordUIWorkspace(agent=WordAgent(service=service), allowed_roots=[root])


def test_http_api_key_and_read_only_guards(tmp_path):
    target = tmp_path / "target.docx"
    Document().save(str(target))

    workspace = _make_workspace(tmp_path)
    try:
        server = create_server("127.0.0.1", 0, workspace=workspace, api_key="secret", read_only=False)
    except PermissionError:
        pytest.skip("socket binding is restricted in this sandbox")
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{port}"
    try:
        config_status, config_payload = _request_json(base_url, "/api/config")
        assert config_status == 200
        assert config_payload["api_key_required"] is True
        assert config_payload["read_only"] is False

        create_status, create_payload = _request_json(base_url, "/api/sessions", method="POST", payload={})
        assert create_status == 200
        session_id = create_payload["session"]["session_id"]

        unauthorized_status, unauthorized_payload = _request_json(
            base_url,
            f"/api/sessions/{session_id}/targets/add",
            method="POST",
            payload={"file_path": str(target)},
        )
        assert unauthorized_status == 401
        assert unauthorized_payload["error_code"] == "AUTH_REQUIRED"

        ok_status, ok_payload = _request_json(
            base_url,
            f"/api/sessions/{session_id}/targets/add",
            method="POST",
            payload={"file_path": str(target)},
            headers={"X-API-Key": "secret"},
        )
        assert ok_status == 200
        assert ok_payload["status"] == "ok"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)

    read_only_workspace = _make_workspace(tmp_path)
    read_only_server = create_server(
        "127.0.0.1",
        0,
        workspace=read_only_workspace,
        api_key="secret",
        read_only=True,
    )
    ro_port = read_only_server.server_address[1]
    ro_thread = threading.Thread(target=read_only_server.serve_forever, daemon=True)
    ro_thread.start()
    ro_base_url = f"http://127.0.0.1:{ro_port}"
    try:
        create_status, create_payload = _request_json(ro_base_url, "/api/sessions", method="POST", payload={})
        assert create_status == 200
        session_id = create_payload["session"]["session_id"]

        blocked_status, blocked_payload = _request_json(
            ro_base_url,
            f"/api/sessions/{session_id}/plans/apply",
            method="POST",
            payload={"plan_id": "p1"},
            headers={"X-API-Key": "secret"},
        )
        assert blocked_status == 403
        assert blocked_payload["error_code"] == "READ_ONLY"
    finally:
        read_only_server.shutdown()
        read_only_server.server_close()
        ro_thread.join(timeout=3)
