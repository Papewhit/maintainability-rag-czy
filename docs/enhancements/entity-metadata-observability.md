---
document_type: enhancement
enhancement_id: ENH-RAG-0002
status: candidate
scope: rag.observability
motivation: Quantify invalid or missing entity metadata without noisy logs.
last_verified_commit: 8babe339cda636936c6c0af3c95a99e7c77c2f19
last_verified_time: 2026-07-12T00:00:00+08:00
source_findings: []
related_issues:
  - KI-RAG-0002
follow_up: null
---

# Entity Metadata Data-Quality Observability

## Opportunity

Add low-noise counters or sampled logs for missing fields, invalid JSON, scalar JSON, and non-array payloads.

## Expected Value

Provide evidence for when historical normalization should become a scheduled migration.

## Non-Goals

No alert thresholds, telemetry backend, or migration schedule is selected here.

## Dependencies

Metadata codec and the repository's future telemetry conventions.

## Planning Status

Candidate only; create an OpenSpec change or issue before implementation.

