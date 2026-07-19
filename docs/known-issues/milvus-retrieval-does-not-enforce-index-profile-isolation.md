---
document_type: known_issue
issue_id: KI-RAG-0011
status: open
scope: rag.storage.profile-isolation
severity: high
first_confirmed: 2026-07-18
last_verified_commit: 5e49a4669f78dbaddf00ee97f1f76c7960bba419
last_verified_date: 2026-07-19
source_findings: []
---

# Milvus Retrieval Does Not Enforce Index-profile Isolation

## Observed Behavior

The active collection is named `embeddings_collection_v3_quality`, but it also
contains 21 table leaves whose stored `index_profile` is `v4_full` and whose
filenames are E2E fixtures. The ordinary retrieval filter begins with
`chunk_level == 3` and does not constrain `index_profile`, so these mixed-profile
rows remain reachable.

During a real UI query, a `v4_full` E2E table leaf was selected into the final
top five beside the newly uploaded `v3_quality` document. The public trace
reported the configured profile as `v3_quality`, while the selected entity's
stored profile was `v4_full`.

## Impact

Test data or records produced under a different indexing contract can affect
production-like retrieval scores, source filenames, confidence, and answer
evidence. A trace-level configured profile is not sufficient proof that every
candidate obeyed that profile. Parent hydration may also consult a different
profile namespace from the selected leaf, so mixed-profile evidence can have
inconsistent leaf and parent availability.

## Evidence or Reproduction

- `.env` configures `MILVUS_COLLECTION=embeddings_collection_v3_quality` and
  `RAG_INDEX_PROFILE=v3_quality`.
- A direct Milvus query found 21
  `e2e_20260625235358_SCM优化方案.pdf_table_*` leaves in that collection, all
  carrying `index_profile=v4_full`.
- The same query found zero current-file table leaves and 157 current-file
  `v3_quality` records.
- `backend/rag/utils.py::build_retrieval_filters()` constructs its base filter
  from `chunk_level` without an index-profile predicate.
- Session `session_1784388109821`, assistant message `23`, selected
  `e2e_20260625235358_SCM优化方案.pdf_table_1_leaf_0` as final rank 5 while its
  trace-level `index_profile` remained `v3_quality`.
- PostgreSQL stores the corresponding parent as
  `v4_full::e2e_20260625235358_SCM优化方案.pdf_table_1`, confirming that the
  selected leaf belongs to the other profile's authority namespace.

## Workaround

Use a clean, dedicated Milvus collection for each active profile and do not run
E2E ingestion against a persistent user-validation collection. Before relying
on results, query the collection's distinct stored profile values and fixture
filename prefixes. This reduces contamination risk but does not make the
runtime filter enforce the profile contract.

## Resolution Criteria

- A retrieval request cannot return a row from another index profile, whether
  isolation is enforced by collection ownership, mandatory row filtering, or
  an equivalently validated boundary.
- Startup or index validation detects mixed-profile collections before user
  queries consume them.
- Upload, delete, filename registry, candidate retrieval, adjacent-chunk repair,
  and parent hydration use one consistent profile identity.
- Public trace can demonstrate the effective profile of selected candidates,
  and integration coverage includes deliberately mixed-profile fixture rows.
