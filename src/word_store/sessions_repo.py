"""Repository helpers for session lifecycle queries."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from psycopg.types.json import Jsonb

from .db import PostgresStore


class SessionsRepository:
    """SQL-first repository for `sessions` table operations."""

    def __init__(self, store: PostgresStore) -> None:
        self.store = store

    def create_session(
        self,
        user_id: str,
        *,
        session_id: str | UUID | None = None,
        title: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        session_meta = metadata or {}
        columns = (
            "session_id, user_id, title, status, metadata, created_at, updated_at, last_activity_at"
        )
        with self.store.connection() as conn:
            with conn.cursor() as cur:
                if session_id is None:
                    cur.execute(
                        """
                        insert into sessions (user_id, title, metadata)
                        values (%s, %s, %s)
                        returning
                            session_id, user_id, title, status, metadata, created_at, updated_at, last_activity_at
                        """,
                        (user_id, title, Jsonb(session_meta)),
                    )
                else:
                    cur.execute(
                        f"""
                        insert into sessions (session_id, user_id, title, metadata)
                        values (%s, %s, %s, %s)
                        returning {columns}
                        """,
                        (str(session_id), user_id, title, Jsonb(session_meta)),
                    )
                row = cur.fetchone()
                conn.commit()
        if row is None:
            raise RuntimeError("failed to create session")
        return row

    def list_sessions(
        self,
        user_id: str,
        *,
        status: str | None = None,
        limit: int = 50,
        before_updated_at: datetime | None = None,
    ) -> list[dict[str, Any]]:
        sql = """
            select
                session_id, user_id, title, status, metadata, created_at, updated_at, last_activity_at
            from sessions
            where user_id = %s and status <> 'deleted'
        """
        params: list[Any] = [user_id]
        if status is not None:
            sql += " and status = %s"
            params.append(status)
        if before_updated_at is not None:
            sql += " and updated_at < %s"
            params.append(before_updated_at)
        sql += " order by updated_at desc limit %s"
        params.append(limit)
        with self.store.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, params)
                rows = cur.fetchall()
        return rows

    def get_session(self, session_id: str | UUID) -> dict[str, Any] | None:
        with self.store.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    select
                        session_id, user_id, title, status, metadata, created_at, updated_at, last_activity_at
                    from sessions
                    where session_id = %s
                    """,
                    (str(session_id),),
                )
                return cur.fetchone()

    def update_session(
        self,
        session_id: str | UUID,
        *,
        title: str | None = None,
        status: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        if title is None and status is None and metadata is None:
            return self.get_session(session_id)
        with self.store.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    update sessions
                    set
                        title = coalesce(%s, title),
                        status = coalesce(%s, status),
                        metadata = coalesce(%s, metadata)
                    where session_id = %s
                    returning
                        session_id, user_id, title, status, metadata, created_at, updated_at, last_activity_at
                    """,
                    (
                        title,
                        status,
                        Jsonb(metadata) if metadata is not None else None,
                        str(session_id),
                    ),
                )
                row = cur.fetchone()
                conn.commit()
        return row

