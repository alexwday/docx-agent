"""Stress test: curated retrieval + synthesis + decomposed evaluation.

60 hand-curated Q&A pairs across three document types (supp_financials,
pillar3, investor_slides).  Each query tests the full pipeline end-to-end:

  1. Retrieval — does the target page appear in results?
  2. Synthesis — given retrieved chunks, produce a grounded answer
  3. Decomposed judge — faithfulness, completeness, citation accuracy

Queries with ``answer_pages_tbd: True`` skip hit-rate metrics until the
corresponding document is ingested.
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any
from uuid import UUID

import openai

from data_sources.auth import build_openai_client
from data_sources.config import DataSourcesConfig
from data_sources.db import DataSourcesDB
from data_sources.retrieve.supp_financials import SuppFinancialsRetriever
from data_sources.scripts.stress_test_queries import ALL_QUERIES
from data_sources.scripts.stress_test_report import build_report_payload, write_report_files
from word_store.db import PostgresStore


# ── SOTA synthesis prompt ─────────────────────────────────────────────

_ANSWER_SYSTEM_PROMPT = """\
You are a senior financial data analyst answering questions using pages from \
Canadian bank financial disclosures — which may include supplementary financial \
information packages, Pillar 3 regulatory capital disclosures, or investor \
presentations. You have expertise in IFRS accounting, bank financial analysis, \
and regulatory capital.

PROCESS — follow these steps before writing your answer:
1. Each source page includes a **Relevance** score (0–1) from the retrieval \
system. Higher scores indicate the page is more likely to contain the answer, \
but lower-scored pages may still hold critical or more specific data.
2. Before writing the final answer, internally review ALL pages from first to \
last. Do NOT stop at the first relevant page — continue through every page, \
as lower-ranked pages may contain better or more specific data. Keep this \
review internal; do NOT include the full page-by-page review in your response.
3. Weight your attention by relevance score but do NOT skip low-relevance pages \
entirely. A page with Relevance 0.40 can still be the best source for a \
specific sub-question.
4. After reviewing all pages, identify which source(s) contain the most \
directly relevant data for each part of the question.
5. Synthesize information across multiple sources when needed to fully answer.

GROUNDING RULES:
- Base every claim on figures that appear explicitly in the provided sources. \
NEVER invent or guess at figures not present in the sources. NEVER attribute \
your own reasoning, conventions, or domain knowledge to the source — only \
state what is explicitly written on the page.
- When performing arithmetic (sums, differences, ratios), use only source \
figures and show the calculation.
- Use the smallest set of source pages that fully answers the question. Treat \
other pages as cross-checks only, and do not cite them unless they provide a \
required fact that the primary page does not contain.
- When multiple tables contain similar-looking data, verify you are reading \
from the correct table by checking the source label and column headers.
- If the question asks for a total, overall portfolio, or full book, prefer \
aggregate figures over narrower slices such as trading-only, non-trading, \
centrally cleared, non-centrally cleared, or exchange-traded subtotals unless \
the question explicitly asks for the narrower slice.
- If one source contains all requested metrics and another source contains only \
part of them, use the fuller source as the primary answer and treat the \
partial source as supporting context only.
- When an appendix, flow statement, calculation page, or other direct aggregate \
page answers the scoped question, prefer that page over reconstructed sums from \
segment pages, highlights pages, or partial product slices.
- Be cautious about double-counting: in financial statements the same economic \
event can appear across multiple sections (e.g., a share buyback reduces both \
common shares and retained earnings). Count each event once.
- For shareholder returns / buybacks, include ALL classes of shareholders \
(common and preferred) unless the question explicitly specifies only one class. \
Count only explicit dividends, share repurchases, or purchases for cancellation. \
Do not include treasury-share inventory movements (purchases/sales) as \
shareholder returns.

COMPLETENESS:
- When the source table includes prior-period comparators (e.g., Q4/25, Q1/25, \
or prior-year annual), include the most recent prior-period figure and note \
the change or trend. This adds essential context at minimal cost.
- When the question asks to "break down" or "decompose" a figure, provide \
both the absolute amounts AND the percentage share of the total.
- When describing how data is organized in a table, use the exact headings and \
row labels from the source. Do not paraphrase or generalize (e.g., say "by \
Retail and Wholesale segments and their sub-portfolios" not "by \
portfolio/geography").

TERMINOLOGY MAPPING:
- Apply financial domain expertise to bridge the user's terminology to the \
source data labels. Users often use analyst jargon, abbreviations, or informal \
terms that differ from the formal line items in the report.
- When mapping terminology, state both the user's term and the source label so \
the reader understands the relationship (e.g., "NPL ratio, shown in the source \
as 'GIL as a % of related loans'").
- If only a partial or superset match exists, provide what is available and \
note the difference.

CITATIONS:
- Cite every factual claim with [Source N] matching the source label number.
- Quote exact figures as they appear (millions of Canadian dollars, percentages).
- After each markdown table, include numbered footnotes as plain text lines:
  [1] Page NN, "Section/Page Title", "Row/Table label"
  These map each data point back to its exact source location for readers.
- Keep citations minimal: only cite sources that materially support the answer.

HANDLING GAPS:
- Only if NO source contains relevant or related data: "The provided sources \
do not contain data on [topic]."

RESPONSE FORMAT — use these exact markdown headings:

### Summary Response
2-3 sentences. Plain language condensed answer. No tables. No [Source N] citations.
The reader should grasp the key finding in seconds.

### Detailed Response
1. Written context paragraph(s) explaining what was found and how data is organized.
   Include [Source N] citations in this text.

