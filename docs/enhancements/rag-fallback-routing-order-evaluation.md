---
document_type: enhancement
enhancement_id: ENH-RAG-0004
status: candidate
scope: rag.fallback.routing
motivation: Evaluate whether signal-specific scope relaxation before query rewrite improves answer quality enough to justify changing the fixed fallback order.
last_verified_commit: cbcd3de07c3b0544701d778e6315b0216a857027
last_verified_date: 2026-07-17
source_findings:
  - RAG-MF-F006
related_issues: []
---

# RAG Fallback Routing-order Evaluation

## Opportunity

Evaluate whether confidence patterns dominated by overly narrow scope perform better when Level 2 scope relaxation precedes Level 1 query rewrite, instead of always following the current Level 1 → Level 2 order.

## Expected Value

Potentially avoid spending rewrite latency on queries whose primary failure is candidate eligibility rather than query formulation, while preserving hard-filter boundaries.

## Non-Goals

This document does not change the `rag-multilevel-fallback` order, add adaptive routing, define compatibility behavior, or authorize implementation.

## Dependencies

A stable multilevel fallback baseline, signal-stratified evaluation queries, per-level quality and latency measurements, and explicit scenarios defining when ordering may differ.

## Planning Status

Candidate only. Any routing-order change requires a separate OpenSpec change with comparative quality, latency, and hard-scope evidence.
