from __future__ import annotations

from data_sources.scripts.stress_test_report import render_html_report


def test_render_html_report_uses_query_tabs_and_simplified_panels():
    report = {
        "generated_at_utc": "2026-03-05T16:26:00+00:00",
        "source_context": {"schema_json": {"bank_code": "RBC", "period_code": "Q1_2026"}},
        "summary": {
            "retrieval": {"hit_rate": 100.0},
            "answer_quality": {
                "scored_queries": 2,
                "average_retrieval_accuracy": 4.5,
                "average_answer_accuracy": 4.5,
                "average_completeness": 4.0,
                "average_overall": 4.5,
            },
        },
        "queries": [
            {
                "query_num": 1,
                "query": "First unique query",
                "why_hard": "Requires mapping a user term to the exact disclosure label.",
                "difficulty": "hard",
                "target_page": "Page_32",
                "rank": 1,
                "model_answer": (
                    "### Summary Response\n\n"
                    "The amount was 42.\n\n"
                    "### Detailed Response\n\n"
                    "The data from the source shows: [Source 1]\n\n"
                    "| Data Source | Bank | Platform | Metric | Value | Type |\n"
                    "| --- | --- | --- | --- | --- | --- |\n"
                    "| Supplementary Financials | RY | Enterprise | Amount | 42 | $M |\n\n"
                    "[1] Page_32, \"Section A\", \"Table 1\"\n\n"
                    "### Notes\n\n"
                    "- No assumptions required.\n"
                ),
                "retrieval_accuracy": 5,
                "answer_accuracy": 5,
                "answer_completeness": 5,
                "overall_score": 5,
                "explanation": "The answer is faithful and complete.",
                "judge": {
                    "retrieval_notes": "Target page retrieved at rank 1.",
                    "completeness_notes": "Everything required is present.",
                    "accuracy_notes": "All values match the source.",
                    "correct_pages_cited": ["Page_32"],
                    "missing_pages": [],
                },
                "inaccurate_claims": [],
                "validated_answer_summary": "Validated summary for query one.",
                "validated_answer_citations": ["Amount: 42"],
                "answer_pages": ["Page_32"],
                "target_contents": {"Page_32": "Ground truth content should not appear."},
            },
            {
                "query_num": 2,
                "query": "Second unique query",
                "why_hard": "Needs multi-step reasoning across a table and a footnote.",
                "difficulty": "medium",
                "target_page": "Page_38",
                "rank": 2,
                "model_answer": "Plain text answer.",
                "retrieval_accuracy": 4,
                "answer_accuracy": 4,
                "answer_completeness": 3,
                "overall_score": 4,
                "explanation": "The answer is mostly complete.",
                "judge": {
                    "retrieval_notes": "Target page retrieved at rank 2.",
                    "completeness_notes": "One caveat was omitted.",
                    "accuracy_notes": "Values are correct.",
                    "correct_pages_cited": ["Page_38"],
                    "missing_pages": [],
                },
                "inaccurate_claims": [],
                "validated_answer_summary": "Validated summary for query two.",
                "validated_answer_citations": ["Metric: 84"],
                "answer_pages": ["Page_38"],
                "target_contents": {"Page_38": "Second ground truth content should not appear."},
            },
        ],
    }

    html = render_html_report(report)

    assert "Curated Q&amp;A Stress Test" not in html
    assert "Retrieved Source Pages" not in html
    assert "Ground truth source content" not in html
    assert "Raw judge JSON" not in html
    assert "Target Page_32" not in html
    assert "HARD" not in html

    assert "<h2>First unique query</h2>" in html
    assert "<h2>Second unique query</h2>" in html
    assert ">Q1</button>" in html
    assert ">Q2</button>" in html
    assert "Why is this challenging?" in html

    assert "<h3>Summary Response</h3>" in html
    assert "<table>" in html
    assert "Analysis of Test Response:" in html
    assert "Expected Response:" in html
    assert "Validated summary for query one." in html
    assert "Performance Testing" in html
    assert "sidebar" in html


def test_sanitize_html_escapes_script_tags():
    from data_sources.scripts.stress_test_report import _sanitize_html

    dirty = '<p>Hello</p><script>alert("xss")</script><strong>OK</strong>'
    clean = _sanitize_html(dirty)

    assert "<script>" not in clean
    assert "&lt;script&gt;" in clean
    assert "<p>Hello</p>" in clean
    assert "<strong>OK</strong>" in clean
