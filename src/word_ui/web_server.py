"""Lightweight web server for the docx-agent UI workspace."""

from __future__ import annotations

import argparse
from datetime import date, datetime
from decimal import Decimal
from http import HTTPStatus
import json
import os
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse
from uuid import UUID, uuid4

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from .workspace import WordUIWorkspace


STATIC_DIR = Path(__file__).resolve().parent / "static"
INDEX_HTML_PATH = STATIC_DIR / "index.html"
V2_API_PREFIX = "/api/v2"
DOCUMENT_MUTATION_SUFFIXES = ("/plans/apply", "/documents/create")
PROTECTED_OPERATION_SUFFIXES = (
    "/documents/create",
    "/context-files/add",
    "/context-files/remove",
    "/targets/add",
    "/targets/remove",
    "/preview/select",
    "/preview/refresh",
    "/plans/run",
    "/plans/apply",
    "/validate",
)


def load_index_html() -> str:
    if not INDEX_HTML_PATH.exists():
        return "<html><body><h1>UI file not found: index.html</h1></body></html>"
    return INDEX_HTML_PATH.read_text(encoding="utf-8")


def _error_payload(error_code: str, message: str, **payload: Any) -> dict[str, Any]:
    return {
        "status": "error",
        "contract_version": "v1",
        "error_code": error_code,
        "message": message,
        **payload,
    }


def _error_payload_v2(error_code: str, message: str, **payload: Any) -> dict[str, Any]:
    return {
        "status": "error",
        "contract_version": "v2",
        "error_code": error_code,
        "message": message,
        **payload,
    }


def _segment_path(path: str, index: int) -> str:
    segments = [item for item in path.split("/") if item]
    if index < len(segments):
        return segments[index]
    return ""


def is_document_mutation_route(path: str) -> bool:
    return any(path.endswith(suffix) for suffix in DOCUMENT_MUTATION_SUFFIXES)


def requires_api_key(path: str) -> bool:
    return any(path.endswith(suffix) for suffix in PROTECTED_OPERATION_SUFFIXES)


def _status_from_result(result: dict[str, Any]) -> HTTPStatus:
    return HTTPStatus.OK if result.get("status") == "ok" else HTTPStatus.BAD_REQUEST


def server_config_payload(
    read_only: bool,
    api_key: str | None,
    allowed_roots: list[str] | None = None,
    legacy_v1_routes_enabled: bool = True,
    v2_enabled: bool = False,
) -> dict[str, Any]:
    return {
        "status": "ok",
        "contract_version": "v1",
        "read_only": read_only,
        "api_key_required": bool(api_key),
        "allowed_roots": allowed_roots or [],
        "legacy_v1_routes_enabled": legacy_v1_routes_enabled,
        "v2_enabled": v2_enabled,
    }


