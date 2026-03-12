"""Send sheet content to LLM and get back structured metadata."""

from __future__ import annotations

import json
import logging
import time
from typing import TYPE_CHECKING

import openai

from data_sources.auth import build_openai_client
from data_sources.models import ExtractedMetric, RawSheet, SheetExtraction

if TYPE_CHECKING:
    from data_sources.config import DataSourcesConfig

logger = logging.getLogger(__name__)

__all__ = ["extract_sheet_metadata"]

_MAX_RETRIES = 3
_RETRY_DELAY = 2.0
_RETRYABLE_OPENAI_ERRORS = tuple(
    exc
    for exc in (
        getattr(openai, "RateLimitError", None),
        getattr(openai, "APITimeoutError", None),
        getattr(openai, "APIConnectionError", None),
        getattr(openai, "InternalServerError", None),
    )
    if exc is not None
)

SYSTEM_PROMPT = """\
You are analyzing a sheet from a Canadian bank's supplementary financial report.
Given the raw content of one Excel sheet, extract the following as JSON:

1. "page_title": The main title/heading of this page (string or null).

2. "is_data_sheet": true if this contains financial data tables, false if it's a \
cover page, table of contents, glossary, notes, or sector definitions.

3. "summary": A thorough, detailed summary of everything on this page. Include:
   - What financial segment or business area this covers
   - Every major category and subcategory of data present
   - The types of metrics available (income statement, balance sheet, ratios, credit quality, etc.)
   - The time periods covered and granularity (quarterly, annual, etc.)
   - What specific questions a financial analyst might answer using this page
   - Any notable breakdowns (by geography, by product, by risk type, etc.)
   - Any footnotes, methodology notes, or definitional caveats
   Write 5-10 sentences. Be comprehensive — this summary is used for semantic search \
and must capture every angle someone might query this page from.

4. "keywords": An exhaustive list of keywords and phrases that someone might search \
for when looking for data on this page. Include ALL of the following:
   - Every metric name exactly as written on the page
   - Standard acronyms (ROE, NIM, PCL, CET1, RWA, AUM, AUA, FVOCI, FVTPL, OCI, etc.)
   - Full expanded names for all acronyms
   - Industry synonyms and alternative names (e.g. "charge-off" for "write-off", \
"NPL" for "impaired loans", "FICC" for fixed income/currencies/commodities)
   - Common analyst jargon (e.g. "top line" for revenue, "bottom line" for net income, \
"opex" for non-interest expense)
   - Regulatory framework terms (Basel III, Pillar 3, IFRS 9, IFRS 17, SA-CCR, IRB, etc.)
   - Segment and platform names
   - Geographic breakdowns mentioned
   - Product types mentioned
   - French equivalents for Canadian banking terms where applicable
   - Any footnote references or special notation
   There is NO limit — include as many as are relevant. All keywords should be lowercase.

5. "metrics": List of objects with keys: "metric_name", "platform", "sub_platform", \
"periods_available" for EVERY row of financial data on the page. Include:
   - Every single metric row, even subtotals, totals, and derived ratios
   - platform = the major section (e.g. "Personal Banking", "Consolidated", \
"Capital Markets", "Canada", "United States")
   - sub_platform = subsection (e.g. "Income Statement", "Credit Quality", \
"Average Balances", "Stage 1", "Stage 3")
   - periods_available = list every period column header exactly as shown
   There is NO limit on the number of metrics — extract every single one.

6. "requires_prior_context": true/false - does this sheet need previous sheets to \
understand its content? (e.g. continuation tables, references to prior definitions)

7. "context_note": If requires_prior_context is true, explain what context from \
previous sheets is needed (string or null).

Respond with ONLY valid JSON, no markdown fences or extra text.\
"""


def _normalize_keywords(raw_keywords: list[object]) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()
    for item in raw_keywords:
        if not isinstance(item, str):
            continue
        keyword = " ".join(item.lower().split())
        if not keyword or keyword in seen:
            continue
        seen.add(keyword)
        normalized.append(keyword)
    return normalized


