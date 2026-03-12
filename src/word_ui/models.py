"""State models for the UI workspace session contract."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(slots=True)
class ChatMessage:
    message_id: str
    role: str
    text: str
    created_at: str
    operation_refs: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "message_id": self.message_id,
            "role": self.role,
            "text": self.text,
            "created_at": self.created_at,
            "operation_refs": list(self.operation_refs),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ChatMessage":
        return cls(
            message_id=str(data.get("message_id", "")),
            role=str(data.get("role", "assistant")),
            text=str(data.get("text", "")),
            created_at=str(data.get("created_at", "")),
            operation_refs=[str(item) for item in data.get("operation_refs", [])],
        )


@dataclass(slots=True)
class PreviewState:
    selected_file: str | None = None
    revision_id: str | None = None
    refreshed_at: str | None = None
    artifact_path: str | None = None
    artifact_format: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "selected_file": self.selected_file,
            "revision_id": self.revision_id,
            "refreshed_at": self.refreshed_at,
            "artifact_path": self.artifact_path,
            "artifact_format": self.artifact_format,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "PreviewState":
        return cls(
            selected_file=data.get("selected_file"),
            revision_id=data.get("revision_id"),
            refreshed_at=data.get("refreshed_at"),
            artifact_path=data.get("artifact_path"),
            artifact_format=data.get("artifact_format"),
        )


@dataclass(slots=True)
class SessionPlan:
    plan_id: str
    target_doc: str
    objective: str
    support_docs: list[str]
    section_plan: list[dict[str, Any]]
    created_at: str
    applied_at: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "plan_id": self.plan_id,
            "target_doc": self.target_doc,
            "objective": self.objective,
            "support_docs": list(self.support_docs),
            "section_plan": [dict(item) for item in self.section_plan],
            "created_at": self.created_at,
            "applied_at": self.applied_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SessionPlan":
        section_plan = data.get("section_plan", [])
        return cls(
            plan_id=str(data.get("plan_id", "")),
            target_doc=str(data.get("target_doc", "")),
            objective=str(data.get("objective", "")),
            support_docs=[str(item) for item in data.get("support_docs", [])],
            section_plan=[dict(item) for item in section_plan],
            created_at=str(data.get("created_at", "")),
            applied_at=data.get("applied_at"),
        )


@dataclass(slots=True)
class WorkspaceSession:
    session_id: str
    created_at: str
    updated_at: str
    context_files: list[str] = field(default_factory=list)
    editable_targets: list[str] = field(default_factory=list)
    active_target: str | None = None
    preview: PreviewState = field(default_factory=PreviewState)
    messages: list[ChatMessage] = field(default_factory=list)
    plans: dict[str, SessionPlan] = field(default_factory=dict)

    def touch(self) -> None:
        self.updated_at = utc_now_iso()

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "context_files": list(self.context_files),
            "editable_targets": list(self.editable_targets),
            "active_target": self.active_target,
            "preview": self.preview.to_dict(),
            "messages": [message.to_dict() for message in self.messages],
            "plans": [plan.to_dict() for plan in self.plans.values()],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "WorkspaceSession":
        plans_input = data.get("plans", [])
        plans: dict[str, SessionPlan] = {}
        for item in plans_input:
            plan = SessionPlan.from_dict(dict(item))
            plans[plan.plan_id] = plan
        return cls(
            session_id=str(data.get("session_id", "")),
            created_at=str(data.get("created_at", "")),
            updated_at=str(data.get("updated_at", "")),
            context_files=[str(item) for item in data.get("context_files", [])],
            editable_targets=[str(item) for item in data.get("editable_targets", [])],
            active_target=data.get("active_target"),
            preview=PreviewState.from_dict(dict(data.get("preview", {}))),
            messages=[ChatMessage.from_dict(dict(item)) for item in data.get("messages", [])],
            plans=plans,
        )
