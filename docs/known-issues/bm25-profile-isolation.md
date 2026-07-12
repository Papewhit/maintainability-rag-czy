---
document_type: known_issue
issue_id: KI-RAG-0004
status: open
scope: rag.embedding
severity: medium
first_confirmed: 2026-07-12
last_verified_commit: 8babe339cda636936c6c0af3c95a99e7c77c2f19
last_verified_time: 2026-07-12T00:00:00+08:00
source_findings:
  - DOC-EVG-F006
follow_up: null
---

# Index Profiles Do Not Automatically Isolate BM25 State

## Observed Behavior

The default BM25 state path does not include `RAG_INDEX_PROFILE`.

## Impact

Multiple profiles can share corpus statistics and distort sparse scores.

## Evidence or Reproduction

`backend/infra/embedding.py:14-20,102-106`.

## Workaround

Configure a distinct `BM25_STATE_PATH` for every index profile.

## Resolution Criteria

Derive profile-aware default paths or enforce explicit configuration with tests and migration guidance.

