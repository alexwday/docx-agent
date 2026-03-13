"""Curated Q&A pairs for the multi-source stress test framework.

Three document sets, 60 queries total:
  - SUPP_FINANCIALS_QUERIES (20): migrated from original stress_test.py
  - PILLAR3_QUERIES (20): Pillar 3 regulatory disclosure questions
  - INVESTOR_SLIDES_QUERIES (20): investor presentation questions

Query schema:
  q                     : question text
  terms                 : lexical query terms
  why_hard              : domain knowledge required
  difficulty            : easy | medium | hard
  answer_pages          : list of canonical page IDs (empty if answer_pages_tbd)
  answer_pages_tbd      : True = pages not yet known (pillar3 / investor_slides)
  expected_answer_summary: reference answer summary
  answer_citations      : exact source figures
  sources               : list of {report_type, bank, year, quarter} dicts
"""

from __future__ import annotations

from typing import Any

# ── Supplementary Financials (20 queries) ──────────────────────────────

SUPP_FINANCIALS_QUERIES: list[dict[str, Any]] = [
    # ── Derivatives (5 queries) ──────────────────────────────────────
    {
        "q": "What is the total notional amount of RBC's interest rate swap portfolio?",
        "terms": ["notional", "interest", "rate", "swap"],
        "why_hard": "'swap portfolio' is trader jargon. Must map to 'Swaps' under 'Interest rate contracts' in the derivatives credit risk table.",
        "difficulty": "easy",
        "answer_pages": ["Page_33"],
        "answer_pages_tbd": False,
        "answer_citations": [
            "Interest rate contracts — Swaps: Notional amount $28,561,916M (Q1/26)",
        ],
        "expected_answer_summary": "RBC's interest rate swap notional amount was $28,561,916 million as of Q1 2026, as reported in the Derivatives - Related Credit Risk table. This compares to $22,991,164 million in Q4 2025.",
        "sources": [{"report_type": "supp_financials", "bank": "RBC", "year": 2026, "quarter": "Q1"}],
    },
    {
        "q": "What is the gross positive fair value of RBC's derivative book before netting?",
        "terms": ["gross", "positive", "fair", "value", "derivative", "netting"],
        "why_hard": "'derivative book' is informal. Must find 'Total gross fair values before netting' on Page_32. 'Before netting' is explicit but the table uses 'before netting' as a row label.",
        "difficulty": "medium",
        "answer_pages": ["Page_32"],
        "answer_pages_tbd": False,
        "answer_citations": [
            "Total gross fair values before netting: Positive $173,856M, Negative $172,902M (Q1/26)",
        ],
        "expected_answer_summary": "RBC's total gross positive fair value of derivatives before netting was $173,856 million in Q1 2026, with negative fair value at $172,902 million. After netting, these reduce to $172,021M and $171,067M respectively.",
        "sources": [{"report_type": "supp_financials", "bank": "RBC", "year": 2026, "quarter": "Q1"}],
    },
    {
        "q": "How much counterparty exposure does RBC have from OTC credit default swaps?",
        "terms": ["counterparty", "exposure", "otc", "credit", "default", "swaps"],
        "why_hard": "'counterparty exposure' maps to 'credit equivalent amount' or 'replacement cost'. 'credit default swaps' must match 'Credit derivatives'. Multiple domain knowledge bridges required.",
        "difficulty": "hard",
        "answer_pages": ["Page_33"],
        "answer_pages_tbd": False,
        "answer_citations": [
            "Credit derivatives: Notional $348,419M, Replacement cost $704M, Credit equivalent amount $2,179M (Q1/26)",
        ],
        "expected_answer_summary": "RBC's credit derivatives (the closest disclosed category for OTC credit default swaps) had a credit equivalent amount of $2,179M in Q1 2026, with replacement cost of $704M and notional amount of $348,419M.",
        "sources": [{"report_type": "supp_financials", "bank": "RBC", "year": 2026, "quarter": "Q1"}],
    },
    {
        "q": "What is the risk-weighted equivalent of RBC's total OTC and exchange-traded derivative positions?",
        "terms": ["risk-weighted", "equivalent", "total", "derivative", "positions"],
        "why_hard": "Requires summing across OTC and exchange-traded. 'positions' is informal for the full portfolio. Must find the 'Total derivatives' row on Page_33.",
        "difficulty": "medium",
        "answer_pages": ["Page_33"],
        "answer_pages_tbd": False,
        "answer_citations": [
            "Total derivatives: Risk-weighted equivalent $18,930M (Q1/26)",
        ],
        "expected_answer_summary": "RBC's total derivatives (OTC + exchange-traded) had a risk-weighted equivalent of $18,930 million in Q1 2026, down slightly from $18,968M in Q4 2025. The total notional amount was $47,543,435M with replacement cost of $34,649M.",
        "sources": [{"report_type": "supp_financials", "bank": "RBC", "year": 2026, "quarter": "Q1"}],
    },
    {
        "q": "How large is RBC's FX forward book and what is the replacement cost?",
        "terms": ["fx", "forward", "replacement", "cost"],
        "why_hard": "'FX forward' must map to 'Foreign exchange contracts — Forward contracts'. 'book' is trader jargon for position. Tests specific product-level granularity within Page_33.",
        "difficulty": "medium",
        "answer_pages": ["Page_33"],
        "answer_pages_tbd": False,
        "answer_citations": [
            "Foreign exchange contracts — Forward contracts: Notional $3,330,641M, Replacement cost $6,303M (Q1/26)",
        ],
        "expected_answer_summary": "RBC's FX forward book had notional amount of $3,330,641 million with replacement cost of $6,303 million in Q1 2026. The credit equivalent amount was $32,062M and risk-weighted equivalent $6,029M.",
        "sources": [{"report_type": "supp_financials", "bank": "RBC", "year": 2026, "quarter": "Q1"}],
    },
    # ── Income statement / revenue (3 queries) ───────────────────────
    {
        "q": "What is RBC's total net interest income and how does it compare to last year?",
        "terms": ["total", "net", "interest", "income", "compare", "last", "year"],
        "why_hard": "Straightforward but tests whether Page_5 (income statement) is found for NII. Year-over-year comparison requires reading across periods.",
        "difficulty": "easy",
        "answer_pages": ["Page_5"],
        "answer_pages_tbd": False,
        "answer_citations": [
            "Net interest income: $8,585M (Q1/26)",
            "Net interest income full year 2025: $33,000M vs 2024: $27,953M",
        ],
        "expected_answer_summary": "RBC reported net interest income of $8,585M in Q1 2026. For the full year 2025, NII was $33,000M compared to $27,953M in 2024, representing growth of approximately 18%.",
        "sources": [{"report_type": "supp_financials", "bank": "RBC", "year": 2026, "quarter": "Q1"}],
    },
    {
        "q": "Break down RBC's FICC trading revenue versus equities for the latest quarter",
        "terms": ["ficc", "trading", "revenue", "equities", "latest", "quarter"],
        "why_hard": "'FICC' (fixed income, currencies, commodities) is Wall Street shorthand not in the data. Must map to 'interest rate and credit' + 'foreign exchange and commodities' on Page_6.",
        "difficulty": "hard",
        "answer_pages": ["Page_6"],
        "answer_pages_tbd": False,
        "answer_citations": [
            "Interest rate and credit: $755M (Q1/26)",
            "Equities: $569M (Q1/26)",
            "Foreign exchange and commodities: $329M (Q1/26)",
        ],
        "expected_answer_summary": "In Q1 2026, RBC's trading revenue by product was: Interest rate and credit $755M, Foreign exchange and commodities $329M (together the FICC equivalent ~$1,084M), and Equities $569M. Total trading revenue was $1,653M.",
        "sources": [{"report_type": "supp_financials", "bank": "RBC", "year": 2026, "quarter": "Q1"}],
    },
    {
        "q": "What is RBC's pre-provision pre-tax earnings run rate?",
        "terms": ["pre-provision", "pre-tax", "earnings", "run", "rate"],
        "why_hard": "'PPPT earnings' is an analyst construct not a GAAP line item. Must map to income before PCL and taxes on the income statement. 'run rate' adds temporal framing.",
        "difficulty": "hard",
        "answer_pages": ["Page_5"],
        "answer_pages_tbd": False,
        "answer_citations": [
            "Total revenue: $17,960M (Q1/26)",
            "Non-interest expense: $9,463M (Q1/26)",
            "PPPT = Total revenue - NIE = $17,960M - $9,463M = $8,497M",
        ],
        "expected_answer_summary": "Pre-provision pre-tax earnings can be approximated from the income statement as total revenue ($17,960M) minus non-interest expense ($9,463M), yielding approximately $8,497M for Q1 2026. This is an analyst construct, not a GAAP line item.",
        "sources": [{"report_type": "supp_financials", "bank": "RBC", "year": 2026, "quarter": "Q1"}],
    },
    # ── Expense (1 query) ────────────────────────────────────────────
    {
        "q": "How much does RBC spend on employee compensation and benefits?",
        "terms": ["employee", "compensation", "benefits", "spend"],
        "why_hard": "'employee compensation' must map to 'Human resources' category. 'spend' instead of 'expense'. Tests whether Page_7 is found via semantic understanding.",
        "difficulty": "easy",
        "answer_pages": ["Page_7"],
        "answer_pages_tbd": False,
        "answer_citations": [
            "Total Human resources: $6,289M (Q1/26)",
            "Salaries: $2,392M, Variable compensation: $2,753M, Benefits: $801M, Share-based: $343M",
        ],
        "expected_answer_summary": "RBC spent $6,289M on total human resources in Q1 2026, comprising salaries ($2,392M), variable compensation ($2,753M), benefits and retention compensation ($801M), and share-based compensation ($343M).",
        "sources": [{"report_type": "supp_financials", "bank": "RBC", "year": 2026, "quarter": "Q1"}],
    },
    # ── Insurance (2 queries) ────────────────────────────────────────
    {
        "q": "How much did RBC earn from underwriting policies this quarter?",
        "terms": ["underwriting", "policies", "earn"],
        "why_hard": "No keyword contains 'underwriting'. Must rely on semantic understanding that insurance service result ≈ underwriting profit. Zero keyword overlap.",
        "difficulty": "hard",
        "answer_pages": ["Page_12"],
        "answer_pages_tbd": False,
        "answer_citations": [
            "Insurance service result: $240M (Q1/26)",
        ],
        "expected_answer_summary": "RBC's insurance service result, the closest disclosed measure to underwriting profit, was $240M in Q1 2026.",
        "sources": [{"report_type": "supp_financials", "bank": "RBC", "year": 2026, "quarter": "Q1"}],
    },
    {
        "q": "What is the CSM balance for RBC's insurance book?",
        "terms": ["csm", "insurance", "balance"],
        "why_hard": "CSM abbreviation must map to 'contractual service margin'. Row 25 on Page_12 shows the CSM balance. Tests abbreviation-to-full-term matching.",
        "difficulty": "medium",
        "answer_pages": ["Page_12"],
        "answer_pages_tbd": False,
        "answer_citations": [
            "Contractual service margin: $1,773M (Q1/26)",
        ],
        "expected_answer_summary": "RBC's Contractual Service Margin (CSM) balance was $1,773M in Q1 2026, as disclosed on the Insurance page (Page_12) under Additional information.",
        "sources": [{"report_type": "supp_financials", "bank": "RBC", "year": 2026, "quarter": "Q1"}],
    },
    # ── OCI / Comprehensive income (1 query) ─────────────────────────
    {
        "q": "Unrealized mark-to-market gains on FVOCI debt securities this quarter?",
        "terms": ["unrealized", "mark-to-market", "fvoci", "debt", "securities"],
        "why_hard": "'mark-to-market' is trading floor language for fair value changes. Must map to 'Net unrealized gains (losses) on debt securities and loans at FVOCI' on Page_17.",
        "difficulty": "medium",
        "answer_pages": ["Page_17"],
        "answer_pages_tbd": False,
        "answer_citations": [
            "Net unrealized gains on debt securities and loans at FVOCI: $375M (Q1/26)",
        ],
        "expected_answer_summary": "RBC reported net unrealized gains of $375M on debt securities and loans at FVOCI in Q1 2026.",
        "sources": [{"report_type": "supp_financials", "bank": "RBC", "year": 2026, "quarter": "Q1"}],
    },
    # ── Capital / Regulatory (2 queries) ─────────────────────────────
    {
        "q": "What drove the change in RBC's CET1 ratio from last quarter?",
        "terms": ["drove", "change", "cet1", "ratio", "last", "quarter"],
        "why_hard": "'what drove' is a causal question. CET1 changes must come from the flow statement. Tests whether retrieval finds the capital flow page (Page_19) vs. the highlights page.",
        "difficulty": "hard",
        "answer_pages": ["Page_19"],
        "answer_pages_tbd": False,
        "answer_citations": [
            "CET1 capital opening amount: $98,748M (Q1/26)",
            "CET1 capital closing amount: $100,415M (Q1/26)",
            "Prior quarter (Q4/25) closing CET1: $98,748M",
        ],
        "expected_answer_summary": "The Flow Statement of Regulatory Capital (Page_19) shows CET1 capital increased from $98,748M (opening Q1/26) to $100,415M (closing Q1/26). The flow items include new capital issues, retained earnings, and various regulatory deductions/adjustments.",
        "sources": [{"report_type": "supp_financials", "bank": "RBC", "year": 2026, "quarter": "Q1"}],
    },
    {
        "q": "Which business segment consumes the most risk-weighted assets at RBC?",
        "terms": ["business", "segment", "consumes", "risk-weighted", "assets"],
        "why_hard": "'consumes' is informal for 'has allocated'. Comparative question requiring the breakdown by segment on Page_20.",
        "difficulty": "medium",
        "answer_pages": ["Page_20"],
        "answer_pages_tbd": False,
        "answer_citations": [
            "Capital Markets: $271,150M RWA (Q1/26) — largest segment",
            "Personal Banking: $163,829M RWA",
            "Commercial Banking: $136,146M RWA",
            "Wealth Management: $130,856M RWA",
            "Total capital RWA: $734,693M",
        ],
        "expected_answer_summary": "Capital Markets consumes the most RWA at $271,150M (37% of total), followed by Personal Banking at $163,829M and Commercial Banking at $136,146M. Total capital RWA was $734,693M in Q1 2026.",
        "sources": [{"report_type": "supp_financials", "bank": "RBC", "year": 2026, "quarter": "Q1"}],
    },
    # ── Credit quality (2 queries) ───────────────────────────────────
    {
        "q": "What is RBC's NPL ratio and how does it compare to the PCL rate?",
        "terms": ["npl", "ratio", "compare", "pcl", "rate"],
        "why_hard": "'NPL' (non-performing loans) must map to 'gross impaired loans' ratio. 'PCL rate' is shorthand for provision for credit losses as a percentage. Both abbreviations.",
        "difficulty": "hard",
        "answer_pages": ["Page_29"],
        "answer_pages_tbd": False,
        "answer_citations": [
            "GIL as a % of related loans and acceptances: 0.86% (Q1/26)",
            "PCL on loans as a % of average net loans: 0.41% (Q1/26)",
        ],
        "expected_answer_summary": "RBC's gross impaired loans (NPL equivalent) ratio was 0.86% of related loans in Q1 2026, compared with a PCL rate of 0.41% of average net loans. Both ratios are disclosed on the Credit Quality Ratios page (Page_29).",
        "sources": [{"report_type": "supp_financials", "bank": "RBC", "year": 2026, "quarter": "Q1"}],
    },
    {
        "q": "Is there model validation or back-testing data comparing predicted vs actual credit losses?",
        "terms": ["model", "validation", "back-testing", "predicted", "actual", "credit"],
        "why_hard": "'model validation' and 'back-testing' are regulatory concepts not used as keywords. Must map to 'Actual Losses vs. Estimated Losses' on Page_31.",
        "difficulty": "hard",
        "answer_pages": ["Page_31"],
        "answer_pages_tbd": False,
        "answer_citations": [
            "Actual Losses vs. Estimated Losses: compares actual vs estimated loss rates for Retail (residential mortgages, personal, credit cards, small business) and Wholesale",
            "Basel Pillar 3 Back-Testing (Internal Ratings Based): PD, EAD, LGD parameters for retail and wholesale portfolios",
        ],
        "expected_answer_summary": "Yes, Page_31 contains two back-testing tables: (1) Actual Losses vs. Estimated Losses comparing actual and estimated loss rates for retail sub-portfolios and wholesale; (2) Basel Pillar 3 Back-Testing (IRB) showing PD, EAD, and LGD parameters by portfolio segment.",
        "sources": [{"report_type": "supp_financials", "bank": "RBC", "year": 2026, "quarter": "Q1"}],
    },
    # ── Balance sheet / averages (1 query) ───────────────────────────
    {
        "q": "What is RBC's average earning asset base and net interest margin?",
        "terms": ["average", "earning", "asset", "net", "interest", "margin"],
        "why_hard": "'earning asset base' is analyst shorthand for interest-earning assets. Requires combining Page_16 for average earning assets with Page_2 for the reported consolidated NIM ratio.",
        "difficulty": "medium",
        "answer_pages": ["Page_16", "Page_2"],
        "answer_pages_tbd": False,
        "answer_citations": [
            "Average earning assets, net: $2,191,100M (Q1/26)",
            "Net interest margin (NIM) (average earning assets, net): 1.55% (Q1/26)",
        ],
        "expected_answer_summary": "RBC's average earning assets, net were $2,191,100M in Q1 2026 on Page_16. RBC's reported net interest margin (average earning assets, net) was 1.55% in Q1 2026 on Page_2.",
        "sources": [{"report_type": "supp_financials", "bank": "RBC", "year": 2026, "quarter": "Q1"}],
    },
    # ── Equity / Returns (1 query) ───────────────────────────────────
    {
        "q": "How much did RBC return to shareholders through buybacks and dividends in Q1?",
        "terms": ["return", "shareholders", "buybacks", "dividends", "q1"],
        "why_hard": "'return to shareholders' is investor framing. Must map to 'dividends' and 'share repurchases' line items on the equity statement (Page_18).",
        "difficulty": "medium",
        "answer_pages": ["Page_18"],
        "answer_pages_tbd": False,
        "answer_citations": [
            "Common share dividends: -$2,292M (Q1/26)",
            "Dividends on preferred shares and distributions on other equity instruments: -$141M (Q1/26)",
            "Common shares purchased for cancellation: -$63M (Q1/26)",
            "Premium paid on common shares purchased for cancellation: -$897M (Q1/26)",
        ],
        "expected_answer_summary": "In Q1 2026, RBC returned approximately $3,393M to shareholders: $2,292M in common dividends, $141M in preferred dividends/distributions, and $960M related to common share repurchases ($63M of common shares purchased for cancellation plus $897M of premium paid on those repurchases), as shown on the Statements of Changes in Equity (Page_18).",
        "sources": [{"report_type": "supp_financials", "bank": "RBC", "year": 2026, "quarter": "Q1"}],
    },
    # ── ROE / RORC (1 query) ─────────────────────────────────────────
    {
        "q": "What is RBC's return on common equity and how is it calculated?",
        "terms": ["return", "common", "equity", "calculated"],
        "why_hard": "Straightforward ROE question, but the page title says 'RORC' which is less common. Tests whether 'ROE' maps to this specific calculation page (Page_34).",
        "difficulty": "easy",
        "answer_pages": ["Page_34"],
        "answer_pages_tbd": False,
        "answer_citations": [
            "ROE: 17.6% (Q1/26)",
            "Net income available to common shareholders: $5,643M (Q1/26)",
            "Average common equity: $127,350M (Q1/26)",
            "ROE is based on annualized net income available to common shareholders over average common equity",
        ],
        "expected_answer_summary": "RBC's return on common equity was 17.6% in Q1 2026. Page_34 also shows net income available to common shareholders of $5,643M and average common equity of $127,350M, which are the inputs to the annualized ROE calculation reported on that page.",
        "sources": [{"report_type": "supp_financials", "bank": "RBC", "year": 2026, "quarter": "Q1"}],
    },
    # ── Canadian Banking appendix (1 query) ──────────────────────────
    {
        "q": "Break down Canadian P&C banking revenue between net interest income and fee income",
        "terms": ["canadian", "p&c", "banking", "revenue", "net", "interest", "fee"],
        "why_hard": "'P&C banking' is shorthand for 'Personal & Commercial Banking'. Revenue decomposition requires finding both NII and non-interest revenue lines on Page_38.",
        "difficulty": "medium",
        "answer_pages": ["Page_38"],
        "answer_pages_tbd": False,
        "answer_citations": [
            "Canadian Banking net interest income: $5,473M (Q1/26)",
            "Canadian Banking non-interest income: $1,657M (Q1/26)",
            "Canadian Banking total revenue: $7,130M (Q1/26)",
        ],
        "expected_answer_summary": "Canadian Banking revenue in Q1 2026 was $7,130M, comprising net interest income of $5,473M (77%) and non-interest income of $1,657M (23%), as shown on the Appendix - Canadian Banking page (Page_38).",
        "sources": [{"report_type": "supp_financials", "bank": "RBC", "year": 2026, "quarter": "Q1"}],
    },
]


