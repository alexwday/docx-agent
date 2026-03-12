"""CLI: Test retrieval against ingested supplementary financial data.

Usage:
    python -m data_sources.scripts.test_retrieve "What is RBC's CET1 ratio?"
    python -m data_sources.scripts.test_retrieve "Personal Banking credit quality" --bank RBC --period Q1_2026
"""

from __future__ import annotations

import argparse
import logging
import sys

from data_sources.config import DataSourcesConfig
from data_sources.db import DataSourcesDB
from data_sources.retrieve.supp_financials import SuppFinancialsRetriever
from word_store.db import PostgresStore


def main() -> None:
    parser = argparse.ArgumentParser(description="Test retrieval against supplementary financial data.")
    parser.add_argument("query", help="Research statement / question to search for")
    parser.add_argument("--bank", default=None, help="Filter by bank code (e.g. RBC)")
    parser.add_argument("--period", default=None, help="Filter by period code (e.g. Q1_2026)")
    parser.add_argument("--terms", nargs="*", default=None, help="Explicit query terms (space-separated)")
    parser.add_argument("--top-k", type=int, default=5, help="Number of results to return")
    parser.add_argument("-v", "--verbose", action="store_true", help="Enable debug logging")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)-8s %(name)s  %(message)s",
    )

    config = DataSourcesConfig.from_env()
    config.reranker_top_k = args.top_k
    store = PostgresStore(dsn=config.database_dsn)
    db = DataSourcesDB(store)

    retriever = SuppFinancialsRetriever(config=config, db=db)

    # Build query terms from the query if not explicitly provided
    query_terms = args.terms
    if query_terms is None:
        # Simple tokenization: split on spaces, lowercase, remove short words
        query_terms = [
            w.lower().strip(".,;:!?")
            for w in args.query.split()
            if len(w) > 2
        ]

    # Build a minimal source dict with optional filters
    source: dict = {
        "source_id": "supp_financials",
        "source_type": "financial_report",
        "location": {"retriever_id": "supp_financials"},
        "schema_json": {},
    }
    if args.bank:
        source["schema_json"]["bank_code"] = args.bank.upper()
    if args.period:
        source["schema_json"]["period_code"] = args.period

    result = retriever.run(
        source=source,
        research_statement=args.query,
        query_terms=query_terms,
    )

    print(f"\n=== Retrieval Results ({result['status']}) ===")
    print(f"Summary: {result.get('summary', 'N/A')}")
    print(f"Relevance score: {result.get('relevance_score', 0)}")
    print(f"Matched terms: {result.get('matched_terms', [])}")
    print()

    for i, row in enumerate(result.get("sample_rows", []), 1):
        print(f"--- Result {i}: {row.get('page_title', row.get('sheet_name', 'Unknown'))} ---")
        print(f"    Bank: {row.get('bank_code')} | Period: {row.get('period_code')}")
        print(f"    Score: {row.get('score', 0):.3f} | Via: {', '.join(row.get('match_sources', []))}")
        # Print first 500 chars of content as preview
        content = row.get("content", "")
        if len(content) > 500:
            content = content[:500] + "\n    ... [truncated]"
        print(f"    Content preview:\n{content}")
        print()


if __name__ == "__main__":
    main()
