"""Repository helpers for per-message orchestration events."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any
from uuid import UUID

from psycopg.types.json import Jsonb

from .db import PostgresStore


class MessageEventsRepository:
    """SQL-first repository for `message_events` operations."""

    def __init__(self, store: PostgresStore) -> None:
        self.store = store

    def create_event(
        self,
        session_id: str | UUID,
        message_id: str | UUID,
        *,
        event_type: str,
        payload: dict[str, Any],
        event_index: int | None = None,
    ) -> dict[str, Any]:
        session_key = str(session_id)
        message_key = str(message_id)
        with self.store.connection() as conn:
            with conn.transaction():
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        select message_id
                        from session_messages
                        where session_id = %s and message_id = %s
                        for update
                        """,
                        (session_key, message_key),
                    )
                    if cur.fetchone() is None:
                        raise ValueError(
                            f"unknown session/message pair: session_id={session_key} message_id={message_key}"
                        )

                    index = event_index
                    if index is None:
                        cur.execute(
                            """
                            select coalesce(max(event_index), 0) + 1 as next_event_index
                            from message_events
                            where message_id = %s
                            """,
                            (message_key,),
                        )
                        index = cur.fetchone()["next_event_index"]

                    cur.execute(
                        """
                        insert into message_events (session_id, message_id, event_index, event_type, payload)
                        values (%s, %s, %s, %s, %s)
                        returning event_id, session_id, message_id, event_index, event_type, payload, created_at
                        """,
                        (
                            session_key,
                            message_key,
                            index,
                            event_type,
                            Jsonb(payload),
                        ),
                    )
                    row = cur.fetchone()
        if row is None:
            raise RuntimeError("failed to create message event")
        return row

    def list_events(self, session_id: str | UUID, message_id: str | UUID) -> list[dict[str, Any]]:
        with self.store.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    select event_id, session_id, message_id, event_index, event_type, payload, created_at
                    from message_events
                    where session_id = %s and message_id = %s
                    order by event_index asc
                    """,
                    (str(session_id), str(message_id)),
                )
                rows = cur.fetchall()
        return rows

    def list_recent_events(
        self,
        session_id: str | UUID,
        *,
        limit: int = 200,
        exclude_message_id: str | UUID | None = None,
        event_types: Sequence[str] | None = None,
    ) -> list[dict[str, Any]]:
        sql = """
            select event_id, session_id, message_id, event_index, event_type, payload, created_at
            from message_events
            where session_id = %s
        """
        params: list[Any] = [str(session_id)]
        if exclude_message_id is not None:
            sql += " and message_id <> %s"
            params.append(str(exclude_message_id))
        if event_types:
            sql += " and event_type = any(%s)"
            params.append(list(event_types))
        sql += " order by created_at desc, event_index desc limit %s"
        params.append(limit)
        with self.store.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, params)
                rows = cur.fetchall()
        return rows
