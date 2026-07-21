---
document_type: known_issue
issue_id: KI-RAG-0020
status: open
scope: rag.ingestion.inventory
severity: high
first_confirmed: 2026-07-20
last_verified_commit: 911892fe2fed917305fd89ebf44d059294837c85
last_verified_date: 2026-07-20
source_findings: []
---

# Document inventory is not a durable upload authority

## Observed Behavior

`GET /documents` does not list uploaded document records. It queries Milvus for
at most 10,000 leaf rows under the process's current `index_profile`, then
groups the returned rows by filename. Files under another profile, files that
exist on disk without visible leaves, and filenames outside the first query
page are absent from the administrator's “已上传文档” view.

The ingestion success boundary is also weaker than the UI response implies.
`MilvusWriter._prepare_batch()` falls back from a failed batch embedding to
per-leaf embedding and silently skips every leaf that still fails. If all
leaves fail, `write_documents()` performs no insert and increments no index
version, but returns normally. `DocumentService.upload_document()` does not
inspect an inserted or skipped count and therefore returns an upload-success
response after the file and parent records have already been written.

This issue is distinct from [KI-RAG-0015](document-list-can-lag-completed-multi-upload.md),
which covers a temporary visibility window after a successful insert. Refresh
can resolve that window; it cannot reveal another profile or a zero-leaf
upload.

## Impact

The administrator UI can under-report the corpus for several independent
reasons while presenting one undifferentiated empty or incomplete list. A user
cannot tell whether a document is in another profile, waiting for Milvus
visibility, beyond the query cap, or never indexed despite an apparent upload
success. Re-uploading can overwrite local and parent state without resolving
the underlying profile or embedding failure.

## Evidence or Reproduction

On 2026-07-20, a read-only check against the configured
`embeddings_collection_v3_quality` found:

- current profile `v3_quality`: 157 leaves belonging to 1 document;
- profile `v4_full` in the same collection: 205 leaves belonging to 2
  documents;
- `DocumentService.list_documents()`: 1 document, matching only the current
  profile;
- the upload directory: 7 files, demonstrating that filesystem presence is
  not the list authority.

The 10,000-row cap is explicit in
`DocumentService.list_documents()` even though `MilvusManager.query_all()`
already provides pagination.

An isolated writer reproduction supplied one leaf and an embedding service
that failed both batch and individual calls. `write_documents()` returned
normally with zero Milvus inserts and zero index-version increments.

## Workaround

- Treat `GET /documents` as the current-profile indexed-leaf view, not an
  all-upload inventory.
- Keep collection, `RAG_INDEX_PROFILE`, and BM25 state aligned when uploading
  or reindexing documents.
- Verify retrieval or profile-specific Milvus rows after upload before relying
  on the success message.
- Use manual refresh only for the temporary consistency case in KI-RAG-0015.

## Resolution Criteria

- A durable document registry owns filename, upload state, effective profile,
  indexing state, timestamps, and terminal failure details independently of
  Milvus leaf visibility.
- The upload response reports success only after the required leaf writes are
  confirmed; partial and zero-leaf writes are explicit failures or governed
  partial states.
- The API and UI explicitly distinguish all uploaded documents from the
  current-profile indexed view.
- Milvus-derived aggregation paginates all matching rows or uses a distinct
  filename query without silently truncating at 10,000 leaves.
- Regression coverage exercises delayed visibility, mixed profiles, more than
  10,000 leaves, and complete embedding failure as separate cases.
