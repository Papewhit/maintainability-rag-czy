---
document_type: known_issue
issue_id: KI-RAG-0010
status: open
scope: rag.ingestion.table-evidence
severity: high
first_confirmed: 2026-07-18
last_verified_commit: 5e49a4669f78dbaddf00ee97f1f76c7960bba419
last_verified_date: 2026-07-19
source_findings: []
---

# Table Evidence Is Not Indexed Below the v4 Table-aware Profile

## Observed Behavior

DeepDoc can successfully parse a PDF containing tables while the configured
index profile silently omits every table parent and leaf from storage. The
conversion layer emits normalized tables only when the profile allows
`v4_table_aware`; lower profiles retain nearby narrative blocks such as
"本项目所需交付物列于下表" but not the table rows referenced by that text.

The frontend upload of `SCM优化方案.pdf` used `RAG_INDEX_PROFILE=v3_quality`.
Its parse metadata reports DeepDoc `native_text`, 76 pages, no parse warnings,
and successful ingestion. The active Milvus collection contains 157 records
for that filename but zero `SCM优化方案.pdf_table_*` records. ParentChunkStore
likewise contains the page-17 `2.2 交付物` narrative parent without a table
parent. The complete five-row table remains only in the uploaded PDF.

## Impact

A table-dependent query can retrieve a high-scoring paragraph that points to
"the table below" while the referenced evidence is unavailable to retrieval,
reranking, source display, and answer delivery. Successful upload and empty
parse warnings do not reveal this evidence loss. Answers may appear correct
only when the same facts are repeated elsewhere as ordinary prose.

## Evidence or Reproduction

- Source PDF page 17 contains `2.2 交付物`, a five-row deliverables table, and
  `2.3 项目周期` on the same physical page.
- `backend/documents/parse_adapter/converters.py` sets
  `enriched_tables=[]` unless `_profile_allows(profile, "v4_table_aware")`.
- The persisted page-17 current-file parents under both `legacy` and
  `v3_quality` contain only `2.2 交付物\n本项目所需交付物列于下表。`.
- Milvus collection `embeddings_collection_v3_quality` contains 157 current-file
  records and zero current-file table records.
- Session `session_1784388109821`, assistant message `23`, ranked that incomplete
  page-17 chunk second for query `配置管理系统 交付物`.
- The same run ranked a page-76 prose repetition containing all five deliverables
  first, proving that the final refusal was not evidence that the facts were
  absent from the document.

## Workaround

For validation that depends on table evidence, use an isolated index built with
a profile that already includes `v4_table_aware`, and verify the expected
`*_table_*` parent and leaf counts after ingestion. Alternatively, use a prose
section that independently contains the required facts; do not treat a pointer
paragraph as proof that its adjacent table was indexed.

## Resolution Criteria

- Supported index profiles explicitly state whether parsed tables are retained
  or discarded, and upload diagnostics expose the effective behavior.
- A successful table-bearing upload reports parsed, parent, and leaf table
  counts or an explicit table-evidence-disabled state.
- A real PDF integration test proves that a query targeting a table can retrieve
  the referenced rows under every profile that claims table support.
- Source display and answer delivery are validated from the same final table
  evidence rather than from a nearby pointer paragraph.
