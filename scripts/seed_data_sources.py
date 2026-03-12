"""Seed the data_source_catalog table with mock data sources."""

from __future__ import annotations

from word_store import DataSourcesRepository, PostgresStore


def main() -> None:
    store = PostgresStore()
    repo = DataSourcesRepository(store)

    sources = [
        {
            "source_id": "risk_db.suppliers",
            "name": "Supplier Risk Database",
            "source_type": "postgres_table",
            "location": {
                "host": "risk-db.internal",
                "database": "risk",
                "schema": "public",
                "table": "suppliers",
                "research_output_format": "docx",
            },
            "schema_json": {
                "columns": [
                    {"name": "supplier_id", "type": "text", "description": "Unique supplier identifier"},
                    {"name": "supplier_name", "type": "text", "description": "Supplier company name"},
                    {"name": "risk_score", "type": "integer", "description": "Risk score 0-100"},
                    {"name": "primary_risk", "type": "text", "description": "Primary risk category"},
                ],
            },
        },
        {
            "source_id": "sales_db.orders",
            "name": "Sales Orders",
            "source_type": "postgres_table",
            "location": {
                "host": "sales-db.internal",
                "database": "sales",
                "schema": "public",
                "table": "orders",
                "research_output_format": "docx",
            },
            "schema_json": {
                "columns": [
                    {"name": "order_id", "type": "text", "description": "Order identifier"},
                    {"name": "region", "type": "text", "description": "Sales region code"},
                    {"name": "status", "type": "text", "description": "Order status"},
                    {"name": "days_late", "type": "integer", "description": "Days past expected delivery"},
                ],
            },
        },
        {
            "source_id": "finance_db.quarterly_metrics",
            "name": "Quarterly Financial Metrics",
            "source_type": "warehouse_view",
            "location": {
                "host": "finance-dw.internal",
                "database": "finance",
                "schema": "reporting",
                "view": "quarterly_metrics",
                "research_output_format": "docx",
            },
            "schema_json": {
                "columns": [
                    {"name": "quarter", "type": "text", "description": "Fiscal quarter label"},
                    {"name": "revenue_m", "type": "numeric", "description": "Revenue in millions USD"},
                    {"name": "expenses_m", "type": "numeric", "description": "Total expenses in millions USD"},
                    {"name": "margin_pct", "type": "numeric", "description": "Profit margin percentage"},
                    {"name": "yoy_growth_pct", "type": "numeric", "description": "Year-over-year revenue growth %"},
                ],
            },
        },
        {
            "source_id": "compliance_db.audit_findings",
            "name": "Compliance Audit Findings",
            "source_type": "postgres_table",
            "location": {
                "host": "compliance-db.internal",
                "database": "compliance",
                "schema": "audit",
                "table": "findings",
                "research_output_format": "docx",
            },
            "schema_json": {
                "columns": [
                    {"name": "finding_id", "type": "text", "description": "Audit finding identifier"},
                    {"name": "category", "type": "text", "description": "Compliance category"},
                    {"name": "severity", "type": "text", "description": "Finding severity: low, medium, high, critical"},
                    {"name": "status", "type": "text", "description": "Remediation status"},
                    {"name": "owner", "type": "text", "description": "Responsible department"},
                ],
            },
        },
        {
            "source_id": "hr_db.team_performance",
            "name": "Team Performance Metrics",
            "source_type": "warehouse_view",
            "location": {
                "host": "hr-dw.internal",
                "database": "hr",
                "schema": "analytics",
                "view": "team_performance",
                "research_output_format": "docx",
            },
            "schema_json": {
                "columns": [
                    {"name": "team", "type": "text", "description": "Department or team name"},
                    {"name": "headcount", "type": "integer", "description": "Current team headcount"},
                    {"name": "attrition_pct", "type": "numeric", "description": "Annual attrition rate %"},
                    {"name": "avg_performance", "type": "numeric", "description": "Average performance rating 1-5"},
                ],
            },
        },
    ]

    for src in sources:
        result = repo.upsert_source(**src)
        print(f"  Upserted: {result['source_id']} — {result['name']}")  # noqa: T201

    print(f"\nSeeded {len(sources)} data sources.")  # noqa: T201


if __name__ == "__main__":
    main()
