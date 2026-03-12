from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("psycopg")

from word_store.db import DatabaseConfigError, resolve_database_dsn
from word_store.migrate import DEFAULT_SQL_PATH, build_parser


def test_resolve_database_dsn_prefers_explicit(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("DOCX_AGENT_DATABASE_DSN", "postgres://from-env")
    value = resolve_database_dsn("postgres://from-arg")
    assert value == "postgres://from-arg"


def test_resolve_database_dsn_uses_env(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("DOCX_AGENT_DATABASE_DSN", raising=False)
    monkeypatch.setenv("DATABASE_URL", "postgres://from-database-url")
    value = resolve_database_dsn()
    assert value == "postgres://from-database-url"


def test_resolve_database_dsn_raises_without_value(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("DOCX_AGENT_DATABASE_DSN", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    with pytest.raises(DatabaseConfigError):
        resolve_database_dsn()


def test_build_parser_default_sql_path_exists():
    parser = build_parser()
    args = parser.parse_args([])
    assert Path(args.sql_path).resolve() == DEFAULT_SQL_PATH
    assert DEFAULT_SQL_PATH.exists()