2. A markdown table with standardized columns. Choose the appropriate format:

   SINGLE-PERIOD (when only one period's data is needed):
   | Data Source | Bank | Platform | Metric | Value | Type |
   |---|---|---|---|---|---|
   | Pillar 3 Regulatory Disclosure | BMO | Enterprise | CET1 Ratio | 13.1 | % |

   MULTI-PERIOD (when comparing across periods — use one column per period):
   | Data Source | Bank | Platform | Metric | 2026 Q1 | 2025 Q4 | Type |
   |---|---|---|---|---|---|---|
   | Pillar 3 Regulatory Disclosure | BMO | Enterprise | CET1 Ratio | 13.1 | 13.3 | % |

   Column rules:
   - Data Source: derive from the report_type in the source label:
       supp_financials   → "Supplementary Financials"
       pillar3           → "Pillar 3 Regulatory Disclosure"
       investor_slides   → "Investor Presentation"
     Use the report_type of the source being cited in that row. If sources
     span multiple report types in one table, each row uses its own type.
   - Bank: use ticker symbol — RBC→RY, TD→TD, BMO→BMO, Scotiabank→BNS,
     CIBC→CM, National Bank→NA. If bank_code is unrecognized, use it as-is.
   - Platform: infer from the source page content. Use "Enterprise" for
     consolidated/bank-wide figures. Use specific names for segment data
     (e.g., "Capital Markets", "Wealth Management", "Personal & Commercial
     Banking", "Insurance") exactly as labeled in the source.
   - Metric: the metric/line-item name from the source data
   - Value columns: report monetary amounts in millions. Use comma separators
     for large numbers (e.g., 28,561,916). For multi-period, use
     "{Year} {Quarter}" as column headers (e.g., "2026 Q1", "2025 Q4").
   - Type: unit indicator ($M, %, bps, #, x, etc.)

3. Footnotes — immediately after the table, on separate lines:
   [1] Page NN, "Page Title", "Row/table label if applicable"
   [2] ...

4. Optional concluding paragraph with interpretation or comparison.

### Notes
Bullet points covering any of the following that apply:
- **Terminology**: user term → source label mapping
- **Assumptions**: any assumptions in interpreting the question
- **Calculations**: show arithmetic with figures (e.g., "28,561,916 − 22,991,164 = 5,570,752 [Source 1]")
- **Caveats**: relevant source footnotes or qualifications
- **Gaps**: anything the sources do not cover\
"""

_JUDGE_SYSTEM_PROMPT = """\
You are an evaluation judge for a RAG (retrieval-augmented generation) system \
that answers questions about financial documents. You will rigorously assess an \
AI-generated answer against ground truth data across three independent \
dimensions, each scored on a 1–5 scale.

Think deeply and carefully before scoring. Use extended reasoning to work \
through each dimension step by step.

You receive:
- QUESTION: The user's question
- DIFFICULTY: easy / medium / hard
- EXPECTED ANSWER: A reference answer summary
- ANSWER CITATIONS: Exact figures/lines from the source data
- GENERATED ANSWER: The AI's answer to evaluate
- CANONICAL SOURCE DATA: One or more curated pages that define the intended \
  scope of the answer
- ADDITIONAL CITED SOURCE DATA: Any extra pages the model cited, provided so \
  you can verify whether those citations genuinely support the claims
- CANONICAL SOURCE PAGE NAMES: The page names that should have been retrieved \
  and cited

Evaluate on these three dimensions:

──────────────────────────────────────────────────────────────────────────────
1. RETRIEVAL ACCURACY (1–5): Did the system retrieve the correct chunks?
──────────────────────────────────────────────────────────────────────────────

Think step by step:
a) List every canonical source page that the expected answer requires.
b) For each one, check whether the generated answer cites it (directly or via \
   an equivalent page that contains the same data).
c) Note any canonical pages that were NOT retrieved/cited — these are misses.
d) Note any non-canonical pages that were cited — are they helpful or noise?

Scoring rubric:
  5 = All canonical pages retrieved and cited; no irrelevant noise pages
  4 = All canonical pages retrieved; minor extra pages cited but not harmful
  3 = Most canonical pages retrieved (≥75%); one page missed but answer still \
      partially viable from what was retrieved
  2 = Some canonical pages retrieved (50–74%); significant gaps that force the \
      answer to rely on incomplete data
  1 = Few or no canonical pages retrieved (<50%); answer cannot be grounded

Record which canonical pages were correctly cited in "correct_pages_cited" and \
which were missing in "missing_pages".

──────────────────────────────────────────────────────────────────────────────
2. ANSWER ACCURACY (1–5): Does the answer get the right values and make \
   correct references to source material?
──────────────────────────────────────────────────────────────────────────────

Think step by step:
a) Compare every specific figure, percentage, dollar amount, ratio, or date \
   in the generated answer against the CANONICAL SOURCE DATA and ANSWER \
   CITATIONS.
b) For each claim, classify it as: CORRECT (matches source), WRONG (contradicts \
   source), or UNSUPPORTED (not verifiable from provided sources).
c) Check that source references ([Source N]) point to pages that actually \
   contain the cited data.
d) Check for hallucinated context — does the answer invent qualitative claims \
   not in the source data?

Scoring rubric:
  5 = Every factual claim is correct and properly sourced; no hallucinations
  4 = All major claims correct; one minor inaccuracy (e.g., rounding difference, \
      slightly imprecise label) that does not change the substantive answer
  3 = Core answer is correct but contains 1–2 material errors or unsupported \
      claims that could mislead a reader
  2 = Some correct elements but multiple material errors or hallucinated claims
  1 = Predominantly incorrect, hallucinated, or contradicts the source data

List any inaccurate claims in "inaccurate_claims" (empty list if all accurate). \
Provide detailed reasoning in "accuracy_notes".

──────────────────────────────────────────────────────────────────────────────
3. ANSWER COMPLETENESS (1–5): Does the response fully answer the user's query?
──────────────────────────────────────────────────────────────────────────────

Think step by step:
a) Break the user's question into its component parts (what is being asked).
b) For each part, check whether the generated answer addresses it.
c) Compare against the EXPECTED ANSWER — does the generated answer cover the \
   same scope, or does it miss key elements?
d) Consider whether the answer provides appropriate context (e.g., prior period \
   comparisons, relevant caveats) or is too narrow.

Scoring rubric:
  5 = Addresses every part of the question with appropriate detail and context; \
      nothing meaningful is omitted
  4 = Addresses all major parts; omits one minor element or piece of context \
      that a thorough answer would include
  3 = Addresses the primary question but misses secondary elements, relevant \
      comparisons, or important context
  2 = Only partially addresses the question; significant gaps in coverage
  1 = Fails to address the question or is only tangentially relevant

Explain gaps in "completeness_notes".

──────────────────────────────────────────────────────────────────────────────
EVALUATION RULES
──────────────────────────────────────────────────────────────────────────────

- The canonical source pages define the benchmark scope for the question.
- Do not penalize retrieval for citing additional non-canonical pages if those \
  pages genuinely support claims and the canonical pages are also present.
- However, if the answer substitutes a narrower, conflicting, or less direct \
  cited page for a canonical page that directly answers the question, penalize \
  both retrieval accuracy and answer accuracy as appropriate.
- Extra supported detail is acceptable if it does not conflict with the \
  canonical answer and does not distort the primary answer.
- The generated answer uses a structured format with sections: "Summary Response" \
  (brief, no citations), "Detailed Response" (table + explanation with [Source N] \
  citations and footnotes), and "Notes" (terminology, assumptions, calculations, \
  caveats, gaps). Evaluate content quality across all sections regardless of \
  structure. Do not penalize for section formatting.
