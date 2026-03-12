"""Repository helpers for artifact-derived knowledge units."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from psycopg.types.json import Jsonb

from .db import PostgresStore


class ArtifactKnowledgeRepository:
    """SQL-first repository for `artifact_knowledge_units` operations."""

    def __init__(self, store: PostgresStore) -> None:
        self.store = store

    def create_knowledge_unit(
        self,
        session_id: str | UUID,
        artifact_id: str | UUID,
        *,
        unit_type: str,
        content: str,
        sequence_no: int = 0,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        payload = metadata or {}
        with self.store.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    insert into artifact_knowledge_units (
                        session_id, artifact_id, unit_type, sequence_no, content, metadata
                    ) values (%s, %s, %s, %s, %s, %s)
                    returning
                        knowledge_id,
                        session_id,
                        artifact_id,
                        unit_type,
                        sequence_no,
                        content,
                        metadata,
                        created_at
                    """,
                    (
                        str(session_id),
                        str(artifact_id),
                        unit_type,
                        sequence_no,
                        content,
                        Jsonb(payload),
                    ),
                )
                row = cur.fetchone()
                conn.commit()
        if row is None:
            raise RuntimeError("failed to create knowledge unit")
        return row

    def list_knowledge_units(
        self,
        session_id: str | UUID,
        *,
        artifact_id: str | UUID | None = None,
        unit_type: str | None = None,
        limit: int = 500,
    ) -> list[dict[str, Any]]:
        sql = """
            select
                knowledge_id,
                session_id,
                artifact_id,
                unit_type,
                sequence_no,
                content,
                metadata,
                created_at
            from artifact_knowledge_units
            where session_id = %s
        """
        params: list[Any] = [str(session_id)]
        if artifact_id is not None:
            sql += " and artifact_id = %s"
            params.append(str(artifact_id))
        if unit_type is not None:
            sql += " and unit_type = %s"
            params.append(unit_type)
        sql += " order by artifact_id asc, sequence_no asc limit %s"
        params.append(limit)
        with self.store.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, params)
                rows = cur.fetchall()
        return rows

