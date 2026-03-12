"""CLI utility to apply Postgres schema migration scripts."""

from __future__ import annotations

import argparse
from pathlib import Path

from .db import PostgresStore


DEFAULT_SQL_PATH = (
    Path(__file__).resolve().parents[2] / "docs" / "BIG_UPGRADE_PLAN" / "sql" / "0001_schema_v1.sql"
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Apply docx-agent Postgres schema migration SQL.")
    parser.add_argument(
        "--dsn",
        default=None,
        help="Postgres DSN. If omitted, DOCX_AGENT_DATABASE_DSN or DATABASE_URL is used.",
    )
    parser.add_argument(
        "--sql-path",
        default=str(DEFAULT_SQL_PATH),
        help="Path to SQL migration file.",
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()
    store = PostgresStore(dsn=args.dsn)
    applied_path = store.run_script_file(args.sql_path)
    print(f"Applied migration: {applied_path}")  # noqa: T201


if __name__ == "__main__":
    main()

