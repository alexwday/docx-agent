"""Orchestrate ingestion: read Excel → extract metadata → embed → store."""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict
from pathlib import Path
from typing import Any
from uuid import UUID

from data_sources.config import DataSourcesConfig
from data_sources.db import DataSourcesDB
from data_sources.embeddings import embed_texts
from data_sources.ingest.excel_reader import read_excel_sheets
from data_sources.ingest.llm_extractor import extract_sheet_metadata
from data_sources.models import RawSheet, ReportSheet

logger = logging.getLogger(__name__)

__all__ = ["ingest_supplementary_report", "ingest_pdf_report"]
_MAX_CONTEXT_CHAIN_DEPTH = 3


def _summary_embedding_text(sheet: ReportSheet) -> str:
    parts = [sheet.page_title or sheet.sheet_name]
    if sheet.summary:
        parts.append(sheet.summary)
    if sheet.context_note:
        parts.append(f"context: {sheet.context_note}")
    return "\n".join(part for part in parts if part).strip()


def _keyword_embedding_text(sheet: ReportSheet, keyword: str) -> str:
    parts = [sheet.page_title or sheet.sheet_name, f"keyword: {keyword}"]
    if sheet.context_note:
        parts.append(f"context: {sheet.context_note}")
    return " | ".join(part for part in parts if part)


def _metric_embedding_text(sheet: ReportSheet, metric) -> str:  # noqa: ANN001
    parts = [sheet.page_title or sheet.sheet_name, f"metric: {metric.metric_name}"]
    if metric.platform:
        parts.append(f"platform: {metric.platform}")
    if metric.sub_platform:
        parts.append(f"sub-platform: {metric.sub_platform}")
    if metric.periods_available:
        parts.append("periods: " + ", ".join(metric.periods_available))
    return " | ".join(part for part in parts if part)


