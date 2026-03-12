"""Structured JSON and HTML reporting for the stress test runner."""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from html import escape
from pathlib import Path
from typing import Any

try:
    from markdown_it import MarkdownIt
except ImportError:  # pragma: no cover - fallback is exercised if dependency is absent.
    MarkdownIt = None  # type: ignore[assignment,misc]


def build_report_payload(
    *,
    query_results: list[dict[str, Any]],
    config: Any,
    sources: list[dict[str, Any]],
) -> dict[str, Any]:
    """Build a structured report payload from per-query stress test results."""
    total = len(query_results)
    # Exclude TBD queries from hit-rate metrics
    evaluable = [row for row in query_results if row.get("hit") is not None]
    hits = sum(1 for row in evaluable if row.get("hit"))
    misses = len(evaluable) - hits

    by_difficulty: dict[str, dict[str, Any]] = {}
    for difficulty in ("easy", "medium", "hard"):
        subset = [row for row in evaluable if row.get("difficulty") == difficulty]
        if not subset:
            continue
        diff_hits = sum(1 for row in subset if row.get("hit"))
        by_difficulty[difficulty] = {
            "total": len(subset),
            "hits": diff_hits,
            "hit_rate": round((diff_hits / len(subset)) * 100, 1),
        }

    scored = [row for row in query_results if int(row.get("overall_score") or 0) > 0]
    avg_retrieval = (
        round(sum(float(row.get("retrieval_accuracy") or 0) for row in scored) / len(scored), 2)
        if scored
        else None
    )
    avg_accuracy = (
        round(sum(float(row.get("answer_accuracy") or 0) for row in scored) / len(scored), 2)
        if scored
        else None
    )
    avg_completeness = (
        round(sum(float(row.get("answer_completeness") or 0) for row in scored) / len(scored), 2)
        if scored
        else None
    )
    avg_overall = (
        round(sum(float(row.get("overall_score") or 0) for row in scored) / len(scored), 2)
        if scored
        else None
    )
    overall_scores = {1: 0, 2: 0, 3: 0, 4: 0, 5: 0}
    for row in scored:
        score = int(row.get("overall_score") or 0)
        if score in overall_scores:
            overall_scores[score] += 1

    hit_sources: dict[str, int] = {}
    for row in query_results:
        if row.get("hit") and row.get("via"):
            for source_name in row["via"]:
                hit_sources[source_name] = hit_sources.get(source_name, 0) + 1

    hit_ranks = [int(row["rank"]) for row in evaluable if row.get("hit") and row.get("rank")]

    summary = {
        "total_queries": total,
        "evaluable_queries": len(evaluable),
        "tbd_queries": total - len(evaluable),
        "retrieval": {
            "hits": hits,
            "misses": misses,
            "hit_rate": round((hits / len(evaluable)) * 100, 1) if evaluable else 0.0,
            "average_hit_rank": round(sum(hit_ranks) / len(hit_ranks), 2) if hit_ranks else None,
            "hit_sources": hit_sources,
            "by_difficulty": by_difficulty,
        },
        "answer_quality": {
            "scored_queries": len(scored),
            "average_retrieval_accuracy": avg_retrieval,
            "average_answer_accuracy": avg_accuracy,
            "average_completeness": avg_completeness,
            "average_overall": avg_overall,
            "overall_score_distribution": overall_scores,
        },
    }

    return {
        "report_type": "stress_test",
        "report_version": 2,
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "config": {
            "retrieval_model": getattr(config, "retrieval_model", None),
            "retrieval_top_k": getattr(config, "retrieval_top_k", None),
            "reranker_top_k": getattr(config, "reranker_top_k", None),
        },
        "sources_context": [
            {
                "source_id": s.get("source_id"),
                "source_type": s.get("source_type"),
                "report_type": s.get("report_type"),
                "retriever_id": (s.get("location") or {}).get("retriever_id"),
                "schema_json": s.get("schema_json", {}),
            }
            for s in sources
        ],
        "summary": summary,
        "queries": query_results,
    }


