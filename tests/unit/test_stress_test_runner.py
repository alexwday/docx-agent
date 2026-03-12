from __future__ import annotations

from contextlib import contextmanager
import sys
import types

psycopg_stub = types.ModuleType("psycopg")
psycopg_stub.connect = lambda *args, **kwargs: None
psycopg_rows_stub = types.ModuleType("psycopg.rows")
psycopg_rows_stub.dict_row = object()
psycopg_types_stub = types.ModuleType("psycopg.types")
psycopg_types_json_stub = types.ModuleType("psycopg.types.json")
psycopg_types_json_stub.Jsonb = lambda payload: payload
psycopg_types_json_stub.set_json_dumps = lambda func: None
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
from data_sources.scripts import stress_test


def _config() -> DataSourcesConfig:
    return DataSourcesConfig(
        database_dsn="postgresql://unit-test",
        openai_api_key="test-key",
    )


class _FakeExecuteResult:
    def __init__(self, row: dict[str, str] | None) -> None:
        self.row = row

    def fetchone(self) -> dict[str, str] | None:
        return self.row


class _FakeConnection:
    def __init__(self, executed: list[tuple[str, tuple]], row: dict[str, str] | None) -> None:
        self.executed = executed
        self.row = row

    def execute(self, sql: str, params: tuple) -> _FakeExecuteResult:
        self.executed.append((" ".join(sql.split()), params))
        return _FakeExecuteResult(self.row)


class _FakeStore:
    def __init__(self, executed: list[tuple[str, tuple]], row: dict[str, str] | None = None) -> None:
        self.executed = executed
        self.row = row

    @contextmanager
    def connection(self):
        yield _FakeConnection(self.executed, self.row)


class _FakeDB:
    def __init__(self, store) -> None:
        self.store = store


def test_fetch_target_content_scopes_lookup_to_report_identity():
    executed: list[tuple[str, tuple]] = []
    db = _FakeDB(_FakeStore(executed, {"raw_content": "target page content"}))
    source = {
        "source_id": "supp_financials",
        "report_type": "supp_financials",
        "location": {"retriever_id": "supp_financials"},
        "schema_json": {"bank_code": "RBC", "period_code": "Q1_2026"},
    }

    content = stress_test._fetch_target_content("Page_33", db, source)

    assert content == "target page content"
    sql, params = executed[0]
    assert "JOIN data_sources.report_documents rd ON rd.document_id = rs.document_id" in sql
    assert "rd.bank_code = %s" in sql
    assert "rd.period_code = %s" in sql
    assert "rd.report_type = %s" in sql
    assert params == ("Page_33", "RBC", "Q1_2026", "supp_financials")


def test_run_stress_test_continues_after_model_failures_and_writes_reports(monkeypatch, tmp_path):
    _src = [{"report_type": "supp_financials", "bank": "RBC", "year": 2026, "quarter": "Q1"}]
    queries = [
        {
            "q": "First query",
            "terms": ["first"],
            "why_hard": "first",
            "difficulty": "easy",
            "answer_pages": ["Page_1"],
            "answer_pages_tbd": False,
            "answer_citations": ["Page_1 citation"],
            "expected_answer_summary": "First expected answer",
            "sources": _src,
        },
        {
            "q": "Second query",
            "terms": ["second"],
            "why_hard": "second",
            "difficulty": "medium",
            "answer_pages": ["Page_2"],
            "answer_pages_tbd": False,
            "answer_citations": ["Page_2 citation"],
            "expected_answer_summary": "Second expected answer",
            "sources": _src,
        },
    ]
    query_to_page = {row["q"]: row["answer_pages"][0] for row in queries}
    answer_calls: list[str] = []
    judge_calls: list[str] = []

    class _FakePostgresStore:
        def __init__(self, dsn: str) -> None:
            self.dsn = dsn

    class _FakeRetriever:
        def __init__(self, config: DataSourcesConfig, db: _FakeDB) -> None:
            self.config = config
            self.db = db

        def run(self, *, source: dict, research_statement: str, query_terms: list[str]) -> dict[str, object]:
            page_name = query_to_page[research_statement]
            return {
                "summary": "ok",
                "sample_rows": [
                    {
                        "sheet_id": f"sheet-{page_name}",
                        "sheet_name": page_name,
                        "page_title": page_name,
                        "bank_code": "RBC",
                        "period_code": "Q1_2026",
                        "score": 0.9,
                        "match_sources": ["keyword_exact"],
                        "matched_terms": list(query_terms),
                        "score_breakdown": {},
                        "content": f"[Source | {page_name} | {page_name} | RBC Q1_2026]\ncontent for {page_name}",
                    }
                ],
            }

    def fake_generate_answer(query: str, context_rows: list[dict[str, object]], config: DataSourcesConfig) -> str:
        answer_calls.append(query)
        if query == "First query":
            raise RuntimeError("rate limited")
        return "Generated answer [Source 1]"

    def fake_judge_answer(
        query: str,
        answer: str,
        qdata: dict[str, object],
        ground_truth_pages: dict[str, str],
        cited_source_pages: dict[str, str],
        config: DataSourcesConfig,
    ) -> dict[str, object]:
        judge_calls.append(query)
        raise RuntimeError("judge timeout")

    monkeypatch.setattr(stress_test, "ALL_QUERIES", queries)
    monkeypatch.setattr(stress_test.DataSourcesConfig, "from_env", classmethod(lambda cls: _config()))
    monkeypatch.setattr(stress_test, "PostgresStore", _FakePostgresStore)
    monkeypatch.setattr(stress_test, "DataSourcesDB", _FakeDB)
    monkeypatch.setattr(stress_test, "SuppFinancialsRetriever", _FakeRetriever)
    monkeypatch.setattr(
        stress_test,
        "_fetch_target_content",
        lambda page_name, db, source: f"ground truth for {page_name}",
    )
    monkeypatch.setattr(stress_test, "_generate_answer", fake_generate_answer)
    monkeypatch.setattr(stress_test, "_judge_answer", fake_judge_answer)

    report = stress_test.run_stress_test(output_dir=tmp_path)

    assert answer_calls == ["First query", "Second query"]
    assert judge_calls == ["Second query"]
    assert report["summary"]["total_queries"] == 2
    assert len(report["queries"]) == 2
    assert report["queries"][0]["errors"]["answer"] == "Synthesis error: rate limited"
    assert report["queries"][0]["explanation"] == "Synthesis error: rate limited"
    assert report["queries"][0]["overall_score"] == 0
    assert report["queries"][1]["errors"]["judge"] == "Judge error: judge timeout"
    assert report["queries"][1]["explanation"] == "Judge error: judge timeout"
    assert report["queries"][1]["overall_score"] == 0
    assert (tmp_path / "stress_test_report.json").exists()
    assert (tmp_path / "stress_test_report.html").exists()