- Footnotes beneath tables (e.g., [1] Page 33, "Section", "Table") are \
  supplementary to [Source N] citations. Do not confuse them with citation markers.
- The overall score is the average of the three dimension scores, rounded to \
  the nearest integer (minimum 1).

──────────────────────────────────────────────────────────────────────────────
OUTPUT FORMAT
──────────────────────────────────────────────────────────────────────────────

Return a JSON object with exactly these fields:
{
  "retrieval_accuracy": <int 1-5>,
  "correct_pages_cited": [<list of canonical page names correctly cited>],
  "missing_pages": [<list of canonical page names not cited>],
  "retrieval_notes": "<brief explanation of retrieval assessment>",
  "answer_accuracy": <int 1-5>,
  "inaccurate_claims": [<list of strings describing inaccurate claims, empty if all accurate>],
  "accuracy_notes": "<brief explanation of accuracy assessment>",
  "answer_completeness": <int 1-5>,
  "completeness_notes": "<brief explanation of completeness assessment>",
  "overall_score": <int 1-5>,
  "explanation": "<brief overall assessment synthesizing all three dimensions>"
}\
"""


# ── Helpers ────────────────────────────────────────────────────────────

log = logging.getLogger(__name__)

_OPENAI_RETRYABLE_ERRORS = (
    openai.RateLimitError,
    openai.APITimeoutError,
    openai.APIConnectionError,
)

_HEADER_RE = re.compile(
    r"^(?:===.*===|\[Source\s*(?:\d+\s*)?\|[^\]]*\])\n?",
    re.MULTILINE,
)
_ANSWER_SOURCE_RE = re.compile(r"\[Source\s+(\d+)\]")


def _call_openai_with_retry(
    client: openai.OpenAI,
    *,
    max_retries: int = 3,
    base_delay: float = 2.0,
    **kwargs: Any,
) -> Any:
    """Call ``client.chat.completions.create`` with exponential backoff on transient errors."""
    last_exc: Exception | None = None
    for attempt in range(max_retries + 1):
        try:
            return client.chat.completions.create(**kwargs)
        except _OPENAI_RETRYABLE_ERRORS as exc:
            last_exc = exc
            if attempt < max_retries:
                delay = base_delay * (2 ** attempt)
                log.warning("OpenAI transient error (attempt %d/%d), retrying in %.1fs: %s", attempt + 1, max_retries, delay, exc)
                time.sleep(delay)
        except openai.APIError as exc:
            if exc.status_code is not None and exc.status_code >= 500:
                last_exc = exc
                if attempt < max_retries:
                    delay = base_delay * (2 ** attempt)
                    log.warning("OpenAI 5xx error (attempt %d/%d), retrying in %.1fs: %s", attempt + 1, max_retries, delay, exc)
                    time.sleep(delay)
            else:
                raise
    raise last_exc  # type: ignore[misc]


def _strip_header(content: str) -> str:
    """Remove retriever-injected headers (old === or new [Source|...] format)."""
    return _HEADER_RE.sub("", content)


def _build_source_dict(
    *,
    report_type: str,
    bank: str,
    year: int,
    quarter: str,
) -> dict[str, Any]:
    """Build a retriever-compatible source dict from query metadata."""
    period_code = f"{quarter}_{year}"
    return {
        "source_id": f"{report_type}_{bank}_{period_code}",
        "source_type": "financial_report",
        "report_type": report_type,
        "location": {"retriever_id": report_type},
        "schema_json": {"bank_code": bank, "period_code": period_code, "report_type": report_type},
    }


def _build_failure_judgment(
    explanation: str,
    *,
    inaccurate_claims: list[str] | None = None,
    completeness_notes: str | None = None,
) -> dict[str, Any]:
    """Build a consistent fallback judgment when the pipeline cannot score an answer."""
    return {
        "retrieval_accuracy": 0,
        "correct_pages_cited": [],
        "missing_pages": [],
        "retrieval_notes": explanation,
        "answer_accuracy": 0,
        "inaccurate_claims": inaccurate_claims or [explanation],
        "accuracy_notes": explanation,
        "answer_completeness": 0,
        "completeness_notes": completeness_notes or explanation,
        "overall_score": 0,
        "explanation": explanation,
    }


# ── Answer generation ─────────────────────────────────────────────────

def _generate_answer(
    query: str,
    context_rows: list[dict[str, Any]],
    config: DataSourcesConfig,
) -> str:
    """Generate a grounded answer from retrieved context."""
    context_parts = []
    for i, row in enumerate(context_rows, 1):
        content = row.get("content", "")
        if not content:
            continue
        clean = _strip_header(content)
        sheet_name = row.get("sheet_name", "?")
        page_title = row.get("page_title") or sheet_name
        bank_code = row.get("bank_code", "?")
        period_code = row.get("period_code", "?")
        report_type = row.get("report_type", "?")
        relevance = row.get("score", 0)
        label = f"[Source {i} | {report_type} | {sheet_name} | {page_title} | {bank_code} {period_code} | Relevance: {relevance:.2f}]"
        context_parts.append(f"{label}\n{clean}")

    context_text = "\n\n---\n\n".join(context_parts)

    client = build_openai_client(config)
    response = _call_openai_with_retry(
        client,
        model=config.retrieval_model,
        max_completion_tokens=config.retrieval_max_tokens,
        messages=[
            {"role": "system", "content": _ANSWER_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": f"SOURCE PAGES:\n{context_text}\n\nQUESTION: {query}",
            },
        ],
    )
    return response.choices[0].message.content or ""


def _generate_per_bank_research(
    query: str,
    bank_code: str,
    bank_rows: list[dict[str, Any]],
    all_bank_codes: list[str],
    config: DataSourcesConfig,
) -> str:
    """Stage 1 of multi-bank synthesis: produce a full research response for one bank.

    Uses the same system prompt and response format as a normal single-bank
    query. A per-bank context header in the user message tells the model:
    - which bank it is researching
    - that identical research is being run for the other banks in parallel
    - to scope its answer entirely to this bank's data

    The resulting per-bank responses are then fed as sources to the final
    synthesis step.
    """
    context_parts = []
    for i, row in enumerate(bank_rows, 1):
        content = row.get("content", "")
        if not content:
            continue
        clean = _strip_header(content)
        sheet_name = row.get("sheet_name", "?")
        page_title = row.get("page_title") or sheet_name
        period_code = row.get("period_code", "?")
        report_type = row.get("report_type", "?")
        relevance = row.get("score", 0)
        label = f"[Source {i} | {report_type} | {sheet_name} | {page_title} | {bank_code} {period_code} | Relevance: {relevance:.2f}]"
        context_parts.append(f"{label}\n{clean}")

    context_text = "\n\n---\n\n".join(context_parts)

    other_banks = [b for b in all_bank_codes if b != bank_code]
    per_bank_context = (
        f"PER-BANK RESEARCH MODE\n"
        f"You are researching {bank_code} only. "
        f"Identical research is being run in parallel for: {', '.join(other_banks)}. "
        f"Answer the question solely from {bank_code}'s source pages below. "
        f"Do not reference or compare other banks — that synthesis happens in a later step.\n\n"
    )

    client = build_openai_client(config)
    response = _call_openai_with_retry(
        client,
        model=config.retrieval_model,
        max_completion_tokens=4096,
        messages=[
            {"role": "system", "content": _ANSWER_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": (
                    f"{per_bank_context}"
                    f"SOURCE PAGES:\n{context_text}\n\n"
                    f"QUESTION: {query}"
                ),
            },
        ],
    )
    return response.choices[0].message.content or ""


def _synthesize_multi_bank(
    query: str,
    per_bank_research: dict[str, str],
    config: DataSourcesConfig,
) -> tuple[str, list[dict[str, Any]]]:
    """Stage 2 of multi-bank synthesis: produce a final comparative answer.

    Each bank's per-bank research response becomes a pseudo-row so the
    existing ``_generate_answer`` pipeline handles citation labelling and
    the model can emit ``[Source N]`` references that map back to individual
    banks.  A synthesis context header tells the model it is combining
    per-bank research, not raw source pages.

    Returns the final answer string and the pseudo-rows used as context
    (for downstream citation extraction and judge evaluation).
    """
    banks = list(per_bank_research.keys())
    pseudo_rows: list[dict[str, Any]] = [
        {
            "content": research,
            "sheet_name": bank_code,
            "page_title": f"{bank_code} Research Summary",
            "bank_code": bank_code,
            "period_code": "multi",
            "report_type": "pillar3",
            "score": 1.0,
            "match_sources": [],
        }
        for bank_code, research in per_bank_research.items()
    ]

    context_parts = []
    for i, row in enumerate(pseudo_rows, 1):
        label = (
            f"[Source {i} | pillar3 | {row['bank_code']} Research Summary "
            f"| {row['bank_code']} multi | Relevance: 1.00]"
        )
        context_parts.append(f"{label}\n{row['content']}")
    context_text = "\n\n---\n\n".join(context_parts)

    synthesis_context = (
        f"CROSS-BANK SYNTHESIS MODE\n"
        f"The sources below are per-bank research responses for: {', '.join(banks)}. "
        f"Each source is a complete analysis for one bank derived from that bank's "
        f"regulatory disclosure pages. Synthesise them into a single comparative "
        f"answer covering all {len(banks)} banks.\n\n"
    )

    client = build_openai_client(config)
    response = _call_openai_with_retry(
        client,
        model=config.retrieval_model,
        max_completion_tokens=config.retrieval_max_tokens,
        messages=[
            {"role": "system", "content": _ANSWER_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": (
                    f"{synthesis_context}"
                    f"SOURCE PAGES:\n{context_text}\n\n"
                    f"QUESTION: {query}"
                ),
            },
        ],
    )
    answer = response.choices[0].message.content or ""
    return answer, pseudo_rows


# ── Decomposed judge ──────────────────────────────────────────────────

def _judge_answer(
    query: str,
    answer: str,
    qdata: dict[str, Any],
    ground_truth_pages: dict[str, str],
    cited_source_pages: dict[str, str],
    config: DataSourcesConfig,
) -> dict[str, Any]:
    """Score an answer using the decomposed 3-dimension judge."""
    difficulty = qdata.get("difficulty", "medium")
    expected = qdata.get("expected_answer_summary", "")
    citations = qdata.get("answer_citations", [])
    canonical_payload = _format_ground_truth_payload(ground_truth_pages)
    canonical_page_list = "\n".join(
        f"- {page_name}" for page_name in _normalize_answer_pages(list(ground_truth_pages))
    )
    supplemental_pages = {
        page_name: content
        for page_name, content in cited_source_pages.items()
        if page_name not in ground_truth_pages
    }
    supplemental_payload = _format_ground_truth_payload(supplemental_pages)
    supplemental_page_list = "\n".join(
        f"- {page_name}" for page_name in _normalize_answer_pages(list(supplemental_pages))
    ) or "- None"

    user_msg = (
        f"QUESTION:\n{query}\n\n"
        f"DIFFICULTY: {difficulty}\n\n"
        f"EXPECTED ANSWER:\n{expected}\n\n"
        f"ANSWER CITATIONS:\n" + "\n".join(f"- {c}" for c in citations) + "\n\n"
        f"GENERATED ANSWER:\n{answer}\n\n"
        f"CANONICAL SOURCE PAGES:\n{canonical_page_list}\n\n"
        f"CANONICAL SOURCE DATA:\n{canonical_payload}\n\n"
        f"ADDITIONAL CITED SOURCE PAGES:\n{supplemental_page_list}\n\n"
        f"ADDITIONAL CITED SOURCE DATA:\n{supplemental_payload}"
    )

    client = build_openai_client(config)
    response = _call_openai_with_retry(
        client,
        model=config.retrieval_model,
        max_completion_tokens=config.retrieval_max_tokens,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": _JUDGE_SYSTEM_PROMPT},
            {"role": "user", "content": user_msg},
        ],
    )
    raw = response.choices[0].message.content or "{}"
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        parsed = {
            "retrieval_accuracy": 0,
            "correct_pages_cited": [],
            "missing_pages": [],
            "retrieval_notes": f"Judge returned invalid JSON: {raw[:200]}",
            "answer_accuracy": 0,
            "inaccurate_claims": ["Judge parse error"],
            "accuracy_notes": "Parse error",
            "answer_completeness": 0,
            "completeness_notes": "Parse error",
            "overall_score": 0,
            "explanation": "Judge parse error",
        }
    return _normalize_judgment(parsed)


# ── Ground truth helpers ──────────────────────────────────────────────

def _qualify_page(bank_code: str, sheet_name: str) -> str:
    """Return a qualified page identifier that includes the bank: ``BANK:sheet``."""
    return f"{bank_code}:{sheet_name}"


def _fetch_per_source_ground_truth(
    per_source_answer_pages: dict[str, list[str]],
    db: DataSourcesDB,
    source_dicts: list[dict[str, Any]],
) -> dict[str, str]:
    """Fetch ground truth for multi-bank queries where each bank has specific pages.

    Returns a dict keyed by qualified page names (``BANK:sheet``).
    """
    bank_to_source: dict[str, dict[str, Any]] = {}
    for source_dict in source_dicts:
        bc = (source_dict.get("schema_json") or {}).get("bank_code") or ""
        if bc:
            bank_to_source[bc] = source_dict

    result: dict[str, str] = {}
    for bank_code, sheets in per_source_answer_pages.items():
        source_dict = bank_to_source.get(bank_code)
        if not source_dict:
            continue
        for sheet_name in sheets:
            content = _fetch_target_content(sheet_name, db, source_dict)
            if content:
                result[_qualify_page(bank_code, sheet_name)] = content
    return result


def _collect_per_source_answer_page_hits(
    rows: list[dict[str, Any]],
    per_source_answer_pages: dict[str, list[str]],
) -> dict[str, dict[str, Any]]:
    """Collect retrieval metadata for multi-bank canonical pages.

    Matches retrieved rows by ``(bank_code, sheet_name)`` and returns hits
    keyed by qualified page names (``BANK:sheet``).
    """
    target_set = {
        _qualify_page(bank, sheet)
        for bank, sheets in per_source_answer_pages.items()
        for sheet in sheets
    }
    hits: dict[str, dict[str, Any]] = {}
    for rank, row in enumerate(rows, 1):
        bank_code = str(row.get("bank_code") or "").strip()
        sheet_name = str(row.get("sheet_name") or "").strip()
        qualified = _qualify_page(bank_code, sheet_name)
        if qualified in target_set and qualified not in hits:
            hits[qualified] = {
                "rank": rank,
                "score": row.get("score", 0),
                "via": row.get("match_sources", []),
            }
    return hits


def _fetch_target_content(page_name: str, db: DataSourcesDB, source: dict[str, Any]) -> str:
    """Fetch raw content for a target page scoped to the configured source."""
    schema_json = source.get("schema_json") or {}
    location = source.get("location") or {}
    bank_code = schema_json.get("bank_code") or location.get("bank_code")
    period_code = schema_json.get("period_code") or location.get("period_code")
    report_type = (
        source.get("report_type")
        or schema_json.get("report_type")
        or location.get("report_type")
        or location.get("retriever_id")
        or source.get("source_id")
    )
    if not bank_code or not period_code or not report_type:
        logging.warning(
            "Skipping ground truth lookup for %s due to incomplete source scope: bank=%r period=%r report_type=%r",
            page_name,
            bank_code,
            period_code,
            report_type,
        )
        return ""

    with db.store.connection() as conn:
        cur = conn.execute(
            """
            SELECT rs.raw_content
            FROM data_sources.report_sheets rs
            JOIN data_sources.report_documents rd ON rd.document_id = rs.document_id
            WHERE rs.sheet_name = %s
              AND rd.bank_code = %s
              AND rd.period_code = %s
              AND rd.report_type = %s
            LIMIT 1
            """,
            (page_name, bank_code, period_code, report_type),
        )
        row = cur.fetchone()
        return row["raw_content"] if row else ""


def _normalize_answer_pages(answer_pages: list[str]) -> list[str]:
    """Return answer pages in stable order without blanks or duplicates."""
    normalized: list[str] = []
    seen: set[str] = set()
    for page_name in answer_pages:
        page = str(page_name).strip()
        if not page or page in seen:
            continue
        seen.add(page)
        normalized.append(page)
    return normalized


def _fetch_ground_truth_pages_multi(
    answer_pages: list[str],
    db: DataSourcesDB,
    source_dicts: list[dict[str, Any]],
) -> dict[str, str]:
    """Try each source_dict in turn for each answer_page; return first match per page."""
    result: dict[str, str] = {}
    for page_name in _normalize_answer_pages(answer_pages):
        for source_dict in source_dicts:
            content = _fetch_target_content(page_name, db, source_dict)
            if content:
                result[page_name] = content
                break
    return result


def _format_ground_truth_payload(ground_truth_pages: dict[str, str]) -> str:
    """Format one or more ground-truth pages for the judge prompt."""
    sections: list[str] = []
    for page_name, content in ground_truth_pages.items():
        sections.append(f"[{page_name}]\n{content}")
    return "\n\n---\n\n".join(sections)


def _collect_answer_page_hits(
    rows: list[dict[str, Any]],
    answer_pages: list[str],
) -> dict[str, dict[str, Any]]:
    """Collect retrieval metadata for the curated answer pages."""
    answer_page_set = set(_normalize_answer_pages(answer_pages))
    hits: dict[str, dict[str, Any]] = {}
    for rank, row in enumerate(rows, 1):
        page_name = str(row.get("sheet_name") or "")
        if page_name not in answer_page_set or page_name in hits:
            continue
        hits[page_name] = {
            "rank": rank,
            "score": row.get("score", 0),
            "via": row.get("match_sources", []),
        }
    return hits


def _extract_answer_source_refs(answer: str) -> list[int]:
    """Extract cited source numbers from a model answer."""
    refs = {int(match.group(1)) for match in _ANSWER_SOURCE_RE.finditer(answer)}
    return sorted(refs)


def _collect_cited_source_pages(
    answer: str,
    context_rows: list[dict[str, Any]],
) -> dict[str, str]:
    """Map cited [Source N] references back to the rows shown to the answer model."""
    refs = _extract_answer_source_refs(answer)
    cited_pages: dict[str, str] = {}
    for ref in refs:
        row_index = ref - 1
        if row_index < 0 or row_index >= len(context_rows):
            continue
        row = context_rows[row_index]
        page_name = str(row.get("sheet_name") or "").strip()
        content = _strip_header(str(row.get("content") or ""))
        if page_name and content and page_name not in cited_pages:
            cited_pages[page_name] = content
    return cited_pages


def _normalize_judgment(judgment: dict[str, Any]) -> dict[str, Any]:
    """Clamp judge output into a consistent score policy (1–5 scale)."""
    normalized = dict(judgment)

    def _clamp(key: str) -> int:
        try:
            val = int(normalized.get(key) or 0)
        except (TypeError, ValueError):
            val = 0
        return max(0, min(5, val))

    retrieval = _clamp("retrieval_accuracy")
    accuracy = _clamp("answer_accuracy")
    completeness = _clamp("answer_completeness")

    if retrieval + accuracy + completeness > 0:
        overall = round((retrieval + accuracy + completeness) / 3)
        overall = max(1, overall)
    else:
        overall = 0

    normalized["retrieval_accuracy"] = retrieval
    normalized["answer_accuracy"] = accuracy
    normalized["answer_completeness"] = completeness
    normalized["overall_score"] = overall
    normalized.setdefault("correct_pages_cited", [])
    normalized.setdefault("missing_pages", [])
    normalized.setdefault("retrieval_notes", "")
    normalized.setdefault("inaccurate_claims", [])
    normalized.setdefault("accuracy_notes", "")
    normalized.setdefault("completeness_notes", "")
    normalized.setdefault("explanation", "")
    return normalized


# ── Per-query worker (runs in a thread) ───────────────────────────────

def _run_single_query(
    qi: int,
    qdata: dict[str, Any],
    retriever: SuppFinancialsRetriever,
    db: DataSourcesDB,
    config: DataSourcesConfig,
) -> dict[str, Any]:
    """Execute one query (retrieval → synthesis → judge) and return its result record."""
    query = qdata["q"]
    terms = qdata["terms"]
    difficulty = qdata["difficulty"]
    answer_pages = _normalize_answer_pages(qdata.get("answer_pages", []))
    answer_pages_tbd = qdata.get("answer_pages_tbd", False)
    # Multi-bank queries supply per_source_answer_pages: {bank_code: [sheet_names]}.
    # When present, effective answer pages are derived from it as qualified "BANK:sheet" keys.
    per_source_answer_pages: dict[str, list[str]] | None = qdata.get("per_source_answer_pages")

    source_dicts = [_build_source_dict(**src) for src in qdata["sources"]]

    log.info("=" * 80)
    log.info("Q%d [%s]: %s", qi, difficulty.upper(), query)
    if per_source_answer_pages:
        per_src_summary = ", ".join(
            f"{b}:{s}" for b, sheets in per_source_answer_pages.items() for s in sheets
        )
        log.info("  Target (per-source): %s | Why hard: %s", per_src_summary, qdata["why_hard"][:80])
    elif answer_pages:
        log.info("  Target: %s | Why hard: %s", ", ".join(answer_pages), qdata["why_hard"][:80])
    else:
        log.info("  Target: TBD | Why hard: %s", qdata["why_hard"][:80])
    log.info("=" * 80)

    retrieval_error: str | None = None
    answer_error: str | None = None
    judge_error: str | None = None
    rows: list[dict[str, Any]] = []
    found_target: bool | None = None
    target_rank = None
    target_score = None
    target_via = None
    answer_page_hits: dict[str, dict[str, Any]] = {}
    matched_answer_pages: list[str] = []
    missing_answer_pages: list[str] = []

    # Determine effective answer pages and pre-fetch ground truth.
    if per_source_answer_pages and not answer_pages_tbd:
        # Multi-bank path: derive qualified page ids from per_source_answer_pages.
        effective_answer_pages = [
            _qualify_page(bank, sheet)
            for bank, sheets in per_source_answer_pages.items()
            for sheet in sheets
        ]
        ground_truth_pages = _fetch_per_source_ground_truth(per_source_answer_pages, db, source_dicts)
        missing_ground_truth_pages = [p for p in effective_answer_pages if p not in ground_truth_pages]
        if missing_ground_truth_pages:
            log.warning("Could not fetch per-source ground truth for %s", ", ".join(missing_ground_truth_pages))
    elif not answer_pages_tbd and answer_pages:
        # Single-source path: flat answer_pages list.
        effective_answer_pages = list(answer_pages)
        ground_truth_pages = _fetch_ground_truth_pages_multi(answer_pages, db, source_dicts)
        missing_ground_truth_pages = [p for p in answer_pages if p not in ground_truth_pages]
        if missing_ground_truth_pages:
            log.warning("Could not fetch ground truth for %s", ", ".join(missing_ground_truth_pages))
    else:
        effective_answer_pages = []
        ground_truth_pages = {}
        missing_ground_truth_pages = []

    # ── Stage 1: Retrieval ────────────────────────────────────────────
    t0 = time.monotonic()
    all_rows: list[dict[str, Any]] = []
    for source_dict in source_dicts:
        try:
            result = retriever.run(
                source=source_dict,
                research_statement=query,
                query_terms=terms,
            )
            all_rows.extend(result.get("sample_rows", []))
        except Exception as exc:
            retrieval_error = f"Retrieval error: {exc}"
            break
    rows = all_rows
    t_retrieval = time.monotonic() - t0

    if not retrieval_error and effective_answer_pages:
        if per_source_answer_pages and not answer_pages_tbd:
            answer_page_hits = _collect_per_source_answer_page_hits(rows, per_source_answer_pages)
        else:
            answer_page_hits = _collect_answer_page_hits(rows, effective_answer_pages)
        matched_answer_pages = [p for p in effective_answer_pages if p in answer_page_hits]
        missing_answer_pages = [p for p in effective_answer_pages if p not in answer_page_hits]
        found_target = not missing_answer_pages
        if matched_answer_pages:
            if found_target:
                target_rank = max(int(answer_page_hits[p]["rank"]) for p in effective_answer_pages)
                target_score = min(float(answer_page_hits[p].get("score") or 0) for p in effective_answer_pages)
                target_via = sorted({
                    s_name
                    for p in effective_answer_pages
                    for s_name in answer_page_hits[p].get("via", [])
                })
            else:
                primary_hit = (
                    answer_page_hits.get(effective_answer_pages[0])
                    or answer_page_hits[matched_answer_pages[0]]
                )
                target_rank = int(primary_hit["rank"])
                target_score = primary_hit.get("score", 0)
                target_via = primary_hit.get("via", [])

    pages_returned = [
        f"{row.get('sheet_name', '?')}({row.get('score', 0):.2f})"
        for row in rows[:5]
    ]
    log.info("  Q%d RETRIEVAL (%.1fs): Pages: %s", qi, t_retrieval, ", ".join(pages_returned))

    if retrieval_error:
        log.warning("  Q%d [X] ERROR — %s", qi, retrieval_error)
    elif answer_pages_tbd:
        log.info("  Q%d [?] TBD — answer pages not yet known, skipping hit check", qi)
    elif found_target:
        page_hits = ", ".join(f"{p}#{answer_page_hits[p]['rank']}" for p in answer_pages)
        log.info("  Q%d [+] HIT — Pages %s, combined score=%.3f, via=%s", qi, page_hits, target_score, target_via)
    elif matched_answer_pages:
        log.info("  Q%d [~] PARTIAL HIT — Found %s; missing %s", qi, ", ".join(matched_answer_pages), ", ".join(missing_answer_pages))
    else:
        log.info("  Q%d [X] MISS — %s NOT fully present in top %d results", qi, ", ".join(answer_pages), len(rows))

    # ── Stage 2: Synthesis ────────────────────────────────────────────
    # Multi-bank queries use a two-stage map-reduce approach to avoid
    # concatenating all banks' raw chunks into one oversized call:
    #   Map:    per-bank extraction — one compact research summary per bank
    #   Reduce: final synthesis — comparative answer from the summaries
    t1 = time.monotonic()
    answer = ""
    answer_rows: list[dict[str, Any]] = []
    per_bank_research: dict[str, str] = {}
    t_research = 0.0
    t_synthesis = 0.0
    if retrieval_error:
        answer_error = f"Skipped synthesis because retrieval failed: {retrieval_error}"
    elif per_source_answer_pages and not answer_pages_tbd:
        try:
            # Group retrieved rows by bank_code
            bank_to_rows: dict[str, list[dict[str, Any]]] = {}
            for row in rows:
                bc = str(row.get("bank_code") or "unknown")
                bank_to_rows.setdefault(bc, []).append(row)

            all_bank_codes = list(bank_to_rows.keys())
            log.info(
                "  Q%d RESEARCH: launching %d parallel bank threads (%s)",
                qi, len(all_bank_codes), ", ".join(all_bank_codes),
            )

            # Stage 2a: per-bank extraction — all banks in parallel
            t_research_start = time.monotonic()
            with ThreadPoolExecutor(max_workers=len(all_bank_codes)) as bank_pool:
                future_to_bank = {
                    bank_pool.submit(
                        _generate_per_bank_research,
                        query, bc, bank_to_rows[bc], all_bank_codes, config,
                    ): bc
                    for bc in all_bank_codes
                }
                for future in as_completed(future_to_bank):
                    bc = future_to_bank[future]
                    try:
                        per_bank_research[bc] = future.result()
                        log.info("  Q%d RESEARCH (%s): done", qi, bc)
                    except Exception as exc:
                        log.warning("  Q%d RESEARCH (%s): error — %s", qi, bc, exc)
                        per_bank_research[bc] = f"[Research failed for {bc}: {exc}]"
            t_research = time.monotonic() - t_research_start
            log.info(
                "  Q%d RESEARCH: all %d banks done in %.1fs",
                qi, len(all_bank_codes), t_research,
            )

            # Stage 2b: cross-bank synthesis
            t_synthesis_start = time.monotonic()
            answer, answer_rows = _synthesize_multi_bank(query, per_bank_research, config)
            t_synthesis = time.monotonic() - t_synthesis_start
        except Exception as exc:
            answer_error = f"Synthesis error: {exc}"
    else:
        try:
            t_synthesis_start = time.monotonic()
            answer_rows = list(rows)
            answer = _generate_answer(query, answer_rows, config)
            t_synthesis = time.monotonic() - t_synthesis_start
        except Exception as exc:
            answer_error = f"Synthesis error: {exc}"
    t_answer = time.monotonic() - t1

    if answer_error:
        log.warning("  Q%d SYNTHESIS (%.1fs): %s", qi, t_answer, answer_error[:300])
    else:
        log.info("  Q%d SYNTHESIS (%.1fs): %s", qi, t_answer, (answer[:300] + "...") if len(answer) > 300 else answer)

    # ── Stage 3: Decomposed judge ─────────────────────────────────────
    t2 = time.monotonic()
    if answer_pages_tbd:
        judgment = _build_failure_judgment("Answer pages TBD — cannot evaluate retrieval hit.")
    elif missing_ground_truth_pages:
        judgment = _build_failure_judgment(
            f"No ground truth available for pages: {', '.join(missing_ground_truth_pages)}",
            inaccurate_claims=[
                f"No ground truth available for pages: {', '.join(missing_ground_truth_pages)}"
            ],
            completeness_notes="Ground truth missing",
        )
    elif answer_error:
        judgment = _build_failure_judgment(answer_error)
    else:
        try:
            cited_source_pages = _collect_cited_source_pages(answer, answer_rows)
            judgment = _judge_answer(
                query,
                answer,
                qdata,
                ground_truth_pages,
                cited_source_pages,
                config,
            )
        except Exception as exc:
            judge_error = f"Judge error: {exc}"
            judgment = _build_failure_judgment(judge_error)
    t_judge = time.monotonic() - t2

    retrieval_acc = judgment.get("retrieval_accuracy", 0)
    answer_acc = judgment.get("answer_accuracy", 0)
    answer_comp = judgment.get("answer_completeness", 0)
    overall = judgment.get("overall_score", 0)
    explanation = judgment.get("explanation", "")

    log.info("  Q%d JUDGMENT (%.1fs):", qi, t_judge)
    log.info("    Retrieval Accuracy:  %d/5 — %s", retrieval_acc, judgment.get("retrieval_notes", "")[:80])
    log.info("    Answer Accuracy:     %d/5 — %s", answer_acc, judgment.get("accuracy_notes", "")[:80])
    log.info("    Answer Completeness: %d/5 — %s", answer_comp, judgment.get("completeness_notes", "")[:80])
    log.info("    Overall:             %d/5 — %s", overall, explanation[:80])

    elapsed = t_retrieval + t_answer + t_judge

    if t_research > 0:
        log.info(
            "  Q%d ── TOTAL %.1fs  [retrieval %.1fs | research %.1fs (%d banks parallel)"
            " | synthesis %.1fs | judge %.1fs]",
            qi, elapsed, t_retrieval, t_research, len(per_bank_research),
            t_synthesis, t_judge,
        )
    else:
        log.info(
            "  Q%d ── TOTAL %.1fs  [retrieval %.1fs | synthesis %.1fs | judge %.1fs]",
            qi, elapsed, t_retrieval, t_synthesis, t_judge,
        )
    returned_pages = [
        {
            "source_num": idx,
            "sheet_id": row.get("sheet_id"),
            "sheet_name": row.get("sheet_name"),
            "page_title": row.get("page_title"),
            "bank_code": row.get("bank_code"),
            "period_code": row.get("period_code"),
            "report_type": row.get("report_type"),
            "score": row.get("score"),
            "match_sources": row.get("match_sources", []),
            "matched_terms": row.get("matched_terms", []),
            "score_breakdown": row.get("score_breakdown", {}),
            "content": row.get("content", ""),
        }
        for idx, row in enumerate(rows, 1)
    ]

    return {
        "query_num": qi,
        "query": query,
        "difficulty": difficulty,
        "terms": terms,
        "why_hard": qdata["why_hard"],
        "answer_pages": answer_pages,
        "answer_pages_tbd": answer_pages_tbd,
        "per_source_answer_pages": per_source_answer_pages or {},
        "effective_answer_pages": effective_answer_pages,
        "per_bank_research": per_bank_research,
        "query_sources": qdata["sources"],
        "matched_answer_pages": matched_answer_pages,
        "missing_answer_pages": missing_answer_pages,
        "answer_page_ranks": {p: int(h["rank"]) for p, h in answer_page_hits.items()},
        "answer_page_scores": {p: float(h.get("score") or 0) for p, h in answer_page_hits.items()},
        "hit": found_target,
        "rank": target_rank,
        "score": target_score,
        "via": target_via,
        "total_returned": len(rows),
        "elapsed_s": round(elapsed, 1),
        "model_answer": answer,
        "model_answer_source_refs": _extract_answer_source_refs(answer),
        "answer_context_pages": [
            str(row.get("sheet_name") or "")
            for row in answer_rows
            if str(row.get("sheet_name") or "").strip()
        ],
        "retrieval_accuracy": retrieval_acc,
        "answer_accuracy": answer_acc,
        "answer_completeness": answer_comp,
        "inaccurate_claims": judgment.get("inaccurate_claims", []),
        "overall_score": overall,
        "explanation": explanation,
        "validated_answer_summary": qdata.get("expected_answer_summary", ""),
        "validated_answer_citations": qdata.get("answer_citations", []),
        "target_contents": ground_truth_pages,
        "judge": judgment,
        "errors": {
            "retrieval": retrieval_error,
            "answer": answer_error,
            "judge": judge_error,
        },
        "retrieval": {
            "hit": found_target,
            "rank": target_rank,
            "score": target_score,
            "via": target_via,
            "total_returned": len(rows),
            "returned_pages": returned_pages,
        },
        "timings": {
            "retrieval_s": round(t_retrieval, 3),
            "research_s": round(t_research, 3),
            "synthesis_s": round(t_synthesis, 3),
            "answer_s": round(t_answer, 3),
            "judge_s": round(t_judge, 3),
            "elapsed_s": round(elapsed, 3),
        },
    }


# ── Main test runner ──────────────────────────────────────────────────

def run_stress_test(
    output_dir: Path | None = None,
    *,
    query_filter: str | None = None,
    max_queries: int | None = None,
    parallel_queries: int = 4,
) -> dict[str, Any]:
    """Run the stress test across all (or filtered) queries and write reports.

    Args:
        output_dir: Directory for JSON/HTML report output.
        query_filter: If set, only run queries whose sources include this report_type
            (e.g. ``"supp_financials"``).
        max_queries: Cap the number of queries run (useful for quick previews).
        parallel_queries: Number of queries to run concurrently (default 4).
    """
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-8s %(name)s  %(message)s",
    )

    config = DataSourcesConfig.from_env()
    store = PostgresStore(dsn=config.database_dsn)
    db = DataSourcesDB(store)
    retriever = SuppFinancialsRetriever(config=config, db=db)

    queries = list(ALL_QUERIES)
    if query_filter:
        queries = [
            q for q in queries
            if any(s.get("report_type") == query_filter for s in q.get("sources", []))
        ]
    if max_queries:
        queries = queries[:max_queries]

    log.info("Running %d queries with parallel_queries=%d", len(queries), parallel_queries)

    all_results: list[dict[str, Any]] = []

    with ThreadPoolExecutor(max_workers=parallel_queries) as pool:
        futures = {
            pool.submit(_run_single_query, qi, qdata, retriever, db, config): qi
            for qi, qdata in enumerate(queries, 1)
        }
        for future in as_completed(futures):
            all_results.append(future.result())

    # Restore query order for consistent report output
    all_results.sort(key=lambda r: r["query_num"])

    # Collect unique source dicts from results
    sources_seen: dict[str, dict[str, Any]] = {}
    for result in all_results:
        for src in result["query_sources"]:
            sd = _build_source_dict(**src)
            sources_seen[sd["source_id"]] = sd

    # ── Summary ───────────────────────────────────────────────────
    evaluable = [r for r in all_results if r["hit"] is not None]
    total = len(all_results)
    hits = sum(1 for r in evaluable if r["hit"])

    log.info("=" * 80)
    log.info("STRESS TEST SUMMARY (%d queries, %d evaluable)", total, len(evaluable))
    log.info("=" * 80)
    if evaluable:
        hit_pct = hits / len(evaluable) * 100
        log.info("  Retrieval: %d/%d (%.0f%% hit rate, excl. TBD)", hits, len(evaluable), hit_pct)

    for diff in ("easy", "medium", "hard"):
        subset = [r for r in evaluable if r["difficulty"] == diff]
        if subset:
            d_hits = sum(1 for r in subset if r["hit"])
            log.info("  %-8s: %d/%d", diff.capitalize(), d_hits, len(subset))

    scored = [r for r in all_results if r["overall_score"] > 0]
    if scored:
        log.info("  Avg Retrieval Accuracy:  %.1f/5", sum(r["retrieval_accuracy"] for r in scored) / len(scored))
        log.info("  Avg Answer Accuracy:     %.1f/5", sum(r["answer_accuracy"] for r in scored) / len(scored))
        log.info("  Avg Completeness:        %.1f/5", sum(r["answer_completeness"] for r in scored) / len(scored))
        log.info("  Avg Overall:             %.1f/5", sum(r["overall_score"] for r in scored) / len(scored))
    else:
        log.info("  No queries were scored (ground truth may be unavailable)")

    sources_used = list(sources_seen.values())
    report = build_report_payload(query_results=all_results, config=config, sources=sources_used)
    output_root = output_dir or Path("data/stress_test_reports")
    paths = write_report_files(report, output_root)
    log.info("  JSON: %s", paths["json"])
    log.info("  HTML: %s", paths["html"])
    return report


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run the multi-source stress test and write JSON/HTML reports."
    )
    parser.add_argument(
        "--output-dir",
        default="data/stress_test_reports",
        help="Directory for generated JSON and HTML reports.",
    )
    parser.add_argument(
        "--source-filter",
        default=None,
        help="Run only queries whose sources include this report_type (e.g. supp_financials).",
    )
    parser.add_argument(
        "--max-queries",
        type=int,
        default=None,
        help="Run only the first N matching queries (useful for quick previews).",
    )
    parser.add_argument(
        "--parallel-queries",
        type=int,
        default=4,
        help="Number of queries to run in parallel (default: 4).",
    )
    args = parser.parse_args()
    run_stress_test(
        output_dir=Path(args.output_dir),
        query_filter=args.source_filter,
        max_queries=args.max_queries,
        parallel_queries=args.parallel_queries,
    )


if __name__ == "__main__":
    main()