def write_report_files(report: dict[str, Any], output_dir: Path) -> dict[str, Path]:
    """Write JSON and HTML report files to disk."""
    output_dir.mkdir(parents=True, exist_ok=True)

    json_path = output_dir / "stress_test_report.json"
    html_path = output_dir / "stress_test_report.html"

    json_path.write_text(json.dumps(report, indent=2) + "\n")
    html_path.write_text(render_html_report(report))

    return {"json": json_path, "html": html_path}


_MARKDOWN_RENDERER = (
    MarkdownIt("commonmark", {"html": False, "breaks": True}).enable("table")
    if MarkdownIt is not None
    else None
)


_SAFE_HTML_TAGS = frozenset({
    "p", "h1", "h2", "h3", "h4", "h5", "h6",
    "ul", "ol", "li",
    "table", "thead", "tbody", "tfoot", "tr", "th", "td",
    "code", "pre", "em", "strong", "blockquote", "hr", "br",
    "a", "div", "span",
})

_HTML_TAG_RE = re.compile(r"<(/?)(\w+)(\s[^>]*)?>", re.IGNORECASE)


def _sanitize_html(html: str) -> str:
    """Escape HTML tags not in the safe allowlist."""
    def _replace(match: re.Match[str]) -> str:
        tag_name = match.group(2).lower()
        if tag_name in _SAFE_HTML_TAGS:
            return match.group(0)
        return escape(match.group(0))
    return _HTML_TAG_RE.sub(_replace, html)


def _format_generated_timestamp(value: Any) -> str:
    raw = str(value or "").strip()
    if not raw:
        return "Unknown"
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return raw
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC).strftime("%Y-%m-%d %H:%M UTC")


def _render_markdown_block(text: str, *, empty_label: str) -> str:
    if not text.strip():
        return f'<p class="empty-state">{escape(empty_label)}</p>'

    if _MARKDOWN_RENDERER is None:
        safe = escape(text).replace("\n", "<br>\n")
        return f'<div class="markdown-body"><p>{safe}</p></div>'

    rendered = _sanitize_html(_MARKDOWN_RENDERER.render(text).strip())
    return f'<div class="markdown-body">{rendered}</div>'


def _render_score_tile(title: str, score: int, max_score: int = 5) -> str:
    """Render a score tile with color based on score value (1–5 scale)."""
    css_class = f"score-{min(score, 5)}"
    return (
        f'<div class="score-card {css_class}">'
        f'<div class="score-card-title">{escape(title)}</div>'
        f'<div class="score-card-value">{score} / {max_score}</div>'
        "</div>"
    )


def _render_list(items: list[str], *, empty_label: str = "None") -> str:
    if not items:
        return f'<p class="empty-state">{escape(empty_label)}</p>'
    rendered = "".join(f"<li>{escape(item)}</li>" for item in items)
    return f'<ul class="detail-list">{rendered}</ul>'


def _render_query_nav(query: dict[str, Any], active: bool) -> str:
    query_num = int(query["query_num"])
    active_class = " active" if active else ""
    query_text = escape(str(query.get("query") or ""))
    return (
        f'<button class="query-tab{active_class}" type="button" '
        f'data-query-target="query-{query_num}" '
        f'title="{query_text}" '
        f'aria-label="Open Q{query_num}: {query_text}">'
        f"Q{query_num}"
        "</button>"
    )


def _render_source_chips(query: dict[str, Any]) -> str:
    """Render source chips and TBD badge for a query panel."""
    query_sources = query.get("query_sources") or []
    chips = []
    for src in query_sources:
        rt = escape(str(src.get("report_type") or ""))
        bank = escape(str(src.get("bank") or ""))
        quarter = escape(str(src.get("quarter") or ""))
        year = escape(str(src.get("year") or ""))
        chips.append(f'<span class="source-chip">{rt} | {bank} | {quarter}_{year}</span>')
    tbd_badge = ""
    if query.get("answer_pages_tbd"):
        tbd_badge = '<span class="tbd-badge">&#9888; Answer pages TBD</span>'
    if not chips and not tbd_badge:
        return ""
    return (
        '<div class="source-chips">'
        + "".join(chips)
        + tbd_badge
        + "</div>"
    )


