---
document_type: known_issue
issue_id: KI-RAG-0015
status: open
scope: rag.ingestion.ui-consistency
severity: medium
first_confirmed: 2026-07-19
last_verified_commit: 5e49a4669f78dbaddf00ee97f1f76c7960bba419
last_verified_date: 2026-07-19
source_findings: []
---

# Document list can lag a completed multi-document upload

## Observed Behavior

After two documents completed uploading through the knowledge-base UI, the
"已上传文档" list showed only the first document. Using the page's refresh
action made both documents appear. The second document was therefore stored;
the observed failure was the post-upload list state, not ingestion loss.

The frontend uploads selected files sequentially and calls `loadDocuments()`
only once after the whole loop. `GET /documents` then derives the list directly
from a Milvus query. `MilvusWriter` returns after inserts and increments the
index-version cache, but it does not flush, pass a write visibility token, or
otherwise establish a read-your-writes boundary for that list query.
`MilvusManager` also creates a fresh client for each insert and query operation.

This execution path permits the final list read to observe the first completed
write but not the most recent one. It is the leading explanation for the exact
symptom, but the response body of the original stale `GET /documents` request
was not captured, so a Milvus visibility delay is not claimed as conclusively
measured in that run.

## Impact

The UI can report an incomplete knowledge-base inventory immediately after a
successful batch. Users may retry an already successful upload or incorrectly
assume that the missing document was not indexed. A later refresh restores the
correct list, so this issue does not currently demonstrate durable data loss.

This is distinct from [KI-RAG-0008](document-upload-processing-observability.md):
KI-RAG-0008 concerns progress while ingestion is running, while this issue
concerns list consistency after the upload requests have completed.

## Evidence or Reproduction

1. Open the administrator knowledge-base page.
2. Select two supported documents and upload them in one batch.
3. Wait for both upload requests to report completion.
4. Observe that the list may contain only the first document.
5. Press "刷新" and observe that both documents appear.

The 2026-07-19 retained browser state showed both `SCM优化方案.pdf` and
`国电电力.pdf` after refresh. Code inspection showed the single post-loop list
read in `frontend/script.js::uploadDocument()`, the Milvus-backed aggregation in
`backend/services/document_service.py::list_documents()`, and separate
client-per-operation writes and reads in `backend/infra/vector_store/`.

## Workaround

Use the knowledge-base page's refresh action after a multi-document upload
before deciding that a document is missing. Confirm retrieval or storage state
before re-uploading the same filename.

## Resolution Criteria

- A completed two-or-more-document upload deterministically renders every
  successful upload without a manual refresh.
- The document-list path has an explicit read-after-write contract rather than
  depending on an unspecified immediate Milvus read.
- A regression exercises delayed visibility or the selected consistency
  mechanism and proves that a stale response cannot overwrite the completed
  batch state.
- Upload progress and post-upload list consistency remain separately testable.
