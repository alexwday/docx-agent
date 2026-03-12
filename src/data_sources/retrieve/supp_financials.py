"""Hybrid retriever for supplementary financial report data."""

from __future__ import annotations

import json
import logging
import math
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from typing import Any

from data_sources.auth import build_openai_client
from data_sources.config import DataSourcesConfig
from data_sources.db import DataSourcesDB
from data_sources.embeddings import embed_texts
from data_sources.retrieve.reranker import rerank_and_expand

logger = logging.getLogger(__name__)

__all__ = ["SuppFinancialsRetriever"]

_METRIC_EXTRACTION_PROMPT = """\
You are helping retrieve pages from a Canadian bank's supplementary financial report.
Extract the concrete financial line items, ratios, and reporting labels that are most
useful for locating the answer.

Return JSON with one key:
{
  "metric_names": ["..."]
}

Rules:
- Include exact source-style labels when likely (for example "provision for credit losses",
  "contractual service margin", "risk-weighted assets", "insurance service result").
- Include common analyst abbreviations and expansions when both matter (for example
  "CET1 ratio" and "Common Equity Tier 1 ratio").
- Prefer precise retrieval targets over vague business concepts.
- Return at most 12 strings.
"""

_HYDE_EXPANSION_PROMPT = """\
You are helping retrieve pages from a Canadian bank's quarterly supplementary financial
information package.

Given a user's research question, return JSON with:
1. "alternatives": 4 alternative phrasings that use likely source-language, analyst
   jargon, and regulatory terminology.
2. "hypothetical_summary": a 4-6 sentence description of the ideal report page that
   would answer the question, written in the register of a data catalog entry.

Rules:
- Mention likely page content, table structure, line items, and period columns.
- Use Canadian bank / IFRS / regulatory terminology when appropriate.
- Do not fabricate a numeric answer.
"""

_TOKEN_RE = re.compile(r"[a-z0-9%]+")
_SHORT_KEEP_TOKENS = {
    "fx", "pd", "lgd", "ead", "nim", "roe", "rwa", "cet1", "csm",
    "ficc", "pcl", "npl", "gil", "nil", "otc", "irb", "aum", "aua",
}
_STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "between", "break", "breakdown",
    "compare", "comparison", "did", "does", "drive", "drove", "for", "from",
    "how", "in", "into", "is", "it", "its", "last", "latest", "of", "on",
    "out", "quarter", "show", "the", "this", "through", "to", "vs", "versus",
    "was", "what", "which", "who", "why", "with", "year", "rbc",
}
_LOW_SIGNAL_TERMS = {
    "amount", "banking", "book", "breakdown", "calculated", "change", "compare",
    "comparison", "data", "latest", "page", "portfolio", "quarter", "ratio",
    "report", "spend", "total", "year",
}
_DOMAIN_SYNONYMS: dict[str, tuple[str, ...]] = {
    "fx": ("foreign exchange", "foreign exchange contracts", "forward contracts"),
    "fx forward": ("foreign exchange contracts", "forward contracts"),
    "ficc": ("interest rate and credit", "foreign exchange and commodities", "trading revenue"),
    "pppt": ("pre provision pre tax", "total revenue", "non interest expense"),
    "pre provision pre tax": ("pppt",),
    "underwriting": ("insurance service result", "premiums"),
    "underwriting profit": ("insurance service result",),
    "policies": ("insurance", "premiums"),
    "csm": ("contractual service margin",),
    "fvoci": ("fair value through other comprehensive income", "other comprehensive income"),
    "cet1": (
        "common tier 1", "common equity tier 1", "regulatory capital",
        "flow statement of the movements in regulatory capital",
    ),
    "rwa": ("risk weighted assets",),
    "npl": ("non performing loans", "gross impaired loans", "gil as a % of related loans"),
    "pcl": ("provision for credit losses",),
    "roe": ("return on common equity", "return on equity"),
    "rorc": ("return on risk capital",),
    "p and c": ("personal and commercial banking", "canadian banking"),
    "fee income": ("non interest income",),
    "counterparty exposure": ("credit equivalent amount", "replacement cost"),
    "mark to market": ("fair value", "unrealized gains", "unrealized losses"),
    "back testing": ("actual losses vs estimated losses", "basel pillar 3 back testing", "pd", "ead", "lgd"),
    "model validation": ("actual losses vs estimated losses", "back testing"),
    "buybacks": ("share repurchases", "common share repurchases"),
    "employee compensation": ("human resources", "salaries", "variable compensation", "benefits"),
    "earning asset base": ("interest earning assets", "selected average balance sheet items", "total loans", "securities"),
    "cds": ("credit default swaps", "credit derivatives"),
    "swap portfolio": ("swaps", "interest rate contracts"),
    "derivative book": ("derivatives", "fair value of derivative instruments"),
}
_MAX_LEXICAL_PHRASES = 36
_MAX_SEMANTIC_QUERIES = 12