def dispatch_api_post(
    path: str,
    payload: dict[str, Any],
    headers: dict[str, str] | None,
    workspace: WordUIWorkspace | None,
    read_only: bool = False,
    api_key: str | None = None,
) -> tuple[HTTPStatus, dict[str, Any]]:
    if workspace is None:
        result = _error_payload(
            "NOT_AVAILABLE",
            "legacy v1 routes are disabled; use /api/v2 routes",
        )
        return HTTPStatus.GONE, result

    if path == "/api/sessions":
        result = workspace.create_session(session_id=payload.get("session_id"))
        return _status_from_result(result), result

    if not path.startswith("/api/sessions/"):
        result = _error_payload("NOT_FOUND", f"route not found: {path}")
        return HTTPStatus.NOT_FOUND, result

    if read_only and is_document_mutation_route(path):
        result = _error_payload("READ_ONLY", "document mutation operations are disabled in read-only mode")
        return HTTPStatus.FORBIDDEN, result

    normalized_headers = {key.lower(): value for key, value in (headers or {}).items()}
    if api_key and requires_api_key(path):
        incoming_key = normalized_headers.get("x-api-key")
        if incoming_key != api_key:
            result = _error_payload("AUTH_REQUIRED", "missing or invalid X-API-Key for protected operation")
            return HTTPStatus.UNAUTHORIZED, result

    session_id = _segment_path(path, 2)
    if path.endswith("/messages"):
        result = workspace.send_message(session_id, payload.get("text") or "")
    elif path.endswith("/agent-response"):
        operation_refs = payload.get("operation_refs") or []
        result = workspace.agent_response(
            session_id=session_id,
            text=payload.get("text") or "",
            operation_refs=operation_refs,
        )
    elif path.endswith("/chat"):
        result = workspace.chat_with_agent(
            session_id=session_id,
            user_text=payload.get("text") or "",
        )
    elif path.endswith("/documents/create"):
        result = workspace.create_document(
            session_id, payload.get("file_path") or "", title=payload.get("title")
        )
    elif path.endswith("/context-files/add"):
        result = workspace.add_context_file(session_id, payload.get("file_path") or "")
    elif path.endswith("/context-files/remove"):
        result = workspace.remove_context_file(session_id, payload.get("file_path") or "")
    elif path.endswith("/targets/add"):
        result = workspace.add_editable_target(session_id, payload.get("file_path") or "")
    elif path.endswith("/targets/remove"):
        result = workspace.remove_editable_target(session_id, payload.get("file_path") or "")
    elif path.endswith("/preview/select"):
        result = workspace.select_preview_file(session_id, payload.get("file_path") or "")
    elif path.endswith("/preview/refresh"):
        revision_id = payload.get("revision_id") or str(uuid4())
        result = workspace.refresh_preview(
            session_id=session_id,
            file_path=payload.get("file_path") or "",
            revision_id=revision_id,
        )
    elif path.endswith("/plans/run"):
        result = workspace.run_plan(
            session_id=session_id,
            objective=payload.get("objective") or "",
            target_doc=payload.get("target_doc"),
        )
    elif path.endswith("/plans/apply"):
        result = workspace.apply_plan(
            session_id=session_id,
            plan_id=payload.get("plan_id") or "",
        )
    elif path.endswith("/validate"):
        expected_sections = payload.get("expected_sections") or []
        result = workspace.validate_result(
            session_id=session_id,
            target_doc=payload.get("target_doc"),
            expected_sections=expected_sections,
        )
    else:
        result = _error_payload("NOT_FOUND", f"route not found: {path}")
        return HTTPStatus.NOT_FOUND, result

    return _status_from_result(result), result


def dispatch_api_v2_post(
    path: str,
    payload: dict[str, Any],
    workspace_v2: Any | None,
) -> tuple[HTTPStatus, dict[str, Any]]:
    if workspace_v2 is None:
        result = _error_payload_v2(
            "INTERNAL_ERROR",
            "v2 workspace is not configured; set DOCX_AGENT_DATABASE_DSN or DATABASE_URL",
        )
        return HTTPStatus.INTERNAL_SERVER_ERROR, result

    if path == "/api/v2/auth/login":
        result = workspace_v2.login(payload.get("employee_id") or "")
        return _status_from_result(result), result

    if path == "/api/v2/sessions":
        result = workspace_v2.create_session(
            user_id=payload.get("user_id") or "",
            title=payload.get("title"),
            metadata=payload.get("metadata") or {},
        )
        return _status_from_result(result), result

    if not path.startswith("/api/v2/sessions/"):
        result = _error_payload_v2("NOT_FOUND", f"route not found: {path}")
        return HTTPStatus.NOT_FOUND, result

    session_id = _segment_path(path, 3)
    if path.endswith("/respond"):
        filters = payload.get("data_source_filters")
        filter_list = list(filters) if isinstance(filters, list) else None
        report_plan_state = payload.get("report_plan_state")
        if not isinstance(report_plan_state, dict):
            report_plan_state = None
        report_plan_action = payload.get("report_plan_action")
        report_plan_action_value = str(report_plan_action).strip() if report_plan_action is not None else None
        result = workspace_v2.respond(
            session_id=session_id,
            message=payload.get("message"),
            data_source_filters=filter_list,
            response_mode=payload.get("response_mode") or "auto",
            report_plan_state=report_plan_state,
            report_plan_action=report_plan_action_value,
        )
    elif path.endswith("/delete"):
        result = workspace_v2.delete_session(session_id)
    elif path.endswith("/rename"):
        result = workspace_v2.rename_session(session_id, payload.get("title") or "")
    elif path.endswith("/artifacts/upload"):
        result = workspace_v2.upload_artifact(
            session_id=session_id,
            file_path=payload.get("file_path") or "",
            artifact_type=payload.get("artifact_type") or "upload",
        )
    else:
        result = _error_payload_v2("NOT_FOUND", f"route not found: {path}")
        return HTTPStatus.NOT_FOUND, result

    return _status_from_result(result), result


