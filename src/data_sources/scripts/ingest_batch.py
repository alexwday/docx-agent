"""Batch ingest all report files found under a structured data/raw/ tree.

Folder convention:
    <root>/<report_type>/<period_code>/<bank_code>/<filename>

    e.g. data/raw/supp_financials/Q1_2026/RBC/26q1supp.xlsx

File routing:
    .xlsx  → ingest_supplementary_report()
    .pdf   → ingest_pdf_report()

Usage:
    python -m data_sources.scripts.ingest_batch [--root data/raw] [--dry-run] [--ensure-schema]
"""

from __future__ import annotations

import argparse
import logging
import re
import time
from pathlib import Path
from typing import Any

from data_sources.config import DataSourcesConfig
from data_sources.db import DataSourcesDB
from data_sources.ingest.pipeline import ingest_pdf_report, ingest_supplementary_report
from word_store.db import PostgresStore

log = logging.getLogger(__name__)

_PERIOD_RE = re.compile(r"^Q(\d)_(\d{4})$", re.IGNORECASE)
_SUPPORTED_EXTENSIONS = {".xlsx", ".pdf"}


def _count_file_pages(path: Path, ext: str) -> int:
    """Return the number of sheets/pages in a file without fully parsing it."""
    if ext == ".xlsx":
        try:
            import openpyxl
            wb = openpyxl.load_workbook(str(path), read_only=True, data_only=True)
            count = len(wb.sheetnames)
            wb.close()
            return count
        except Exception:
            return -1
    elif ext == ".pdf":
        try:
            import fitz  # type: ignore[import]
            doc = fitz.open(str(path))
            count = len(doc)
            doc.close()
            return count
        except Exception:
            return -1
    return -1


def _parse_period(period_code: str) -> tuple[int, int]:
    """Convert 'Q1_2026' → (fiscal_year=2026, fiscal_quarter=1)."""
    match = _PERIOD_RE.match(period_code)
    if not match:
        raise ValueError(
            f"Cannot parse period_code {period_code!r}; expected format Q<N>_<YYYY>"
        )
    return int(match.group(2)), int(match.group(1))


def _discover_files(root: Path) -> list[dict[str, Any]]:
    """Walk root looking for files matching {report_type}/{period_code}/{bank_code}/*."""
    entries: list[dict[str, Any]] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        if path.suffix.lower() not in _SUPPORTED_EXTENSIONS:
            continue
        # Expect exactly 3 parent levels above root
        try:
            rel = path.relative_to(root)
        except ValueError:
            continue
        parts = rel.parts
        if len(parts) != 4:
            log.debug("Skipping %s — expected 3 directory levels below root, got %d", path, len(parts) - 1)
            continue
        report_type, period_code, bank_code, _ = parts
        try:
            fiscal_year, fiscal_quarter = _parse_period(period_code)
        except ValueError as exc:
            log.warning("Skipping %s — %s", path, exc)
            continue
        entries.append({
            "path": path,
            "report_type": report_type,
            "period_code": period_code,
            "bank_code": bank_code,
            "fiscal_year": fiscal_year,
            "fiscal_quarter": fiscal_quarter,
            "ext": path.suffix.lower(),
        })
    return entries


def run_batch(
    root: Path,
    *,
    dry_run: bool = False,
    ensure_schema: bool = False,
    skip_existing: bool = False,
) -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-8s %(name)s  %(message)s",
    )

    config = DataSourcesConfig.from_env()
    store = PostgresStore(dsn=config.database_dsn)
    db = DataSourcesDB(store)

    if ensure_schema:
        log.info("Ensuring schema…")
        db.ensure_schema()

    entries = _discover_files(root)
    if not entries:
        log.info("No files found under %s", root)
        return

    log.info("Discovered %d file(s) to ingest under %s", len(entries), root)

    results: list[dict[str, Any]] = []
    for entry in entries:
        path = entry["path"]
        label = f"{entry['report_type']}/{entry['period_code']}/{entry['bank_code']}/{path.name}"
        if dry_run:
            log.info("[DRY RUN] Would ingest: %s", label)
            results.append({"label": label, "status": "dry_run"})
            continue

        if skip_existing:
            db_count = db.document_sheet_count(entry["bank_code"], entry["report_type"], entry["period_code"])
            expected = _count_file_pages(path, entry["ext"])
            if db_count > 0 and (expected < 0 or db_count >= expected):
                log.info("Skipping (complete: %d/%d sheets): %s", db_count, expected, label)
                results.append({"label": label, "status": "skipped", "elapsed_s": 0})
                continue
            if db_count > 0 and db_count < expected:
                log.info("Re-ingesting (partial: %d/%d sheets in DB): %s", db_count, expected, label)

        log.info("Ingesting: %s", label)
        t0 = time.monotonic()
        try:
            common_kwargs: dict[str, Any] = dict(
                file_path=path,
                bank_code=entry["bank_code"],
                report_type=entry["report_type"],
                period_code=entry["period_code"],
                fiscal_year=entry["fiscal_year"],
                fiscal_quarter=entry["fiscal_quarter"],
                config=config,
                db=db,
            )
            if entry["ext"] == ".pdf":
                summary = ingest_pdf_report(**common_kwargs)
            else:
                summary = ingest_supplementary_report(**common_kwargs)
            elapsed = time.monotonic() - t0
            results.append({"label": label, "status": "ok", "elapsed_s": round(elapsed, 1), **summary})
            log.info(
                "  OK — %d sheets (%d data), %d metrics, %.1fs",
                summary.get("total_sheets", 0),
                summary.get("data_sheets", 0),
                summary.get("total_metrics", 0),
                elapsed,
            )
        except Exception as exc:
            elapsed = time.monotonic() - t0
            log.error("  FAILED — %s: %s", label, exc, exc_info=True)
            results.append({"label": label, "status": "error", "error": str(exc), "elapsed_s": round(elapsed, 1)})

    # ── Summary table ──────────────────────────────────────────────
    print()
    print(f"{'File':<55} {'Status':<10} {'Sheets':>6} {'Data':>6} {'Metrics':>8} {'Time':>6}")
    print("-" * 95)
    for r in results:
        status = r["status"]
        sheets = r.get("total_sheets", "-")
        data = r.get("data_sheets", "-")
        metrics = r.get("total_metrics", "-")
        elapsed_s = f"{r.get('elapsed_s', 0):.1f}s"
        label = r["label"]
        if len(label) > 54:
            label = "…" + label[-53:]
        print(f"{label:<55} {status:<10} {str(sheets):>6} {str(data):>6} {str(metrics):>8} {elapsed_s:>6}")
    print()
    ok = sum(1 for r in results if r["status"] == "ok")
    errors = sum(1 for r in results if r["status"] == "error")
    skipped = sum(1 for r in results if r["status"] == "skipped")
    log.info("Done: %d ok, %d errors, %d skipped, %d dry-run", ok, errors, skipped, len(results) - ok - errors - skipped)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Batch ingest all report files under data/raw/<type>/<period>/<bank>/."
    )
    parser.add_argument(
        "--root",
        default="data/raw",
        help="Root directory to walk (default: data/raw).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="List files that would be ingested without actually ingesting them.",
    )
    parser.add_argument(
        "--ensure-schema",
        action="store_true",
        help="Run schema migrations before ingesting.",
    )
    parser.add_argument(
        "--skip-existing",
        action="store_true",
        help="Skip files that already have sheets in the database.",
    )
    args = parser.parse_args()
    run_batch(Path(args.root), dry_run=args.dry_run, ensure_schema=args.ensure_schema, skip_existing=args.skip_existing)


if __name__ == "__main__":
    main()
