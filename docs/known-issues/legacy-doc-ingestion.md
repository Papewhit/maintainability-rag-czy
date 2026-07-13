---
document_type: known_issue
issue_id: KI-RAG-0005
status: open
scope: rag.ingestion
severity: medium
first_confirmed: 2026-07-12
last_verified_commit: 8babe339cda636936c6c0af3c95a99e7c77c2f19
last_verified_date: 2026-07-12
source_findings:
  - DOC-EVG-F007
---

# Legacy DOC Extension Is Registered Without a DOC Parser

## Observed Behavior

The registry accepts `.doc`, but DeepDoc routes it to the DOCX parser without conversion.

## Impact

Legacy binary DOC uploads can fail although the extension appears supported.

## Evidence or Reproduction

`registry.py`, `deepdoc/adapter.py`, and `deepdoc/_docx_parser.py`.

## Workaround

Convert legacy DOC files to DOCX before upload.

## Resolution Criteria

Add a tested DOC conversion/parser path or remove `.doc` registration and reject it explicitly.