def ingest_supplementary_report(
    *,
    file_path: str | Path,
    bank_code: str,
    report_type: str,
    period_code: str,
    fiscal_year: int,
    fiscal_quarter: int,
    config: DataSourcesConfig,
    db: DataSourcesDB,
    reader: Callable[[Path], list[RawSheet]] | None = None,
) -> dict[str, Any]:
    """Full ingestion pipeline for a supplementary financial report.

    Steps:
    1. Read Excel sheets into raw text
    2. LLM-extract metadata for each sheet
    3. Embed summaries
    4. Store everything in Postgres

    Returns a summary dict with counts and timing.
    """
    t_start = time.monotonic()
    path = Path(file_path)

    # ── Step 1: Read file ──────────────────────────────────────────
    reader_fn = reader or read_excel_sheets
    reader_name = getattr(reader_fn, "__name__", None) or getattr(reader_fn, "func", reader_fn).__name__
    logger.info("Step 1/4: Reading file %s (reader: %s)", path.name, reader_name)
    raw_sheets = reader_fn(path)
    logger.info("Read %d sheets", len(raw_sheets))

    # ── Step 2: LLM extraction ─────────────────────────────────────
    logger.info("Step 2/4: Extracting metadata via LLM (%s)", config.extraction_model)
    report_sheets: list[ReportSheet] = []
    prior_titles: list[str] = []

    for raw in raw_sheets:
        extraction = extract_sheet_metadata(
            raw,
            config=config,
            model=config.extraction_model,
            max_tokens=config.extraction_max_tokens,
            prior_sheet_titles=prior_titles,
        )
        report_sheets.append(
            ReportSheet(
                sheet_index=raw.sheet_index,
                sheet_name=raw.sheet_name,
                raw_content=raw.raw_content,
                page_title=extraction.page_title,
                is_data_sheet=extraction.is_data_sheet,
                summary=extraction.summary,
                keywords=extraction.keywords,
                metrics=extraction.metrics,
                context_note=extraction.context_note if extraction.requires_prior_context else None,
                metadata={
                    "requires_prior_context": extraction.requires_prior_context,
                },
            )
        )
        if extraction.page_title:
            prior_titles.append(extraction.page_title)
        else:
            prior_titles.append(raw.sheet_name)

    # ── Step 3: Embed summaries + individual keywords + individual metrics ──
    logger.info("Step 3/4: Embedding summaries, keywords, and metrics")

    # 3a: Summaries — one per sheet
    summaries = [_summary_embedding_text(s) for s in report_sheets]

    # 3b: All individual keywords across all sheets, embedded with page context
    #     so common terms like "total" or "other" do not collapse to a single
    #     corpus-wide vector regardless of page.
    all_keyword_texts: list[str] = []
    keyword_text_map: list[tuple[int, int]] = []  # (sheet_idx_in_report_sheets, keyword_idx)
    for si, s in enumerate(report_sheets):
        for ki, keyword in enumerate(s.keywords):
            all_keyword_texts.append(_keyword_embedding_text(s, keyword))
            keyword_text_map.append((si, ki))
    unique_keyword_texts = list(dict.fromkeys(all_keyword_texts))  # preserve order, dedupe

    # 3c: All individual metric description strings
    all_metric_texts: list[str] = []
    metric_text_map: list[tuple[int, int]] = []  # (sheet_idx_in_report_sheets, metric_idx)
    for si, s in enumerate(report_sheets):
        for mi, m in enumerate(s.metrics):
            text = _metric_embedding_text(s, m)
            all_metric_texts.append(text)
            metric_text_map.append((si, mi))

    logger.info(
        "Embedding: %d summaries, %d contextualized keywords, %d metrics",
        len(summaries), len(unique_keyword_texts), len(all_metric_texts),
    )

    # Fire all three in parallel
    with ThreadPoolExecutor(max_workers=3) as pool:
        fut_sum = pool.submit(
            embed_texts, summaries,
            config=config,
            model=config.embedding_model,
            dimensions=config.embedding_dimensions,
        )
        fut_kw = pool.submit(
            embed_texts, unique_keyword_texts,
            config=config,
            model=config.embedding_model,
            dimensions=config.embedding_dimensions,
        )
        fut_met = pool.submit(
            embed_texts, all_metric_texts,
            config=config,
            model=config.embedding_model,
            dimensions=config.embedding_dimensions,
        )
        summary_embeddings = fut_sum.result()
        kw_embeddings_flat = fut_kw.result()
        metric_embeddings_flat = fut_met.result()

    # Map summary embeddings back to sheets
    for sheet, emb in zip(report_sheets, summary_embeddings):
        if emb and _summary_embedding_text(sheet):
            sheet.summary_embedding = emb

    # Build keyword-text→embedding lookup
    kw_embedding_lookup: dict[str, list[float]] = {}
    for keyword_text, emb in zip(unique_keyword_texts, kw_embeddings_flat):
        if emb:
            kw_embedding_lookup[keyword_text] = emb

    # Build per-sheet keyword embeddings lists
    per_sheet_keyword_embeddings: dict[int, list[list[float]]] = {}
    for (si, ki), keyword_text in zip(keyword_text_map, all_keyword_texts):
        if si not in per_sheet_keyword_embeddings:
            per_sheet_keyword_embeddings[si] = [[] for _ in report_sheets[si].keywords]
        per_sheet_keyword_embeddings[si][ki] = kw_embedding_lookup.get(keyword_text, [])

    # Build per-sheet metric embeddings lists
    per_sheet_metric_embeddings: dict[int, list[list[float]]] = {}
    for (si, mi), emb in zip(metric_text_map, metric_embeddings_flat):
        if si not in per_sheet_metric_embeddings:
            per_sheet_metric_embeddings[si] = [[] for _ in report_sheets[si].metrics]
        per_sheet_metric_embeddings[si][mi] = emb

    # ── Step 4: Store in Postgres ──────────────────────────────────
    logger.info("Step 4/4: Storing in Postgres")

    # Upsert document (re-ingestion replaces old data)
    doc_row = db.upsert_document(
        bank_code=bank_code,
        report_type=report_type,
        period_code=period_code,
        fiscal_year=fiscal_year,
        fiscal_quarter=fiscal_quarter,
        source_filename=path.name,
    )
    document_id = doc_row["document_id"]

    # Clear old sheets for this document (idempotent re-ingestion)
    deleted = db.delete_sheets_for_document(document_id)
    if deleted:
        logger.info("Cleared %d old sheets for document %s", deleted, document_id)

    # Insert sheets and collect IDs for context resolution
    sheet_id_map: dict[int, UUID] = {}  # sheet_index → sheet_id
    total_metrics = 0

    for si, sheet in enumerate(report_sheets):
        row = db.insert_sheet(
            document_id=document_id,
            sheet_index=sheet.sheet_index,
            sheet_name=sheet.sheet_name,
            page_title=sheet.page_title,
            raw_content=sheet.raw_content,
            summary=sheet.summary,
            keywords=sheet.keywords,
            summary_embedding=sheet.summary_embedding,
            context_sheet_ids=None,  # Resolved in second pass
            context_note=sheet.context_note,
            is_data_sheet=sheet.is_data_sheet,
            metadata=sheet.metadata,
        )
        sheet_id = row["sheet_id"]
        sheet_id_map[sheet.sheet_index] = sheet_id

        # Insert metrics with per-metric embeddings
        if sheet.metrics:
            metric_dicts = [asdict(m) for m in sheet.metrics]
            m_embs = per_sheet_metric_embeddings.get(si)
            count = db.insert_metrics(
                sheet_id=sheet_id,
                metrics=metric_dicts,
                embeddings=m_embs,
            )
            total_metrics += count

        # Insert per-keyword embeddings
        if sheet.keywords:
            kw_embs = per_sheet_keyword_embeddings.get(si, [[] for _ in sheet.keywords])
            db.insert_keyword_embeddings(
                sheet_id=sheet_id,
                keywords=sheet.keywords,
                embeddings=kw_embs,
            )

    # Second pass: resolve context_sheet_ids for sheets that need prior context
    _resolve_context_chains(report_sheets, sheet_id_map, db)

    elapsed = time.monotonic() - t_start
    data_sheets = sum(1 for s in report_sheets if s.is_data_sheet)

    result = {
        "document_id": str(document_id),
        "bank_code": bank_code,
        "period_code": period_code,
        "total_sheets": len(report_sheets),
        "data_sheets": data_sheets,
        "total_metrics": total_metrics,
        "elapsed_seconds": round(elapsed, 1),
    }
    logger.info(
        "Ingestion complete: %d sheets (%d data), %d metrics in %.1fs",
        len(report_sheets),
        data_sheets,
        total_metrics,
        elapsed,
        extra={"event": "ingestion_complete", **result},
    )
    return result


