"""Postgres helpers for the data_sources schema."""

from __future__ import annotations

import logging
from pathlib import Path
import re
from typing import Any
from uuid import UUID

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from word_store.db import PostgresStore

logger = logging.getLogger(__name__)

SCHEMA_SQL_PATH = Path(__file__).parent / "sql" / "0001_data_sources_schema.sql"
_METRIC_NORMALIZE_RE = re.compile(r"[^a-z0-9]+")


def _normalize_metric_text(value: str) -> str:
    normalized = value.lower().strip().replace("&", " and ")
    for ch in "¹²³⁴⁵⁶⁷⁸⁹⁰()*":
        normalized = normalized.replace(ch, "")
    normalized = _METRIC_NORMALIZE_RE.sub(" ", normalized)
    return " ".join(normalized.split())


class DataSourcesDB:
    """Query helpers for the data_sources schema."""

    def __init__(self, store: PostgresStore) -> None:
        self.store = store

    # ── Schema management ──────────────────────────────────────────

    def ensure_schema(self) -> None:
        """Create the data_sources schema and tables if they don't exist."""
        sql = SCHEMA_SQL_PATH.read_text(encoding="utf-8")
        with self.store.connection() as conn:
            conn.autocommit = True
            with conn.cursor() as cur:
                cur.execute(sql)
        logger.info("data_sources schema ensured", extra={"event": "schema_ensured"})

    # ── Report documents ───────────────────────────────────────────

    def upsert_document(
        self,
        *,
        bank_code: str,
        report_type: str,
        period_code: str,
        fiscal_year: int,
        fiscal_quarter: int,
        source_filename: str,
        metadata: dict | None = None,
    ) -> dict[str, Any]:
        """Insert or update a report document, returning the row."""
        with self.store.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO data_sources.report_documents (
                        bank_code, report_type, period_code,
                        fiscal_year, fiscal_quarter, source_filename, metadata
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (bank_code, report_type, period_code) DO UPDATE SET
                        fiscal_year = EXCLUDED.fiscal_year,
                        fiscal_quarter = EXCLUDED.fiscal_quarter,
                        source_filename = EXCLUDED.source_filename,
                        metadata = EXCLUDED.metadata,
                        ingested_at = now()
                    RETURNING *
                    """,
                    (
                        bank_code,
                        report_type,
                        period_code,
                        fiscal_year,
                        fiscal_quarter,
                        source_filename,
                        Jsonb(metadata or {}),
                    ),
                )
                row = cur.fetchone()
                conn.commit()
        if row is None:
            raise RuntimeError("failed to upsert report document")
        return row

    # ── Report sheets ──────────────────────────────────────────────

    def delete_sheets_for_document(self, document_id: UUID) -> int:
        """Delete all sheets (and their metrics/keyword embeddings) for a document."""
        with self.store.connection() as conn:
            with conn.cursor() as cur:
                sub = "(SELECT sheet_id FROM data_sources.report_sheets WHERE document_id = %s)"
                doc_str = str(document_id)
                cur.execute(f"DELETE FROM data_sources.keyword_embeddings WHERE sheet_id IN {sub}", (doc_str,))
                cur.execute(f"DELETE FROM data_sources.sheet_metrics WHERE sheet_id IN {sub}", (doc_str,))
                cur.execute("DELETE FROM data_sources.report_sheets WHERE document_id = %s", (doc_str,))
                count = cur.rowcount
                conn.commit()
        return count

    def insert_sheet(
        self,
        *,
        document_id: UUID,
        sheet_index: int,
        sheet_name: str,
        page_title: str | None,
        raw_content: str,
        summary: str | None,
        keywords: list[str],
        summary_embedding: list[float] | None,
        context_sheet_ids: list[UUID] | None,
        context_note: str | None,
        is_data_sheet: bool,
        metadata: dict | None = None,
    ) -> dict[str, Any]:
        """Insert a single report sheet."""
        embedding_str = None
        if summary_embedding:
            embedding_str = "[" + ",".join(str(v) for v in summary_embedding) + "]"

        with self.store.connection() as conn:
            with conn.cursor() as cur:
                context_ids_str = None
                if context_sheet_ids:
                    context_ids_str = [str(sid) for sid in context_sheet_ids]

                cur.execute(
                    """
                    INSERT INTO data_sources.report_sheets (
                        document_id, sheet_index, sheet_name, page_title,
                        raw_content, summary, keywords, summary_embedding,
                        context_sheet_ids, context_note, is_data_sheet, metadata
                    ) VALUES (
                        %s, %s, %s, %s,
                        %s, %s, %s, %s::vector,
                        %s, %s, %s, %s
                    )
                    RETURNING *
                    """,
                    (
                        str(document_id),
                        sheet_index,
                        sheet_name,
                        page_title,
                        raw_content,
                        summary,
                        keywords,
                        embedding_str,
                        context_ids_str,
                        context_note,
                        is_data_sheet,
                        Jsonb(metadata or {}),
                    ),
                )
                row = cur.fetchone()
                conn.commit()
        if row is None:
            raise RuntimeError("failed to insert report sheet")
        return row

    # ── Sheet metrics ──────────────────────────────────────────────

    def insert_metrics(
        self,
        *,
        sheet_id: UUID,
        metrics: list[dict[str, Any]],
        embeddings: list[list[float]] | None = None,
    ) -> int:
        """Bulk insert metrics for a sheet with optional per-metric embeddings."""
        if not metrics:
            return 0
        with self.store.connection() as conn:
            with conn.cursor() as cur:
                count = 0
                for i, m in enumerate(metrics):
                    name = m.get("metric_name", "")
                    normalized = _normalize_metric_text(name)

                    emb_str = None
                    if embeddings and i < len(embeddings) and embeddings[i]:
                        emb_str = "[" + ",".join(str(v) for v in embeddings[i]) + "]"

                    cur.execute(
                        """
                        INSERT INTO data_sources.sheet_metrics (
                            sheet_id, metric_name, metric_name_normalized,
                            platform, sub_platform, periods_available,
                            embedding, metadata
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s::vector, %s)
                        """,
                        (
                            str(sheet_id),
                            name,
                            normalized,
                            m.get("platform"),
                            m.get("sub_platform"),
                            m.get("periods_available", []),
                            emb_str,
                            Jsonb(m.get("metadata", {})),
                        ),
                    )
                    count += 1
                conn.commit()
        return count

    def insert_keyword_embeddings(
        self,
        *,
        sheet_id: UUID,
        keywords: list[str],
        embeddings: list[list[float]],
    ) -> int:
        """Bulk insert per-keyword embeddings for a sheet."""
        if not keywords or not embeddings:
            return 0
        with self.store.connection() as conn:
            with conn.cursor() as cur:
                count = 0
                for kw, emb in zip(keywords, embeddings):
                    if not emb:
                        continue
                    emb_str = "[" + ",".join(str(v) for v in emb) + "]"
                    cur.execute(
                        """
                        INSERT INTO data_sources.keyword_embeddings (
                            sheet_id, keyword, embedding
                        ) VALUES (%s, %s, %s::vector)
                        """,
                        (str(sheet_id), kw, emb_str),
                    )
                    count += 1
                conn.commit()
        return count

    # ── Retrieval queries ──────────────────────────────────────────

    def search_by_keywords(
        self,
        *,
        keywords: list[str],
        bank_code: str | None = None,
        period_code: str | None = None,
        report_type: str | None = None,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        """Find sheets matching any of the given keywords."""
        if not keywords:
            return []
        lowered = [k.lower() for k in keywords]
        sql = """
            SELECT rs.*, rd.bank_code, rd.period_code, rd.report_type,
                   array(
                       SELECT unnest(rs.keywords) INTERSECT SELECT unnest(%s::text[])
                   ) AS matched_keywords
            FROM data_sources.report_sheets rs
            JOIN data_sources.report_documents rd ON rd.document_id = rs.document_id
            WHERE rs.keywords && %s::text[]
              AND rs.is_data_sheet = true
        """
        params: list[Any] = [lowered, lowered]
        if bank_code:
            sql += " AND rd.bank_code = %s"
            params.append(bank_code)
        if period_code:
            sql += " AND rd.period_code = %s"
            params.append(period_code)
        if report_type:
            sql += " AND rd.report_type = %s"
            params.append(report_type)
        sql += " ORDER BY cardinality(array(SELECT unnest(rs.keywords) INTERSECT SELECT unnest(%s::text[]))) DESC"
        params.append(lowered)
        sql += " LIMIT %s"
        params.append(limit)

        with self.store.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, params)
                return cur.fetchall()

    def search_by_metric_names(
        self,
        *,
        metric_names: list[str],
        bank_code: str | None = None,
        period_code: str | None = None,
        report_type: str | None = None,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        """Find sheets with metrics matching the given names (ILIKE)."""
        if not metric_names:
            return []
        normalized_terms: list[str] = []
        for name in metric_names:
            normalized = _normalize_metric_text(name)
            if normalized:
                normalized_terms.append(normalized)
        if not normalized_terms:
            return []

        conditions = []
        params: list[Any] = []
        for normalized in normalized_terms:
            conditions.append("sm.metric_name_normalized ILIKE %s")
            params.append(f"%{normalized}%")

        where_metrics = " OR ".join(conditions)
        sql = f"""
            WITH metric_matches AS (
                SELECT sm.sheet_id,
                       count(*) AS metric_hit_count,
                       array_agg(DISTINCT sm.metric_name) AS matched_metric_names
                FROM data_sources.sheet_metrics sm
                JOIN data_sources.report_sheets rs ON rs.sheet_id = sm.sheet_id
                JOIN data_sources.report_documents rd ON rd.document_id = rs.document_id
                WHERE ({where_metrics})
                  AND rs.is_data_sheet = true
        """
        if bank_code:
            sql += " AND rd.bank_code = %s"
            params.append(bank_code)
        if period_code:
            sql += " AND rd.period_code = %s"
            params.append(period_code)
        if report_type:
            sql += " AND rd.report_type = %s"
            params.append(report_type)
        sql += """
                GROUP BY sm.sheet_id
                ORDER BY metric_hit_count DESC
                LIMIT %s
            )
            SELECT rs.*, rd.bank_code, rd.period_code, rd.report_type,
                   mm.metric_hit_count, mm.matched_metric_names
            FROM metric_matches mm
            JOIN data_sources.report_sheets rs ON rs.sheet_id = mm.sheet_id
            JOIN data_sources.report_documents rd ON rd.document_id = rs.document_id
            ORDER BY mm.metric_hit_count DESC, rs.sheet_index ASC
        """
        params.append(limit)

        with self.store.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, params)
                return cur.fetchall()

    def list_sheet_catalog(
        self,
        *,
        bank_code: str | None = None,
        period_code: str | None = None,
        report_type: str | None = None,
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        """Fetch all candidate sheets plus aggregated metric metadata for ranking."""
        sql = """
            SELECT rs.*, rd.bank_code, rd.period_code, rd.report_type,
                   COALESCE(array_agg(DISTINCT sm.metric_name)
                       FILTER (WHERE sm.metric_name IS NOT NULL), '{}'::text[]) AS metric_names,
                   COALESCE(array_agg(DISTINCT sm.platform)
                       FILTER (WHERE sm.platform IS NOT NULL), '{}'::text[]) AS platforms,
                   COALESCE(array_agg(DISTINCT sm.sub_platform)
                       FILTER (WHERE sm.sub_platform IS NOT NULL), '{}'::text[]) AS sub_platforms
            FROM data_sources.report_sheets rs
            JOIN data_sources.report_documents rd ON rd.document_id = rs.document_id
            LEFT JOIN data_sources.sheet_metrics sm ON sm.sheet_id = rs.sheet_id
            WHERE rs.is_data_sheet = true
        """
        params: list[Any] = []
        if bank_code:
            sql += " AND rd.bank_code = %s"
            params.append(bank_code)
        if period_code:
            sql += " AND rd.period_code = %s"
            params.append(period_code)
        if report_type:
            sql += " AND rd.report_type = %s"
            params.append(report_type)
        sql += """
            GROUP BY rs.sheet_id, rd.document_id, rd.bank_code, rd.period_code, rd.report_type
            ORDER BY rs.sheet_index ASC
        """
        if limit is not None:
            sql += " LIMIT %s"
            params.append(limit)

        with self.store.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, params)
                return cur.fetchall()

    def search_by_embedding(
        self,
        *,
        embedding: list[float],
        bank_code: str | None = None,
        period_code: str | None = None,
        report_type: str | None = None,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        """Find sheets by cosine similarity to the given embedding."""
        embedding_str = "[" + ",".join(str(v) for v in embedding) + "]"
        sql = """
            SELECT rs.*, rd.bank_code, rd.period_code, rd.report_type,
                   1 - (rs.summary_embedding <=> %s::vector) AS cosine_similarity
            FROM data_sources.report_sheets rs
            JOIN data_sources.report_documents rd ON rd.document_id = rs.document_id
            WHERE rs.summary_embedding IS NOT NULL
              AND rs.is_data_sheet = true
        """
        params: list[Any] = [embedding_str]
        if bank_code:
            sql += " AND rd.bank_code = %s"
            params.append(bank_code)
        if period_code:
            sql += " AND rd.period_code = %s"
            params.append(period_code)
        if report_type:
            sql += " AND rd.report_type = %s"
            params.append(report_type)
        sql += " ORDER BY rs.summary_embedding <=> %s::vector ASC LIMIT %s"
        params.extend([embedding_str, limit])

        with self.store.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, params)
                return cur.fetchall()

    def search_by_keyword_embeddings(
        self,
        *,
        embedding: list[float],
        bank_code: str | None = None,
        period_code: str | None = None,
        report_type: str | None = None,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        """Find sheets via nearest individual keyword embeddings.

        Returns sheet rows with the best-matching keyword similarity per sheet.
        """
        embedding_str = "[" + ",".join(str(v) for v in embedding) + "]"
        sql = """
            SELECT DISTINCT ON (rs.sheet_id)
                   rs.*, rd.bank_code, rd.period_code, rd.report_type,
                   1 - (ke.embedding <=> %s::vector) AS cosine_similarity,
                   ke.keyword AS matched_keyword
            FROM data_sources.keyword_embeddings ke
            JOIN data_sources.report_sheets rs ON rs.sheet_id = ke.sheet_id
            JOIN data_sources.report_documents rd ON rd.document_id = rs.document_id
            WHERE ke.embedding IS NOT NULL
              AND rs.is_data_sheet = true
        """
        params: list[Any] = [embedding_str]
        if bank_code:
            sql += " AND rd.bank_code = %s"
            params.append(bank_code)
        if period_code:
            sql += " AND rd.period_code = %s"
            params.append(period_code)
        if report_type:
            sql += " AND rd.report_type = %s"
            params.append(report_type)
        sql += " ORDER BY rs.sheet_id, ke.embedding <=> %s::vector ASC"
        params.append(embedding_str)

        # Wrap to get top sheets by best keyword match
        wrapped = f"""
            SELECT * FROM ({sql}) sub
            ORDER BY cosine_similarity DESC
            LIMIT %s
        """
        params.append(limit)

        with self.store.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(wrapped, params)
                return cur.fetchall()

    def search_by_metric_embeddings(
        self,
        *,
        embedding: list[float],
        bank_code: str | None = None,
        period_code: str | None = None,
        report_type: str | None = None,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        """Find sheets via nearest individual metric name embeddings.

        Returns sheet rows with the best-matching metric similarity per sheet.
        """
        embedding_str = "[" + ",".join(str(v) for v in embedding) + "]"
        sql = """
            SELECT DISTINCT ON (rs.sheet_id)
                   rs.*, rd.bank_code, rd.period_code, rd.report_type,
                   1 - (sm.embedding <=> %s::vector) AS cosine_similarity,
                   sm.metric_name AS matched_metric
            FROM data_sources.sheet_metrics sm
            JOIN data_sources.report_sheets rs ON rs.sheet_id = sm.sheet_id
            JOIN data_sources.report_documents rd ON rd.document_id = rs.document_id
            WHERE sm.embedding IS NOT NULL
              AND rs.is_data_sheet = true
        """
        params: list[Any] = [embedding_str]
        if bank_code:
            sql += " AND rd.bank_code = %s"
            params.append(bank_code)
        if period_code:
            sql += " AND rd.period_code = %s"
            params.append(period_code)
        if report_type:
            sql += " AND rd.report_type = %s"
            params.append(report_type)
        sql += " ORDER BY rs.sheet_id, sm.embedding <=> %s::vector ASC"
        params.append(embedding_str)

        wrapped = f"""
            SELECT * FROM ({sql}) sub
            ORDER BY cosine_similarity DESC
            LIMIT %s
        """
        params.append(limit)

        with self.store.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(wrapped, params)
                return cur.fetchall()

    def get_sheets_by_ids(self, sheet_ids: list[UUID]) -> list[dict[str, Any]]:
        """Fetch full sheet rows by IDs."""
        if not sheet_ids:
            return []
        id_strs = [str(sid) for sid in sheet_ids]
        with self.store.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT rs.*, rd.bank_code, rd.period_code, rd.report_type
                    FROM data_sources.report_sheets rs
                    JOIN data_sources.report_documents rd ON rd.document_id = rs.document_id
                    WHERE rs.sheet_id = ANY(%s::uuid[])
                    ORDER BY rs.sheet_index
                    """,
                    (id_strs,),
                )
                return cur.fetchall()

    def get_neighbor_sheets(
        self,
        *,
        document_id: UUID,
        sheet_index: int,
        radius: int = 1,
    ) -> list[dict[str, Any]]:
        """Get sheets adjacent to a given sheet index within the same document."""
        with self.store.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT rs.*, rd.bank_code, rd.period_code, rd.report_type
                    FROM data_sources.report_sheets rs
                    JOIN data_sources.report_documents rd ON rd.document_id = rs.document_id
                    WHERE rs.document_id = %s
                      AND rs.sheet_index BETWEEN %s AND %s
                      AND rs.is_data_sheet = true
                    ORDER BY rs.sheet_index
                    """,
                    (str(document_id), sheet_index - radius, sheet_index + radius),
                )
                return cur.fetchall()