def test_run_stress_test_uses_all_answer_pages_for_ground_truth_and_hit_tracking(monkeypatch, tmp_path):
    queries = [
        {
            "q": "What is RBC's average earning asset base and net interest margin?",
            "terms": ["average", "margin"],
            "why_hard": "needs two pages",
            "difficulty": "medium",
            "answer_pages": ["Page_16", "Page_2"],
            "answer_pages_tbd": False,
            "answer_citations": [
                "Average earning assets, net: $2,191,100M (Q1/26)",
                "Net interest margin (NIM) (average earning assets, net): 1.55% (Q1/26)",
            ],
            "expected_answer_summary": "Average earning assets were $2,191,100M and NIM was 1.55%.",
            "sources": [{"report_type": "supp_financials", "bank": "RBC", "year": 2026, "quarter": "Q1"}],
        }
    ]
    captured_ground_truth: dict[str, str] = {}
    captured_cited_sources: dict[str, str] = {}

    class _FakePostgresStore:
        def __init__(self, dsn: str) -> None:
            self.dsn = dsn

    class _FakeRetriever:
        def __init__(self, config: DataSourcesConfig, db: _FakeDB) -> None:
            self.config = config
            self.db = db

        def run(self, *, source: dict, research_statement: str, query_terms: list[str]) -> dict[str, object]:
            return {
                "summary": "ok",
                "sample_rows": [
                    {
                        "sheet_id": "sheet-2",
                        "sheet_name": "Page_2",
                        "page_title": "Financial Highlights",
                        "bank_code": "RBC",
                        "period_code": "Q1_2026",
                        "score": 0.95,
                        "match_sources": ["keyword_exact"],
                        "matched_terms": ["margin"],
                        "score_breakdown": {},
                        "content": "[Source | Page_2 | Financial Highlights | RBC Q1_2026]\ncontent for Page_2",
                    },
                    {
                        "sheet_id": "sheet-8",
                        "sheet_name": "Page_8",
                        "page_title": "Personal Banking",
                        "bank_code": "RBC",
                        "period_code": "Q1_2026",
                        "score": 0.94,
                        "match_sources": ["lexical"],
                        "matched_terms": ["average"],
                        "score_breakdown": {},
                        "content": "[Source | Page_8 | Personal Banking | RBC Q1_2026]\ncontent for Page_8",
                    },
                    {
                        "sheet_id": "sheet-16",
                        "sheet_name": "Page_16",
                        "page_title": "Selected Average Balance Sheet Items",
                        "bank_code": "RBC",
                        "period_code": "Q1_2026",
                        "score": 0.91,
                        "match_sources": ["metric_exact"],
                        "matched_terms": ["average earning assets"],
                        "score_breakdown": {},
                        "content": "[Source | Page_16 | Selected Average Balance Sheet Items | RBC Q1_2026]\ncontent for Page_16",
                    },
                ],
            }

    def fake_generate_answer(query: str, context_rows: list[dict[str, object]], config: DataSourcesConfig) -> str:
        assert [row["sheet_name"] for row in context_rows] == ["Page_2", "Page_8", "Page_16"]
        return "Average earning assets $2,191,100M [Source 3]; NIM 1.55% [Source 1]"

    def fake_judge_answer(
        query: str,
        answer: str,
        qdata: dict[str, object],
        ground_truth_pages: dict[str, str],
        cited_source_pages: dict[str, str],
        config: DataSourcesConfig,
    ) -> dict[str, object]:
        captured_ground_truth.update(ground_truth_pages)
        captured_cited_sources.update(cited_source_pages)
        return {
            "retrieval_accuracy": 5,
            "answer_accuracy": 4,
            "answer_completeness": 5,
            "retrieval_notes": "All pages found.",
            "accuracy_notes": "Minor rounding.",
            "completeness_notes": "Complete",
            "inaccurate_claims": [],
            "correct_pages_cited": ["Page_2", "Page_16"],
            "missing_pages": [],
            "overall_score": 5,
            "explanation": "Looks good",
        }

    monkeypatch.setattr(stress_test, "ALL_QUERIES", queries)
    monkeypatch.setattr(stress_test.DataSourcesConfig, "from_env", classmethod(lambda cls: _config()))
    monkeypatch.setattr(stress_test, "PostgresStore", _FakePostgresStore)
    monkeypatch.setattr(stress_test, "DataSourcesDB", _FakeDB)
    monkeypatch.setattr(stress_test, "SuppFinancialsRetriever", _FakeRetriever)
    monkeypatch.setattr(
        stress_test,
        "_fetch_target_content",
        lambda page_name, db, source: f"ground truth for {page_name}",
    )
    monkeypatch.setattr(stress_test, "_generate_answer", fake_generate_answer)
    monkeypatch.setattr(stress_test, "_judge_answer", fake_judge_answer)

    report = stress_test.run_stress_test(output_dir=tmp_path)

    query_report = report["queries"][0]
    assert captured_ground_truth == {
        "Page_16": "ground truth for Page_16",
        "Page_2": "ground truth for Page_2",
    }
    assert captured_cited_sources == {
        "Page_2": "content for Page_2",
        "Page_16": "content for Page_16",
    }
    assert query_report["hit"] is True
    assert query_report["rank"] == 3
    assert query_report["matched_answer_pages"] == ["Page_16", "Page_2"]
    assert query_report["missing_answer_pages"] == []
    assert query_report["answer_page_ranks"] == {"Page_2": 1, "Page_16": 3}
    assert query_report["answer_context_pages"] == ["Page_2", "Page_8", "Page_16"]
    assert query_report["target_contents"] == captured_ground_truth