def _fallback_is_data_sheet(sheet: RawSheet) -> bool:
    normalized_name = " ".join(sheet.sheet_name.lower().replace("_", " ").split())
    normalized_content = " ".join(sheet.raw_content.lower().split())[:1000]
    non_data_markers = (
        "cover page",
        "table of contents",
        "contents",
        "glossary",
        "variables",
        "definitions",
    )
    return not any(marker in normalized_name or marker in normalized_content for marker in non_data_markers)


def _build_user_message(
    sheet: RawSheet,
    prior_sheet_titles: list[str],
) -> str:
    """Build the user message with sheet content and context."""
    parts = [f"Sheet name: {sheet.sheet_name}"]
    if prior_sheet_titles:
        titles_str = ", ".join(prior_sheet_titles[-10:])  # Last 10 for context
        parts.append(f"Previous sheet titles: {titles_str}")
    parts.append("")
    parts.append("Sheet content:")
    parts.append(sheet.raw_content)
    return "\n".join(parts)


def _parse_extraction(raw_json: str) -> SheetExtraction:
    """Parse the LLM JSON response into a SheetExtraction."""
    data = json.loads(raw_json)

    metrics = []
    for m in data.get("metrics", []):
        metrics.append(
            ExtractedMetric(
                metric_name=m.get("metric_name", ""),
                platform=m.get("platform"),
                sub_platform=m.get("sub_platform"),
                periods_available=m.get("periods_available", []),
            )
        )

    return SheetExtraction(
        page_title=data.get("page_title"),
        is_data_sheet=data.get("is_data_sheet", True),
        summary=data.get("summary"),
        keywords=_normalize_keywords(data.get("keywords", [])),
        metrics=metrics,
        requires_prior_context=data.get("requires_prior_context", False),
        context_note=data.get("context_note"),
    )


def extract_sheet_metadata(
    sheet: RawSheet,
    *,
    config: DataSourcesConfig,
    model: str = "gpt-5-mini",
    max_tokens: int = 4096,
    prior_sheet_titles: list[str] | None = None,
) -> SheetExtraction:
    """Send a single sheet to the LLM and extract structured metadata."""
    client = build_openai_client(config)
    user_msg = _build_user_message(sheet, prior_sheet_titles or [])

    for attempt in range(1, _MAX_RETRIES + 1):
        try:
            response = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_msg},
                ],
                max_completion_tokens=max_tokens,
                response_format={"type": "json_object"},
            )
            content = response.choices[0].message.content or "{}"
            extraction = _parse_extraction(content)
            logger.info(
                "Extracted metadata for sheet %s: title=%s, metrics=%d, keywords=%d",
                sheet.sheet_name,
                extraction.page_title,
                len(extraction.metrics),
                len(extraction.keywords),
                extra={
                    "event": "sheet_extracted",
                    "sheet_name": sheet.sheet_name,
                    "is_data_sheet": extraction.is_data_sheet,
                },
            )
            return extraction

        except json.JSONDecodeError as exc:
            logger.warning(
                "JSON parse error on attempt %d for sheet %s: %s",
                attempt,
                sheet.sheet_name,
                exc,
            )
            if attempt == _MAX_RETRIES:
                # Return a minimal extraction rather than crashing
                logger.error("Failed to parse LLM response for sheet %s after %d attempts", sheet.sheet_name, _MAX_RETRIES)
                return SheetExtraction(
                    page_title=sheet.sheet_name,
                    is_data_sheet=_fallback_is_data_sheet(sheet),
                    summary=None,
                    keywords=[],
                    metrics=[],
                    requires_prior_context=False,
                    context_note=None,
                )

        except _RETRYABLE_OPENAI_ERRORS as exc:
            if attempt == _MAX_RETRIES:
                raise
            wait = _RETRY_DELAY * attempt
            logger.warning("LLM retry %d/%d after %.1fs: %s", attempt, _MAX_RETRIES, wait, exc)
            time.sleep(wait)

    # Should not reach here, but satisfy type checker
    raise RuntimeError("Exhausted retries for sheet extraction")
