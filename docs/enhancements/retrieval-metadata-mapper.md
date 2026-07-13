---
document_type: enhancement
enhancement_id: ENH-RAG-0001
status: candidate
scope: rag.retrieval
motivation: Reduce field omissions across retrieval result normalization paths.
last_verified_commit: 8babe339cda636936c6c0af3c95a99e7c77c2f19
last_verified_date: 2026-07-12
source_findings: []
related_issues: []
---

# Declarative Retrieval Metadata Mapper

## Opportunity

Centralize output-field defaults, type conversion, and passthrough rules now manually repeated across retrieval paths.

## Expected Value

Lower the chance that a newly requested metadata field is omitted from one result format.

## Non-Goals

This document does not schedule implementation or change the current wire schema.

## Dependencies

Current `_RETRIEVAL_OUTPUT_FIELDS`, Milvus formatting, trace, and codec contracts.

## Planning Status

Candidate only; create an OpenSpec change or issue before implementation.
