"""Dataclass models for supplementary financial data sources."""

from __future__ import annotations

from dataclasses import dataclass, field
from uuid import UUID


@dataclass(slots=True)
class ReportDocument:
    """A single ingested report file."""

    document_id: UUID
    bank_code: str
    report_type: str
    period_code: str
    fiscal_year: int
    fiscal_quarter: int
    source_filename: str
    metadata: dict = field(default_factory=dict)


@dataclass(slots=True)
class RawSheet:
    """A sheet read from Excel before LLM extraction."""

    sheet_index: int
    sheet_name: str
    raw_content: str


@dataclass(slots=True)
class ExtractedMetric:
    """A single metric extracted by the LLM from a sheet."""

    metric_name: str
    platform: str | None = None
    sub_platform: str | None = None
    periods_available: list[str] = field(default_factory=list)


@dataclass(slots=True)
class SheetExtraction:
    """LLM extraction result for one sheet."""

    page_title: str | None
    is_data_sheet: bool
    summary: str | None
    keywords: list[str]
    metrics: list[ExtractedMetric]
    requires_prior_context: bool
    context_note: str | None


@dataclass(slots=True)
class ReportSheet:
    """A sheet with raw content and LLM-extracted metadata, ready for storage."""

    sheet_index: int
    sheet_name: str
    raw_content: str
    page_title: str | None
    is_data_sheet: bool
    summary: str | None
    keywords: list[str]
    metrics: list[ExtractedMetric]
    summary_embedding: list[float] | None = None
    context_sheet_ids: list[UUID] = field(default_factory=list)
    context_note: str | None = None
    metadata: dict = field(default_factory=dict)


@dataclass(slots=True)
class RetrievedSheet:
    """A sheet returned by the retrieval pipeline."""

    sheet_id: UUID
    document_id: UUID
    sheet_index: int
    sheet_name: str
    page_title: str | None
    raw_content: str
    summary: str | None
    bank_code: str
    period_code: str
    score: float
    report_type: str = ""
    match_sources: list[str] = field(default_factory=list)
    matched_terms: list[str] = field(default_factory=list)
    score_breakdown: dict[str, float] = field(default_factory=dict)