def _render_query_panel(query: dict[str, Any], active: bool) -> str:
    query_num = int(query["query_num"])
    panel_active = " active" if active else ""

    retrieval_acc = int(query.get("retrieval_accuracy") or 0)
    answer_acc = int(query.get("answer_accuracy") or 0)
    answer_comp = int(query.get("answer_completeness") or 0)
    overall = int(query.get("overall_score") or 0)
    judge = query.get("judge") or {}

    score_tiles = "".join(
        [
            _render_score_tile("Retrieval", retrieval_acc),
            _render_score_tile("Accuracy", answer_acc),
            _render_score_tile("Completeness", answer_comp),
            _render_score_tile("Overall", overall),
        ]
    )

    why_hard = str(query.get("why_hard") or "").strip()
    why_html = (
        '<div class="why-bubble">'
        "<h4>Why is this challenging?</h4>"
        f"<p>{escape(why_hard)}</p>"
        "</div>"
        if why_hard
        else ""
    )

    source_chips_html = _render_source_chips(query)

    correct_pages = [str(item) for item in judge.get("correct_pages_cited") or []]
    missing_pages = [str(item) for item in judge.get("missing_pages") or []]
    inaccurate_claims = [str(item) for item in query.get("inaccurate_claims") or []]
    validated_citations = [str(item) for item in query.get("validated_answer_citations") or []]

    return (
        f'<section id="query-{query_num}" class="query-panel{panel_active}">'
        '<div class="query-top">'
        '<div class="query-question">'
        f'<div class="query-question-label">Test Query: Q{query_num}</div>'
        f'<h2>{escape(str(query.get("query") or ""))}</h2>'
        f"{source_chips_html}"
        "</div>"
        f"{why_html}"
        "</div>"
        # ── Judge bar (collapsible) ──
        '<div class="judge-bar">'
        f'<button class="judge-bar-header" type="button" aria-expanded="false" data-judge-toggle="judge-body-{query_num}">'
        '<span class="judge-bar-left">'
        '<span class="judge-bar-title">Analysis of Test Response</span>'
        '<span class="judge-bar-hint">Click to expand full analysis</span>'
        '</span>'
        f'<span class="judge-bar-scores">{score_tiles}</span>'
        '<span class="judge-bar-chevron" aria-hidden="true">&#9662;</span>'
        "</button>"
        f'<div id="judge-body-{query_num}" class="judge-bar-body">'
        '<div class="judge-bar-columns">'
        '<div class="analysis-section">'
        "<h4>Analysis of Test Response:</h4>"
        f'{_render_markdown_block(str(query.get("explanation") or ""), empty_label="No explanation provided.")}'
        '<p class="sub-label">Retrieval Notes</p>'
        f'{_render_markdown_block(str(judge.get("retrieval_notes") or ""), empty_label="None")}'
        '<p class="sub-label">Correct Pages Cited</p>'
        f'{_render_list(correct_pages, empty_label="None recorded")}'
        '<p class="sub-label">Missing Pages</p>'
        f'{_render_list(missing_pages, empty_label="None")}'
        '<p class="sub-label">Accuracy Notes</p>'
        f'{_render_markdown_block(str(judge.get("accuracy_notes") or ""), empty_label="None")}'
        '<p class="sub-label">Inaccurate Claims</p>'
        f'{_render_list(inaccurate_claims, empty_label="None")}'
        '<p class="sub-label">Completeness Notes</p>'
        f'{_render_markdown_block(str(judge.get("completeness_notes") or ""), empty_label="None")}'
        "</div>"
        '<div class="expected-section">'
        "<h4>Expected Response:</h4>"
        f'{_render_markdown_block(str(query.get("validated_answer_summary") or ""), empty_label="No validated answer summary.")}'
        '<p class="sub-label">Validated Citations</p>'
        f'{_render_list(validated_citations, empty_label="None")}'
        "</div>"
        "</div>"
        "</div>"
        "</div>"
        # ── Full-width test response ──
        '<div class="response-section">'
        '<h3 class="col-title">Test Response:</h3>'
        f'{_render_markdown_block(str(query.get("model_answer") or ""), empty_label="No model answer was generated.")}'
        "</div>"
        "</section>"
    )


