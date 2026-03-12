"""Repository helpers for session message persistence."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from psycopg.types.json import Jsonb

from .db import PostgresStore


class MessagesRepository:
    """SQL-first repository for `session_messages` operations."""

    def __init__(self, store: PostgresStore) -> None:
        self.store = store

    def create_message(
        self,
        session_id: str | UUID,
        *,
        role: str,
        content_text: str | None,
        content_json: dict[str, Any] | None = None,
        parent_message_id: str | UUID | None = None,
        processing_state: str = "completed",
        processing_started_at: datetime | None = None,
        processing_ended_at: datetime | None = None,
        error: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        payload = content_json or {}
        session_key = str(session_id)
        with self.store.connection() as conn:
            with conn.transaction():
                with conn.cursor() as cur:
                    cur.execute(
                        "select session_id from sessions where session_id = %s for update",
                        (session_key,),
                    )
                    if cur.fetchone() is None:
                        raise ValueError(f"unknown session_id: {session_key}")

                    cur.execute(
                        """
                        select coalesce(max(sequence_no), 0) + 1 as next_sequence_no
                        from session_messages
                        where session_id = %s
                        """,
                        (session_key,),
                    )
                    next_seq = cur.fetchone()["next_sequence_no"]
                    cur.execute(
                        """
                        insert into session_messages (
                            session_id,
                            sequence_no,
                            role,
                            content_text,
                            content_json,
                            parent_message_id,
                            processing_state,
                            processing_started_at,
                            processing_ended_at,
                            error
                        ) values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        returning
                            message_id,
                            session_id,
                            sequence_no,
                            role,
                            content_text,
                            content_json,
                            parent_message_id,
                            processing_state,
                            processing_started_at,
                            processing_ended_at,
                            error,
                            created_at
                        """,
                        (
                            session_key,
                            next_seq,
                            role,
                            content_text,
                            Jsonb(payload),
                            str(parent_message_id) if parent_message_id is not None else None,
                            processing_state,
                            processing_started_at,
                            processing_ended_at,
                            Jsonb(error) if error is not None else None,
                        ),
                    )
                    row = cur.fetchone()
        if row is None:
            raise RuntimeError("failed to create message")
        return row

    def list_messages(
        self,
        session_id: str | UUID,
        *,
        limit: int = 200,
        after_sequence_no: int | None = None,
    ) -> list[dict[str, Any]]:
        sql = """
            select
                message_id,
                session_id,
                sequence_no,
                role,
                content_text,
                content_json,
                parent_message_id,
                processing_state,
                processing_started_at,
                processing_ended_at,
                error,
                created_at
            from session_messages
            where session_id = %s
        """
        params: list[Any] = [str(session_id)]
        if after_sequence_no is not None:
            sql += " and sequence_no > %s"
            params.append(after_sequence_no)
        sql += " order by sequence_no asc limit %s"
        params.append(limit)
        with self.store.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, params)
                rows = cur.fetchall()
        return rows

    def get_message(self, session_id: str | UUID, message_id: str | UUID) -> dict[str, Any] | None:
        with self.store.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    select
                        message_id,
                        session_id,
                        sequence_no,
                        role,
                        content_text,
                        content_json,
                        parent_message_id,
                        processing_state,
                        processing_started_at,
                        processing_ended_at,
                        error,
                        created_at
                    from session_messages
                    where session_id = %s and message_id = %s
                    """,
                    (str(session_id), str(message_id)),
                )
                return cur.fetchone()

    def update_processing_state(
        self,
        session_id: str | UUID,
        message_id: str | UUID,
        *,
        processing_state: str,
        processing_started_at: datetime | None = None,
        processing_ended_at: datetime | None = None,
        error: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        with self.store.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    update session_messages
                    set
                        processing_state = %s,
                        processing_started_at = coalesce(%s, processing_started_at),
                        processing_ended_at = coalesce(%s, processing_ended_at),
                        error = %s
                    where session_id = %s and message_id = %s
                    returning
                        message_id,
                        session_id,
                        sequence_no,
                        role,
                        content_text,
                        content_json,
                        parent_message_id,
                        processing_state,
                        processing_started_at,
                        processing_ended_at,
                        error,
                        created_at
                    """,
                    (
                        processing_state,
                        processing_started_at,
                        processing_ended_at,
                        Jsonb(error) if error is not None else None,
                        str(session_id),
                        str(message_id),
                    ),
                )
                row = cur.fetchone()
                conn.commit()
        return row

    def count_user_messages(self, session_id: str | UUID) -> int:
        """Return the number of user-role messages in a session."""
        with self.store.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "select count(*) as cnt from session_messages where session_id = %s and role = 'user'",
                    (str(session_id),),
                )
                row = cur.fetchone()
        return row["cnt"] if row else 0

    def update_message_content_and_state(
        self,
        session_id: str | UUID,
        message_id: str | UUID,
        *,
        content_text: str | None = None,
        content_json: dict[str, Any] | None = None,
        processing_state: str | None = None,
        processing_started_at: datetime | None = None,
        processing_ended_at: datetime | None = None,
        error: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        with self.store.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    update session_messages
                    set
                        content_text = coalesce(%s, content_text),
                        content_json = coalesce(%s, content_json),
                        processing_state = coalesce(%s, processing_state),
                        processing_started_at = coalesce(%s, processing_started_at),
                        processing_ended_at = coalesce(%s, processing_ended_at),
                        error = %s
                    where session_id = %s and message_id = %s
                    returning
                        message_id,
                        session_id,
                        sequence_no,
                        role,
                        content_text,
                        content_json,
                        parent_message_id,
                        processing_state,
                        processing_started_at,
                        processing_ended_at,
                        error,
                        created_at
                    """,
                    (
                        content_text,
                        Jsonb(content_json) if content_json is not None else None,
                        processing_state,
                        processing_started_at,
                        processing_ended_at,
                        Jsonb(error) if error is not None else None,
                        str(session_id),
                        str(message_id),
                    ),
                )
                row = cur.fetchone()
                conn.commit()
        return row
