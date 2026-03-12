"""Repository helpers for global data source catalog queries."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from psycopg.types.json import Jsonb

from .db import PostgresStore


class DataSourcesRepository:
    """SQL-first repository for `data_source_catalog` operations."""

    def __init__(self, store: PostgresStore) -> None:
        self.store = store

    def upsert_source(
        self,
        *,
        source_id: str,
        name: str,
        source_type: str,
        location: dict[str, Any] | None = None,
        schema_json: dict[str, Any] | None = None,
        enabled: bool = True,
    ) -> dict[str, Any]:
        location_payload = location or {}
        schema_payload = schema_json or {}
        with self.store.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    insert into data_source_catalog (
                        source_id,
                        name,
                        source_type,
                        location,
                        schema_json,
                        enabled
                    ) values (%s, %s, %s, %s, %s, %s)
                    on conflict (source_id) do update
                    set
                        name = excluded.name,
                        source_type = excluded.source_type,
                        location = excluded.location,
                        schema_json = excluded.schema_json,
                        enabled = excluded.enabled,
                        updated_at = now()
                    returning source_id, name, source_type, location, schema_json, enabled, updated_at
                    """,
                    (
                        source_id,
                        name,
                        source_type,
                        Jsonb(location_payload),
                        Jsonb(schema_payload),
                        enabled,
                    ),
                )
                row = cur.fetchone()
                conn.commit()
        if row is None:
            raise RuntimeError("failed to upsert data source")
        return row

    def list_sources(
        self,
        *,
        enabled_only: bool = True,
        source_type: str | None = None,
        source_ids: Sequence[str] | None = None,
    ) -> list[dict[str, Any]]:
        sql = """
            select source_id, name, source_type, location, schema_json, enabled, updated_at
            from data_source_catalog
            where 1 = 1
        """
        params: list[Any] = []
        if enabled_only:
            sql += " and enabled = true"
        if source_type is not None:
            sql += " and source_type = %s"
            params.append(source_type)
        if source_ids:
            sql += " and source_id = any(%s)"
            params.append(list(source_ids))
        sql += " order by source_id asc"
        with self.store.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, params)
                rows = cur.fetchall()
        return rows

