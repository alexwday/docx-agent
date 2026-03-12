"""Postgres connection and migration helpers for V2 session storage."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import date, datetime
from decimal import Decimal
import json
import os
from pathlib import Path
from typing import Any, Iterator
from uuid import UUID

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import set_json_dumps


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


set_json_dumps(lambda obj: json.dumps(obj, default=_json_default))


class DatabaseConfigError(ValueError):
    """Raised when a required Postgres DSN is not configured."""


def _detect_postgres_dsn() -> str | None:
    """Auto-detect local Postgres by scanning for Unix socket files."""
    import glob
    import re
    socket_patterns = [
        "/tmp/.s.PGSQL.*",
        "/var/run/postgresql/.s.PGSQL.*",
        "/var/tmp/.s.PGSQL.*",
    ]
    ports: list[int] = []
    for pattern in socket_patterns:
        for path in glob.glob(pattern):
            if path.endswith(".lock"):
                continue
            m = re.search(r"\.s\.PGSQL\.(\d+)$", path)
            if m:
                ports.append(int(m.group(1)))
    if not ports:
        return None
    port = 5432 if 5432 in ports else min(ports)
    user = os.environ.get("USER") or os.environ.get("LOGNAME") or "postgres"
    if port == 5432:
        return f"postgresql://{user}@localhost/docx_agent"
    return f"postgresql://{user}@localhost:{port}/docx_agent"


def resolve_database_dsn(dsn: str | None = None) -> str:
    """Resolve DB DSN from explicit value, environment variables, or auto-detection."""
    candidate = dsn or os.environ.get("DOCX_AGENT_DATABASE_DSN") or os.environ.get("DATABASE_URL")
    if candidate and candidate.strip():
        return candidate.strip()
    detected = _detect_postgres_dsn()
    if detected:
        return detected
    raise DatabaseConfigError(
        "database DSN is required: pass dsn or set DOCX_AGENT_DATABASE_DSN/DATABASE_URL"
    )


class PostgresStore:
    """Lightweight SQL-first Postgres access helper."""

    def __init__(self, dsn: str | None = None) -> None:
        self.dsn = resolve_database_dsn(dsn)

    @contextmanager
    def connection(self) -> Iterator[psycopg.Connection[Any]]:
        conn = psycopg.connect(self.dsn, row_factory=dict_row)
        try:
            yield conn
        finally:
            conn.close()

    def run_script(self, sql_script: str) -> None:
        if not sql_script.strip():
            raise ValueError("sql_script must be a non-empty string")
        with self.connection() as conn:
            conn.autocommit = True
            with conn.cursor() as cur:
                cur.execute(sql_script)

    def run_script_file(self, file_path: str | Path) -> Path:
        path = Path(file_path).expanduser().resolve()
        sql_script = path.read_text(encoding="utf-8")
        self.run_script(sql_script)
        return path