def dispatch_api_v2_get(
    path: str,
    query_params: dict[str, list[str]],
    workspace_v2: Any | None,
) -> tuple[HTTPStatus, dict[str, Any]]:
    if workspace_v2 is None:
        result = _error_payload_v2(
            "INTERNAL_ERROR",
            "v2 workspace is not configured; set DOCX_AGENT_DATABASE_DSN or DATABASE_URL",
        )
        return HTTPStatus.INTERNAL_SERVER_ERROR, result

    if path == "/api/v2/data-sources/catalog":
        enabled_raw = (query_params.get("enabled") or ["true"])[0].lower()
        enabled_only = enabled_raw != "false"
        source_type = (query_params.get("source_type") or [None])[0]
        result = workspace_v2.list_data_source_catalog(enabled_only=enabled_only, source_type=source_type)
        return _status_from_result(result), result

    if path.startswith("/api/v2/users/") and path.endswith("/sessions"):
        user_id = _segment_path(path, 3)
        status = (query_params.get("status") or [None])[0]
        limit_raw = (query_params.get("limit") or ["50"])[0]
        try:
            limit = max(1, min(int(limit_raw), 500))
        except ValueError:
            return HTTPStatus.BAD_REQUEST, _error_payload_v2("INVALID_ARGUMENT", "limit must be an integer")
        result = workspace_v2.list_user_sessions(user_id=user_id, status=status, limit=limit)
        return _status_from_result(result), result

    if not path.startswith("/api/v2/sessions/"):
        result = _error_payload_v2("NOT_FOUND", f"route not found: {path}")
        return HTTPStatus.NOT_FOUND, result

    session_id = _segment_path(path, 3)
    if path.endswith("/hydrate"):
        result = workspace_v2.hydrate_session(session_id)
    elif path.endswith("/artifacts"):
        artifact_type = (query_params.get("artifact_type") or [None])[0]
        limit_raw = (query_params.get("limit") or ["200"])[0]
        try:
            limit = max(1, min(int(limit_raw), 2000))
        except ValueError:
            return HTTPStatus.BAD_REQUEST, _error_payload_v2("INVALID_ARGUMENT", "limit must be an integer")
        result = workspace_v2.list_session_artifacts(session_id, artifact_type=artifact_type, limit=limit)
    elif "/artifacts/" in path and path.endswith("/preview"):
        artifact_id = _segment_path(path, 5)
        result = workspace_v2.preview_artifact(session_id, artifact_id)
    elif "/operations/" in path:
        operation_id = _segment_path(path, 5)
        result = workspace_v2.get_operation(session_id, operation_id)
    elif "/messages/" in path and path.endswith("/events"):
        message_id = _segment_path(path, 5)
        result = workspace_v2.message_events(session_id, message_id)
    else:
        result = _error_payload_v2("NOT_FOUND", f"route not found: {path}")
        return HTTPStatus.NOT_FOUND, result

    return _status_from_result(result), result


