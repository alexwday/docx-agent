"""Retriever plugin interfaces and registry for data-source research tools."""

from __future__ import annotations

from typing import Any, Callable, Protocol


def match_terms_count(haystack: str, query_terms: list[str]) -> int:
    if not haystack or not query_terms:
        return 0
    return sum(1 for term in query_terms if term in haystack)


def source_haystack(source: dict[str, Any]) -> str:
    location = source.get("location")
    schema_json = source.get("schema_json")
    return " ".join(
        [
            str(source.get("source_id") or ""),
            str(source.get("name") or ""),
            str(source.get("source_type") or ""),
            str(location or ""),
            str(schema_json or ""),
        ]
    ).lower()


class SourceRetriever(Protocol):
    """Contract for data-source retriever plugins."""

    retriever_id: str

    def run(
        self,
        *,
        source: dict[str, Any],
        research_statement: str,
        query_terms: list[str],
    ) -> dict[str, Any]:
        """Run retrieval and return a structured result payload."""


class FunctionSourceRetriever:
    """Adapter for function-based retrievers."""

    def __init__(
        self,
        *,
        retriever_id: str,
        fn: Callable[..., dict[str, Any]],
    ) -> None:
        self.retriever_id = retriever_id
        self._fn = fn

    def run(
        self,
        *,
        source: dict[str, Any],
        research_statement: str,
        query_terms: list[str],
    ) -> dict[str, Any]:
        return self._fn(
            source=source,
            research_statement=research_statement,
            query_terms=query_terms,
        )


class MockSupplierRiskRetriever:
    """Mock retriever for supplier risk source data."""

    retriever_id = "mock_supplier_risk"

    def run(
        self,
        *,
        source: dict[str, Any],
        research_statement: str,
        query_terms: list[str],
    ) -> dict[str, Any]:
        sample_rows = [
            {
                "supplier_id": "SUP-104",
                "supplier_name": "Apex Plastics",
                "risk_score": 87,
                "primary_risk": "Late deliveries",
            },
            {
                "supplier_id": "SUP-221",
                "supplier_name": "North Ridge Metals",
                "risk_score": 79,
                "primary_risk": "Quality deviations",
            },
            {
                "supplier_id": "SUP-019",
                "supplier_name": "Summit Components",
                "risk_score": 74,
                "primary_risk": "Capacity constraints",
            },
        ]
        hay = " ".join(
            [
                research_statement.lower(),
                " ".join(str(value) for row in sample_rows for value in row.values()).lower(),
            ]
        )
        matched_terms = [term for term in query_terms if term in hay][:8]
        return {
            "status": "completed",
            "handler": "mock_supplier_risk_retriever",
            "mode": "mock_data",
            "matched_terms": matched_terms,
            "sample_rows": sample_rows,
            "summary": (
                "Supplier risk mock retriever identified high-risk suppliers with primary delays, "
                "quality deviations, and capacity constraints."
            ),
            "relevance_score": len(matched_terms) + 2,
        }


class MockSalesOrdersRetriever:
    """Mock retriever for sales order source data."""

    retriever_id = "mock_sales_orders"

    def run(
        self,
        *,
        source: dict[str, Any],
        research_statement: str,
        query_terms: list[str],
    ) -> dict[str, Any]:
        sample_rows = [
            {"order_id": "ORD-7781", "region": "NA", "status": "delayed", "days_late": 6},
            {"order_id": "ORD-7788", "region": "EU", "status": "on_time", "days_late": 0},
            {"order_id": "ORD-7794", "region": "NA", "status": "delayed", "days_late": 4},
        ]
        hay = " ".join(
            [
                research_statement.lower(),
                " ".join(str(value) for row in sample_rows for value in row.values()).lower(),
            ]
        )
        matched_terms = [term for term in query_terms if term in hay][:8]
        return {
            "status": "completed",
            "handler": "mock_sales_orders_retriever",
            "mode": "mock_data",
            "matched_terms": matched_terms,
            "sample_rows": sample_rows,
            "summary": "Sales orders mock retriever shows recent delayed-order concentration in the NA region.",
            "relevance_score": len(matched_terms) + 1,
        }


