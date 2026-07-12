---
document_type: finding_ledger
change: documentation-evidence-governance
last_verified_commit: 8babe339cda636936c6c0af3c95a99e7c77c2f19
last_verified_time: 2026-07-12T00:00:00+08:00
---

# Change Findings

## DOC-EVG-F001

- Kind: documentation_drift
- Primary scope: documentation.architecture
- Evidence status: confirmed
- Unresolved: false
- Observation: `docs/ARCHITECTURE.md` names removed `backend/rag/layered_rerank.py` and `backend/rag/rules.py` modules and omits active ingestion, terminology, storage, and shared postprocess components.
- Inference: The current-system overview cannot be relied on for implementation or review orientation.
- Evidence: `docs/ARCHITECTURE.md`; verified repository paths at commit `8babe339cda636936c6c0af3c95a99e7c77c2f19`.
- Disposition: architecture
- Disposition target: `docs/ARCHITECTURE.md`

## DOC-EVG-F002

- Kind: documentation_drift
- Primary scope: rag.ingestion
- Evidence status: confirmed
- Unresolved: false
- Observation: `backend/documents/parse_adapter/converters.py` still describes minimal splitting and a future Maintainability Chunker even though `parsed_to_chunks()` invokes `run_normalizer()` and `chunk_normalized()`.
- Inference: Maintainer-facing code documentation contradicts the active implementation.
- Evidence: `backend/documents/parse_adapter/converters.py` module docstring and `parsed_to_chunks()`.
- Disposition: closed_in_place
- Disposition target: null
- Resolution evidence: `backend/documents/parse_adapter/converters.py` module documentation corrected by this change.

## DOC-EVG-F003

- Kind: documentation_drift
- Primary scope: documentation.preprocess
- Evidence status: confirmed
- Unresolved: false
- Observation: `docs/document-preprocessing-insights.md` is an automatically generated historical document with stale current-state claims, including obsolete OCR guidance.
- Decision: Mark the entire document historical and point to the current architecture; do not refresh its body or persist its unimplemented suggestions.
- Evidence: user governance decision in this change; active DeepDoc OCR implementation under `backend/documents/parse_adapter/deepdoc/_ocr.py`.
- Disposition: closed_in_place
- Disposition target: null
- Resolution evidence: `docs/document-preprocessing-insights.md` historical status marker.

## DOC-EVG-F004

- Kind: delivery_risk
- Primary scope: delivery.documentation
- Evidence status: confirmed
- Unresolved: false
- Observation: `.gitignore` ignores `docs/*` and `scripts/`, so new authority documents and the validator can be omitted from a PR without appearing in ordinary Git status.
- Evidence: `.gitignore`; `git check-ignore` results for proposed files.
- Disposition: closed_in_place
- Disposition target: null
- Residual risk: none
- Resolution evidence: `.gitignore` explicitly tracks `scripts/validate_documentation.py`, explicitly ignores the generated catalog, and the staged PR manifest includes approved authority documents; strict manifest validation passes against `documentation-ignore-baseline.txt`.

## DOC-EVG-F005

- Kind: behavior_defect
- Primary scope: rag.terminology
- Evidence status: confirmed
- Unresolved: true
- Observation: Terminology rescan queries ParentChunkStore with Milvus leaf IDs and upserts level 3 leaf records into the parent-only store.
- Inference: Parent snapshots are normally empty, rollback is unreliable, and the parent store can be polluted.
- Evidence: Independent architecture review; `backend/rag/terminology/rescan.py:294-363`.
- Disposition: known_issue
- Disposition target: docs/known-issues/terminology-rescan-parent-contract.md
- Residual risk: Rescan remains unsafe for parent metadata until implementation is corrected.

## DOC-EVG-F006

- Kind: system_limitation
- Primary scope: rag.embedding
- Evidence status: confirmed
- Unresolved: true
- Observation: `RAG_INDEX_PROFILE` does not participate in the default BM25 state path.
- Evidence: `backend/infra/embedding.py:14-20,102-106`.
- Disposition: known_issue
- Disposition target: docs/known-issues/bm25-profile-isolation.md
- Residual risk: Profiles can share sparse corpus statistics unless operators set distinct paths.

## DOC-EVG-F007

- Kind: system_limitation
- Primary scope: rag.ingestion
- Evidence status: confirmed
- Unresolved: true
- Observation: `.doc` is registered to DeepDoc but all non-PDF inputs are routed through the DOCX parser with no legacy-DOC conversion.
- Evidence: `backend/documents/parse_adapter/registry.py`; `backend/documents/parse_adapter/deepdoc/adapter.py`; `_docx_parser.py`.
- Disposition: known_issue
- Disposition target: docs/known-issues/legacy-doc-ingestion.md
- Residual risk: Legacy DOC uploads can fail despite extension registration.
