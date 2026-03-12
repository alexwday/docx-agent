from __future__ import annotations

import sys
import types
from uuid import uuid4

psycopg_stub = types.ModuleType("psycopg")
psycopg_stub.connect = lambda *args, **kwargs: None
psycopg_rows_stub = types.ModuleType("psycopg.rows")
psycopg_rows_stub.dict_row = object()
psycopg_types_stub = types.ModuleType("psycopg.types")
psycopg_types_json_stub = types.ModuleType("psycopg.types.json")
psycopg_types_json_stub.Jsonb = lambda payload: payload
sys.modules.setdefault("psycopg", psycopg_stub)
sys.modules.setdefault("psycopg.rows", psycopg_rows_stub)
sys.modules.setdefault("psycopg.types", psycopg_types_stub)
sys.modules.setdefault("psycopg.types.json", psycopg_types_json_stub)

word_store_stub = types.ModuleType("word_store")
word_store_db_stub = types.ModuleType("word_store.db")
word_store_db_stub.PostgresStore = object
word_store_db_stub.resolve_database_dsn = lambda dsn=None: dsn or "postgresql://unit-test"
word_store_stub.db = word_store_db_stub
sys.modules.setdefault("word_store", word_store_stub)
sys.modules.setdefault("word_store.db", word_store_db_stub)

from data_sources.config import DataSourcesConfig
from data_sources.retrieve.reranker import rerank_and_expand
from data_sources.retrieve.supp_financials import SuppFinancialsRetriever


def _sheet_row(
    *,
    sheet_name: str,
    page_title: str | None = None,
    summary: str | None = None,
    keywords: list[str] | None = None,
    metric_names: list[str] | None = None,
    platforms: list[str] | None = None,
    sub_platforms: list[str] | None = None,
    raw_content: str = "",
    score: float = 0.0,
    matched_terms: list[str] | None = None,
    sheet_index: int = 0,
    context_sheet_ids: list[str] | None = None,
) -> dict:
    document_id = uuid4()
    sheet_id = uuid4()
    return {
        "sheet_id": sheet_id,
        "document_id": document_id,
        "sheet_index": sheet_index,
        "sheet_name": sheet_name,
        "page_title": page_title or sheet_name,
        "raw_content": raw_content or f"Raw content for {sheet_name}",
        "summary": summary,
        "keywords": keywords or [],
        "metric_names": metric_names or [],
        "platforms": platforms or [],
        "sub_platforms": sub_platforms or [],
        "bank_code": "RBC",
        "period_code": "Q1_2026",
        "context_sheet_ids": context_sheet_ids or [],
        "_retrieval_score": score,
        "matched_terms": matched_terms or [],
    }


class _FakeDB:
    def __init__(
        self,
        *,
        keyword_rows: list[dict] | None = None,
        metric_rows: list[dict] | None = None,
        catalog_rows: list[dict] | None = None,
        sheets_by_id: dict[str, dict] | None = None,
        neighbor_rows: list[dict] | None = None,
    ) -> None:
        self.keyword_rows = keyword_rows or []
        self.metric_rows = metric_rows or []
        self.catalog_rows = catalog_rows or []
        self.sheets_by_id = sheets_by_id or {}
        self.neighbor_rows = neighbor_rows or []

    def search_by_keywords(self, **_: object) -> list[dict]:
        return self.keyword_rows

    def search_by_metric_names(self, **_: object) -> list[dict]:
        return self.metric_rows

    def list_sheet_catalog(self, **_: object) -> list[dict]:
        return self.catalog_rows

    def get_sheets_by_ids(self, sheet_ids: list) -> list[dict]:
        return [self.sheets_by_id[str(sheet_id)] for sheet_id in sheet_ids if str(sheet_id) in self.sheets_by_id]

    def get_neighbor_sheets(self, **_: object) -> list[dict]:
        return self.neighbor_rows


def _config() -> DataSourcesConfig:
    return DataSourcesConfig(
        database_dsn="postgresql://unit-test",
        openai_api_key="test-key",
        retrieval_top_k=8,
        reranker_top_k=3,
    )


def test_lexical_catalog_search_uses_domain_aliases_for_underwriting_queries():
    insurance_row = _sheet_row(
        sheet_name="Page_12",
        page_title="Insurance",
        summary="Insurance service result, insurance investment result, and contractual service margin.",
        keywords=["insurance service result", "contractual service margin", "premiums"],
        metric_names=["Insurance service result", "Contractual service margin"],
        raw_content="Insurance service result 240; contractual service margin 1773.",
    )
    unrelated_row = _sheet_row(
        sheet_name="Page_5",
        page_title="Income Statement",
        summary="Total revenue and net interest income.",
        keywords=["net interest income", "total revenue"],
        metric_names=["Net interest income", "Total revenue"],
        raw_content="Net interest income 8585.",
        sheet_index=1,
    )
    retriever = SuppFinancialsRetriever(config=_config(), db=_FakeDB(catalog_rows=[insurance_row, unrelated_row]))

    query_plan = retriever._build_query_plan(
        research_statement="How much did RBC earn from underwriting policies last quarter?",
        query_terms=["underwriting", "policies", "earn"],
        metric_names=[],
        hyde_result={"alternatives": [], "hypothetical_summary": None},
    )
    results = retriever._lexical_catalog_search(
        query_plan=query_plan,
        bank_code="RBC",
        period_code="Q1_2026",
    )

    assert results
    assert results[0]["sheet_name"] == "Page_12"
    assert "insurance service result" in results[0]["matched_terms"]


