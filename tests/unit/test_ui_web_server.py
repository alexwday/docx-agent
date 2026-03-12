from __future__ import annotations

import json
import threading
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest

from word_ui.web_server import (
    create_server,
    is_document_mutation_route,
    load_index_html,
    requires_api_key,
    server_config_payload,
)


def _request_json(base_url: str, path: str, method: str = "GET", payload: dict | None = None):
    data = None
    headers = {}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    request = Request(f"{base_url}{path}", data=data, method=method, headers=headers)
    try:
        with urlopen(request, timeout=3) as response:
            return response.status, json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        return exc.code, json.loads(exc.read().decode("utf-8"))


def test_load_index_html_has_workspace_markup():
    html = load_index_html()
    assert "docx-agent Workspace" in html
    assert "Employee Login" in html
    assert "Data Source Filters (Optional)" in html
    assert "Uploaded Documents" in html


def test_web_server_session_endpoints():
    try:
        server = create_server("127.0.0.1", 0)
    except PermissionError:
        pytest.skip("socket binding is restricted in this sandbox")
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{port}"
    try:
        create_status, create_payload = _request_json(base_url, "/api/sessions", method="POST", payload={})
        assert create_status == 200
        assert create_payload["status"] == "ok"
        session_id = create_payload["session"]["session_id"]

        state_status, state_payload = _request_json(base_url, f"/api/sessions/{session_id}")
        assert state_status == 200
        assert state_payload["status"] == "ok"
        assert state_payload["session"]["session_id"] == session_id
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)


def test_web_server_route_classification_helpers():
    assert is_document_mutation_route("/api/sessions/x/plans/apply") is True
    assert is_document_mutation_route("/api/sessions/x/plans/run") is False
    assert requires_api_key("/api/sessions/x/targets/add") is True
    assert requires_api_key("/api/sessions/x/messages") is False


def test_server_config_payload():
    config = server_config_payload(read_only=True, api_key="secret")
    assert config["status"] == "ok"
    assert config["read_only"] is True
    assert config["api_key_required"] is True
