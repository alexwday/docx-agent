"""UI workspace service for chat/session/file/preview interactions."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from uuid import uuid4

from word_agent import WordAgent

from .models import ChatMessage, SessionPlan, WorkspaceSession, utc_now_iso
from .preview import DocxPreviewRenderer, PreviewRenderError


class WordUIWorkspace:
    """In-process UI workspace state and orchestration bridge."""

    def __init__(
        self,
        agent: WordAgent | None = None,
        preview_renderer: DocxPreviewRenderer | None = None,
        allowed_roots: list[str | Path] | None = None,
        session_store_path: str | None = None,
        contract_version: str = "v1",
        openai_api_key: str | None = None,
        openai_model: str = "gpt-4.1",
    ) -> None:
        self.agent = agent or WordAgent(model=openai_model, api_key=openai_api_key)
        self.preview_renderer = preview_renderer or DocxPreviewRenderer()
        self.allowed_roots = self._resolve_allowed_roots(allowed_roots)
        self.session_store_path = self._resolve_session_store_path(session_store_path)
        self.contract_version = contract_version
        self._sessions: dict[str, WorkspaceSession] = {}
        self._load_sessions_from_disk()

    # Session lifecycle -----------------------------------------------------

    def create_session(self, session_id: str | None = None) -> dict[str, Any]:
        session_key = session_id or str(uuid4())
        if session_key in self._sessions:
            return self._error("INVALID_ARGUMENT", f"session already exists: {session_key}")
        now = utc_now_iso()
        session = WorkspaceSession(session_id=session_key, created_at=now, updated_at=now)
        self._sessions[session_key] = session
        self._persist_sessions_to_disk()
        return self._ok(session=session.to_dict())

    def get_session_state(self, session_id: str) -> dict[str, Any]:
        session = self._require_session(session_id)
        if isinstance(session, dict):
            return session
        return self._ok(session=session.to_dict())

    # Conversation ----------------------------------------------------------

    def send_message(self, session_id: str, text: str) -> dict[str, Any]:
        session = self._require_session(session_id)
        if isinstance(session, dict):
            return session
        if not text.strip():
            return self._error("INVALID_ARGUMENT", "text must be a non-empty string")
        message = ChatMessage(
            message_id=str(uuid4()),
            role="user",
            text=text,
            created_at=utc_now_iso(),
        )
        session.messages.append(message)
        self._mark_dirty(session)
        return self._ok(message=message.to_dict(), session=session.to_dict())

    def agent_response(
        self,
        session_id: str,
        text: str,
        operation_refs: list[str] | None = None,
    ) -> dict[str, Any]:
        session = self._require_session(session_id)
        if isinstance(session, dict):
            return session
        if not text.strip():
            return self._error("INVALID_ARGUMENT", "text must be a non-empty string")
        message = ChatMessage(
            message_id=str(uuid4()),
            role="assistant",
            text=text,
            created_at=utc_now_iso(),
            operation_refs=list(operation_refs or []),
        )
        session.messages.append(message)
        self._mark_dirty(session)
        return self._ok(message=message.to_dict(), session=session.to_dict())

    def chat_with_agent(self, session_id: str, user_text: str) -> dict[str, Any]:
        """Send user text to the LLM and store the response as an agent message."""
        session = self._require_session(session_id)
        if isinstance(session, dict):
            return session
        if not user_text.strip():
            return self._error("INVALID_ARGUMENT", "text must be a non-empty string")

        # Build message history from recent session messages (last 20)
        recent = session.messages[-20:]
        messages = [{"role": m.role, "content": m.text} for m in recent]

        # Build system context about the session state
        parts: list[str] = []
        if session.active_target:
            parts.append(f"Active target document: {session.active_target}")
        if session.context_files:
            parts.append(f"Context files: {', '.join(session.context_files)}")
        if session.editable_targets:
            parts.append(f"Editable targets: {', '.join(session.editable_targets)}")
        system_context = "\n".join(parts)

        response_text = self.agent.chat(messages, system_context)
        result = self.agent_response(session_id, text=response_text)
        return result

    # File-list events ------------------------------------------------------

    def add_context_file(self, session_id: str, file_path: str) -> dict[str, Any]:
        session = self._require_session(session_id)
        if isinstance(session, dict):
            return session
        normalized = self._normalize_path(file_path)
        if isinstance(normalized, dict):
            return normalized
        ensured = self._ensure_allowed_existing_file(normalized)
        if isinstance(ensured, dict):
            return ensured
        if normalized not in session.context_files:
            session.context_files.append(normalized)
            self._mark_dirty(session)
        return self._ok(context_files=list(session.context_files), session=session.to_dict())

    def remove_context_file(self, session_id: str, file_path: str) -> dict[str, Any]:
        session = self._require_session(session_id)
        if isinstance(session, dict):
            return session
        normalized = self._normalize_path(file_path)
        if isinstance(normalized, dict):
            return normalized
        if normalized not in session.context_files:
            return self._error("INVALID_ARGUMENT", f"context file not found in session: {normalized}")
        session.context_files = [item for item in session.context_files if item != normalized]
        self._mark_dirty(session)
        return self._ok(context_files=list(session.context_files), session=session.to_dict())

    def create_document(self, session_id: str, file_path: str, title: str | None = None) -> dict[str, Any]:
        """Create a new blank .docx and add it as an editable target."""
        session = self._require_session(session_id)
        if isinstance(session, dict):
            return session
        normalized = self._normalize_path(file_path)
        if isinstance(normalized, dict):
            return normalized
        if Path(normalized).suffix.lower() != ".docx":
            return self._error("INVALID_ARGUMENT", "file_path must end with .docx")
        path = Path(normalized)
        if not self._is_path_allowed(path):
            return self._error("PATH_NOT_ALLOWED", f"path is outside allowed roots: {path}")
        if path.exists():
            return self._error("INVALID_ARGUMENT", f"file already exists: {path}")
        # Ensure parent directory exists
        path.parent.mkdir(parents=True, exist_ok=True)
        # Create via engine
        result = self.agent.service.create_document(str(path), title=title)
        if result.get("status") != "ok":
            return result
        # Auto-add as editable target + set active
        if normalized not in session.editable_targets:
            session.editable_targets.append(normalized)
        session.active_target = normalized
        session.preview.selected_file = normalized
        self._mark_dirty(session)
        return self._ok(file_path=normalized, editable_targets=list(session.editable_targets), session=session.to_dict())

    def add_editable_target(self, session_id: str, file_path: str) -> dict[str, Any]:
        session = self._require_session(session_id)
        if isinstance(session, dict):
            return session
        normalized = self._normalize_path(file_path)
        if isinstance(normalized, dict):
            return normalized
        ensured = self._ensure_allowed_existing_file(normalized)
        if isinstance(ensured, dict):
            return ensured
        if Path(normalized).suffix.lower() != ".docx":
            return self._error("INVALID_ARGUMENT", "editable target must be a .docx file")
        if normalized not in session.editable_targets:
            session.editable_targets.append(normalized)
        if session.active_target is None:
            session.active_target = normalized
        if session.preview.selected_file is None:
            session.preview.selected_file = normalized
        self._mark_dirty(session)
        return self._ok(editable_targets=list(session.editable_targets), session=session.to_dict())

    def remove_editable_target(self, session_id: str, file_path: str) -> dict[str, Any]:
        session = self._require_session(session_id)
        if isinstance(session, dict):
            return session
        normalized = self._normalize_path(file_path)
        if isinstance(normalized, dict):
            return normalized
        if normalized not in session.editable_targets:
            return self._error("INVALID_ARGUMENT", f"editable target not found in session: {normalized}")
        session.editable_targets = [item for item in session.editable_targets if item != normalized]
        if session.active_target == normalized:
            session.active_target = session.editable_targets[0] if session.editable_targets else None
        if session.preview.selected_file == normalized:
            session.preview.selected_file = session.active_target
            session.preview.revision_id = None
            session.preview.refreshed_at = None
            session.preview.artifact_path = None
            session.preview.artifact_format = None
        self._mark_dirty(session)
        return self._ok(editable_targets=list(session.editable_targets), session=session.to_dict())

    # Preview events --------------------------------------------------------

    def select_preview_file(self, session_id: str, file_path: str) -> dict[str, Any]:
        session = self._require_session(session_id)
        if isinstance(session, dict):
            return session
        normalized = self._normalize_path(file_path)
        if isinstance(normalized, dict):
            return normalized
        if normalized not in session.editable_targets:
            return self._error("INVALID_ARGUMENT", "preview file must be in editable_targets")
        session.active_target = normalized
        session.preview.selected_file = normalized
        session.preview.revision_id = None
        session.preview.refreshed_at = None
        session.preview.artifact_path = None
        session.preview.artifact_format = None
        self._mark_dirty(session)
        return self._ok(preview=session.preview.to_dict(), session=session.to_dict())

    def refresh_preview(
        self,
        session_id: str,
        file_path: str,
        revision_id: str,
    ) -> dict[str, Any]:
        session = self._require_session(session_id)
        if isinstance(session, dict):
            return session
        normalized = self._normalize_path(file_path)
        if isinstance(normalized, dict):
            return normalized
        if normalized not in session.editable_targets:
            return self._error("INVALID_ARGUMENT", "preview file must be in editable_targets")
        if not revision_id.strip():
            return self._error("INVALID_ARGUMENT", "revision_id must be a non-empty string")
        try:
            artifact = self.preview_renderer.render_docx_to_html(normalized, revision_id)
        except PreviewRenderError as exc:
            return self._error("PREVIEW_RENDER_FAILED", str(exc))
        session.active_target = normalized
        session.preview.selected_file = normalized
        session.preview.revision_id = revision_id
        session.preview.refreshed_at = utc_now_iso()
        session.preview.artifact_path = artifact["artifact_path"]
        session.preview.artifact_format = artifact["artifact_format"]
        self._mark_dirty(session)
        return self._ok(
            preview=session.preview.to_dict(),
            preview_artifact=artifact,
            session=session.to_dict(),
        )

    # Execution events ------------------------------------------------------

    def run_plan(
        self,
        session_id: str,
        objective: str,
        target_doc: str | None = None,
    ) -> dict[str, Any]:
        session = self._require_session(session_id)
        if isinstance(session, dict):
            return session
        if not objective.strip():
            return self._error("INVALID_ARGUMENT", "objective must be a non-empty string")

        target = self._resolve_target_doc(session, target_doc)
        if isinstance(target, dict):
            return target

        plan_response = self.agent.plan_template_fill(
            target_doc=target,
            support_docs=list(session.context_files),
            objective=objective,
        )
        if plan_response["status"] != "ok":
            return plan_response

        plan_id = str(uuid4())
        session.plans[plan_id] = SessionPlan(
            plan_id=plan_id,
            target_doc=target,
            objective=objective,
            support_docs=list(session.context_files),
            section_plan=[dict(item) for item in plan_response["section_plan"]],
            created_at=utc_now_iso(),
        )
        self._mark_dirty(session)
        self.agent_response(
            session_id=session_id,
            text=f"Plan {plan_id} generated with {len(plan_response['section_plan'])} section items.",
            operation_refs=[f"plan:{plan_id}"],
        )
        return self._ok(
            plan_id=plan_id,
            target_doc=target,
            section_plan=plan_response["section_plan"],
            session=session.to_dict(),
        )

    def apply_plan(self, session_id: str, plan_id: str) -> dict[str, Any]:
        session = self._require_session(session_id)
        if isinstance(session, dict):
            return session
        plan = session.plans.get(plan_id)
        if plan is None:
            return self._error("INVALID_ARGUMENT", f"plan not found: {plan_id}")

        enriched_plan: list[dict[str, Any]] = []
        context = {"objective": plan.objective, "support_docs": list(plan.support_docs)}
        for section_item in plan.section_plan:
            generated = self.agent.generate_section_content(section_item, context)
            if generated["status"] != "ok":
                return generated
            item_copy = dict(section_item)
            item_copy["paragraphs"] = generated["paragraphs"]
            enriched_plan.append(item_copy)

        apply_response = self.agent.apply_section_plan(plan.target_doc, enriched_plan)
        if apply_response["status"] == "ok":
            plan.applied_at = utc_now_iso()
            revision_id = str(uuid4())
            preview_result = self.refresh_preview(session_id, plan.target_doc, revision_id)
            self.agent_response(
                session_id=session_id,
                text=f"Applied plan {plan_id}: {apply_response['applied_count']} sections updated.",
                operation_refs=[f"plan:{plan_id}", "operation:apply_section_plan", "operation:refresh_preview"],
            )
            self._mark_dirty(session)
            return self._ok(
                plan_id=plan_id,
                target_doc=plan.target_doc,
                result=apply_response,
                preview_result=preview_result,
                session=session.to_dict(),
            )

        self.agent_response(
            session_id=session_id,
            text=f"Plan {plan_id} failed during apply.",
            operation_refs=[f"plan:{plan_id}", "operation:apply_section_plan"],
        )
        self._mark_dirty(session)
        return self._error(
            "APPLY_FAILED",
            f"plan apply failed: {plan_id}",
            plan_id=plan_id,
            target_doc=plan.target_doc,
            result=apply_response,
            session=session.to_dict(),
        )

    def validate_result(
        self,
        session_id: str,
        target_doc: str | None = None,
        expected_sections: list[str] | None = None,
    ) -> dict[str, Any]:
        session = self._require_session(session_id)
        if isinstance(session, dict):
            return session

        target = self._resolve_target_doc(session, target_doc)
        if isinstance(target, dict):
            return target

        sections = expected_sections
        if sections is None:
            sections = []
            for plan in session.plans.values():
                if plan.target_doc != target:
                    continue
                sections.extend(item.get("heading_text", "") for item in plan.section_plan)
        expected = [item for item in sections if item]
        validation = self.agent.validate_document_result(target, expected)
        self.agent_response(
            session_id=session_id,
            text=f"Validation for {Path(target).name}: {validation['status']}.",
            operation_refs=["operation:validate_document_result"],
        )
        self._mark_dirty(session)
        if validation["status"] == "ok":
            return self._ok(
                target_doc=target,
                expected_sections=expected,
                result=validation,
                session=session.to_dict(),
            )
        return self._error(
            "VALIDATION_FAILED",
            f"validation failed for target: {target}",
            target_doc=target,
            expected_sections=expected,
            result=validation,
            session=session.to_dict(),
        )

    # Internal helpers ------------------------------------------------------

    def _require_session(self, session_id: str) -> WorkspaceSession | dict[str, Any]:
        if not session_id:
            return self._error("INVALID_ARGUMENT", "session_id must be a non-empty string")
        session = self._sessions.get(session_id)
        if session is None:
            return self._error("INVALID_ARGUMENT", f"unknown session_id: {session_id}")
        return session

    def _normalize_path(self, file_path: str) -> str | dict[str, Any]:
        if not file_path or not isinstance(file_path, str):
            return self._error("INVALID_ARGUMENT", "file_path must be a non-empty string")
        return str(Path(file_path).expanduser().resolve())

    def _resolve_allowed_roots(self, allowed_roots: list[str | Path] | None) -> list[Path]:
        if not allowed_roots:
            return []
        return [Path(item).expanduser().resolve() for item in allowed_roots]

    def _resolve_session_store_path(self, value: str | None) -> Path | None:
        if value is None:
            return None
        return Path(value).expanduser().resolve()

    def _is_path_allowed(self, path: Path) -> bool:
        if not self.allowed_roots:
            return True
        for root in self.allowed_roots:
            try:
                path.relative_to(root)
                return True
            except ValueError:
                continue
        return False

    def _ensure_allowed_existing_file(self, file_path: str) -> bool | dict[str, Any]:
        path = Path(file_path)
        if not self._is_path_allowed(path):
            return self._error("PATH_NOT_ALLOWED", f"path is outside allowed roots: {path}")
        if not path.exists():
            return self._error("FILE_NOT_FOUND", f"file does not exist: {path}")
        if not path.is_file():
            return self._error("INVALID_ARGUMENT", f"path is not a file: {path}")
        return True

    def _mark_dirty(self, session: WorkspaceSession) -> None:
        session.touch()
        self._persist_sessions_to_disk()

    def _load_sessions_from_disk(self) -> None:
        store = self.session_store_path
        if store is None or not store.exists():
            return
        try:
            data = json.loads(store.read_text(encoding="utf-8"))
            sessions = data.get("sessions", [])
            for item in sessions:
                session = WorkspaceSession.from_dict(dict(item))
                if session.session_id:
                    self._sessions[session.session_id] = session
        except (OSError, ValueError):
            # Invalid session state should not block startup.
            self._sessions = {}

    def _persist_sessions_to_disk(self) -> None:
        store = self.session_store_path
        if store is None:
            return
        payload = {
            "saved_at": utc_now_iso(),
            "sessions": [session.to_dict() for session in self._sessions.values()],
        }
        store.parent.mkdir(parents=True, exist_ok=True)
        temp = store.with_suffix(f"{store.suffix}.tmp")
        temp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        temp.replace(store)

    def _resolve_target_doc(
        self,
        session: WorkspaceSession,
        target_doc: str | None,
    ) -> str | dict[str, Any]:
        if target_doc is not None:
            normalized = self._normalize_path(target_doc)
            if isinstance(normalized, dict):
                return normalized
            ensured = self._ensure_allowed_existing_file(normalized)
            if isinstance(ensured, dict):
                return ensured
            if normalized not in session.editable_targets:
                return self._error("INVALID_ARGUMENT", "target_doc must be listed in editable_targets")
            session.active_target = normalized
            session.preview.selected_file = normalized
            session.preview.artifact_path = None
            session.preview.artifact_format = None
            session.preview.revision_id = None
            session.preview.refreshed_at = None
            return normalized
        if session.active_target is not None:
            ensured = self._ensure_allowed_existing_file(session.active_target)
            if isinstance(ensured, dict):
                return ensured
            return session.active_target
        if session.editable_targets:
            session.active_target = session.editable_targets[0]
            ensured = self._ensure_allowed_existing_file(session.active_target)
            if isinstance(ensured, dict):
                return ensured
            session.preview.selected_file = session.active_target
            session.preview.artifact_path = None
            session.preview.artifact_format = None
            session.preview.revision_id = None
            session.preview.refreshed_at = None
            return session.active_target
        return self._error("INVALID_ARGUMENT", "no editable target available in session")

    def _ok(self, **payload: Any) -> dict[str, Any]:
        return {
            "status": "ok",
            "contract_version": self.contract_version,
            **payload,
        }

    def _error(self, error_code: str, message: str, **payload: Any) -> dict[str, Any]:
        return {
            "status": "error",
            "contract_version": self.contract_version,
            "error_code": error_code,
            "message": message,
            **payload,
        }
