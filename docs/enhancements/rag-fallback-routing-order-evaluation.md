---
document_type: enhancement
enhancement_id: ENH-RAG-0004
status: candidate
scope: rag.fallback.routing
motivation: Evaluate whether signal-directed Level-2-first paths should try query rewrite before Level 3 and which ordering produces better quality and latency.
last_verified_commit: 5e49a4669f78dbaddf00ee97f1f76c7960bba419
last_verified_date: 2026-07-19
source_findings:
  - RAG-MF-F006
  - RAG-MF-F026
related_issues:
  - KI-RAG-0013
---

# RAG Fallback Routing-order Evaluation

## Opportunity

Evaluate whether confidence patterns dominated by overly narrow scope perform
better when Level 2 scope relaxation precedes Level 1 query rewrite, and
whether a signal-directed path that starts at Level 2 should be allowed to try
Level 1 before terminating at Level 3.

The current router does not always follow a fixed Level 1 → Level 2 order.
`weak_margin_and_root` starts directly at Level 2; once Level 2 has been
attempted, the next router decision is Level 3 and Level 1 is not considered.
The open evaluation question therefore includes both initial ordering and
whether a failed direct-Level-2 path should backfill query rewrite.

## Expected Value

Potentially avoid spending rewrite latency on queries whose primary failure is candidate eligibility rather than query formulation, while preserving hard-filter boundaries.

It may also avoid terminating at Level 3 when scope relaxation did not address
the actual failure and a query rewrite could still recover useful evidence.

## Runtime Evidence

On 2026-07-18, the precise query `统一源图是什么？` in session
`session_1784383996604` produced strong, directly relevant final evidence but
the confidence gate returned only `weak_margin_and_root` (`top_score=0.87475`,
`top_margin=0.00538`, `dominant_root_share=0.20527`). The router selected Level
2 directly, then selected Level 3 with `levels_exhausted` after Level 2 retained
the same confidence reason. The persisted path was `[2, 3]`; Level 1 was never
attempted.

An earlier run of the same query reached Level 3 before Level 2 because initial
reranking exhausted the remaining budget. Together, the runs show that latency
state can change whether scope relaxation is attempted, while the signal rule
still prevents rewrite from being evaluated on the direct-Level-2 path.

On 2026-07-19, session `session_1784426649833` repeated the same routing shape
for a more explicit question about how unified-source-graph event nodes connect
to the change index table. Five final chunks visibly supplied the requested
relationship, but confidence returned `weak_margin_and_root` with
`top_score=0.87571`, `top_margin=0.00817`, and
`dominant_root_share=0.20393`; Level 2 kept `none -> none`, then Level 3
refused the answer. This strengthens the need to separate routing-order
evaluation from confidence false rejection and index contamination, now
tracked by KI-RAG-0013.

This evidence does not prove that Level 1 would improve this query. The same
run also exposed a confidence false positive and a candidate-cap defect, so any
ordering comparison must separate routing-order benefit from those effects.

## Non-Goals

This document does not change the `rag-multilevel-fallback` order, add adaptive routing, define compatibility behavior, or authorize implementation. It also does not redefine confidence thresholds or resolve the Level 2 candidate-cap defect.

## Dependencies

A stable multilevel fallback baseline, signal-stratified evaluation queries,
per-level quality and latency measurements, and explicit scenarios defining
when ordering may differ. Evaluation must distinguish at least:

- direct Level 2 → Level 3 versus Level 2 → Level 1 → Level 3 for
  `weak_margin_and_root`;
- genuine scope restriction from high-score, multi-root corroborating evidence;
- warm and cold reranker latency states;
- runs where Level 2 actually enlarges the candidate pool from runs affected by
  the Level 2 candidate-cap known issue.

## Planning Status

Candidate only. Any routing-order change requires a separate OpenSpec change with comparative quality, latency, and hard-scope evidence.