class MockFinancialDataRetriever:
    """Mock retriever for quarterly financial metrics."""

    retriever_id = "mock_financial_data"

    def run(
        self,
        *,
        source: dict[str, Any],
        research_statement: str,
        query_terms: list[str],
    ) -> dict[str, Any]:
        sample_rows = [
            {"quarter": "Q1-2025", "revenue_m": 42.1, "expenses_m": 31.8, "margin_pct": 24.5, "yoy_growth_pct": 8.2},
            {"quarter": "Q2-2025", "revenue_m": 45.7, "expenses_m": 33.2, "margin_pct": 27.4, "yoy_growth_pct": 11.1},
            {"quarter": "Q3-2025", "revenue_m": 39.3, "expenses_m": 30.5, "margin_pct": 22.4, "yoy_growth_pct": 3.6},
            {"quarter": "Q4-2025", "revenue_m": 51.2, "expenses_m": 36.1, "margin_pct": 29.5, "yoy_growth_pct": 14.8},
        ]
        hay = " ".join(
            [
                research_statement.lower(),
                " ".join(str(value) for row in sample_rows for value in row.values()).lower(),
            ]
        )
        matched_terms = [term for term in query_terms if term in hay][:8]
        return {
            "status": "completed",
            "handler": "mock_financial_data_retriever",
            "mode": "mock_data",
            "matched_terms": matched_terms,
            "sample_rows": sample_rows,
            "summary": (
                "Quarterly financial mock shows strong Q4 revenue of $51.2M with 29.5% margin "
                "and 14.8% YoY growth, while Q3 dipped to $39.3M."
            ),
            "relevance_score": len(matched_terms) + 2,
        }


class MockComplianceRetriever:
    """Mock retriever for compliance audit findings."""

    retriever_id = "mock_compliance_findings"

    def run(
        self,
        *,
        source: dict[str, Any],
        research_statement: str,
        query_terms: list[str],
    ) -> dict[str, Any]:
        sample_rows = [
            {"finding_id": "AUD-301", "category": "Data Privacy", "severity": "high", "status": "open", "owner": "Legal"},
            {"finding_id": "AUD-302", "category": "Access Control", "severity": "critical", "status": "remediation", "owner": "IT Security"},
            {"finding_id": "AUD-303", "category": "Financial Reporting", "severity": "medium", "status": "closed", "owner": "Finance"},
            {"finding_id": "AUD-304", "category": "Vendor Management", "severity": "high", "status": "open", "owner": "Procurement"},
            {"finding_id": "AUD-305", "category": "Business Continuity", "severity": "low", "status": "closed", "owner": "Operations"},
        ]
        hay = " ".join(
            [
                research_statement.lower(),
                " ".join(str(value) for row in sample_rows for value in row.values()).lower(),
            ]
        )
        matched_terms = [term for term in query_terms if term in hay][:8]
        return {
            "status": "completed",
            "handler": "mock_compliance_retriever",
            "mode": "mock_data",
            "matched_terms": matched_terms,
            "sample_rows": sample_rows,
            "summary": (
                "Compliance audit mock shows 1 critical access-control finding in remediation, "
                "2 high-severity open findings in data privacy and vendor management."
            ),
            "relevance_score": len(matched_terms) + 2,
        }


class MockEmployeeRetriever:
    """Mock retriever for team performance metrics."""

    retriever_id = "mock_employee_metrics"

    def run(
        self,
        *,
        source: dict[str, Any],
        research_statement: str,
        query_terms: list[str],
    ) -> dict[str, Any]:
        sample_rows = [
            {"team": "Engineering", "headcount": 48, "attrition_pct": 6.2, "avg_performance": 4.1},
            {"team": "Sales", "headcount": 32, "attrition_pct": 12.5, "avg_performance": 3.8},
            {"team": "Operations", "headcount": 24, "attrition_pct": 4.1, "avg_performance": 4.3},
            {"team": "Marketing", "headcount": 18, "attrition_pct": 8.3, "avg_performance": 3.9},
        ]
        hay = " ".join(
            [
                research_statement.lower(),
                " ".join(str(value) for row in sample_rows for value in row.values()).lower(),
            ]
        )
        matched_terms = [term for term in query_terms if term in hay][:8]
        return {
            "status": "completed",
            "handler": "mock_employee_metrics_retriever",
            "mode": "mock_data",
            "matched_terms": matched_terms,
            "sample_rows": sample_rows,
            "summary": (
                "Employee metrics mock shows Sales team with highest attrition at 12.5%, "
                "while Operations leads in performance (4.3 avg) with lowest attrition (4.1%)."
            ),
            "relevance_score": len(matched_terms) + 1,
        }


