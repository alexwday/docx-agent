from __future__ import annotations

from word_ui.retrievers import (
    FunctionSourceRetriever,
    GenericMetadataRetriever,
    MockComplianceRetriever,
    MockEmployeeRetriever,
    MockFinancialDataRetriever,
    MockSalesOrdersRetriever,
    MockSupplierRiskRetriever,
    RetrieverRegistry,
    SearchIndexMetadataRetriever,
)


def test_registry_uses_source_override_before_type_fallback():
    registry = RetrieverRegistry(
        source_overrides={"risk_db.suppliers": "mock_supplier_risk"},
        type_overrides={"postgres_table": "generic_metadata"},
    )
    registry.register(MockSupplierRiskRetriever())
    registry.register(GenericMetadataRetriever())

    result = registry.run(
        source={
            "source_id": "risk_db.suppliers",
            "name": "Suppliers",
            "source_type": "postgres_table",
            "location": {},
            "schema_json": {},
        },
        research_statement="analyze supplier risk",
        query_terms=["supplier", "risk"],
    )

    assert result["retriever_id"] == "mock_supplier_risk"
    assert result["handler"] == "mock_supplier_risk_retriever"


def test_registry_supports_location_retriever_id_override():
    registry = RetrieverRegistry(
        source_overrides={},
        type_overrides={"search_index": "generic_metadata"},
    )
    registry.register(SearchIndexMetadataRetriever())
    registry.register(GenericMetadataRetriever())

    result = registry.run(
        source={
            "source_id": "notes.index",
            "name": "Notes Index",
            "source_type": "search_index",
            "location": {"retriever_id": "search_index_metadata", "index": "notes"},
            "schema_json": {},
        },
        research_statement="find notes about risk",
        query_terms=["risk"],
    )

    assert result["retriever_id"] == "search_index_metadata"
    assert result["handler"] == "search_index_probe"
    assert result["index_name"] == "notes"


def test_registry_allows_custom_function_retriever():
    registry = RetrieverRegistry(
        source_overrides={"custom.source": "custom:source"},
        type_overrides={},
    )
    registry.register(
        FunctionSourceRetriever(
            retriever_id="custom:source",
            fn=lambda **_: {
                "status": "completed",
                "handler": "custom_retriever",
                "mode": "mock_data",
                "relevance_score": 9,
            },
        )
    )
    registry.register(GenericMetadataRetriever())

    result = registry.run(
        source={"source_id": "custom.source", "source_type": "unknown", "location": {}, "schema_json": {}},
        research_statement="custom retrieval",
        query_terms=["custom"],
    )

    assert result["retriever_id"] == "custom:source"
    assert result["handler"] == "custom_retriever"
    assert result["relevance_score"] == 9


def test_financial_data_mock_retriever_returns_sample_rows():
    retriever = MockFinancialDataRetriever()
    result = retriever.run(
        source={"source_id": "finance_db.quarterly_metrics"},
        research_statement="quarterly revenue and margin trends",
        query_terms=["revenue", "margin"],
    )
    assert result["status"] == "completed"
    assert result["handler"] == "mock_financial_data_retriever"
    assert len(result["sample_rows"]) == 4
    assert all("revenue_m" in row and "margin_pct" in row for row in result["sample_rows"])


def test_compliance_mock_retriever_returns_findings():
    retriever = MockComplianceRetriever()
    result = retriever.run(
        source={"source_id": "compliance_db.audit_findings"},
        research_statement="audit findings with high severity",
        query_terms=["audit", "high"],
    )
    assert result["status"] == "completed"
    assert result["handler"] == "mock_compliance_retriever"
    assert len(result["sample_rows"]) == 5
    assert any(row["severity"] == "critical" for row in result["sample_rows"])


def test_employee_metrics_mock_retriever_returns_team_data():
    retriever = MockEmployeeRetriever()
    result = retriever.run(
        source={"source_id": "hr_db.team_performance"},
        research_statement="team attrition and performance",
        query_terms=["attrition", "engineering"],
    )
    assert result["status"] == "completed"
    assert result["handler"] == "mock_employee_metrics_retriever"
    assert len(result["sample_rows"]) == 4
    assert any(row["team"] == "Engineering" for row in result["sample_rows"])


def test_registry_resolves_all_five_mock_sources():
    registry = RetrieverRegistry(
        source_overrides={
            "risk_db.suppliers": "mock_supplier_risk",
            "sales_db.orders": "mock_sales_orders",
            "finance_db.quarterly_metrics": "mock_financial_data",
            "compliance_db.audit_findings": "mock_compliance_findings",
            "hr_db.team_performance": "mock_employee_metrics",
        },
    )
    registry.register(MockSupplierRiskRetriever())
    registry.register(MockSalesOrdersRetriever())
    registry.register(MockFinancialDataRetriever())
    registry.register(MockComplianceRetriever())
    registry.register(MockEmployeeRetriever())
    registry.register(GenericMetadataRetriever())

    source_ids = [
        "risk_db.suppliers",
        "sales_db.orders",
        "finance_db.quarterly_metrics",
        "compliance_db.audit_findings",
        "hr_db.team_performance",
    ]
    expected_retriever_ids = [
        "mock_supplier_risk",
        "mock_sales_orders",
        "mock_financial_data",
        "mock_compliance_findings",
        "mock_employee_metrics",
    ]

    for source_id, expected_id in zip(source_ids, expected_retriever_ids):
        resolved = registry.resolve_retriever_id({"source_id": source_id, "location": {}, "source_type": "postgres_table"})
        assert resolved == expected_id, f"{source_id} resolved to {resolved}, expected {expected_id}"