def render_html_report(report: dict[str, Any]) -> str:
    """Render a self-contained HTML review report with sidebar layout."""
    queries = report.get("queries") or []
    summary = report.get("summary") or {}
    sources_ctx: list[dict[str, Any]] = report.get("sources_context") or []
    # Legacy v1 compat: if no sources_context, build from source_context
    if not sources_ctx and report.get("source_context"):
        sources_ctx = [report["source_context"]]

    nav_html = "".join(_render_query_nav(query, i == 0) for i, query in enumerate(queries))
    panels_html = "".join(_render_query_panel(query, i == 0) for i, query in enumerate(queries))

    if not panels_html:
        panels_html = (
            '<section class="query-panel active">'
            '<div class="query-col">'
            '<p class="empty-state">No queries were captured in this report.</p>'
            "</div>"
            "</section>"
        )

    # ── Compute aggregate scores (/100) ─────────────────────────────────
    total = len(queries)
    max_score = total * 5

    retrieval_total = sum(int(q.get("retrieval_accuracy") or 0) for q in queries)
    accuracy_total = sum(int(q.get("answer_accuracy") or 0) for q in queries)
    completeness_total = sum(int(q.get("answer_completeness") or 0) for q in queries)
    overall_total = sum(int(q.get("overall_score") or 0) for q in queries)

    def _pct(n: int) -> str:
        return f"{n / max_score * 100:.0f}%" if max_score else "0%"

    # ── Data in scope — one row per unique source ────────────────────────
    scope_rows = []
    for ctx in sources_ctx:
        schema = ctx.get("schema_json") or {}
        rt = escape(str(ctx.get("report_type") or schema.get("report_type") or "").strip())
        bank = escape(str(schema.get("bank_code") or "").strip())
        period_code = str(schema.get("period_code") or "").strip()
        if period_code and "_" in period_code:
            q_part, y_part = period_code.split("_", 1)
        else:
            q_part, y_part = period_code, ""
        scope_rows.append(
            f"<tr><td>{rt}</td><td>{escape(q_part)}</td><td>{escape(y_part)}</td><td>{bank}</td></tr>"
        )
    scope_html = "\n            ".join(scope_rows) if scope_rows else "<tr><td colspan='4'>—</td></tr>"

    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Performance Testing</title>
  <style>
