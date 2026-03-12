#!/usr/bin/env python3
"""Bootstrap the docx-agent Postgres database.

Auto-detects the local Postgres socket / port if no DSN is provided.
Creates the database (if needed), installs pgvector, and runs
the data_sources schema migration.

Usage:
    python scripts/setup_postgres.py                    # auto-detect everything
    python scripts/setup_postgres.py --dsn postgresql://user@localhost:5432/docx_agent
    python scripts/setup_postgres.py --skip-create-db  # if you lack superuser rights
    python scripts/setup_postgres.py --print-dsn       # just print detected DSN and exit

Environment (any of these override auto-detection):
    DOCX_AGENT_DATABASE_DSN
    DATABASE_URL
"""

from __future__ import annotations

import argparse
import glob
import logging
import os
import re
import sys
from pathlib import Path
from urllib.parse import urlparse

# Add src/ to path so we can import project modules without pip install
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s  %(message)s",
)
log = logging.getLogger(__name__)

_DB_NAME = "docx_agent"


# ── DSN detection ─────────────────────────────────────────────────────────────

def _detect_postgres_port() -> int | None:
    """Find the port of a running local Postgres by scanning for socket files."""
    socket_patterns = [
        "/tmp/.s.PGSQL.*",
        "/var/run/postgresql/.s.PGSQL.*",
        "/var/tmp/.s.PGSQL.*",
    ]
    ports: list[int] = []
    for pattern in socket_patterns:
        for path in glob.glob(pattern):
            # Socket files are named .s.PGSQL.<port> (lock files end in .lock)
            if path.endswith(".lock"):
                continue
            match = re.search(r"\.s\.PGSQL\.(\d+)$", path)
            if match:
                ports.append(int(match.group(1)))

    if not ports:
        return None
    # Prefer standard port 5432 if present; otherwise take the lowest found
    return 5432 if 5432 in ports else min(ports)


def _build_dsn(port: int | None = None) -> str:
    """Build a DSN for the local Postgres, using the current OS user."""
    user = os.environ.get("USER") or os.environ.get("LOGNAME") or "postgres"
    if port and port != 5432:
        return f"postgresql://{user}@localhost:{port}/{_DB_NAME}"
    return f"postgresql://{user}@localhost/{_DB_NAME}"


def resolve_dsn(override: str | None = None) -> str:
    """Return the DSN to use, in priority order:
    1. --dsn CLI argument
    2. DOCX_AGENT_DATABASE_DSN environment variable
    3. DATABASE_URL environment variable
    4. Auto-detected from local Postgres socket
    5. Default (localhost:5432)
    """
    if override:
        return override
    for var in ("DOCX_AGENT_DATABASE_DSN", "DATABASE_URL"):
        val = os.environ.get(var, "")
        if val:
            return val

    port = _detect_postgres_port()
    if port:
        log.info("Auto-detected Postgres on port %d", port)
    else:
        log.info("No Postgres socket found — assuming default port 5432")

    return _build_dsn(port)


# ── Database creation ──────────────────────────────────────────────────────────

def _create_database_if_missing(dsn: str) -> None:
    """Connect to the postgres maintenance DB and create docx_agent if absent."""
    try:
        import psycopg  # type: ignore[import]
    except ImportError as exc:
        log.error("psycopg not installed. Run: pip install 'psycopg[binary]'")
        raise SystemExit(1) from exc

    parsed = urlparse(dsn)
    db_name = (parsed.path or f"/{_DB_NAME}").lstrip("/")
    admin_dsn = dsn.replace(f"/{db_name}", "/postgres", 1)

    try:
        conn = psycopg.connect(admin_dsn, autocommit=True)
    except Exception as exc:
        log.warning(
            "Could not connect to admin DB (%s): %s\n"
            "  → Assuming '%s' already exists and continuing.",
            admin_dsn, exc, db_name,
        )
        return

    with conn:
        with conn.cursor() as cur:
            cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", (db_name,))
            exists = cur.fetchone() is not None
            if not exists:
                log.info("Creating database '%s'...", db_name)
                cur.execute(f'CREATE DATABASE "{db_name}"')
                log.info("Database '%s' created.", db_name)
            else:
                log.info("Database '%s' already exists.", db_name)
    conn.close()


# ── pgvector extension ────────────────────────────────────────────────────────

def _install_pgvector(dsn: str) -> None:
    """Install pgvector extension in the target database (idempotent)."""
    try:
        import psycopg  # type: ignore[import]
    except ImportError:
        raise SystemExit(1)

    try:
        conn = psycopg.connect(dsn, autocommit=True)
    except Exception as exc:
        log.error("Cannot connect to %s: %s", dsn, exc)
        raise SystemExit(1) from exc

    with conn:
        with conn.cursor() as cur:
            try:
                cur.execute("CREATE EXTENSION IF NOT EXISTS vector")
                log.info("pgvector extension ready.")
            except Exception as exc:
                log.warning(
                    "Could not install pgvector (%s).\n"
                    "  → If using a managed Postgres, pgvector may already be present\n"
                    "    or require DBA assistance.",
                    exc,
                )
    conn.close()


# ── Schema migration ──────────────────────────────────────────────────────────

def _run_schema(dsn: str) -> None:
    """Create all data_sources tables (idempotent)."""
    from data_sources.db import DataSourcesDB
    from word_store.db import PostgresStore

    log.info("Running data_sources schema migration...")
    store = PostgresStore(dsn=dsn)
    db = DataSourcesDB(store)
    db.ensure_schema()
    log.info("data_sources schema up to date.")


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Bootstrap the docx-agent Postgres database.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--dsn",
        help="PostgreSQL DSN. Auto-detected from local socket if omitted.",
    )
    parser.add_argument(
        "--skip-create-db",
        action="store_true",
        help="Skip CREATE DATABASE (use if you lack superuser rights).",
    )
    parser.add_argument(
        "--print-dsn",
        action="store_true",
        help="Print the resolved DSN and exit (useful for writing .env).",
    )
    args = parser.parse_args()

    dsn = resolve_dsn(args.dsn)

    if args.print_dsn:
        print(dsn)
        return

    log.info("Target DSN: %s", dsn)

    if not args.skip_create_db:
        _create_database_if_missing(dsn)

    _install_pgvector(dsn)
    _run_schema(dsn)

    log.info("Postgres setup complete.")
    # Print DSN so setup.sh can capture it for .env
    print(f"DSN={dsn}")


if __name__ == "__main__":
    main()
