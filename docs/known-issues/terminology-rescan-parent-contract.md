---
document_type: known_issue
issue_id: KI-RAG-0003
status: open
scope: rag.terminology
severity: high
first_confirmed: 2026-07-12
last_verified_commit: 8babe339cda636936c6c0af3c95a99e7c77c2f19
last_verified_time: 2026-07-12T00:00:00+08:00
source_findings:
  - DOC-EVG-F005
follow_up: null
---

# Terminology Rescan Violates the Parent Store Contract

## Observed Behavior

Rescan collects Milvus leaf IDs, uses them to snapshot ParentChunkStore, then upserts level 3 leaf-shaped records into that parent-only store.

## Impact

Parent snapshots are normally empty, parent rollback is unreliable, and rescan can pollute parent storage.

## Evidence or Reproduction

`backend/rag/terminology/rescan.py:294-363` and the level 1/2 contract in `DocumentService`.

## Workaround

Avoid terminology rescan where parent metadata consistency is required; rebuild through normal ingestion.

## Resolution Criteria

Resolve leaf-to-parent IDs before snapshot/update, update actual parents only, and add rollback/integration tests.