@dataclass(slots=True)
class QueryPlan:
    lexical_phrases: list[str]
    metric_search_terms: list[str]
    semantic_queries: list[str]


def _dedupe_preserve_order(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        cleaned = " ".join(str(value).split())
        if not cleaned or cleaned in seen:
            continue
        seen.add(cleaned)
        result.append(cleaned)
    return result


def _normalize_text(text: str) -> str:
    normalized = text.lower().replace("&", " and ")
    normalized = re.sub(r"[^a-z0-9%]+", " ", normalized)
    return " ".join(normalized.split())


def _tokenize(text: str) -> list[str]:
    tokens = _TOKEN_RE.findall(_normalize_text(text))
    result: list[str] = []
    for token in tokens:
        if token.isdigit():
            continue
        if len(token) > 2 or token in _SHORT_KEEP_TOKENS:
            result.append(token)
    return result


def _extract_ngrams(tokens: list[str], *, max_n: int = 3) -> list[str]:
    phrases: list[str] = []
    for n in range(2, max_n + 1):
        for idx in range(0, len(tokens) - n + 1):
            phrase_tokens = tokens[idx : idx + n]
            if all(token in _STOPWORDS for token in phrase_tokens):
                continue
            phrases.append(" ".join(phrase_tokens))
    return phrases


def _expand_domain_aliases(query_text: str, phrases: list[str]) -> list[str]:
    normalized_query = _normalize_text(query_text)
    observed = {_normalize_text(phrase) for phrase in phrases}
    expansions: list[str] = []
    for key, values in _DOMAIN_SYNONYMS.items():
        normalized_key = _normalize_text(key)
        if normalized_key and (normalized_key in normalized_query or normalized_key in observed):
            expansions.extend(values)
    return _dedupe_preserve_order([_normalize_text(item) for item in expansions])


def _short_query_label(text: str) -> str | None:
    normalized = _normalize_text(text)
    if not normalized or len(normalized.split()) > 6:
        return None
    return normalized


def _is_high_signal_phrase(phrase: str) -> bool:
    normalized = _normalize_text(phrase)
    if not normalized:
        return False
    tokens = normalized.split()
    if len(tokens) == 1:
        token = tokens[0]
        return token in _SHORT_KEEP_TOKENS or (len(token) >= 6 and token not in _LOW_SIGNAL_TERMS)
    meaningful = [token for token in tokens if token not in _STOPWORDS and token not in _LOW_SIGNAL_TERMS]
    return bool(meaningful)


def _metric_term_matches(search_term: str, matched_term: str) -> bool:
    """Return whether a matched metric meaningfully covers a requested metric term."""
    if not search_term or not matched_term:
        return False
    if search_term in matched_term or matched_term in search_term:
        return True

    search_tokens = set(_tokenize(search_term))
    matched_tokens = set(_tokenize(matched_term))
    if not search_tokens or not matched_tokens:
        return False

    overlap = len(search_tokens & matched_tokens)
    min_required = 1 if min(len(search_tokens), len(matched_tokens)) == 1 else 2
    return overlap >= min_required


def _score_metric_match_coverage(metric_terms: list[str], matched_terms: list[str]) -> float:
    """Score metric matches by requested-concept coverage rather than raw volume."""
    normalized_terms = _dedupe_preserve_order(
        [_normalize_text(term) for term in metric_terms if _normalize_text(term)]
    )
    normalized_matches = _dedupe_preserve_order(
        [_normalize_text(term) for term in matched_terms if _normalize_text(term)]
    )
    if not normalized_terms or not normalized_matches:
        return 0.0

    covered_terms = sum(
        1
        for term in normalized_terms
        if any(_metric_term_matches(term, matched) for matched in normalized_matches)
    )
    return covered_terms / len(normalized_terms)


class SuppFinancialsRetriever:
    """Retriever for Canadian bank supplementary financial data."""

    retriever_id: str = "supp_financials"

    def __init__(self, config: DataSourcesConfig, db: DataSourcesDB) -> None:
        self.config = config
        self.db = db

    def run(
        self,
        *,
        source: dict[str, Any],
        research_statement: str,
        query_terms: list[str],
    ) -> dict[str, Any]:
        """Run hybrid retrieval and return ranked pages plus provenance."""
        t_start = time.monotonic()
        schema_json = source.get("schema_json", {})
        location = source.get("location", {})
        bank_code = schema_json.get("bank_code") or location.get("bank_code")
        period_code = schema_json.get("period_code") or location.get("period_code")
        report_type = schema_json.get("report_type") or location.get("report_type")

        try:
            with ThreadPoolExecutor(max_workers=2) as pool:
                fut_metrics = pool.submit(self._extract_metric_names, research_statement)
                fut_hyde = pool.submit(self._hyde_expand_query, research_statement)
                metric_names = fut_metrics.result()
                hyde_result = fut_hyde.result()

            query_plan = self._build_query_plan(
                research_statement=research_statement,
                query_terms=query_terms,
                metric_names=metric_names,
                hyde_result=hyde_result,
            )

            channel_results: dict[str, list[dict[str, Any]]] = {}
            with ThreadPoolExecutor(max_workers=4) as pool:
                futures = {
                    pool.submit(
                        self._keyword_search,
                        keyword_terms=query_plan.lexical_phrases,
                        bank_code=bank_code,
                        period_code=period_code,
                        report_type=report_type,
                    ): "keyword_exact",
                    pool.submit(
                        self._metric_search,
                        metric_terms=query_plan.metric_search_terms,
                        bank_code=bank_code,
                        period_code=period_code,
                        report_type=report_type,
                    ): "metric_exact",
                    pool.submit(
                        self._lexical_catalog_search,
                        query_plan=query_plan,
                        bank_code=bank_code,
                        period_code=period_code,
                        report_type=report_type,
                    ): "lexical",
                    pool.submit(
                        self._semantic_search,
                        query_plan=query_plan,
                        bank_code=bank_code,
                        period_code=period_code,
                        report_type=report_type,
                    ): "semantic",
                }

                for future in as_completed(futures):
                    label = futures[future]
                    try:
                        result = future.result()
                    except Exception as exc:  # pragma: no cover - defensive guard
                        logger.warning("Retrieval channel %s failed: %s", label, exc)
                        continue
                    if label == "semantic":
                        channel_results.update(result)
                    else:
                        channel_results[label] = result

            retrieved = rerank_and_expand(
                channel_results=channel_results,
                db=self.db,
                top_k=self.config.reranker_top_k,
            )
            retrieved.sort(key=lambda sheet: sheet.score, reverse=True)

            sample_rows: list[dict[str, Any]] = []
            matched_terms: list[str] = []
            for sheet in retrieved:
                header = f"[Source | {sheet.report_type} | {sheet.bank_code} | {sheet.period_code} | {sheet.page_title or sheet.sheet_name}]"
                content_parts = [header]
                if sheet.matched_terms:
                    content_parts.append("Matched terms: " + ", ".join(sheet.matched_terms[:12]))
                if sheet.match_sources:
                    content_parts.append("Retrieval channels: " + ", ".join(sheet.match_sources))
                content_parts.append(sheet.raw_content)
                sample_rows.append(
                    {
                        "sheet_id": str(sheet.sheet_id),
                        "page_title": sheet.page_title,
                        "sheet_name": sheet.sheet_name,
                        "bank_code": sheet.bank_code,
                        "period_code": sheet.period_code,
                        "report_type": sheet.report_type,
                        "score": sheet.score,
                        "match_sources": sheet.match_sources,
                        "matched_terms": sheet.matched_terms,
                        "score_breakdown": sheet.score_breakdown,
                        "content": "\n".join(content_parts),
                    }
                )
                matched_terms.extend(sheet.matched_terms)

            top_score = retrieved[0].score if retrieved else 0.0
            elapsed = time.monotonic() - t_start
            channel_summary = ", ".join(
                f"{name}:{len(rows)}"
                for name, rows in sorted(channel_results.items())
                if rows
            ) or "no_hits"
            summary = f"Found {len(retrieved)} relevant pages via {channel_summary} in {elapsed:.1f}s"

            logger.info(
                summary,
                extra={
                    "event": "retrieval_complete",
                    "retriever_id": self.retriever_id,
                    "pages_returned": len(retrieved),
                    "duration_ms": round(elapsed * 1000),
                },
            )
            return {
                "status": "completed",
                "retriever_id": self.retriever_id,
                "handler": "supp_financials_retriever",
                "mode": "live_probe",
                "relevance_score": round(top_score * 100),
                "matched_terms": _dedupe_preserve_order(matched_terms),
                "sample_rows": sample_rows,
                "summary": summary,
            }

        except Exception as exc:  # pragma: no cover - defensive guard
            logger.exception("Retrieval failed: %s", exc)
            return {
                "status": "failed",
                "retriever_id": self.retriever_id,
                "handler": "supp_financials_retriever",
                "mode": "live_probe",
                "relevance_score": 0,
                "error": str(exc),
                "matched_terms": [],
                "sample_rows": [],
                "summary": f"Retrieval failed: {exc}",
            }

    def _candidate_limit(self) -> int:
        return max(self.config.retrieval_top_k, self.config.reranker_top_k * 3, 25)

    def _build_query_plan(
        self,
        *,
        research_statement: str,
        query_terms: list[str],
        metric_names: list[str],
        hyde_result: dict[str, Any],
    ) -> QueryPlan:
        heuristic_terms = self._heuristic_terms(research_statement, query_terms)
        alias_terms = _expand_domain_aliases(
            research_statement,
            heuristic_terms + metric_names,
        )
        lexical_phrases = _dedupe_preserve_order(
            heuristic_terms
            + [_normalize_text(item) for item in metric_names]
            + alias_terms
        )[:_MAX_LEXICAL_PHRASES]

        metric_search_terms = _dedupe_preserve_order(
            [_normalize_text(item) for item in metric_names]
            + [phrase for phrase in lexical_phrases if len(phrase.split()) <= 5 and _is_high_signal_phrase(phrase)]
            + alias_terms
        )[:_MAX_LEXICAL_PHRASES]

        semantic_queries = _dedupe_preserve_order(
            [research_statement]
            + [item for item in hyde_result.get("alternatives", []) if isinstance(item, str)]
            + metric_names[:6]
            + alias_terms[:6]
            + ([hyde_result["hypothetical_summary"]] if hyde_result.get("hypothetical_summary") else [])
        )[:_MAX_SEMANTIC_QUERIES]

        return QueryPlan(
            lexical_phrases=lexical_phrases,
            metric_search_terms=metric_search_terms,
            semantic_queries=semantic_queries,
        )

    def _heuristic_terms(self, research_statement: str, query_terms: list[str]) -> list[str]:
        explicit_terms = [_normalize_text(term) for term in query_terms if _normalize_text(term)]
        filtered_tokens = [
            token
            for token in _tokenize(research_statement)
            if token not in _STOPWORDS
        ]
        phrases = filtered_tokens + _extract_ngrams(filtered_tokens)
        return _dedupe_preserve_order(explicit_terms + phrases)

    def _keyword_search(
        self,
        *,
        keyword_terms: list[str],
        bank_code: str | None,
        period_code: str | None,
        report_type: str | None = None,
    ) -> list[dict[str, Any]]:
        exact_terms = [term for term in keyword_terms if _is_high_signal_phrase(term)]
        if not exact_terms:
            return []
        rows = self.db.search_by_keywords(
            keywords=exact_terms[: self._candidate_limit()],
            bank_code=bank_code,
            period_code=period_code,
            report_type=report_type,
            limit=self._candidate_limit(),
        )
        if not rows:
            return []

        max_hits = max(len(row.get("matched_keywords") or []) for row in rows) or 1
        enriched: list[dict[str, Any]] = []
        for row in rows:
            matched_terms = _dedupe_preserve_order(
                [str(term) for term in row.get("matched_keywords") or [] if str(term).strip()]
            )
            item = dict(row)
            item["matched_terms"] = matched_terms
            item["_retrieval_score"] = len(matched_terms) / max_hits if matched_terms else 0.0
            enriched.append(item)
        return enriched

    def _metric_search(
        self,
        *,
        metric_terms: list[str],
        bank_code: str | None,
        period_code: str | None,
        report_type: str | None = None,
    ) -> list[dict[str, Any]]:
        if not metric_terms:
            return []
        rows = self.db.search_by_metric_names(
            metric_names=metric_terms[: self._candidate_limit()],
            bank_code=bank_code,
            period_code=period_code,
            report_type=report_type,
            limit=self._candidate_limit(),
        )
        if not rows:
            return []

        max_hits = max(int(row.get("metric_hit_count") or 0) for row in rows) or 1
        enriched: list[dict[str, Any]] = []
        for row in rows:
            matched_terms = _dedupe_preserve_order(
                [str(term) for term in row.get("matched_metric_names") or [] if str(term).strip()]
            )
            coverage_score = _score_metric_match_coverage(metric_terms, matched_terms)
            volume_bonus = 0.05 * (float(row.get("metric_hit_count") or 0) / max_hits)
            item = dict(row)
            item["matched_terms"] = matched_terms
            item["_retrieval_score"] = min(1.0, coverage_score + volume_bonus)
            enriched.append(item)
        enriched.sort(key=lambda row: float(row.get("_retrieval_score") or 0.0), reverse=True)
        return enriched

    def _lexical_catalog_search(
        self,
        *,
        query_plan: QueryPlan,
        bank_code: str | None,
        period_code: str | None,
        report_type: str | None = None,
    ) -> list[dict[str, Any]]:
        if not query_plan.lexical_phrases:
            return []

        rows = self.db.list_sheet_catalog(
            bank_code=bank_code,
            period_code=period_code,
            report_type=report_type,
        )
        if not rows:
            return []

        prepared = [self._prepare_catalog_entry(row) for row in rows]
        query_tokens = _dedupe_preserve_order(
            [token for phrase in query_plan.lexical_phrases for token in _tokenize(phrase)]
        )
        if not query_tokens:
            return []

        idf = self._compute_query_idf(query_tokens, prepared)
        scored_rows: list[dict[str, Any]] = []
        max_score = 0.0
        for entry in prepared:
            score, matched_terms = self._score_catalog_entry(
                entry=entry,
                query_phrases=query_plan.lexical_phrases,
                query_tokens=query_tokens,
                idf=idf,
            )
            if score <= 0:
                continue
            item = dict(entry["row"])
            item["matched_terms"] = matched_terms
            item["_retrieval_score"] = score
            scored_rows.append(item)
            max_score = max(max_score, score)

        if max_score <= 0:
            return []
        for row in scored_rows:
            row["_retrieval_score"] = float(row["_retrieval_score"]) / max_score
        scored_rows.sort(key=lambda row: float(row["_retrieval_score"]), reverse=True)
        return scored_rows[: self._candidate_limit()]

    def _prepare_catalog_entry(self, row: dict[str, Any]) -> dict[str, Any]:
        title = " ".join(
            part for part in [row.get("sheet_name") or "", row.get("page_title") or ""] if part
        )
        summary = row.get("summary") or ""
        content = row.get("raw_content") or ""
        keyword_phrases = [_normalize_text(item) for item in row.get("keywords") or [] if item]
        metric_phrases = [_normalize_text(item) for item in row.get("metric_names") or [] if item]
        platform_phrases = [
            _normalize_text(item)
            for item in (row.get("platforms") or []) + (row.get("sub_platforms") or [])
            if item
        ]
        title_text = _normalize_text(title)
        summary_text = _normalize_text(summary)
        content_text = _normalize_text(content)

        title_tokens = set(_tokenize(title))
        summary_tokens = set(_tokenize(summary))
        content_tokens = set(_tokenize(content))
        keyword_tokens = set(token for phrase in keyword_phrases for token in _tokenize(phrase))
        metric_tokens = set(token for phrase in metric_phrases for token in _tokenize(phrase))
        platform_tokens = set(token for phrase in platform_phrases for token in _tokenize(phrase))

        return {
            "row": row,
            "title_text": title_text,
            "summary_text": summary_text,
            "content_text": content_text,
            "keyword_phrases": keyword_phrases,
            "metric_phrases": metric_phrases,
            "platform_phrases": platform_phrases,
            "title_tokens": title_tokens,
            "summary_tokens": summary_tokens,
            "content_tokens": content_tokens,
            "keyword_tokens": keyword_tokens,
            "metric_tokens": metric_tokens,
            "platform_tokens": platform_tokens,
            "all_tokens": title_tokens | summary_tokens | content_tokens | keyword_tokens | metric_tokens | platform_tokens,
        }

    def _compute_query_idf(
        self,
        query_tokens: list[str],
        prepared_rows: list[dict[str, Any]],
    ) -> dict[str, float]:
        total_docs = max(1, len(prepared_rows))
        idf: dict[str, float] = {}
        for token in query_tokens:
            doc_freq = sum(1 for row in prepared_rows if token in row["all_tokens"])
            idf[token] = math.log((1 + total_docs) / (1 + doc_freq)) + 1.0
        return idf

    def _score_catalog_entry(
        self,
        *,
        entry: dict[str, Any],
        query_phrases: list[str],
        query_tokens: list[str],
        idf: dict[str, float],
    ) -> tuple[float, list[str]]:
        score = 0.0
        matched_terms: list[str] = []
        matched_seen: set[str] = set()

        for phrase in query_phrases:
            normalized_phrase = _normalize_text(phrase)
            if not normalized_phrase:
                continue

            field_hits = 0
            phrase_score = 0.0
            if normalized_phrase in entry["title_text"]:
                phrase_score += 4.8
                field_hits += 1
            if normalized_phrase in entry["summary_text"]:
                phrase_score += 2.4
                field_hits += 1
            if normalized_phrase in entry["content_text"]:
                phrase_score += 1.0
                field_hits += 1
            if any(normalized_phrase == item for item in entry["keyword_phrases"]):
                phrase_score += 3.8
                field_hits += 1
            elif any(normalized_phrase in item or item in normalized_phrase for item in entry["keyword_phrases"]):
                phrase_score += 2.6
                field_hits += 1
            if any(normalized_phrase == item or normalized_phrase in item for item in entry["metric_phrases"]):
                phrase_score += 4.2
                field_hits += 1
            if any(normalized_phrase in item for item in entry["platform_phrases"]):
                phrase_score += 2.5
                field_hits += 1

            if field_hits:
                score += phrase_score + 0.25 * max(0, field_hits - 1)
                if normalized_phrase not in matched_seen:
                    matched_seen.add(normalized_phrase)
                    matched_terms.append(normalized_phrase)

        for token in query_tokens:
            token_idf = idf.get(token, 1.0)
            token_fields = 0
            if token in entry["title_tokens"]:
                score += 1.7 * token_idf
                token_fields += 1
            if token in entry["keyword_tokens"]:
                score += 1.5 * token_idf
                token_fields += 1
            if token in entry["metric_tokens"]:
                score += 1.8 * token_idf
                token_fields += 1
            if token in entry["platform_tokens"]:
                score += 1.2 * token_idf
                token_fields += 1
            if token in entry["summary_tokens"]:
                score += 1.0 * token_idf
                token_fields += 1
            if token in entry["content_tokens"]:
                score += 0.35 * token_idf
                token_fields += 1
            if token_fields >= 3:
                score += 0.25 * token_idf
            if token_fields >= 2 and token not in matched_seen and token_idf > 1.15:
                matched_seen.add(token)
                matched_terms.append(token)

        return score, matched_terms

    def _semantic_search(
        self,
        *,
        query_plan: QueryPlan,
        bank_code: str | None,
        period_code: str | None,
        report_type: str | None = None,
    ) -> dict[str, list[dict[str, Any]]]:
        if not query_plan.semantic_queries:
            return {}
        try:
            embeddings = embed_texts(
                query_plan.semantic_queries,
                config=self.config,
                model=self.config.embedding_model,
                dimensions=self.config.embedding_dimensions,
            )
        except Exception as exc:
            logger.warning("Embedding phase failed; continuing without dense retrieval: %s", exc)
            return {}

        per_channel: dict[str, dict[str, dict[str, Any]]] = {
            "summary_semantic": {},
            "keyword_semantic": {},
            "metric_semantic": {},
        }
        future_map: dict[Any, tuple[str, str]] = {}
        with ThreadPoolExecutor(max_workers=12) as pool:
            for query_text, embedding in zip(query_plan.semantic_queries, embeddings):
                if not embedding:
                    continue
                future_map[
                    pool.submit(
                        self.db.search_by_embedding,
                        embedding=embedding,
                        bank_code=bank_code,
                        period_code=period_code,
                        report_type=report_type,
                        limit=self._candidate_limit(),
                    )
                ] = ("summary_semantic", query_text)
                future_map[
                    pool.submit(
                        self.db.search_by_keyword_embeddings,
                        embedding=embedding,
                        bank_code=bank_code,
                        period_code=period_code,
                        report_type=report_type,
                        limit=self._candidate_limit(),
                    )
                ] = ("keyword_semantic", query_text)
                future_map[
                    pool.submit(
                        self.db.search_by_metric_embeddings,
                        embedding=embedding,
                        bank_code=bank_code,
                        period_code=period_code,
                        report_type=report_type,
                        limit=self._candidate_limit(),
                    )
                ] = ("metric_semantic", query_text)

            for future in as_completed(future_map):
                channel_name, query_text = future_map[future]
                try:
                    rows = future.result()
                except Exception as exc:
                    logger.warning("Dense channel %s failed: %s", channel_name, exc)
                    continue
                for row in rows:
                    sheet_id = str(row["sheet_id"])
                    similarity = max(0.0, float(row.get("cosine_similarity") or 0.0))
                    matched_terms = [
                        str(term)
                        for term in [row.get("matched_keyword"), row.get("matched_metric"), _short_query_label(query_text)]
                        if term
                    ]
                    item = dict(row)
                    item["matched_terms"] = _dedupe_preserve_order(matched_terms)
                    item["_retrieval_score"] = similarity

                    current = per_channel[channel_name].get(sheet_id)
                    if current is None or similarity > float(current.get("_retrieval_score") or 0.0):
                        per_channel[channel_name][sheet_id] = item

        result: dict[str, list[dict[str, Any]]] = {}
        for channel_name, rows in per_channel.items():
            ranked = sorted(
                rows.values(),
                key=lambda row: float(row.get("_retrieval_score") or 0.0),
                reverse=True,
            )
            if ranked:
                result[channel_name] = ranked[: self._candidate_limit()]
        return result

    def _extract_metric_names(self, research_statement: str) -> list[str]:
        try:
            client = build_openai_client(self.config)
            response = client.chat.completions.create(
                model=self.config.retrieval_model,
                messages=[
                    {"role": "system", "content": _METRIC_EXTRACTION_PROMPT},
                    {"role": "user", "content": research_statement},
                ],
                max_completion_tokens=self.config.retrieval_max_tokens,
                response_format={"type": "json_object"},
            )
            content = response.choices[0].message.content or "{}"
            data = json.loads(content)
            metric_names = [
                str(item).strip()
                for item in data.get("metric_names", [])
                if str(item).strip()
            ]
            return _dedupe_preserve_order(metric_names)
        except Exception as exc:
            logger.warning("Metric extraction failed: %s", exc)
            return []

    def _hyde_expand_query(self, research_statement: str) -> dict[str, Any]:
        try:
            client = build_openai_client(self.config)
            response = client.chat.completions.create(
                model=self.config.retrieval_model,
                messages=[
                    {"role": "system", "content": _HYDE_EXPANSION_PROMPT},
                    {"role": "user", "content": research_statement},
                ],
                max_completion_tokens=self.config.retrieval_max_tokens,
                response_format={"type": "json_object"},
            )
            content = response.choices[0].message.content or "{}"
            data = json.loads(content)
            alternatives = [
                str(item).strip()
                for item in data.get("alternatives", [])
                if str(item).strip()
            ]
            hypothetical_summary = data.get("hypothetical_summary")
            return {
                "alternatives": _dedupe_preserve_order(alternatives),
                "hypothetical_summary": hypothetical_summary if isinstance(hypothetical_summary, str) else None,
            }
        except Exception as exc:
            logger.warning("HyDE expansion failed: %s", exc)
            return {"alternatives": [], "hypothetical_summary": None}
