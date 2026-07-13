---
document_type: adr
adr_id: ADR-0001
status: accepted
scope: rag.storage
decision_date: 2026-07-12
last_verified_commit: 8babe339cda636936c6c0af3c95a99e7c77c2f19
last_verified_date: 2026-07-12
source_findings: []
supersedes: []
superseded_by: null
---

# ADR-0001: Separate Parent Evidence from Retrieval Leaves

## Context

Maintainability chunking produces complete context parents and smaller retrieval leaves. Step-chain repair must locate adjacent parents from metadata without pretending complete parent bodies live in Milvus.

## Decision

Store level 1/2 parents in ParentChunkStore (PostgreSQL with Redis read cache) and level 3 leaves in Milvus. Locate adjacent context in two hops: filter leaf metadata by filename, index profile, list group, and parent subgroup order; then hydrate deduplicated parent IDs from ParentChunkStore. Parent subgroup order is 1-based; leaf item order remains its original item ordering.

## Alternatives

- Store full parents in Milvus: rejected because retrieval and complete evidence have different payload/storage contracts.
- Query by list group alone: rejected because group IDs can repeat across files and profiles.
- Treat leaf order as parent subgroup order: rejected because the fields describe different hierarchy levels.

## Consequences

Parent store availability affects context expansion but not initial leaf retrieval. Leaf metadata must preserve stable parent/root/list identifiers. Failures degrade to the preceding candidate set and enter trace.

## Evidence

- `backend/services/document_service.py`
- `backend/infra/vector_store/parent_chunk_store.py`
- `backend/infra/vector_store/milvus_writer.py`
- `backend/rag/utils.py::_fetch_adjacent_chunks`
- archived `rag-maintainability-chunker` and `rag-postprocess-evidence` designs
