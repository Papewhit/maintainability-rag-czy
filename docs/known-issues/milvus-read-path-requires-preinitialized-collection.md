---
document_type: known_issue
issue_id: KI-RAG-0014
status: open
scope: rag.storage_initialization
severity: medium
first_confirmed: 2026-07-19
last_verified_commit: 5e49a4669f78dbaddf00ee97f1f76c7960bba419
last_verified_date: 2026-07-19
source_findings: []
---

# Milvus read path requires a preinitialized collection

## Observed Behavior

After applying the full-chain E2E overlay and restarting with the new isolated
collection name, the first RAG execution failed with:

```text
pymilvus.exceptions.MilvusException: collection not found
[database=default][collection=embeddings_collection_v4_full_e2e]
```

Milvus itself was reachable. A read-only `has_collection` check confirmed that
the configured collection did not yet exist; explicitly calling
`MilvusManager.init_collection()` created it successfully.

## Impact

A configuration can be syntactically valid and point to an intentionally new
isolated collection, yet the RAG path is not reachable until another operation
creates the schema. Whether a first query succeeds depends on prior UI
navigation or upload order rather than only on effective configuration.

## Evidence or Reproduction

- `MilvusManager.init_collection()` owns idempotent schema creation.
- `MilvusWriter.write_documents()` calls `init_collection()` before inserts.
- `DocumentService.list_documents()`, upload, and delete paths call
  `init_collection()`.
- Registry and retrieval reads call Milvus query/search methods without first
  initializing a missing collection.
- On 2026-07-19,
  `has_collection("embeddings_collection_v4_full_e2e")` returned false before
  initialization and true after the explicit call against
  `http://127.0.0.1:19530`.

## Workaround

With the intended overlay loaded into the same process environment, run:

```powershell
uv run python -c "from backend.infra.vector_store.milvus_client import MilvusManager; MilvusManager().init_collection()"
```

Then upload or reindex documents under the same profile, collection, and BM25
state. An initialized but empty collection prevents the schema error but does
not provide searchable evidence.

## Resolution Criteria

- A clean deployment or E2E profile can perform its first registry/retrieval
  read without depending on prior knowledge-base UI navigation.
- Missing collection, empty initialized collection, and unavailable Milvus are
  represented as distinct observable states.
- Initialization cannot silently target a collection other than the effective
  configured collection.
