---
document_type: known_issue
issue_id: KI-RAG-0002
status: open
scope: rag.storage
severity: medium
first_confirmed: 2026-07-11
last_verified_commit: 8babe339cda636936c6c0af3c95a99e7c77c2f19
last_verified_date: 2026-07-12
source_findings: []
---

# Historical Entity Metadata Is Not Normalized

## Observed Behavior

Existing Milvus records can contain empty values, arrays, JSON strings, or malformed entity metadata.

## Impact

Runtime behavior is compatible but persisted data quality and coverage cannot be assumed uniform.

## Evidence or Reproduction

`decode_entity_types()` explicitly accepts legacy arrays and JSON strings and rejects malformed/scalar/nested inputs.

## Workaround

The decoder returns a canonical deduplicated `list[str]` or `[]`.

## Resolution Criteria

Inventory shapes, perform controlled rebuild/backfill, and validate chunk count, term-count distribution, and entity coverage under a scheduled migration.