# ── Pillar 3 (20 queries) ───────────────────────────────────────────────

PILLAR3_QUERIES: list[dict[str, Any]] = [
    {
        "q": "For Q1/2026, what are the TLAC RWA ratio and TLAC leverage ratio for each of the six major Canadian banks? Show the current ratio and the quarter-over-quarter change in basis points.",
        "terms": ["TLAC", "RWA ratio", "leverage ratio", "TLAC RWA", "TLAC leverage", "quarter-over-quarter"],
        "why_hard": "Requires finding TLAC disclosures across six separate bank filings and computing QoQ deltas",
        "difficulty": "hard",
        "answer_pages": [],
        "answer_pages_tbd": False,
        # Sheet containing TLAC composition (row 25 = TLAC RWA ratio, row 26 = TLAC leverage ratio).
        # BMO=Page 13, BNS/CIBC/RBC=TLAC1, NBC=sheet 18, TD=sheet 9.
        "per_source_answer_pages": {
            "BMO": ["Page 13"],
            "BNS": ["TLAC1"],
            "CIBC": ["TLAC1"],
            "NBC": ["18"],
            "RBC": ["TLAC1"],
            "TD": ["9"],
        },
        "expected_answer_summary": (
            "BMO: TLAC RWA 29.1% (↓60 bps QoQ), TLAC leverage 8.6% (↑10 bps QoQ). "
            "BNS: TLAC RWA 28.6% (↓50 bps QoQ), TLAC leverage 8.3% (↓20 bps QoQ). "
            "CIBC: TLAC RWA 32.1% (↑20 bps QoQ), TLAC leverage 9.1% (↑10 bps QoQ). "
            "NBC: TLAC RWA 32.5% (↑280 bps QoQ), TLAC leverage 9.2% (↑40 bps QoQ). "
            "RBC: TLAC RWA 30.9% (↓60 bps QoQ), TLAC leverage 9.0% (↓20 bps QoQ). "
            "TD: TLAC RWA 31.1% (↓70 bps QoQ), TLAC leverage 8.6% (↓30 bps QoQ)."
        ),
        "answer_citations": [
            "BMO TLAC RWA ratio (row 25): 29.1% Q1/26, 29.7% Q4/25",
            "BMO TLAC leverage ratio (row 26): 8.6% Q1/26, 8.5% Q4/25",
            "BNS TLAC RWA ratio (row 25): 28.6% Q1/26, 29.1% Q4/25",
            "BNS TLAC leverage ratio (row 26): 8.3% Q1/26, 8.5% Q4/25",
            "CIBC TLAC RWA ratio (row 25): 32.1% Q1/26, 31.9% Q4/25",
            "CIBC TLAC leverage ratio (row 26): 9.1% Q1/26, 9.0% Q4/25",
            "NBC TLAC RWA ratio (row 25): 32.5% Q1/26, 29.7% Q4/25",
            "NBC TLAC leverage ratio (row 26): 9.2% Q1/26, 8.8% Q4/25",
            "RBC TLAC RWA ratio (row 25): 30.9% Q1/26, 31.5% Q4/25",
            "RBC TLAC leverage ratio (row 26): 9.0% Q1/26, 9.2% Q4/25",
            "TD TLAC RWA ratio (row 25): 31.1% Q1/26, 31.8% Q4/25",
            "TD TLAC leverage ratio (row 26): 8.6% Q1/26, 8.9% Q4/25",
        ],
        "sources": [
            {"report_type": "pillar3", "bank": "BMO", "year": 2026, "quarter": "Q1"},
            {"report_type": "pillar3", "bank": "BNS", "year": 2026, "quarter": "Q1"},
            {"report_type": "pillar3", "bank": "CIBC", "year": 2026, "quarter": "Q1"},
            {"report_type": "pillar3", "bank": "NBC", "year": 2026, "quarter": "Q1"},
            {"report_type": "pillar3", "bank": "RBC", "year": 2026, "quarter": "Q1"},
            {"report_type": "pillar3", "bank": "TD", "year": 2026, "quarter": "Q1"},
        ],
    },
    {
        "q": "Compare the CET1 capital ratios reported by all six major Canadian banks for Q1/2026. For each bank, state the CET1 ratio and its change versus Q4/2025 in basis points. Which bank reported the highest and lowest CET1 ratio?",
        "terms": ["CET1", "Common Equity Tier 1", "capital ratio", "quarter-over-quarter", "basis points"],
        "why_hard": "Multi-bank cross-document comparison requiring QoQ delta computation across six filings",
        "difficulty": "hard",
        "answer_pages": [],
        "answer_pages_tbd": False,
        # Sheet containing KM1 key metrics (row 5 = CET1 ratio).
        # BMO=Page 4, BNS/RBC=KM1, CIBC=KM1 - CQ PQ1 PQ2, NBC=sheet 5, TD=sheet 7.
        "per_source_answer_pages": {
            "BMO": ["Page 4"],
            "BNS": ["KM1"],
            "CIBC": ["KM1 - CQ, PQ1, PQ2"],
            "NBC": ["5"],
            "RBC": ["KM1"],
            "TD": ["7"],
        },
        "expected_answer_summary": (
            "BMO: 13.1% (↓20 bps vs Q4/25). BNS: 13.3% (↑10 bps). CIBC: 13.4% (↑10 bps). "
            "NBC: 13.7% (↓10 bps). RBC: 13.7% (↑20 bps). TD: 14.5% (↓20 bps). "
            "Highest CET1: TD at 14.5%. Lowest CET1: BMO at 13.1%."
        ),
        "answer_citations": [
            "BMO CET1 ratio (row 5): 13.1% Q1/26, 13.3% Q4/25",
            "BNS CET1 ratio (row 5): 13.3% Q1/26, 13.2% Q4/25",
            "CIBC CET1 ratio (row 5): 13.4% Q1/26, 13.3% Q4/25",
            "NBC CET1 ratio (row 5): 13.7% Q1/26, 13.8% Q4/25",
            "RBC CET1 ratio (row 5): 13.7% Q1/26, 13.5% Q4/25",
            "TD CET1 ratio (row 5): 14.5% Q1/26, 14.7% Q4/25",
        ],
        "sources": [
            {"report_type": "pillar3", "bank": "BMO", "year": 2026, "quarter": "Q1"},
            {"report_type": "pillar3", "bank": "BNS", "year": 2026, "quarter": "Q1"},
            {"report_type": "pillar3", "bank": "CIBC", "year": 2026, "quarter": "Q1"},
            {"report_type": "pillar3", "bank": "NBC", "year": 2026, "quarter": "Q1"},
            {"report_type": "pillar3", "bank": "RBC", "year": 2026, "quarter": "Q1"},
            {"report_type": "pillar3", "bank": "TD", "year": 2026, "quarter": "Q1"},
        ],
    },
    {
        "q": "What was the Basel III leverage ratio for each of the six major Canadian banks in Q1/2026, and how did it change compared to Q4/2025?",
        "terms": ["leverage ratio", "Basel III", "Tier 1 leverage", "quarter-over-quarter"],
        "why_hard": "Leverage ratio can appear in multiple sections; must distinguish from TLAC leverage ratio across six filings",
        "difficulty": "medium",
        "answer_pages": [],
        "answer_pages_tbd": False,
        # Sheet containing KM1 key metrics (row 14 = Basel III leverage ratio).
        # Same KM1 sheet per bank as CET1 query.
        "per_source_answer_pages": {
            "BMO": ["Page 4"],
            "BNS": ["KM1"],
            "CIBC": ["KM1 - CQ, PQ1, PQ2"],
            "NBC": ["5"],
            "RBC": ["KM1"],
            "TD": ["7"],
        },
        "expected_answer_summary": (
            "BMO: 4.4% (↑10 bps vs Q4/25). BNS: 4.4% (↓10 bps). CIBC: 4.4% (↑10 bps). "
            "NBC: 4.3% (↓20 bps). RBC: 4.4% (unchanged). TD: 4.5% (↓10 bps). "
            "All six banks remain comfortably above the 3% OSFI minimum leverage ratio requirement."
        ),
        "answer_citations": [
            "BMO Basel III leverage ratio (row 14): 4.4% Q1/26, 4.3% Q4/25",
            "BNS Basel III leverage ratio (row 14): 4.4% Q1/26, 4.5% Q4/25",
            "CIBC leverage ratio (row 14): 4.4% Q1/26, 4.3% Q4/25",
            "NBC Basel III leverage ratio (row 14): 4.3% Q1/26, 4.5% Q4/25",
            "RBC Basel III leverage ratio (row 14): 4.4% Q1/26, 4.4% Q4/25",
            "TD Basel III leverage ratio (row 14): 4.5% Q1/26, 4.6% Q4/25",
        ],
        "sources": [
            {"report_type": "pillar3", "bank": "BMO", "year": 2026, "quarter": "Q1"},
            {"report_type": "pillar3", "bank": "BNS", "year": 2026, "quarter": "Q1"},
            {"report_type": "pillar3", "bank": "CIBC", "year": 2026, "quarter": "Q1"},
            {"report_type": "pillar3", "bank": "NBC", "year": 2026, "quarter": "Q1"},
            {"report_type": "pillar3", "bank": "RBC", "year": 2026, "quarter": "Q1"},
            {"report_type": "pillar3", "bank": "TD", "year": 2026, "quarter": "Q1"},
        ],
    },
    {
        "q": "For Q1/2026, compare the total capital ratios across all six major Canadian banks. State the Q1/2026 ratio and the basis point change versus Q4/2025 for each bank.",
        "terms": ["total capital ratio", "capital adequacy", "quarter-over-quarter", "basis points"],
        "why_hard": "Total capital ratio must be distinguished from Tier 1 and CET1; requires cross-filing aggregation",
        "difficulty": "medium",
        "answer_pages": [],
        "answer_pages_tbd": False,
        # Sheet containing KM1 key metrics (row 7 = total capital ratio).
        # Same KM1 sheet per bank as CET1 query.
        "per_source_answer_pages": {
            "BMO": ["Page 4"],
            "BNS": ["KM1"],
            "CIBC": ["KM1 - CQ, PQ1, PQ2"],
            "NBC": ["5"],
            "RBC": ["KM1"],
            "TD": ["7"],
        },
        "expected_answer_summary": (
            "BMO: 16.9% (↓40 bps vs Q4/25). BNS: 17.0% (↓10 bps). CIBC: 17.7% (↑30 bps). "
            "NBC: 17.3% (unchanged). RBC: 16.8% (unchanged). TD: 18.1% (↓30 bps). "
            "Highest total capital ratio: TD at 18.1%. Lowest: RBC at 16.8%."
        ),
        "answer_citations": [
            "BMO total capital ratio (row 7): 16.9% Q1/26, 17.3% Q4/25",
            "BNS total capital ratio (row 7): 17.0% Q1/26, 17.1% Q4/25",
            "CIBC total capital ratio (row 7): 17.7% Q1/26, 17.4% Q4/25",
            "NBC total capital ratio (row 7): 17.3% Q1/26, 17.3% Q4/25",
            "RBC total capital ratio (row 7): 16.8% Q1/26, 16.8% Q4/25",
            "TD total capital ratio (row 7): 18.1% Q1/26, 18.4% Q4/25",
        ],
        "sources": [
            {"report_type": "pillar3", "bank": "BMO", "year": 2026, "quarter": "Q1"},
            {"report_type": "pillar3", "bank": "BNS", "year": 2026, "quarter": "Q1"},
            {"report_type": "pillar3", "bank": "CIBC", "year": 2026, "quarter": "Q1"},
            {"report_type": "pillar3", "bank": "NBC", "year": 2026, "quarter": "Q1"},
            {"report_type": "pillar3", "bank": "RBC", "year": 2026, "quarter": "Q1"},
            {"report_type": "pillar3", "bank": "TD", "year": 2026, "quarter": "Q1"},
        ],
    },
    {
        "q": "What were the Tier 1 capital ratios for all six major Canadian banks in Q1/2026? Show both the current quarter ratio and the quarter-over-quarter change.",
        "terms": ["Tier 1", "capital ratio", "T1 ratio", "quarter-over-quarter", "basis points"],
        "why_hard": "Must extract Tier 1 (not CET1) specifically and compare across all six filings with QoQ delta",
        "difficulty": "medium",
        "answer_pages": [],
        "answer_pages_tbd": False,
        # Sheet containing KM1 key metrics (row 6 = Tier 1 ratio).
        # Same KM1 sheet per bank as CET1 query.
        "per_source_answer_pages": {
            "BMO": ["Page 4"],
            "BNS": ["KM1"],
            "CIBC": ["KM1 - CQ, PQ1, PQ2"],
            "NBC": ["5"],
            "RBC": ["KM1"],
            "TD": ["7"],
        },
        "expected_answer_summary": (
            "BMO: 14.8% (↓20 bps vs Q4/25). BNS: 15.4% (↑10 bps). CIBC: 15.4% (↑30 bps). "
            "NBC: 15.1% (unchanged). RBC: 15.2% (↑10 bps). TD: 16.3% (↓10 bps). "
            "Highest Tier 1 ratio: TD at 16.3%. Lowest: BMO at 14.8%."
        ),
        "answer_citations": [
            "BMO Tier 1 ratio (row 6): 14.8% Q1/26, 15.0% Q4/25",
            "BNS Tier 1 ratio (row 6): 15.4% Q1/26, 15.3% Q4/25",
            "CIBC Tier 1 ratio (row 6): 15.4% Q1/26, 15.1% Q4/25",
            "NBC Tier 1 ratio (row 6): 15.1% Q1/26, 15.1% Q4/25",
            "RBC Tier 1 ratio (row 6): 15.2% Q1/26, 15.1% Q4/25",
            "TD Tier 1 ratio (row 6): 16.3% Q1/26, 16.4% Q4/25",
        ],
        "sources": [
            {"report_type": "pillar3", "bank": "BMO", "year": 2026, "quarter": "Q1"},
            {"report_type": "pillar3", "bank": "BNS", "year": 2026, "quarter": "Q1"},
            {"report_type": "pillar3", "bank": "CIBC", "year": 2026, "quarter": "Q1"},
            {"report_type": "pillar3", "bank": "NBC", "year": 2026, "quarter": "Q1"},
            {"report_type": "pillar3", "bank": "RBC", "year": 2026, "quarter": "Q1"},
            {"report_type": "pillar3", "bank": "TD", "year": 2026, "quarter": "Q1"},
        ],
    },
    {
        "q": "What is RBC's Net Stable Funding Ratio and how does it decompose between available and required stable funding?",
        "terms": ["nsfr", "net", "stable", "funding", "ratio", "available", "required"],
        "why_hard": "NSFR terminology is highly specific (ASF, RSF factors) and uses regulatory definitions that differ from general balance sheet terms.",
        "difficulty": "hard",
        "answer_pages": [],
        "answer_pages_tbd": True,
        "answer_citations": [],
        "expected_answer_summary": "TBD — requires pillar3 document ingestion.",
        "sources": [{"report_type": "pillar3", "bank": "RBC", "year": 2026, "quarter": "Q1"}],
    },
    {
        "q": "How does RBC break down credit risk exposure by counterparty type (sovereign, bank, corporate, retail)?",
        "terms": ["credit", "exposure", "counterparty", "sovereign", "bank", "corporate", "retail"],
        "why_hard": "Counterparty type classification uses Basel categories that differ from business segment labels used elsewhere.",
        "difficulty": "medium",
        "answer_pages": [],
        "answer_pages_tbd": True,
        "answer_citations": [],
        "expected_answer_summary": "TBD — requires pillar3 document ingestion.",
        "sources": [{"report_type": "pillar3", "bank": "RBC", "year": 2026, "quarter": "Q1"}],
    },
    {
        "q": "What is RBC's total Value-at-Risk for market risk, broken down by risk factor?",
        "terms": ["var", "value-at-risk", "market", "risk", "interest", "equity", "commodity"],
        "why_hard": "VaR decomposition by risk factor (interest rate, equity, FX, commodity, credit spread) requires locating the trading VaR table in the Pillar 3 market risk section.",
        "difficulty": "hard",
        "answer_pages": [],
        "answer_pages_tbd": True,
        "answer_citations": [],
        "expected_answer_summary": "TBD — requires pillar3 document ingestion.",
        "sources": [{"report_type": "pillar3", "bank": "RBC", "year": 2026, "quarter": "Q1"}],
    },
    {
        "q": "What is the Expected Shortfall capital charge for RBC's trading book?",
        "terms": ["expected", "shortfall", "es", "trading", "book", "capital"],
        "why_hard": "Expected Shortfall replaced VaR under FRTB. Must distinguish the ES-based IMA charge from the legacy VaR disclosures that may also appear.",
        "difficulty": "hard",
        "answer_pages": [],
        "answer_pages_tbd": True,
        "answer_citations": [],
        "expected_answer_summary": "TBD — requires pillar3 document ingestion.",
        "sources": [{"report_type": "pillar3", "bank": "RBC", "year": 2026, "quarter": "Q1"}],
    },
    {
        "q": "What methodology does RBC use to calculate operational risk capital and what is the capital requirement?",
        "terms": ["operational", "risk", "capital", "methodology", "standardized", "advanced"],
        "why_hard": "Operational risk methodology (SMA vs AMA) is a regulatory disclosure requiring interpretation of Pillar 3 descriptive text alongside the capital figure.",
        "difficulty": "medium",
        "answer_pages": [],
        "answer_pages_tbd": True,
        "answer_citations": [],
        "expected_answer_summary": "TBD — requires pillar3 document ingestion.",
        "sources": [{"report_type": "pillar3", "bank": "RBC", "year": 2026, "quarter": "Q1"}],
    },
    {
        "q": "What are RBC's securitization and off-balance-sheet exposure amounts in the Pillar 3 disclosure?",
        "terms": ["securitization", "off-balance-sheet", "exposure", "conduit", "abcp"],
        "why_hard": "Securitization treatment under Basel distinguishes originators, sponsors, and investors, requiring the correct table in the structured finance section.",
        "difficulty": "hard",
        "answer_pages": [],
        "answer_pages_tbd": True,
        "answer_citations": [],
        "expected_answer_summary": "TBD — requires pillar3 document ingestion.",
        "sources": [{"report_type": "pillar3", "bank": "RBC", "year": 2026, "quarter": "Q1"}],
    },
    {
        "q": "What is the IFRS 9 Stage 1, Stage 2, and Stage 3 breakdown of RBC's loan book?",
        "terms": ["ifrs", "stage", "1", "2", "3", "ecl", "expected", "credit", "loss"],
        "why_hard": "IFRS 9 staging uses specific criteria (12-month vs lifetime ECL) that must be mapped to the staging table, distinct from the performing/impaired split used in prior standards.",
        "difficulty": "medium",
        "answer_pages": [],
        "answer_pages_tbd": True,
        "answer_citations": [],
        "expected_answer_summary": "TBD — requires pillar3 document ingestion.",
        "sources": [{"report_type": "pillar3", "bank": "RBC", "year": 2026, "quarter": "Q1"}],
    },
    {
        "q": "What countercyclical capital buffer (CCyB) rate applies to RBC's Canadian exposures?",
        "terms": ["countercyclical", "capital", "buffer", "ccyb", "canadian", "exposures"],
        "why_hard": "CCyB is jurisdiction-specific and the Pillar 3 table must be filtered to the Canada row. The rate may differ for foreign exposures in the same table.",
        "difficulty": "medium",
        "answer_pages": [],
        "answer_pages_tbd": True,
        "answer_citations": [],
        "expected_answer_summary": "TBD — requires pillar3 document ingestion.",
        "sources": [{"report_type": "pillar3", "bank": "RBC", "year": 2026, "quarter": "Q1"}],
    },
    {
        "q": "What regulatory capital deductions does RBC apply to arrive at its CET1 capital figure?",
        "terms": ["regulatory", "capital", "deductions", "cet1", "goodwill", "intangibles", "dta"],
        "why_hard": "Capital deductions (goodwill, intangibles, deferred tax, pension, minority interests) each have Basel-specific treatment and threshold calculations.",
        "difficulty": "hard",
        "answer_pages": [],
        "answer_pages_tbd": True,
        "answer_citations": [],
        "expected_answer_summary": "TBD — requires pillar3 document ingestion.",
        "sources": [{"report_type": "pillar3", "bank": "RBC", "year": 2026, "quarter": "Q1"}],
    },
    {
        "q": "What is the geographic breakdown of RBC's credit exposures (EAD) by country or region?",
        "terms": ["ead", "exposure", "geography", "country", "region", "canada", "united", "states"],
        "why_hard": "Geographic EAD requires finding the correct cross-tabulation (by geography AND exposure class) within the Pillar 3 credit risk section.",
        "difficulty": "medium",
        "answer_pages": [],
        "answer_pages_tbd": True,
        "answer_citations": [],
        "expected_answer_summary": "TBD — requires pillar3 document ingestion.",
        "sources": [{"report_type": "pillar3", "bank": "RBC", "year": 2026, "quarter": "Q1"}],
    },
    {
        "q": "How do RBC's IRB model back-testing results compare predicted default rates to actual outcomes?",
        "terms": ["irb", "back-testing", "predicted", "actual", "default", "pd", "model"],
        "why_hard": "Model back-testing compares ex-ante PD forecasts to ex-post realised defaults over a historical horizon — requires interpretation of the back-testing table.",
        "difficulty": "hard",
        "answer_pages": [],
        "answer_pages_tbd": True,
        "answer_citations": [],
        "expected_answer_summary": "TBD — requires pillar3 document ingestion.",
        "sources": [{"report_type": "pillar3", "bank": "RBC", "year": 2026, "quarter": "Q1"}],
    },
    {
        "q": "What Pillar 2 supervisory capital add-ons (ICAAP) does RBC disclose?",
        "terms": ["pillar", "2", "icaap", "supervisory", "add-on", "capital", "requirement"],
        "why_hard": "Pillar 2 disclosures are often qualitative; the specific add-on amount may be partially redacted or expressed in ranges, requiring careful parsing.",
        "difficulty": "hard",
        "answer_pages": [],
        "answer_pages_tbd": True,
        "answer_citations": [],
        "expected_answer_summary": "TBD — requires pillar3 document ingestion.",
        "sources": [{"report_type": "pillar3", "bank": "RBC", "year": 2026, "quarter": "Q1"}],
    },
    {
        "q": "What is RBC's CVA (Credit Valuation Adjustment) capital charge?",
        "terms": ["cva", "credit", "valuation", "adjustment", "capital", "charge"],
        "why_hard": "CVA capital charge under SA-CVA or BA-CVA requires distinguishing the CVA desk hedging from the standalone CVA charge in the Pillar 3 table.",
        "difficulty": "hard",
        "answer_pages": [],
        "answer_pages_tbd": True,
        "answer_citations": [],
        "expected_answer_summary": "TBD — requires pillar3 document ingestion.",
        "sources": [{"report_type": "pillar3", "bank": "RBC", "year": 2026, "quarter": "Q1"}],
    },
    {
        "q": "What D-SIB (Domestic Systemically Important Bank) capital surcharge applies to RBC and how is it held?",
        "terms": ["dsib", "systemically", "important", "surcharge", "buffer", "tier", "capital"],
        "why_hard": "D-SIB buffer rate set by OSFI differs from G-SIB surcharge; disclosure must be traced to the specific regulatory buffer table with the applicable holding instrument.",
        "difficulty": "medium",
        "answer_pages": [],
        "answer_pages_tbd": True,
        "answer_citations": [],
        "expected_answer_summary": "TBD — requires pillar3 document ingestion.",
        "sources": [{"report_type": "pillar3", "bank": "RBC", "year": 2026, "quarter": "Q1"}],
    },
    {
        "q": "What is RBC's Interest Rate Risk in the Banking Book (IRRBB) sensitivity to a 100 bps parallel shift?",
        "terms": ["irrbb", "interest", "rate", "risk", "banking", "book", "sensitivity", "basis", "points"],
        "why_hard": "IRRBB EVE and NII sensitivities are disclosed under separate shock scenarios; must locate the 100 bps parallel shift row, not the +200 bps or -100 bps alternative scenarios.",
        "difficulty": "hard",
        "answer_pages": [],
        "answer_pages_tbd": True,
        "answer_citations": [],
        "expected_answer_summary": "TBD — requires pillar3 document ingestion.",
        "sources": [{"report_type": "pillar3", "bank": "RBC", "year": 2026, "quarter": "Q1"}],
    },
]


