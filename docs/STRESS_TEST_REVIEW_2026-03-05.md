# Stress Test Review 2026-03-05

## Findings

1. Retrieval recall is strong.
   - The latest run hit all 20 curated answer pages with 100% hit rate and average hit rank 1.65.
   - The main failure mode is not missing pages; it is how the answering/judging stages use the retrieved set.

2. The answer stage was over-consuming nearby/supporting pages.
   - Several low scores came from citing extra pages that legitimately corroborated the answer but were not in the curated answer-page list.
   - A smaller set of cases were genuine synthesis mistakes: preferring narrower slices over direct aggregate pages, or making unsupported interpretive jumps.
   - Any fix here must live in the real retrieval/answering pipeline, not only in the stress-test harness, otherwise the benchmark stops being faithful.

3. The judge was too strict for supportive citations outside the canonical page list.
   - The previous judge prompt only saw curated answer pages, so it could mark valid supporting citations as hallucinated.
   - This especially affected questions where a highlights page or neighboring calculation page repeated the same metric.

4. A few curated Q&A pairs were ambiguous or over-scoped.
   - Query 10 used "last quarter" while the canonical answer expected the report quarter.
   - Queries 3, 11, and 15 required secondary details that were not clearly demanded by the wording.

5. Judge output could be internally inconsistent.
   - At least one report row had `overall_score = 3` with `citation_accuracy = false`, which should not survive into the final report.

## Implemented Tasks

- [x] Strengthen answer prompt rules around direct aggregate pages, minimal citations, and shareholder-return interpretation.
- [x] Expand judge evidence with model-cited supporting pages so valid corroboration is not auto-penalized.
- [x] Normalize inconsistent judge outputs into a stable score policy before reporting.
- [x] Fix ambiguous or over-scoped curated Q&A entries for queries 3, 10, 11, and 15.
- [x] Add unit coverage for full-context pass-through, cited-source passing, and judgment normalization.

## Correction

- The temporary harness-only change that reduced answer context to 1-2 pages was reverted.
- The stress test now remains faithful to the full reranked context passed through retrieval; any future context-thresholding should be implemented in the real retrieval pipeline first and then mirrored here.

## Remaining Follow-up

- Re-run the full stress test against the live model to measure the new baseline.
- Review whether any remaining low-score cases should widen canonical answer pages versus requiring stricter answer generation.
