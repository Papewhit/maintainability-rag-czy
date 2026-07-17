---
document_type: enhancement
enhancement_id: ENH-RAG-0005
status: candidate
scope: rag.fallback.configuration
motivation: Evaluate whether fallback deprecation warnings need process-once emission after operational evidence shows duplicate logs are materially noisy.
last_verified_commit: cbcd3de07c3b0544701d778e6315b0216a857027
last_verified_date: 2026-07-17
source_findings:
  - RAG-MF-F019
related_issues: []
---

# RAG Fallback Deprecation-warning Deduplication

## Opportunity

Measure whether repeated `RAG_FALLBACK_ENABLED` configuration loads produce materially noisy duplicate deprecation warnings, then define whether warning emission belongs at process startup or needs a process-once guard.

## Expected Value

Keep deprecation guidance visible without adding avoidable per-request log volume.

## Non-Goals

This document does not add guard state, change runtime configuration loading, suppress the required warning, or authorize compatibility behavior.

## Dependencies

Operational log evidence showing duplicate frequency and an explicit once-only warning requirement.

## Planning Status

Candidate only. Any implementation requires a separate OpenSpec change or issue with an observable warning-emission scenario and regression test.
