---
document_type: migrated_change_evidence
status: superseded
superseded_by: docs/architecture/decisions/ADR-0001-parent-leaf-evidence-storage.md
last_verified_commit: 8babe339cda636936c6c0af3c95a99e7c77c2f19
last_verified_date: 2026-07-12
source_change: rag-postprocess-evidence
---

# RAG Postprocess Design Ambiguities: Disposition Map

This document no longer mixes resolved decisions and open debt. It preserves the original topic inventory and points to each durable disposition.

| Original topic | Disposition | Durable target |
| --- | --- | --- |
| Milvus “fetch adjacent parent” meaning | ADR | [ADR-0001](../architecture/decisions/ADR-0001-parent-leaf-evidence-storage.md) |
| Confidence gate versus top-k order | ADR | [ADR-0002](../architecture/decisions/ADR-0002-shared-evidence-postprocess.md) |
| `list_order` level/base | ADR | [ADR-0001](../architecture/decisions/ADR-0001-parent-leaf-evidence-storage.md) |
| `list_group_id` uniqueness | ADR | [ADR-0001](../architecture/decisions/ADR-0001-parent-leaf-evidence-storage.md) |
| Candidate pool versus CrossEncoder cost | Validation/closed in place | [evaluation](evaluation.md) |
| Entity metadata absent compatibility | ADR | [ADR-0002](../architecture/decisions/ADR-0002-shared-evidence-postprocess.md) |
| Real `RagTraceMeta` type | Closed in archived change | `backend/contracts/schemas.py`, `backend/rag/types.py` |
| Stage failure continuation | ADR | [ADR-0002](../architecture/decisions/ADR-0002-shared-evidence-postprocess.md) |
| Performance evidence boundary | Validation | [evaluation](evaluation.md) |
| Explicit Milvus entity schema | Known issue | [KI-RAG-0001](../known-issues/entity-metadata-schema.md) |
| Historical entity metadata normalization | Known issue | [KI-RAG-0002](../known-issues/entity-metadata-history.md) |
| Generic retrieval metadata mapper | Enhancement | [ENH-RAG-0001](../enhancements/retrieval-metadata-mapper.md) |
| Entity metadata observability | Enhancement | [ENH-RAG-0002](../enhancements/entity-metadata-observability.md) |

The detailed historical reasoning remains in `openspec/changes/rag-postprocess-evidence/design.md` and its archived/active change record. Current behavior is authoritative only in [ARCHITECTURE.md](../ARCHITECTURE.md).