# ── Investor Slides (20 queries) ────────────────────────────────────────

INVESTOR_SLIDES_QUERIES: list[dict[str, Any]] = [
    {
        "q": "What was RBC's adjusted EPS and how did it grow year over year?",
        "terms": ["adjusted", "eps", "earnings", "per", "share", "growth"],
        "why_hard": "Adjusted EPS excludes specific items; the investor deck must be checked for which adjustments are disclosed and the YoY comparison slide.",
        "difficulty": "easy",
        "answer_pages": [],
        "answer_pages_tbd": True,
        "answer_citations": [],
        "expected_answer_summary": "TBD — requires investor_slides document ingestion.",
        "sources": [{"report_type": "investor_slides", "bank": "RBC", "year": 2026, "quarter": "Q1"}],
    },
    {
        "q": "What are RBC's ROE and ROTE targets for the medium term and how does Q1 2026 performance compare?",
        "terms": ["roe", "rote", "return", "equity", "tangible", "target", "medium-term"],
        "why_hard": "Targets vs actuals on the same slide require distinguishing management guidance from reported GAAP figures.",
        "difficulty": "medium",
        "answer_pages": [],
        "answer_pages_tbd": True,
        "answer_citations": [],
        "expected_answer_summary": "TBD — requires investor_slides document ingestion.",
        "sources": [{"report_type": "investor_slides", "bank": "RBC", "year": 2026, "quarter": "Q1"}],
    },
    {
        "q": "How did revenue grow across RBC's business segments in Q1 2026?",
        "terms": ["revenue", "segment", "growth", "capital", "markets", "wealth", "banking"],
        "why_hard": "Investor slides often present adjusted revenue growth rates that differ from reported GAAP, and segments may be renamed relative to the supplementary financials.",
        "difficulty": "medium",
        "answer_pages": [],
        "answer_pages_tbd": True,
        "answer_citations": [],
        "expected_answer_summary": "TBD — requires investor_slides document ingestion.",
        "sources": [{"report_type": "investor_slides", "bank": "RBC", "year": 2026, "quarter": "Q1"}],
    },
    {
        "q": "What is RBC's efficiency ratio and what is the target for the full year?",
        "terms": ["efficiency", "ratio", "expense", "non-interest", "operating", "leverage"],
        "why_hard": "'efficiency ratio' may be reported on an adjusted basis in investor materials; the full-year target requires finding the guidance slide.",
        "difficulty": "easy",
        "answer_pages": [],
        "answer_pages_tbd": True,
        "answer_citations": [],
        "expected_answer_summary": "TBD — requires investor_slides document ingestion.",
        "sources": [{"report_type": "investor_slides", "bank": "RBC", "year": 2026, "quarter": "Q1"}],
    },
    {
        "q": "What is RBC's capital return strategy, including dividend policy and buyback plans?",
        "terms": ["capital", "return", "dividend", "buyback", "payout", "ratio", "strategy"],
        "why_hard": "Capital return strategy slides combine dividend payout ratios, NCIB (Normal Course Issuer Bid) approval amounts, and management commentary on buyback pace.",
        "difficulty": "medium",
        "answer_pages": [],
        "answer_pages_tbd": True,
        "answer_citations": [],
        "expected_answer_summary": "TBD — requires investor_slides document ingestion.",
        "sources": [{"report_type": "investor_slides", "bank": "RBC", "year": 2026, "quarter": "Q1"}],
    },
    {
        "q": "What is management's outlook for net interest margin over the next two quarters?",
        "terms": ["net", "interest", "margin", "nim", "outlook", "guidance", "rate"],
        "why_hard": "NIM guidance is typically qualitative or directional in investor presentations, not a precise range, requiring semantic matching to forward-looking language.",
        "difficulty": "medium",
        "answer_pages": [],
        "answer_pages_tbd": True,
        "answer_citations": [],
        "expected_answer_summary": "TBD — requires investor_slides document ingestion.",
        "sources": [{"report_type": "investor_slides", "bank": "RBC", "year": 2026, "quarter": "Q1"}],
    },
    {
        "q": "What loan growth guidance did RBC provide for personal and commercial banking in 2026?",
        "terms": ["loan", "growth", "guidance", "personal", "commercial", "banking", "2026"],
        "why_hard": "Loan growth guidance may be expressed as a range or directional comment, and the category granularity (mortgages vs. commercial) may vary by slide.",
        "difficulty": "medium",
        "answer_pages": [],
        "answer_pages_tbd": True,
        "answer_citations": [],
        "expected_answer_summary": "TBD — requires investor_slides document ingestion.",
        "sources": [{"report_type": "investor_slides", "bank": "RBC", "year": 2026, "quarter": "Q1"}],
    },
    {
        "q": "What are RBC's Wealth Management AUM and AUA figures and what drove the change?",
        "terms": ["wealth", "management", "aum", "aua", "assets", "under", "management"],
        "why_hard": "'AUM' and 'AUA' (assets under administration) are different metrics; the investor slide must be located and the change drivers (market appreciation vs. net flows) extracted.",
        "difficulty": "medium",
        "answer_pages": [],
        "answer_pages_tbd": True,
        "answer_citations": [],
        "expected_answer_summary": "TBD — requires investor_slides document ingestion.",
        "sources": [{"report_type": "investor_slides", "bank": "RBC", "year": 2026, "quarter": "Q1"}],
    },
    {
        "q": "How is Capital Markets revenue broken down between advisory, underwriting, trading, and lending?",
        "terms": ["capital", "markets", "advisory", "underwriting", "trading", "lending", "revenue"],
        "why_hard": "Capital Markets revenue mix uses IB-specific terminology (M&A advisory, DCM/ECM underwriting) that maps to regulatory categories differently than in the supplementary package.",
        "difficulty": "hard",
        "answer_pages": [],
        "answer_pages_tbd": True,
        "answer_citations": [],
        "expected_answer_summary": "TBD — requires investor_slides document ingestion.",
        "sources": [{"report_type": "investor_slides", "bank": "RBC", "year": 2026, "quarter": "Q1"}],
    },
    {
        "q": "How much did the Insurance segment contribute to RBC's total earnings in Q1 2026?",
        "terms": ["insurance", "earnings", "contribution", "segment", "net", "income"],
        "why_hard": "Insurance contribution in the investor deck may be presented as a percentage of total earnings or as a dollar figure, and may differ from supplementary package methodology.",
        "difficulty": "easy",
        "answer_pages": [],
        "answer_pages_tbd": True,
        "answer_citations": [],
        "expected_answer_summary": "TBD — requires investor_slides document ingestion.",
        "sources": [{"report_type": "investor_slides", "bank": "RBC", "year": 2026, "quarter": "Q1"}],
    },
    {
        "q": "How much is RBC investing in digital and technology, and what are the key initiatives?",
        "terms": ["digital", "technology", "investment", "initiative", "platform", "modernization"],
        "why_hard": "Technology investment may be disclosed as a total capex/opex figure or as directional commentary on specific platforms; qualitative slides require semantic retrieval.",
        "difficulty": "medium",
        "answer_pages": [],
        "answer_pages_tbd": True,
        "answer_citations": [],
        "expected_answer_summary": "TBD — requires investor_slides document ingestion.",
        "sources": [{"report_type": "investor_slides", "bank": "RBC", "year": 2026, "quarter": "Q1"}],
    },
    {
        "q": "What geographic expansion plans did RBC highlight for its capital markets or wealth businesses?",
        "terms": ["geographic", "expansion", "international", "growth", "us", "europe", "asia"],
        "why_hard": "Geographic strategy slides combine multiple geographies and business lines; locating specific market entry or expansion commentary requires semantic matching.",
        "difficulty": "hard",
        "answer_pages": [],
        "answer_pages_tbd": True,
        "answer_citations": [],
        "expected_answer_summary": "TBD — requires investor_slides document ingestion.",
        "sources": [{"report_type": "investor_slides", "bank": "RBC", "year": 2026, "quarter": "Q1"}],
    },
    {
        "q": "What is RBC's credit quality outlook and how does management expect PCL to trend?",
        "terms": ["credit", "quality", "outlook", "pcl", "provision", "credit", "losses", "trend"],
        "why_hard": "Management's PCL outlook language is forward-looking and qualitative; must be distinguished from the reported PCL figures on financial slides.",
        "difficulty": "medium",
        "answer_pages": [],
        "answer_pages_tbd": True,
        "answer_citations": [],
        "expected_answer_summary": "TBD — requires investor_slides document ingestion.",
        "sources": [{"report_type": "investor_slides", "bank": "RBC", "year": 2026, "quarter": "Q1"}],
    },
    {
        "q": "What medium-term financial targets has RBC set and what is the current trajectory?",
        "terms": ["medium-term", "financial", "targets", "trajectory", "eps", "roe", "efficiency"],
        "why_hard": "Medium-term targets slides combine multiple metrics (EPS CAGR, ROE, payout ratio) across a 3–5 year horizon; requires synthesizing guidance across multiple rows.",
        "difficulty": "medium",
        "answer_pages": [],
        "answer_pages_tbd": True,
        "answer_citations": [],
        "expected_answer_summary": "TBD — requires investor_slides document ingestion.",
        "sources": [{"report_type": "investor_slides", "bank": "RBC", "year": 2026, "quarter": "Q1"}],
    },
    {
        "q": "What are RBC's stated strategic priorities for fiscal 2026?",
        "terms": ["strategic", "priorities", "fiscal", "2026", "growth", "client"],
        "why_hard": "Strategic priorities are almost entirely qualitative; retrieval must match dense semantic content from executive overview slides against the question.",
        "difficulty": "easy",
        "answer_pages": [],
        "answer_pages_tbd": True,
        "answer_citations": [],
        "expected_answer_summary": "TBD — requires investor_slides document ingestion.",
        "sources": [{"report_type": "investor_slides", "bank": "RBC", "year": 2026, "quarter": "Q1"}],
    },
    {
        "q": "What were the key themes or concerns raised by analysts during the Q1 2026 investor presentation?",
        "terms": ["analyst", "questions", "concerns", "themes", "q&a", "outlook"],
        "why_hard": "Analyst Q&A themes may appear in a summary slide or CEO/CFO talking points; requires locating qualitative commentary, not financial tables.",
        "difficulty": "hard",
        "answer_pages": [],
        "answer_pages_tbd": True,
        "answer_citations": [],
        "expected_answer_summary": "TBD — requires investor_slides document ingestion.",
        "sources": [{"report_type": "investor_slides", "bank": "RBC", "year": 2026, "quarter": "Q1"}],
    },
    {
        "q": "What is the fee income growth trajectory across RBC's business segments?",
        "terms": ["fee", "income", "non-interest", "growth", "wealth", "capital", "markets"],
        "why_hard": "Fee income is disclosed differently across segments (management fees, advisory fees, service charges) and investor slides may aggregate across these.",
        "difficulty": "medium",
        "answer_pages": [],
        "answer_pages_tbd": True,
        "answer_citations": [],
        "expected_answer_summary": "TBD — requires investor_slides document ingestion.",
        "sources": [{"report_type": "investor_slides", "bank": "RBC", "year": 2026, "quarter": "Q1"}],
    },
    {
        "q": "How sensitive is RBC's revenue to changes in foreign exchange rates, particularly USD/CAD?",
        "terms": ["fx", "foreign", "exchange", "sensitivity", "usd", "cad", "revenue", "impact"],
        "why_hard": "FX sensitivity may be expressed as a per-cent or per-dollar-move impact; must find the specific hedging disclosure or sensitivity analysis slide.",
        "difficulty": "hard",
        "answer_pages": [],
        "answer_pages_tbd": True,
        "answer_citations": [],
        "expected_answer_summary": "TBD — requires investor_slides document ingestion.",
        "sources": [{"report_type": "investor_slides", "bank": "RBC", "year": 2026, "quarter": "Q1"}],
    },
    {
        "q": "What is the balance sheet composition outlook for RBC in terms of loan mix and funding profile?",
        "terms": ["balance", "sheet", "composition", "loan", "mix", "funding", "deposits", "outlook"],
        "why_hard": "Balance sheet outlook slides combine asset-side loan mix targets with funding-side deposit strategy; requires multi-part synthesis across potentially separate slides.",
        "difficulty": "hard",
        "answer_pages": [],
        "answer_pages_tbd": True,
        "answer_citations": [],
        "expected_answer_summary": "TBD — requires investor_slides document ingestion.",
        "sources": [{"report_type": "investor_slides", "bank": "RBC", "year": 2026, "quarter": "Q1"}],
    },
    {
        "q": "How does RBC's performance compare to Canadian bank peers on key metrics like ROE and efficiency ratio?",
        "terms": ["peer", "benchmarking", "comparison", "roe", "efficiency", "canadian", "banks"],
        "why_hard": "Peer benchmarking slides require locating the comparative table and correctly attributing figures to each peer bank, while distinguishing adjusted vs. reported metrics.",
        "difficulty": "medium",
        "answer_pages": [],
        "answer_pages_tbd": True,
        "answer_citations": [],
        "expected_answer_summary": "TBD — requires investor_slides document ingestion.",
        "sources": [{"report_type": "investor_slides", "bank": "RBC", "year": 2026, "quarter": "Q1"}],
    },
]


# ── Combined ────────────────────────────────────────────────────────────

ALL_QUERIES: list[dict[str, Any]] = (
    SUPP_FINANCIALS_QUERIES + PILLAR3_QUERIES + INVESTOR_SLIDES_QUERIES
)
