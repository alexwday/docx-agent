from __future__ import annotations

from contextlib import contextmanager
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
from data_sources.ingest.llm_extractor import extract_sheet_metadata
from data_sources.ingest.pipeline import _resolve_context_chains, ingest_supplementary_report
from data_sources.models import RawSheet, ReportSheet, SheetExtraction


class _FakeCursor:
    def __init__(self, executed: list[tuple[str, tuple]]) -> None:
        self.executed = executed

    def __enter__(self) -> _FakeCursor:
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None

    def execute(self, sql: str, params: tuple) -> None:
        self.executed.append((sql, params))


class _FakeConnection:
    def __init__(self, executed: list[tuple[str, tuple]]) -> None:
        self.executed = executed

    def __enter__(self) -> _FakeConnection:
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None

    def cursor(self) -> _FakeCursor:
        return _FakeCursor(self.executed)

    def commit(self) -> None:
        return None


class _FakeStore:
    def __init__(self, executed: list[tuple[str, tuple]]) -> None:
        self.executed = executed

    @contextmanager
    def connection(self):
        yield _FakeConnection(self.executed)


class _FakeDB:
    def __init__(self) -> None:
        self.inserted_sheets: list[dict] = []
        self.inserted_keywords: list[dict] = []
        self.inserted_metrics: list[dict] = []
        self.executed: list[tuple[str, tuple]] = []
        self.store = _FakeStore(self.executed)
        self.document_id = uuid4()

    def upsert_document(self, **_: object) -> dict:
        return {"document_id": self.document_id}

    def delete_sheets_for_document(self, document_id) -> int:
        assert document_id == self.document_id
        return 0

    def insert_sheet(self, **kwargs: object) -> dict:
        self.inserted_sheets.append(dict(kwargs))
        return {"sheet_id": uuid4()}

    def insert_metrics(self, **kwargs: object) -> int:
        self.inserted_metrics.append(dict(kwargs))
        return len(kwargs.get("metrics", []))

    def insert_keyword_embeddings(self, **kwargs: object) -> int:
        self.inserted_keywords.append(dict(kwargs))
        return len(kwargs.get("keywords", []))


def _config() -> DataSourcesConfig:
    return DataSourcesConfig(
        database_dsn="postgresql://unit-test",
        openai_api_key="test-key",
    )


def test_ingestion_embeds_title_only_summaries_and_contextualized_keywords(monkeypatch):
    raw_sheets = [
        RawSheet(sheet_index=0, sheet_name="Page_1", raw_content="Alpha content"),
        RawSheet(sheet_index=1, sheet_name="Page_2", raw_content="Beta content"),
    ]
    extractions = [
        SheetExtraction(
            page_title="Alpha Page",
            is_data_sheet=True,
            summary=None,
            keywords=["total"],
            metrics=[],
            requires_prior_context=False,
            context_note=None,
        ),
        SheetExtraction(
            page_title="Beta Page",
            is_data_sheet=True,
            summary="Detailed beta summary",
            keywords=["total"],
            metrics=[],
            requires_prior_context=False,
            context_note=None,
        ),
    ]
    db = _FakeDB()
    embed_calls: list[list[str]] = []

    monkeypatch.setattr("data_sources.ingest.pipeline.read_excel_sheets", lambda _: raw_sheets)
    monkeypatch.setattr(
        "data_sources.ingest.pipeline.extract_sheet_metadata",
        lambda raw, **_: extractions[raw.sheet_index],
    )

    def fake_embed_texts(texts: list[str], **_: object) -> list[list[float]]:
        embed_calls.append(list(texts))
        return [[float(index + 1)] for index in range(len(texts))]

    monkeypatch.setattr("data_sources.ingest.pipeline.embed_texts", fake_embed_texts)

    ingest_supplementary_report(
        file_path="dummy.xlsx",
        bank_code="RBC",
        report_type="supp_financials",
        period_code="Q1_2026",
        fiscal_year=2026,
        fiscal_quarter=1,
        config=_config(),
        db=db,
    )

    assert ["Alpha Page", "Beta Page\nDetailed beta summary"] in embed_calls
    assert ["Alpha Page | keyword: total", "Beta Page | keyword: total"] in embed_calls
    assert db.inserted_sheets[0]["summary_embedding"] == [1.0]
    assert db.inserted_sheets[1]["summary_embedding"] == [2.0]
    assert db.inserted_keywords[0]["embeddings"] == [[1.0]]
    assert db.inserted_keywords[1]["embeddings"] == [[2.0]]


def test_resolve_context_chains_links_back_across_continuation_run():
    first_id = uuid4()
    second_id = uuid4()
    third_id = uuid4()
    db = _FakeDB()
    sheets = [
        ReportSheet(
            sheet_index=0,
            sheet_name="Page_31",
            raw_content="",
            page_title="Page 31",
            is_data_sheet=True,
            summary=None,
            keywords=[],
            metrics=[],
            metadata={"requires_prior_context": False},
        ),
        ReportSheet(
            sheet_index=1,
            sheet_name="Page_32",
            raw_content="",
            page_title="Page 32",
            is_data_sheet=True,
            summary=None,
            keywords=[],
            metrics=[],
            metadata={"requires_prior_context": True},
        ),
        ReportSheet(
            sheet_index=2,
            sheet_name="Page_33",
            raw_content="",
            page_title="Page 33",
            is_data_sheet=True,
            summary=None,
            keywords=[],
            metrics=[],
            metadata={"requires_prior_context": True},
        ),
    ]

    _resolve_context_chains(
        sheets,
        {0: first_id, 1: second_id, 2: third_id},
        db,
    )

    assert len(db.executed) == 2
    _, first_update_params = db.executed[0]
    _, second_update_params = db.executed[1]
    assert first_update_params[0] == [str(first_id)]
    assert second_update_params[0] == [str(first_id), str(second_id)]


def test_extract_sheet_metadata_parse_fallback_marks_cover_page_non_data(monkeypatch):
    class _FakeCompletions:
        @staticmethod
        def create(**_: object):
            return types.SimpleNamespace(
                choices=[types.SimpleNamespace(message=types.SimpleNamespace(content="{invalid"))]
            )

    class _FakeClient:
        def __init__(self, **_: object) -> None:
            self.chat = types.SimpleNamespace(completions=_FakeCompletions())

    monkeypatch.setattr("data_sources.ingest.llm_extractor.build_openai_client", lambda _: _FakeClient())

    result = extract_sheet_metadata(
        RawSheet(sheet_index=0, sheet_name="Cover Page", raw_content="Cover page and table of contents"),
        config=_config(),
    )

    assert result.page_title == "Cover Page"
    assert result.is_data_sheet is False
    assert result.keywords == []
