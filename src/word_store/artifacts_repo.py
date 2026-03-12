"""Repository helpers for session artifacts and grouped UI panes."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from psycopg.types.json import Jsonb

from .db import PostgresStore


class SessionArtifactsRepository:
    """SQL-first repository for `session_artifacts` operations."""

    def __init__(self, store: PostgresStore) -> None:
        self.store = store

    def create_artifact(
        self,
        session_id: str | UUID,
        *,
        artifact_group_id: str | UUID | None = None,
        artifact_type: str,
        lifecycle_state: str = "final",
        format: str,
        filename: str,
        storage_uri: str,
        mime_type: str | None = None,
        size_bytes: int | None = None,
        checksum: str | None = None,
        created_from_message_id: str | UUID | None = None,
        source_artifact_id: str | UUID | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        artifact_meta = metadata or {}
        with self.store.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    insert into session_artifacts (
                        session_id,
                        artifact_group_id,
                        artifact_type,
                        lifecycle_state,
                        format,
                        filename,
                        storage_uri,
                        mime_type,
                        size_bytes,
                        checksum,
                        created_from_message_id,
                        source_artifact_id,
                        metadata
                    ) values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    returning
                        artifact_id,
                        session_id,
                        artifact_group_id,
                        artifact_type,
                        lifecycle_state,
                        format,
                        filename,
                        storage_uri,
                        mime_type,
                        size_bytes,
                        checksum,
                        created_from_message_id,
                        source_artifact_id,
                        metadata,
                        created_at
                    """,
                    (
                        str(session_id),
                        str(artifact_group_id) if artifact_group_id is not None else None,
                        artifact_type,
                        lifecycle_state,
                        format,
                        filename,
                        storage_uri,
                        mime_type,
                        size_bytes,
                        checksum,
                        str(created_from_message_id) if created_from_message_id is not None else None,
                        str(source_artifact_id) if source_artifact_id is not None else None,
                        Jsonb(artifact_meta),
                    ),
                )
                row = cur.fetchone()
                conn.commit()
        if row is None:
            raise RuntimeError("failed to create artifact")
        return row

    def list_artifacts(
        self,
        session_id: str | UUID,
        *,
        artifact_type: str | None = None,
        limit: int = 200,
    ) -> list[dict[str, Any]]:
        sql = """
            select
                artifact_id,
                session_id,
                artifact_group_id,
                artifact_type,
                lifecycle_state,
                format,
                filename,
                storage_uri,
                mime_type,
                size_bytes,
                checksum,
                created_from_message_id,
                source_artifact_id,
                metadata,
                created_at
            from session_artifacts
            where session_id = %s
        """
        params: list[Any] = [str(session_id)]
        if artifact_type is not None:
            sql += " and artifact_type = %s"
            params.append(artifact_type)
        sql += " order by created_at desc limit %s"
        params.append(limit)
        with self.store.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, params)
                rows = cur.fetchall()
        return rows

    def get_artifact(self, session_id: str | UUID, artifact_id: str | UUID) -> dict[str, Any] | None:
        with self.store.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    select
                        artifact_id,
                        session_id,
                        artifact_group_id,
                        artifact_type,
                        lifecycle_state,
                        format,
                        filename,
                        storage_uri,
                        mime_type,
                        size_bytes,
                        checksum,
                        created_from_message_id,
                        source_artifact_id,
                        metadata,
                        created_at
                    from session_artifacts
                    where session_id = %s and artifact_id = %s
                    """,
                    (str(session_id), str(artifact_id)),
                )
                return cur.fetchone()

    def update_artifact(
        self,
        session_id: str | UUID,
        artifact_id: str | UUID,
        *,
        lifecycle_state: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        with self.store.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    update session_artifacts
                    set
                        lifecycle_state = coalesce(%s, lifecycle_state),
                        metadata = coalesce(%s, metadata)
                    where session_id = %s and artifact_id = %s
                    returning
                        artifact_id,
                        session_id,
                        artifact_group_id,
                        artifact_type,
                        lifecycle_state,
                        format,
                        filename,
                        storage_uri,
                        mime_type,
                        size_bytes,
                        checksum,
                        created_from_message_id,
                        source_artifact_id,
                        metadata,
                        created_at
                    """,
                    (
                        lifecycle_state,
                        Jsonb(metadata) if metadata is not None else None,
                        str(session_id),
                        str(artifact_id),
                    ),
                )
                row = cur.fetchone()
                conn.commit()
        return row

    def list_artifact_panes(self, session_id: str | UUID) -> dict[str, list[dict[str, Any]]]:
        rows = self.list_artifacts(str(session_id), limit=1000)
        uploaded: list[dict[str, Any]] = []
        research: list[dict[str, Any]] = []
        reports: list[dict[str, Any]] = []
        for row in rows:
            artifact_type = row["artifact_type"]
            if artifact_type == "upload":
                uploaded.append(row)
            elif artifact_type == "research_output_doc":
                research.append(row)
            elif artifact_type in ("report_final_doc", "export_file"):
                reports.append(row)
        return {
            "uploaded_documents": uploaded,
            "research_outputs": research,
            "report_documents": reports,
        }
