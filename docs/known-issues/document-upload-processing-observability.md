---
document_type: known_issue
issue_id: KI-RAG-0008
status: open
scope: rag.ingestion.observability
severity: medium
first_confirmed: 2026-07-18
last_verified_commit: 5e49a4669f78dbaddf00ee97f1f76c7960bba419
last_verified_date: 2026-07-18
source_findings: []
---

# Document Upload Processing Has No Visible Progress During a Long-Running Ingestion

## Observed Behavior

During manual setup for the `rag-multilevel-fallback` M8 user-experience
validation, a PDF uploaded through the frontend remained in document processing
for an unusually long time. The frontend showed no processing stage or progress,
and the backend emitted no corresponding step-level log during the observation.

The document was later confirmed to have been ingested correctly. What remained
unobservable was the active stage, progress, and elapsed time while processing
was underway. This issue therefore records an ingestion observability gap; it
does not claim that ingestion failed or that the parser, indexer, or request was
hung.

## Impact

Users cannot distinguish active processing from a stalled upload, and operators
cannot identify which ingestion stage is responsible for the delay. The document
was nevertheless available after ingestion, so this issue does not functionally
block M8.5 fallback UX validation and is not evidence of a retrieval or fallback
failure.

## Evidence or Reproduction

On 2026-07-18, upload the following ignored local fixture through the frontend UI:

- Path in the main repository: `tests/fixtures/documents/SCM优化方案.pdf`
- Size: 2,177,225 bytes
- SHA-256: `D52BDD62EE002C4B44C9A934D42F81D366001C8A5D45B74972645115191689EC`

Observe the frontend processing state and the backend logs while ingestion is in
progress. In the reported run, processing was unusually long, the frontend had
no progress or current-stage display, and the backend had no step-level ingestion
log. The document subsequently appeared correctly ingested. No exact duration or
stage timing was captured, so those remain evidence gaps rather than inferred
facts.

The fixture is intentionally Git-ignored; this document records its identity and
does not make the PDF part of the change delivery.

## Workaround

No workaround is required to continue M8.5 once the document appears in the
knowledge base. Preserve timestamps and the frontend/backend process output when
retrying an upload if ingestion progress itself is under validation.

## Resolution Criteria

- A long-running upload exposes a visible current state or progress indicator in
  the frontend and a terminal success or failure state.
- Backend logs expose correlated ingestion start, meaningful stage transitions,
  completion or failure, and elapsed time without requiring debug-only code
  changes.
- A repeat using the identified PDF can distinguish active work from a stalled
  request and identify the stage responsible for most elapsed time.
- The observability result is assessed separately from M8.5 fallback rendering;
  successful ingestion continues to make the document usable for that validation.