def _resolve_context_chains(
    sheets: list[ReportSheet],
    sheet_id_map: dict[int, UUID],
    db: DataSourcesDB,
) -> None:
    """For sheets that need prior context, set their context_sheet_ids."""
    sheets_by_index = {sheet.sheet_index: sheet for sheet in sheets}
    for sheet in sheets:
        if not sheet.metadata.get("requires_prior_context"):
            continue
        if sheet.sheet_index <= 0:
            continue

        context_indices: list[int] = []
        prior_index = sheet.sheet_index - 1
        while prior_index in sheet_id_map and len(context_indices) < _MAX_CONTEXT_CHAIN_DEPTH:
            context_indices.append(prior_index)
            prior_sheet = sheets_by_index.get(prior_index)
            if prior_sheet is None or not prior_sheet.metadata.get("requires_prior_context"):
                break
            prior_index -= 1

        if not context_indices:
            continue

        context_ids = [sheet_id_map[idx] for idx in reversed(context_indices)]
        current_id = sheet_id_map.get(sheet.sheet_index)
        if current_id:
            # Update the row in DB
            with db.store.connection() as conn:
                with conn.cursor() as cur:
                    id_strs = [str(cid) for cid in context_ids]
                    cur.execute(
                        """
                        UPDATE data_sources.report_sheets
                        SET context_sheet_ids = %s::uuid[]
                        WHERE sheet_id = %s
                        """,
                        (id_strs, str(current_id)),
                    )
                    conn.commit()


def ingest_pdf_report(
    *,
    file_path: str | Path,
    bank_code: str,
    report_type: str,
    period_code: str,
    fiscal_year: int,
    fiscal_quarter: int,
    config: DataSourcesConfig,
    db: DataSourcesDB,
) -> dict[str, Any]:
    """Full ingestion pipeline for a PDF report.

    Each page is processed by a vision model (PyMuPDF renders to PNG; OpenAI
    vision extracts OCR text, markdown tables, and chart descriptions).  The
    resulting rich ``RawSheet`` objects flow through the same LLM extraction,
    embedding, and storage steps as Excel sheets.

    Requires: pip install pymupdf
    """
    from functools import partial

    from data_sources.ingest.pdf_vision_reader import read_pdf_sheets_with_vision

    reader_fn = partial(
        read_pdf_sheets_with_vision,
        config=config,
        model=config.vision_model,
        max_tokens=config.vision_max_tokens,
        max_workers=config.vision_max_workers,
        dpi_scale=config.vision_dpi_scale,
    )

    return ingest_supplementary_report(
        file_path=file_path,
        bank_code=bank_code,
        report_type=report_type,
        period_code=period_code,
        fiscal_year=fiscal_year,
        fiscal_quarter=fiscal_quarter,
        config=config,
        db=db,
        reader=reader_fn,
    )