class WorkspaceHTTPRequestHandler(BaseHTTPRequestHandler):
    """HTTP API + static shell handler for the workspace UI."""

    server_version = "docx-agent-ui/0.1"
    workspace: WordUIWorkspace | None = None
    workspace_v2: Any | None = None
    read_only: bool = False
    api_key: str | None = None
    enable_legacy_v1_routes: bool = True

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        path = parsed.path
        query_params = parse_qs(parsed.query, keep_blank_values=False)
        if path == "/":
            self._write_html(HTTPStatus.OK, load_index_html())
            return
        if path == "/api/health":
            self._write_json(HTTPStatus.OK, {"status": "ok"})
            return
        if path.startswith(V2_API_PREFIX):
            status, result = dispatch_api_v2_get(path, query_params, self.workspace_v2)
            self._write_json(status, result)
            return
        if path == "/api/config":
            allowed_roots = []
            if self.workspace is not None:
                allowed_roots = [str(r) for r in self.workspace.allowed_roots]
            elif self.workspace_v2 is not None:
                roots = getattr(self.workspace_v2, "allowed_roots", None)
                if isinstance(roots, list):
                    allowed_roots = [str(r) for r in roots]
            self._write_json(
                HTTPStatus.OK,
                server_config_payload(
                    self.read_only,
                    self.api_key,
                    allowed_roots,
                    legacy_v1_routes_enabled=self.enable_legacy_v1_routes,
                    v2_enabled=self.workspace_v2 is not None,
                ),
            )
            return
        if path.startswith("/api/") and not self.enable_legacy_v1_routes:
            self._write_json(
                HTTPStatus.GONE,
                self._error("NOT_AVAILABLE", "legacy v1 routes are disabled; use /api/v2 routes"),
            )
            return
        if path.startswith("/api/sessions/") and path.endswith("/preview/content"):
            session_id = self._segment(path, 2)
            self._serve_preview_content(session_id)
            return
        if path.startswith("/api/sessions/") and self._path_depth(path) == 3:
            session_id = self._segment(path, 2)
            result = self.workspace.get_session_state(session_id)
            self._write_json(self._status_from_result(result), result)
            return
        self._write_json(HTTPStatus.NOT_FOUND, self._error("NOT_FOUND", f"route not found: {path}"))

    def do_POST(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        path = parsed.path
        payload = self._read_json_body()
        if isinstance(payload, dict) and payload.get("_error") is True:
            self._write_json(HTTPStatus.BAD_REQUEST, payload)
            return

        if path.startswith(V2_API_PREFIX):
            status, result = dispatch_api_v2_post(
                path=path,
                payload=payload,
                workspace_v2=self.workspace_v2,
            )
            self._write_json(status, result)
            return

        if path.startswith("/api/") and not self.enable_legacy_v1_routes:
            self._write_json(
                HTTPStatus.GONE,
                self._error("NOT_AVAILABLE", "legacy v1 routes are disabled; use /api/v2 routes"),
            )
            return

        status, result = dispatch_api_post(
            path=path,
            payload=payload,
            headers={key: value for key, value in self.headers.items()},
            workspace=self.workspace,
            read_only=self.read_only,
            api_key=self.api_key,
        )
        self._write_json(status, result)

    def log_message(self, fmt: str, *args: Any) -> None:
        """Suppress default request logging."""

    def _serve_preview_content(self, session_id: str) -> None:
        if self.workspace is None:
            self._write_json(
                HTTPStatus.GONE,
                self._error("NOT_AVAILABLE", "legacy v1 routes are disabled; use /api/v2 routes"),
            )
            return
        state = self.workspace.get_session_state(session_id)
        if state.get("status") != "ok":
            self._write_json(self._status_from_result(state), state)
            return
        preview = state["session"]["preview"]
        artifact_path = preview.get("artifact_path")
        if not artifact_path:
            self._write_html(
                HTTPStatus.OK,
                "<html><body><h2>No preview generated yet.</h2><p>Run apply or refresh preview.</p></body></html>",
            )
            return
        artifact = Path(artifact_path)
        if not artifact.exists():
            self._write_html(
                HTTPStatus.OK,
                "<html><body><h2>Preview artifact missing.</h2><p>Try refresh preview again.</p></body></html>",
            )
            return
        self._write_html(HTTPStatus.OK, artifact.read_text(encoding="utf-8"))

    @staticmethod
    def _json_default(obj: Any) -> Any:
        if isinstance(obj, (datetime, date)):
            return obj.isoformat()
        if isinstance(obj, UUID):
            return str(obj)
        if isinstance(obj, Decimal):
            return float(obj)
        if isinstance(obj, bytes):
            return obj.decode("utf-8", errors="replace")
        raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")

    def _write_json(self, status: HTTPStatus, payload: dict[str, Any]) -> None:
        body = json.dumps(payload, default=self._json_default).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _write_html(self, status: HTTPStatus, html_body: str) -> None:
        body = html_body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
        self.end_headers()
        self.wfile.write(body)

    def _read_json_body(self) -> dict[str, Any]:
        content_length = self.headers.get("Content-Length")
        if content_length is None:
            return {}
        try:
            raw = self.rfile.read(int(content_length))
            if not raw:
                return {}
            return json.loads(raw.decode("utf-8"))
        except (ValueError, json.JSONDecodeError):
            return self._error("INVALID_ARGUMENT", "request body must be valid JSON", _error=True)

    def _status_from_result(self, result: dict[str, Any]) -> HTTPStatus:
        return _status_from_result(result)

    def _segment(self, path: str, index: int) -> str:
        segments = [item for item in path.split("/") if item]
        if index < len(segments):
            return segments[index]
        return ""

    def _path_depth(self, path: str) -> int:
        return len([item for item in path.split("/") if item])

    def _is_document_mutation_route(self, path: str) -> bool:
        return is_document_mutation_route(path)

    def _requires_api_key(self, path: str) -> bool:
        return requires_api_key(path)

    def _error(self, error_code: str, message: str, **payload: Any) -> dict[str, Any]:
        return _error_payload(error_code, message, **payload)


def create_server(
    host: str,
    port: int,
    workspace: WordUIWorkspace | None = None,
    workspace_v2: Any | None = None,
    read_only: bool = False,
    api_key: str | None = None,
    enable_legacy_v1_routes: bool | None = None,
) -> ThreadingHTTPServer:
    if enable_legacy_v1_routes is None:
        enable_legacy_v1_routes = workspace_v2 is None
    WorkspaceHTTPRequestHandler.workspace = workspace if enable_legacy_v1_routes else None
    WorkspaceHTTPRequestHandler.workspace_v2 = workspace_v2
    WorkspaceHTTPRequestHandler.read_only = read_only
    WorkspaceHTTPRequestHandler.api_key = api_key
    WorkspaceHTTPRequestHandler.enable_legacy_v1_routes = bool(enable_legacy_v1_routes)
    return ThreadingHTTPServer((host, port), WorkspaceHTTPRequestHandler)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run docx-agent UI workspace server")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8030)
    parser.add_argument(
        "--allowed-root",
        action="append",
        default=None,
        help="Allowed root directory for UI file operations (repeatable). Defaults to current directory.",
    )
    parser.add_argument(
        "--session-store",
        default=".docx-agent-ui-sessions.json",
        help="Path for persisted UI session state JSON.",
    )
    parser.add_argument(
        "--enable-legacy-v1-routes",
        action="store_true",
        help="Enable legacy /api (v1 JSON-session) routes when running alongside /api/v2.",
    )
    parser.add_argument("--read-only", action="store_true", help="Disable document mutation operations.")
    parser.add_argument("--api-key", default=None, help="Require X-API-Key for protected operations.")
    parser.add_argument("--openai-model", default="gpt-4.1", help="OpenAI model name (default: gpt-4.1)")
    parser.add_argument(
        "--database-dsn",
        default=None,
        help="Optional Postgres DSN for enabling V2 API routes. Defaults to env vars.",
    )
    args = parser.parse_args()

    openai_api_key = os.environ.get("OPENAI_API_KEY")
    allowed_roots = args.allowed_root if args.allowed_root else [str(Path.cwd())]
    workspace: WordUIWorkspace | None = None
    workspace_v2 = None
    dsn_candidate = args.database_dsn or os.environ.get("DOCX_AGENT_DATABASE_DSN") or os.environ.get("DATABASE_URL")
    if dsn_candidate:
        try:
            from .workspace_v2 import WordUIWorkspaceV2

            workspace_v2 = WordUIWorkspaceV2(
                dsn=dsn_candidate,
                allowed_roots=allowed_roots,
                openai_api_key=openai_api_key,
                openai_model=args.openai_model,
            )
        except Exception as exc:  # noqa: BLE001
            print(f"warning: failed to initialize v2 workspace: {exc}")  # noqa: T201
    enable_legacy_v1_routes = args.enable_legacy_v1_routes or workspace_v2 is None
    if enable_legacy_v1_routes:
        workspace = WordUIWorkspace(
            allowed_roots=allowed_roots,
            session_store_path=args.session_store,
            openai_api_key=openai_api_key,
            openai_model=args.openai_model,
        )
    server = create_server(
        args.host,
        args.port,
        workspace=workspace,
        workspace_v2=workspace_v2,
        read_only=args.read_only,
        api_key=args.api_key,
        enable_legacy_v1_routes=enable_legacy_v1_routes,
    )
    print(f"docx-agent UI server running at http://{args.host}:{args.port}")  # noqa: T201
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