class SearchIndexMetadataRetriever:
    """Metadata-only search-index retriever."""

    retriever_id = "search_index_metadata"

    def run(
        self,
        *,
        source: dict[str, Any],
        research_statement: str,
        query_terms: list[str],
    ) -> dict[str, Any]:
        location = source.get("location")
        if not isinstance(location, dict):
            location = {}
        index_name = (
            str(location.get("index") or "").strip()
            or str(location.get("collection") or "").strip()
            or str(source.get("source_id") or "")
        )
        hay = source_haystack(source)
        matched_terms = [term for term in query_terms if term in hay]
        return {
            "status": "completed",
            "handler": "search_index_probe",
            "mode": "metadata_only",
            "index_name": index_name,
            "matched_terms": matched_terms[:8],
            "relevance_score": len(matched_terms),
        }


class GenericMetadataRetriever:
    """Fallback metadata-only retriever."""

    retriever_id = "generic_metadata"

    def run(
        self,
        *,
        source: dict[str, Any],
        research_statement: str,
        query_terms: list[str],
    ) -> dict[str, Any]:
        hay = source_haystack(source)
        score = match_terms_count(hay, query_terms)
        return {
            "status": "completed",
            "handler": "generic_source_probe",
            "mode": "metadata_only",
            "relevance_score": score,
        }


class PostgresRelationProbeRetriever:
    """Adapter for relation-level Postgres probe callback."""

    retriever_id = "postgres_relation_probe"

    def __init__(
        self,
        *,
        probe_fn: Callable[..., dict[str, Any]],
        max_rows: int = 5,
    ) -> None:
        self._probe_fn = probe_fn
        self._max_rows = max_rows

    def run(
        self,
        *,
        source: dict[str, Any],
        research_statement: str,
        query_terms: list[str],
    ) -> dict[str, Any]:
        return self._probe_fn(
            source=source,
            query_terms=query_terms,
            max_rows=self._max_rows,
        )


class RetrieverRegistry:
    """Registry that resolves and runs retrievers for a source."""

    def __init__(
        self,
        *,
        source_overrides: dict[str, str] | None = None,
        type_overrides: dict[str, str] | None = None,
    ) -> None:
        self.retrievers: dict[str, SourceRetriever] = {}
        self.source_overrides = dict(source_overrides or {})
        self.type_overrides = dict(type_overrides or {})

    def register(self, retriever: SourceRetriever) -> None:
        self.retrievers[retriever.retriever_id] = retriever

    def resolve_retriever_id(self, source: dict[str, Any]) -> str:
        source_id = str(source.get("source_id") or "")
        location = source.get("location")
        if not isinstance(location, dict):
            location = {}

        override_id = self.source_overrides.get(source_id)
        if override_id and override_id in self.retrievers:
            return override_id

        location_retriever_id = str(location.get("retriever_id") or "").strip()
        if location_retriever_id and location_retriever_id in self.retrievers:
            return location_retriever_id

        source_type = str(source.get("source_type") or "").lower()
        type_retriever_id = self.type_overrides.get(source_type)
        if type_retriever_id and type_retriever_id in self.retrievers:
            return type_retriever_id

        return "generic_metadata"

    def run(
        self,
        *,
        source: dict[str, Any],
        research_statement: str,
        query_terms: list[str],
    ) -> dict[str, Any]:
        retriever_id = self.resolve_retriever_id(source)
        retriever = self.retrievers.get(retriever_id)
        if retriever is None:
            raise ValueError(f"retriever not registered: {retriever_id}")
        output = retriever.run(
            source=source,
            research_statement=research_statement,
            query_terms=query_terms,
        )
        if not isinstance(output, dict):
            return {
                "status": "failed",
                "handler": "retriever_registry",
                "mode": "registry",
                "error": "retriever returned non-dict output",
                "relevance_score": 0,
                "retriever_id": retriever_id,
            }
        result = dict(output)
        result.setdefault("status", "completed")
        result.setdefault("retriever_id", retriever_id)
        result.setdefault("relevance_score", 0)
        return result
