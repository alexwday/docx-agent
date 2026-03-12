"""CLI: Ingest a supplementary financial report.

Usage:
    python -m data_sources.scripts.ingest_supp <file> --bank RBC --period Q1_2026
"""

from __future__ import annotations

import argparse
import logging
import sys

from data_sources.config import DataSourcesConfig
from data_sources.db import DataSourcesDB
from data_sources.ingest.pipeline import ingest_supplementary_report
from word_store.db import PostgresStore


def _parse_period(period_code: str) -> tuple[int, int]:
    """Parse 'Q1_2026' into (fiscal_year=2026, fiscal_quarter=1)."""
    parts = period_code.split("_")
    if len(parts) != 2 or not parts[0].startswith("Q"):
        raise ValueError(f"Invalid period_code format: {period_code!r}. Expected e.g. 'Q1_2026'")
    quarter = int(parts[0][1:])
    year = int(parts[1])
    if quarter < 1 or quarter > 4:
        raise ValueError(f"Quarter must be 1-4, got {quarter}")
    return year, quarter


def main() -> None:
    parser = argparse.ArgumentParser(description="Ingest a supplementary financial report.")
    parser.add_argument("file", help="Path to the Excel (.xlsx) file")
    parser.add_argument("--bank", required=True, help="Bank code (RBC, TD, BMO, BNS, CM, NA)")
    parser.add_argument("--period", required=True, help="Period code (e.g. Q1_2026)")
    parser.add_argument("--report-type", default="supp_financials", help="Report type (default: supp_financials)")
    parser.add_argument("--ensure-schema", action="store_true", help="Create schema/tables if they don't exist")
    parser.add_argument("-v", "--verbose", action="store_true", help="Enable debug logging")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)-8s %(name)s  %(message)s",
    )

    config = DataSourcesConfig.from_env()
    store = PostgresStore(dsn=config.database_dsn)
    db = DataSourcesDB(store)

    if args.ensure_schema:
        logging.info("Ensuring data_sources schema exists...")
        db.ensure_schema()

    fiscal_year, fiscal_quarter = _parse_period(args.period)

    result = ingest_supplementary_report(
        file_path=args.file,
        bank_code=args.bank.upper(),
        report_type=args.report_type,
        period_code=args.period,
        fiscal_year=fiscal_year,
        fiscal_quarter=fiscal_quarter,
        config=config,
        db=db,
    )

    print("\n=== Ingestion Complete ===")
    for k, v in result.items():
        print(f"  {k}: {v}")


if __name__ == "__main__":
    main()