def test_collect_cited_source_pages_maps_refs_to_correct_rows():
    rows = [
        {"sheet_name": "Page_1", "content": "[Source | Page_1 | Title1 | RBC Q1]\nData for page 1"},
        {"sheet_name": "Page_2", "content": "[Source | Page_2 | Title2 | RBC Q1]\nData for page 2"},
        {"sheet_name": "Page_3", "content": "[Source | Page_3 | Title3 | RBC Q1]\nData for page 3"},
    ]
    answer = "The answer uses [Source 1] and [Source 3]."
    result = stress_test._collect_cited_source_pages(answer, rows)

    assert "Page_1" in result
    assert "Page_3" in result
    assert "Page_2" not in result
    assert result["Page_1"] == "Data for page 1"
    assert result["Page_3"] == "Data for page 3"


def test_collect_cited_source_pages_handles_out_of_range_refs():
    rows = [
        {"sheet_name": "Page_1", "content": "[Source | Page_1 | T | RBC Q1]\nData"},
    ]
    answer = "See [Source 1] and [Source 99]."
    result = stress_test._collect_cited_source_pages(answer, rows)

    assert list(result.keys()) == ["Page_1"]


def test_collect_cited_source_pages_deduplicates_by_page_name():
    rows = [
        {"sheet_name": "Page_1", "content": "[Source | Page_1 | T | RBC Q1]\nFirst copy"},
        {"sheet_name": "Page_1", "content": "[Source | Page_1 | T | RBC Q1]\nSecond copy"},
    ]
    answer = "See [Source 1] and [Source 2]."
    result = stress_test._collect_cited_source_pages(answer, rows)

    assert len(result) == 1
    assert result["Page_1"] == "First copy"


def test_normalize_judgment_all_zero_yields_overall_zero():
    normalized = stress_test._normalize_judgment(
        {
            "retrieval_accuracy": 0,
            "answer_accuracy": 0,
            "answer_completeness": 0,
            "completeness_notes": "Nothing relevant",
            "correct_pages_cited": [],
            "overall_score": 2,
            "explanation": "Judge gave score despite zero dimensions.",
        }
    )

    assert normalized["overall_score"] == 0


def test_normalize_judgment_computes_rounded_average():
    normalized = stress_test._normalize_judgment(
        {
            "retrieval_accuracy": 5,
            "answer_accuracy": 3,
            "answer_completeness": 4,
            "completeness_notes": "Mostly complete",
            "correct_pages_cited": ["Page_34"],
            "overall_score": 1,
            "explanation": "Override ignored; average is used.",
        }
    )

    # (5 + 3 + 4) / 3 = 4.0 -> round -> 4
    assert normalized["overall_score"] == 4
