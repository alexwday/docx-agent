"""Fuse retrieval channels, rerank candidates, and expand nearby context."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

from data_sources.db import DataSourcesDB
from data_sources.models import RetrievedSheet

__all__ = ["rerank_and_expand"]

_RRF_K = 20
_CHANNEL_WEIGHTS = {
    "keyword_exact": 1.35,
    "metric_exact": 1.55,
    "lexical": 1.25,
    "summary_semantic": 1.0,
    "keyword_semantic": 1.15,
    "metric_semantic": 1.3,
}
_EXPLICIT_CONTEXT_FRACTION = 0.45
_ADJACENT_CONTEXT_FRACTION = 0.30
_ADJACENT_CONTEXT_THRESHOLD = 0.35


@dataclass(slots=True)
class _CandidateScore:
    sheet_id: str
    source_row: dict[str, Any]
    fused_score: float = 0.0
    final_score: float = 0.0
    match_sources: set[str] = field(default_factory=set)
    matched_terms: set[str] = field(default_factory=set)
    score_breakdown: dict[str, float] = field(default_factory=dict)


def rerank_and_expand(
    *,
    channel_results: dict[str, list[dict[str, Any]]],
    db: DataSourcesDB,
    top_k: int = 5,
) -> list[RetrievedSheet]:
    """Combine heterogeneous retrieval channels with weighted RRF and expand context."""
    candidates: dict[str, _CandidateScore] = {}

    for channel_name, results in channel_results.items():
        if not results:
            continue
        weight = _CHANNEL_WEIGHTS.get(channel_name, 1.0)
        ranked_results = sorted(
            results,
            key=lambda row: float(row.get("_retrieval_score") or 0.0),
            reverse=True,
        )
        for rank, row in enumerate(ranked_results, start=1):
            candidate = _get_or_create(candidates, row)
            raw_score = float(row.get("_retrieval_score") or 0.0)
            best_score = max(candidate.score_breakdown.values(), default=0.0)
            candidate.fused_score += weight / (_RRF_K + rank)
            candidate.match_sources.add(channel_name)
            candidate.score_breakdown[channel_name] = max(
                raw_score,
                candidate.score_breakdown.get(channel_name, 0.0),
            )
            candidate.matched_terms.update(
                str(term)
                for term in row.get("matched_terms", [])
                if str(term).strip()
            )
            if raw_score > best_score:
                candidate.source_row = row

    if not candidates:
        return []

    _finalize_scores(candidates)
    selected = sorted(candidates.values(), key=lambda item: item.final_score, reverse=True)[:top_k]
    if not selected:
        return []

    expansions = _collect_expansions(selected, candidates, db)
    selected_ids = {candidate.sheet_id for candidate in selected}

    result: list[RetrievedSheet] = [
        _to_retrieved_sheet(candidate.source_row, candidate.final_score, candidate)
        for candidate in selected
    ]
    for sheet_id, expansion in expansions.items():
        if sheet_id in selected_ids:
            continue
        rows = db.get_sheets_by_ids([UUID(sheet_id)])
        if not rows:
            continue
        row = rows[0]
        result.append(
            RetrievedSheet(
                sheet_id=row["sheet_id"],
                document_id=row["document_id"],
                sheet_index=row["sheet_index"],
                sheet_name=row["sheet_name"],
                page_title=row.get("page_title"),
                raw_content=row["raw_content"],
                summary=row.get("summary"),
                bank_code=row.get("bank_code", ""),
                period_code=row.get("period_code", ""),
                score=expansion["score"],
                report_type=row.get("report_type", ""),
                match_sources=[expansion["source"]],
                matched_terms=[],
                score_breakdown={expansion["source"]: expansion["score"]},
            )
        )

    result.sort(key=lambda sheet: sheet.score, reverse=True)
    return result


def _get_or_create(
    candidates: dict[str, _CandidateScore],
    row: dict[str, Any],
) -> _CandidateScore:
    sheet_id = str(row["sheet_id"])
    candidate = candidates.get(sheet_id)
    if candidate is None:
        candidate = _CandidateScore(sheet_id=sheet_id, source_row=row)
        candidates[sheet_id] = candidate
    return candidate


def _finalize_scores(candidates: dict[str, _CandidateScore]) -> None:
    max_score = 0.0
    for candidate in candidates.values():
        agreement_boost = 0.03 * max(0, len(candidate.match_sources) - 1)
        evidence_boost = min(0.08, 0.01 * len(candidate.matched_terms))
        channel_strength = 0.05 * sum(candidate.score_breakdown.values())
        candidate.final_score = candidate.fused_score + agreement_boost + evidence_boost + channel_strength
        max_score = max(max_score, candidate.final_score)

    if max_score <= 0:
        return
    for candidate in candidates.values():
        candidate.final_score /= max_score


def _collect_expansions(
    selected: list[_CandidateScore],
    candidates: dict[str, _CandidateScore],
    db: DataSourcesDB,
) -> dict[str, dict[str, Any]]:
    expansions: dict[str, dict[str, Any]] = {}
    for candidate in selected:
        row = candidate.source_row
        for context_sheet_id in row.get("context_sheet_ids") or []:
            context_id = str(context_sheet_id)
            _record_expansion(
                expansions,
                context_id,
                score=candidate.final_score * _EXPLICIT_CONTEXT_FRACTION,
                source="explicit_context",
            )

        if candidate.final_score < _ADJACENT_CONTEXT_THRESHOLD:
            continue
        neighbors = db.get_neighbor_sheets(
            document_id=row["document_id"],
            sheet_index=row["sheet_index"],
        )
        for neighbor in neighbors:
            neighbor_id = str(neighbor["sheet_id"])
            if neighbor_id == candidate.sheet_id:
                continue
            # Keep explicit candidates above implicit neighbors.
            if neighbor_id in candidates and candidates[neighbor_id].final_score >= candidate.final_score * 0.6:
                continue
            _record_expansion(
                expansions,
                neighbor_id,
                score=candidate.final_score * _ADJACENT_CONTEXT_FRACTION,
                source="adjacent_context",
            )
    return expansions


def _record_expansion(
    expansions: dict[str, dict[str, Any]],
    sheet_id: str,
    *,
    score: float,
    source: str,
) -> None:
    existing = expansions.get(sheet_id)
    if existing is None or score > float(existing.get("score") or 0.0):
        expansions[sheet_id] = {"score": score, "source": source}


def _to_retrieved_sheet(
    row: dict[str, Any],
    score: float,
    candidate: _CandidateScore,
) -> RetrievedSheet:
    return RetrievedSheet(
        sheet_id=row["sheet_id"],
        document_id=row["document_id"],
        sheet_index=row["sheet_index"],
        sheet_name=row["sheet_name"],
        page_title=row.get("page_title"),
        raw_content=row["raw_content"],
        summary=row.get("summary"),
        bank_code=row.get("bank_code", ""),
        period_code=row.get("period_code", ""),
        score=score,
        report_type=row.get("report_type", ""),
        match_sources=sorted(candidate.match_sources),
        matched_terms=sorted(candidate.matched_terms),
        score_breakdown=dict(sorted(candidate.score_breakdown.items())),
    )