:root {{
  --bg: #f4f5f7; --panel: #ffffff; --panel-muted: #f8fafc;
  --ink: #111827; --muted: #6b7280;
  --line: #e5e7eb; --line-strong: #d1d5db;
  --accent: #0f172a; --accent-soft: #eef2f7;
  --shadow: 0 12px 32px rgba(15,23,42,.06);
  --blue-tint: #f0f4fa; --blue-border: #c7d2e0;
  --gold-tint: #fdf8ef; --gold-border: #e8dcc8;
  --sidebar-w: 260px;
}}
* {{ box-sizing: border-box; }}
html, body {{
  margin: 0; min-height: 100vh;
  background: radial-gradient(circle at top left, rgba(148,163,184,.10), transparent 26rem),
              linear-gradient(180deg, #f8fafc 0%, var(--bg) 100%);
  color: var(--ink);
  font-family: "Avenir Next","Neue Haas Grotesk Text","Segoe UI",sans-serif;
}}
button {{ font: inherit; }}

.app-shell {{ display: flex; min-height: 100vh; }}

/* Sidebar */
.sidebar {{
  position: sticky; top: 0; align-self: flex-start;
  width: var(--sidebar-w); flex-shrink: 0;
  height: 100vh; overflow-y: auto;
  padding: 1.25rem 1rem 1.5rem;
  border-right: 1px solid var(--line);
  background: var(--panel);
  display: flex; flex-direction: column; gap: .85rem;
}}
.sidebar-brand h1 {{ margin: 0; font-size: 1.1rem; font-weight: 700; letter-spacing: -.03em; }}
.sidebar-brand p {{ margin: .2rem 0 0; color: var(--muted); font-size: .76rem; }}

.sidebar-card {{
  padding: .75rem .85rem; border: 1px solid var(--line);
  border-radius: .75rem; background: var(--panel-muted);
}}
.sidebar-card-title {{
  margin: 0 0 .45rem; color: var(--muted); font-size: .62rem;
  font-weight: 700; text-transform: uppercase; letter-spacing: .08em;
}}
.sidebar-table {{ width: 100%; border-collapse: collapse; }}
.sidebar-table th {{
  color: var(--muted); font-size: .6rem; font-weight: 600;
  text-transform: uppercase; letter-spacing: .06em;
  padding: 0 0 .35rem; border-bottom: 1px solid var(--line); text-align: left;
}}
.sidebar-table th:last-child {{ text-align: right; }}
.sidebar-table td {{ font-size: .78rem; padding: .3rem 0; }}
.sidebar-table td:first-child {{ color: var(--muted); font-size: .75rem; }}
.sidebar-table td:last-child {{ text-align: right; font-weight: 600; }}
.sidebar-table-3 th:nth-child(2), .sidebar-table-3 td:nth-child(2) {{ text-align: right; font-weight: 600; }}
.sidebar-table-3 th:nth-child(3), .sidebar-table-3 td:nth-child(3) {{ text-align: right; color: var(--muted); font-weight: 500; font-size: .72rem; padding-left: .4rem; }}

.query-tabs {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: .3rem; margin-top: .45rem; }}
.query-tab {{
  padding: .35rem .15rem; border: 1px solid var(--line); border-radius: .5rem;
  background: transparent; color: var(--muted); font-size: .72rem; font-weight: 600;
  cursor: pointer; text-align: center;
  transition: border-color 120ms, background 120ms, color 120ms;
}}
.query-tab:hover {{ border-color: var(--line-strong); color: var(--ink); }}
.query-tab.active {{ background: var(--accent); border-color: var(--accent); color: #fff; }}

/* Main */
.main-content {{ flex: 1; min-width: 0; padding: 1.5rem 2rem 3rem; max-width: 1100px; }}

.query-panel {{ display: none; border: 1px solid var(--line); border-radius: 1.25rem; background: rgba(255,255,255,.94); box-shadow: var(--shadow); overflow: hidden; }}
.query-panel.active {{ display: block; }}

.query-top {{
  display: flex; gap: 1.25rem; align-items: flex-start;
  padding: 1.4rem 1.45rem 1.15rem; border-bottom: 1px solid var(--line);
  background: linear-gradient(180deg, #fff 0%, #fbfcfd 100%);
}}
.query-question {{ flex: 1 1 0; min-width: 0; }}
.query-question-label {{
  display: inline-flex; align-items: center; padding: .3rem .56rem;
  border-radius: 999px; border: 1px solid var(--line);
  color: var(--muted); font-size: .75rem; font-weight: 700;
  letter-spacing: .08em; text-transform: uppercase;
}}
.query-question h2 {{ margin: .55rem 0 0; max-width: 50ch; font-size: 1.15rem; font-weight: 650; letter-spacing: -.03em; line-height: 1.22; }}

.why-bubble {{
  flex: 0 0 270px; padding: .85rem 1rem;
  border: 1px solid rgba(99,145,214,.35); border-radius: .85rem;
  background: linear-gradient(135deg, #f6f9ff 0%, #f0f4fb 100%);
  box-shadow: 0 2px 8px rgba(99,145,214,.10), 0 1px 3px rgba(0,0,0,.04);
}}
.why-bubble h4 {{ margin: 0 0 .4rem; color: #5b7ba8; font-size: .72rem; font-weight: 700; letter-spacing: .08em; text-transform: uppercase; }}
.why-bubble p {{ margin: 0; color: var(--muted); font-size: .86rem; line-height: 1.5; }}

/* Judge bar */
.judge-bar {{ border-bottom: 1px solid var(--line); }}
.judge-bar-header {{
  display: flex; align-items: center; gap: .75rem; width: 100%;
  padding: .65rem 1.45rem; border: none;
  background: linear-gradient(180deg, #eef1f6 0%, #e8ecf3 100%);
  border-bottom: 1px solid var(--blue-border);
  cursor: pointer; text-align: left;
  transition: background 120ms;
}}
.judge-bar-header:hover {{ background: linear-gradient(180deg, #e6eaf1 0%, #dfe4ed 100%); }}
.judge-bar-left {{ display: flex; flex-direction: column; gap: .1rem; white-space: nowrap; flex-shrink: 0; }}
.judge-bar-title {{ font-size: .72rem; font-weight: 700; color: var(--ink); text-transform: uppercase; letter-spacing: .06em; }}
.judge-bar-hint {{ font-size: .62rem; color: var(--muted); font-weight: 500; font-style: italic; }}
.judge-bar-scores {{ display: flex; gap: .4rem; flex: 1; min-width: 0; }}
.judge-bar-scores .score-card {{ flex: 0 0 auto; min-width: 72px; padding: .3rem .5rem; }}
.judge-bar-scores .score-card-title {{ font-size: .55rem; margin-bottom: .05rem; }}
.judge-bar-scores .score-card-value {{ font-size: .85rem; }}
.judge-bar-chevron {{ font-size: .8rem; color: var(--muted); transition: transform 200ms; flex-shrink: 0; }}
.judge-bar-header[aria-expanded="true"] .judge-bar-chevron {{ transform: rotate(180deg); }}
.judge-bar-header[aria-expanded="true"] .judge-bar-hint {{ display: none; }}
.judge-bar-body {{ display: none; padding: 1.15rem 1.45rem; background: #f5f7fa; border-top: 1px solid var(--blue-border); }}
.judge-bar-body.open {{ display: block; }}
.judge-bar-columns {{ display: grid; grid-template-columns: 1fr 1fr; gap: 1.5rem; }}

/* Response section */
.response-section {{ padding: 1.25rem 1.45rem 1.45rem; background: var(--panel); }}
.col-title {{ margin: 0 0 .75rem; font-size: .92rem; font-weight: 650; letter-spacing: -.02em; }}

.score-grid {{ display: flex; gap: .5rem; }}
.score-card {{ padding: .6rem .6rem; border: 1px solid var(--line); border-radius: .75rem; text-align: center; }}
.score-card.score-5 {{ border-color: rgba(15,118,110,.30); background: rgba(15,118,110,.08); }}
.score-card.score-4 {{ border-color: rgba(15,118,110,.20); background: rgba(15,118,110,.04); }}
.score-card.score-3 {{ border-color: rgba(180,140,9,.25); background: rgba(180,140,9,.06); }}
.score-card.score-2 {{ border-color: rgba(185,100,28,.25); background: rgba(185,100,28,.06); }}
.score-card.score-1 {{ border-color: rgba(185,28,28,.25); background: rgba(185,28,28,.06); }}
.score-card.score-0 {{ border-color: rgba(185,28,28,.30); background: rgba(185,28,28,.08); }}
.score-card-title {{ font-size: .68rem; font-weight: 700; text-transform: uppercase; letter-spacing: .05em; color: var(--ink); margin-bottom: .2rem; }}
.score-card-value {{ font-size: 1.25rem; font-weight: 800; letter-spacing: -.02em; color: var(--ink); }}

.analysis-section {{
  margin-top: 1.15rem; padding: 1rem 1.1rem;
  border: 1px solid var(--blue-border); border-radius: .85rem; background: var(--blue-tint);
}}
.analysis-section h4 {{ margin: 0 0 .65rem; color: var(--ink); font-size: .88rem; font-weight: 700; }}
.analysis-section .sub-label {{ margin: .85rem 0 .35rem; color: var(--muted); font-size: .72rem; font-weight: 700; letter-spacing: .08em; text-transform: uppercase; }}

.expected-section {{
  margin-top: 1.15rem; padding: 1rem 1.1rem;
  border: 1px solid var(--gold-border); border-radius: .85rem; background: var(--gold-tint);
}}
.expected-section h4 {{ margin: 0 0 .65rem; color: var(--ink); font-size: .88rem; font-weight: 700; }}
.expected-section .sub-label {{ margin: .85rem 0 .35rem; color: var(--muted); font-size: .72rem; font-weight: 700; letter-spacing: .08em; text-transform: uppercase; }}

.markdown-body {{ color: var(--ink); font-size: .82rem; line-height: 1.55; overflow-wrap: anywhere; }}
.markdown-body > :first-child {{ margin-top: 0; }}
.markdown-body > :last-child {{ margin-bottom: 0; }}
.markdown-body h1,.markdown-body h2,.markdown-body h3,.markdown-body h4 {{ margin: 1rem 0 .45rem; line-height: 1.3; letter-spacing: -.02em; }}
.markdown-body h1 {{ font-size: 1.05rem; }} .markdown-body h2 {{ font-size: .97rem; }}
.markdown-body h3 {{ font-size: .9rem; }} .markdown-body h4 {{ font-size: .84rem; }}
.markdown-body p,.markdown-body ul,.markdown-body ol,.markdown-body table,.markdown-body pre,.markdown-body blockquote,.markdown-body hr {{ margin: 0 0 .65rem; }}
.markdown-body ul,.markdown-body ol {{ padding-left: 1.15rem; }}
.markdown-body li + li {{ margin-top: .15rem; }}
.markdown-body strong {{ font-weight: 700; }}
.markdown-body code {{ padding: .06rem .3rem; border-radius: .3rem; background: var(--accent-soft); font: .84em/1.4 "SFMono-Regular","Menlo","Consolas",monospace; }}
.markdown-body pre {{ padding: .85rem 1rem; border: 1px solid var(--line); border-radius: .75rem; background: #f8fafc; overflow: auto; }}
.markdown-body pre code {{ padding: 0; background: transparent; }}
.markdown-body blockquote {{ padding-left: .95rem; border-left: 2px solid var(--line-strong); color: var(--muted); }}
.markdown-body hr {{ border: 0; border-top: 1px solid var(--line); }}
.markdown-body table {{ display: table; width: 100%; table-layout: auto; border-collapse: collapse; }}
.markdown-body th,.markdown-body td {{ padding: .45rem .55rem; border: 1px solid var(--line); text-align: left; vertical-align: top; word-wrap: break-word; overflow-wrap: break-word; }}
.markdown-body thead th {{ background: #f8fafc; font-weight: 700; font-size: .78rem; }}
.markdown-body td {{ font-size: .78rem; }}

.detail-list {{ margin: 0; padding-left: 1.2rem; }}
.detail-list li + li {{ margin-top: .25rem; }}
.empty-state {{ margin: 0; color: var(--muted); }}

.source-chips {{ display: flex; flex-wrap: wrap; gap: .3rem; margin-top: .45rem; }}
.source-chip {{
  display: inline-flex; align-items: center; padding: .18rem .5rem;
  border-radius: 999px; border: 1px solid var(--blue-border);
  background: var(--blue-tint); color: #4a6fa5;
  font-size: .68rem; font-weight: 600; letter-spacing: .03em;
}}
.tbd-badge {{
  display: inline-flex; align-items: center; padding: .18rem .5rem;
  border-radius: 999px; border: 1px solid rgba(180,140,9,.35);
  background: var(--gold-tint); color: #8a6a00;
  font-size: .68rem; font-weight: 600; letter-spacing: .03em;
}}

@media (max-width: 1100px) {{ .judge-bar-columns {{ grid-template-columns: 1fr; }} }}
@media (max-width: 900px) {{
  .app-shell {{ flex-direction: column; }}
  .sidebar {{
    position: relative; width: 100%; height: auto;
    flex-direction: row; flex-wrap: wrap;
    border-right: none; border-bottom: 1px solid var(--line); padding: 1rem;
  }}
  .sidebar-brand {{ width: 100%; }}
  .sidebar-card {{ flex: 1; min-width: 180px; }}
  .query-tabs {{ grid-template-columns: repeat(10, 1fr); }}
  .main-content {{ padding: 1rem; }}
  .query-top {{ flex-direction: column; }}
  .why-bubble {{ flex: none; width: 100%; }}
}}
  </style>
</head>
<body>
  <div class="app-shell">
    <aside class="sidebar">
      <div class="sidebar-brand">
        <h1>Performance Testing</h1>
        <p>Finance Assist &mdash; External Reporting</p>
      </div>

      <div class="sidebar-card">
        <div class="sidebar-card-title">Data in Scope</div>
        <table class="sidebar-table">
          <thead><tr><th>Document Type</th><th>Qtr</th><th>Year</th><th>Bank</th></tr></thead>
          <tbody>
            {scope_html}
          </tbody>
        </table>
      </div>

      <div class="sidebar-card">
        <div class="sidebar-card-title">Results Summary</div>
        <table class="sidebar-table sidebar-table-3">
          <thead><tr><th>Metric</th><th>Score</th><th>Pct</th></tr></thead>
          <tbody>
            <tr><td>Queries</td><td>{total}</td><td></td></tr>
            <tr><td>Retrieval</td><td>{retrieval_total}/{max_score}</td><td>{_pct(retrieval_total)}</td></tr>
            <tr><td>Accuracy</td><td>{accuracy_total}/{max_score}</td><td>{_pct(accuracy_total)}</td></tr>
            <tr><td>Completeness</td><td>{completeness_total}/{max_score}</td><td>{_pct(completeness_total)}</td></tr>
            <tr><td>Overall</td><td>{overall_total}/{max_score}</td><td>{_pct(overall_total)}</td></tr>
          </tbody>
        </table>
      </div>

      <div class="sidebar-card">
        <div class="sidebar-card-title">Test Queries</div>
        <nav class="query-tabs" aria-label="Query tabs">
          {nav_html}
        </nav>
      </div>
    </aside>

    <main class="main-content">
      {panels_html}
    </main>
  </div>

  <script>
    const queryButtons = Array.from(document.querySelectorAll('[data-query-target]'));
    const queryPanels = Array.from(document.querySelectorAll('.query-panel'));
    function activateQuery(targetId) {{
      queryButtons.forEach(b => b.classList.toggle('active', b.dataset.queryTarget === targetId));
      queryPanels.forEach(p => p.classList.toggle('active', p.id === targetId));
    }}
    queryButtons.forEach(b => b.addEventListener('click', () => activateQuery(b.dataset.queryTarget)));
    document.querySelectorAll('[data-judge-toggle]').forEach(btn => {{
      btn.addEventListener('click', () => {{
        const body = document.getElementById(btn.dataset.judgeToggle);
        const isOpen = body.classList.toggle('open');
        btn.setAttribute('aria-expanded', isOpen);
      }});
    }});
  </script>
</body>
</html>
"""
