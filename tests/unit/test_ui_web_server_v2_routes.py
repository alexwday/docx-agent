from __future__ import annotations

from http import HTTPStatus

from word_ui.web_server import dispatch_api_v2_get, dispatch_api_v2_post


class _FakeWorkspaceV2:
    def login(self, employee_id: str):
        return {"status": "ok", "contract_version": "v2", "user": {"user_id": employee_id}}

    def create_session(self, user_id: str, *, title=None, metadata=None):
        return {
            "status": "ok",
            "contract_version": "v2",
            "session": {"session_id": "s1", "user_id": user_id, "title": title, "metadata": metadata or {}},
        }

    def list_user_sessions(self, user_id: str, *, status=None, limit=50):
        return {
            "status": "ok",
            "contract_version": "v2",
            "sessions": [{"session_id": "s1", "user_id": user_id, "status": status or "active"}],
            "next_cursor": None,
            "limit": limit,
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

    def upload_artifact(self, session_id: str, *, file_path: str, artifact_type: str):
        return {
            "status": "ok",
            "contract_version": "v2",
            "session_id": session_id,
            "file_path": file_path,
            "artifact_type": artifact_type,
        }

    def list_session_artifacts(self, session_id: str, *, artifact_type=None, limit=200):
        return {
            "status": "ok",
            "contract_version": "v2",
            "session_id": session_id,
            "artifact_type": artifact_type,
            "limit": limit,
        }

    def preview_artifact(self, session_id: str, artifact_id: str):
        return {"status": "ok", "contract_version": "v2", "session_id": session_id, "artifact_id": artifact_id}

    def get_operation(self, session_id: str, operation_id: str):
        return {"status": "ok", "contract_version": "v2", "session_id": session_id, "operation_id": operation_id}

    def message_events(self, session_id: str, message_id: str):
        return {"status": "ok", "contract_version": "v2", "session_id": session_id, "message_id": message_id}

    def list_data_source_catalog(self, *, enabled_only=True, source_type=None):
        return {
            "status": "ok",
            "contract_version": "v2",
            "enabled_only": enabled_only,
            "source_type": source_type,
            "sources": [],
        }


def test_v2_dispatch_requires_workspace():
    status, payload = dispatch_api_v2_post("/api/v2/auth/login", {"employee_id": "123456789"}, None)
    assert status == HTTPStatus.INTERNAL_SERVER_ERROR
    assert payload["error_code"] == "INTERNAL_ERROR"
    assert payload["contract_version"] == "v2"


def test_v2_dispatch_post_routes_basic():
    workspace = _FakeWorkspaceV2()
    status, payload = dispatch_api_v2_post(
        "/api/v2/sessions/s1/respond",
        {
            "message": "hello",
            "data_source_filters": ["a", "b"],
            "report_plan_state": {"plan_id": "p1", "status": "scaffolding"},
            "report_plan_action": "start_now",
        },
        workspace,
    )
    assert status == HTTPStatus.OK
    assert payload["status"] == "ok"
    assert payload["session_id"] == "s1"
    assert payload["filters"] == ["a", "b"]
    assert payload["report_plan_state"] == {"plan_id": "p1", "status": "scaffolding"}
    assert payload["report_plan_action"] == "start_now"


def test_v2_dispatch_get_routes_basic():
    workspace = _FakeWorkspaceV2()
    status, payload = dispatch_api_v2_get(
        "/api/v2/users/123456789/sessions",
        {"status": ["active"], "limit": ["25"]},
        workspace,
    )
    assert status == HTTPStatus.OK
    assert payload["status"] == "ok"
    assert payload["sessions"][0]["user_id"] == "123456789"
    assert payload["limit"] == 25


def test_v2_dispatch_get_artifact_preview_and_events():
    workspace = _FakeWorkspaceV2()
    preview_status, preview_payload = dispatch_api_v2_get(
        "/api/v2/sessions/s1/artifacts/a1/preview",
        {},
        workspace,
    )
    assert preview_status == HTTPStatus.OK
    assert preview_payload["artifact_id"] == "a1"

    events_status, events_payload = dispatch_api_v2_get(
        "/api/v2/sessions/s1/messages/m1/events",
        {},
        workspace,
    )
    assert events_status == HTTPStatus.OK
    assert events_payload["message_id"] == "m1"
