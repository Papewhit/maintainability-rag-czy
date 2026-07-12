---
document_type: known_issue
issue_id: KI-RAG-0001
status: open
scope: rag.storage
severity: medium
first_confirmed: 2026-07-11
last_verified_commit: 8babe339cda636936c6c0af3c95a99e7c77c2f19
last_verified_time: 2026-07-12T00:00:00+08:00
source_findings: []
follow_up: null
---

# Entity Metadata Has No Explicit Milvus Schema

## Observed Behavior

`entity_types` and `term_match_count` are stored through Milvus dynamic fields rather than an explicitly versioned schema contract.

## Impact

Future schema changes require collection migration planning and cannot rely on Milvus schema enforcement for type consistency.

## Evidence or Reproduction

See `backend/infra/vector_store/milvus_client.py`, `milvus_writer.py`, and `metadata_codec.py`.

## Workaround

Runtime decoding accepts compatible historical shapes and degrades malformed values safely.

## Resolution Criteria

Define a versioned collection schema, migration/alias switch, rollback, and real Milvus integration validation in a separately scheduled change.