def test_run_returns_completed_when_dense_channel_fails(monkeypatch):
    keyword_row = _sheet_row(
        sheet_name="Page_19",
        page_title="Flow Statement of the Movements in Regulatory Capital",
        keywords=["cet1", "regulatory capital"],
        raw_content="Opening amount 98748. Closing amount 100415.",
    )
    keyword_row["matched_keywords"] = ["cet1"]

    retriever = SuppFinancialsRetriever(
        config=_config(),
        db=_FakeDB(keyword_rows=[keyword_row]),
    )
    monkeypatch.setattr(retriever, "_extract_metric_names", lambda _: [])
    monkeypatch.setattr(retriever, "_hyde_expand_query", lambda _: {"alternatives": [], "hypothetical_summary": None})
    monkeypatch.setattr(retriever, "_semantic_search", lambda **_: (_ for _ in ()).throw(RuntimeError("dense down")))

    result = retriever.run(
        source={"schema_json": {"bank_code": "RBC", "period_code": "Q1_2026"}, "location": {}},
        research_statement="What drove the change in CET1 ratio from last quarter?",
        query_terms=["cet1", "ratio", "change"],
    )

    assert result["status"] == "completed"
    assert result["sample_rows"]
    assert "cet1" in result["matched_terms"]
    assert "keyword_exact" not in result["matched_terms"]


def test_reranker_prefers_multi_channel_agreement_and_expands_neighbors():
    primary_row = _sheet_row(
        sheet_name="Page_33",
        page_title="Derivatives - Related Credit Risk",
        summary="Credit derivatives and risk-weighted equivalent.",
        raw_content="Total derivatives risk-weighted equivalent 18930.",
    )
    supporting_row = _sheet_row(
        sheet_name="Page_32",
        page_title="Fair Value of Derivative Instruments",
        summary="Gross fair values before netting.",
        raw_content="Total gross fair values before netting 173856.",
        sheet_index=1,
    )
    alternate_row = _sheet_row(
        sheet_name="Page_20",
        page_title="Risk-Weighted Assets by Segment",
        summary="Capital Markets risk-weighted assets.",
        raw_content="Capital Markets 271150.",
        sheet_index=2,
    )

    db = _FakeDB(
        sheets_by_id={str(supporting_row["sheet_id"]): supporting_row},
        neighbor_rows=[primary_row, supporting_row],
    )
    results = rerank_and_expand(
        channel_results={
            "keyword_exact": [dict(primary_row, _retrieval_score=0.91, matched_terms=["risk weighted equivalent"])],
            "lexical": [dict(primary_row, _retrieval_score=0.88, matched_terms=["total derivatives"])],
            "summary_semantic": [dict(primary_row, _retrieval_score=0.83, matched_terms=["credit derivatives"])],
            "metric_exact": [dict(alternate_row, _retrieval_score=0.97, matched_terms=["risk weighted assets"])],
        },
        db=db,
        top_k=1,
    )

    assert results[0].sheet_name == "Page_33"
    assert any(row.sheet_name == "Page_32" and row.match_sources == ["adjacent_context"] for row in results)


def test_metric_search_propagates_exact_metric_matches_into_output():
    metric_row = _sheet_row(
        sheet_name="Page_34",
        page_title="Return on Common Equity and RORC",
        raw_content="ROE 17.6%; average common equity 127350.",
    )
    metric_row["metric_hit_count"] = 2
    metric_row["matched_metric_names"] = ["ROE", "Average common equity"]

    retriever = SuppFinancialsRetriever(
        config=_config(),
        db=_FakeDB(metric_rows=[metric_row]),
    )
    results = retriever._metric_search(
        metric_terms=["roe", "average common equity"],
        bank_code="RBC",
        period_code="Q1_2026",
    )

    assert results
    assert results[0]["matched_terms"] == ["ROE", "Average common equity"]
    assert results[0]["_retrieval_score"] == 1.0


def test_metric_search_prefers_requested_metric_coverage_over_repeated_partial_hits():
    partial_row = _sheet_row(
        sheet_name="Page_32",
        page_title="Fair Value of Derivative Instruments",
        raw_content="Forward contracts notional amount 3043231.",
    )
    partial_row["metric_hit_count"] = 6
    partial_row["matched_metric_names"] = [
        "Foreign exchange contracts - Forward contracts - notional amount",
        "Forward contracts - foreign exchange contracts - non centrally cleared - over the counter - notional amount",
    ]

    complete_row = _sheet_row(
        sheet_name="Page_33",
        page_title="Derivatives - Related Credit Risk",
        raw_content="Forward contracts notional amount 3330641; replacement cost 6303.",
    )
    complete_row["metric_hit_count"] = 2
    complete_row["matched_metric_names"] = [
        "Foreign exchange contracts - Forward contracts - notional amount",
        "Foreign exchange contracts - Forward contracts - replacement cost",
    ]

    retriever = SuppFinancialsRetriever(
        config=_config(),
        db=_FakeDB(metric_rows=[partial_row, complete_row]),
    )
    results = retriever._metric_search(
        metric_terms=["foreign exchange contracts", "forward contracts", "replacement cost"],
        bank_code="RBC",
        period_code="Q1_2026",
    )

    assert results[0]["sheet_name"] == "Page_33"
    assert results[0]["_retrieval_score"] > results[1]["_retrieval_score"]
