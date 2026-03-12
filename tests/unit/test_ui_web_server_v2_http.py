from __future__ import annotations

import json
import threading
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest

from word_ui.web_server import create_server


class _FakeWorkspaceV2:
    def login(self, employee_id: str):
        return {"status": "ok", "contract_version": "v2", "user": {"user_id": employee_id}}

    def list_user_sessions(self, user_id: str, *, status=None, limit=50):
        return {
            "status": "ok",
            "contract_version": "v2",
            "sessions": [{"session_id": "s1", "user_id": user_id, "status": status or "active"}],
            "next_cursor": None,
            "limit": limit,
        }

    def create_session(self, user_id: str, *, title=None, metadata=None):
        return {
            "status": "ok",
            "contract_version": "v2",
            "session": {"session_id": "s1", "user_id": user_id, "title": title, "metadata": metadata or {}},
        }

    def hydrate_session(self, session_id: str):
        return {"status": "ok", "contract_version": "v2", "session": {"session_id": session_id}, "messages": []}

    def respond(
        self,
        session_id: str,
        *,
        message=None,
        data_source_filters=None,
        response_mode="auto",
        report_plan_state=None,
        report_plan_action=None,
    ):
        return {
            "status": "ok",
            "contract_version": "v2",
            "session_id": session_id,
            "message": message,
            "filters": data_source_filters,
            "response_mode": response_mode,
            "report_plan_state": report_plan_state,
            "report_plan_action": report_plan_action,
        }

    def list_data_source_catalog(self, *, enabled_only=True, source_type=None):
        return {
            "status": "ok",
            "contract_version": "v2",
            "enabled_only": enabled_only,
            "source_type": source_type,
            "sources": [],
        }

    def list_session_artifacts(self, session_id: str, *, artifact_type=None, limit=200):
        return {
            "status": "ok",
            "contract_version": "v2",
            "session_id": session_id,
            "artifact_type": artifact_type,
            "limit": limit,
            "artifacts": [],
            "next_cursor": None,
        }

    def upload_artifact(self, session_id: str, *, file_path: str, artifact_type: str):
        return {
            "status": "ok",
            "contract_version": "v2",
            "session_id": session_id,
            "file_path": file_path,
            "artifact_type": artifact_type,
        }

    def preview_artifact(self, session_id: str, artifact_id: str):
        return {"status": "ok", "contract_version": "v2", "session_id": session_id, "artifact_id": artifact_id}

    def get_operation(self, session_id: str, operation_id: str):
        return {"status": "ok", "contract_version": "v2", "session_id": session_id, "operation_id": operation_id}

    def message_events(self, session_id: str, message_id: str):
        return {"status": "ok", "contract_version": "v2", "session_id": session_id, "message_id": message_id}


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


def test_v2_routes_are_served_over_http():
    workspace_v2 = _FakeWorkspaceV2()
    try:
        server = create_server("127.0.0.1", 0, workspace_v2=workspace_v2)
    except PermissionError:
        pytest.skip("socket binding is restricted in this sandbox")

    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{port}"
    try:
        login_status, login_payload = _request_json(
            base_url,
            "/api/v2/auth/login",
            method="POST",
            payload={"employee_id": "123456789"},
        )
        assert login_status == 200
        assert login_payload["contract_version"] == "v2"
        assert login_payload["user"]["user_id"] == "123456789"

        sessions_status, sessions_payload = _request_json(
            base_url,
            "/api/v2/users/123456789/sessions?status=active&limit=10",
        )
        assert sessions_status == 200
        assert sessions_payload["sessions"][0]["user_id"] == "123456789"
        assert sessions_payload["limit"] == 10

        respond_status, respond_payload = _request_json(
            base_url,
            "/api/v2/sessions/s1/respond",
            method="POST",
            payload={
                "message": "hello",
                "data_source_filters": ["a"],
                "report_plan_state": {"plan_id": "p1", "status": "scaffolding"},
                "report_plan_action": "start_now",
            },
        )
        assert respond_status == 200
        assert respond_payload["session_id"] == "s1"
        assert respond_payload["filters"] == ["a"]
        assert respond_payload["report_plan_state"] == {"plan_id": "p1", "status": "scaffolding"}
        assert respond_payload["report_plan_action"] == "start_now"

        config_status, config_payload = _request_json(base_url, "/api/config")
        assert config_status == 200
        assert config_payload["legacy_v1_routes_enabled"] is False
        assert config_payload["v2_enabled"] is True

        legacy_status, legacy_payload = _request_json(
            base_url,
            "/api/sessions",
            method="POST",
            payload={},
        )
        assert legacy_status == 410
        assert legacy_payload["error_code"] == "NOT_AVAILABLE"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)
