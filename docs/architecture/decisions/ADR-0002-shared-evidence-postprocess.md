---
document_type: adr
adr_id: ADR-0002
status: accepted
scope: rag.postprocess
decision_date: 2026-07-12
last_verified_commit: 8babe339cda636936c6c0af3c95a99e7c77c2f19
last_verified_time: 2026-07-12T00:00:00+08:00
source_findings: []
supersedes: []
superseded_by: null
---

# ADR-0002: Use One Ordered, Failure-Isolated Evidence Postprocess

## Context

Standard and layered candidate strategies require identical evidence semantics. Earlier descriptions disagreed about confidence versus final truncation and did not define whether a failed stage should stop later safe processing.

## Decision

All strategies use `rerank -> auto_merge -> step_chain_check -> structure_rerank -> top_k_truncate -> confidence_gate`. Confidence evaluates the exact final evidence delivered to answer generation. Each recoverable stage catches its error, records timing/error/fallback trace, and passes the last safe output to later stages. Entity-aware fusion is optional and preserves generic metadata behavior when entity signals are absent.

## Alternatives

- Confidence before final truncation: rejected because it evaluates evidence the answer may never receive.
- Stop after any stage failure: rejected because independent later stages can still improve safe evidence.
- Separate standard/layered postprocess: rejected because it creates semantic and trace drift.

## Consequences

Trace schemas must expose stable stage status and candidate counts. Default-disabled gates remain visible in the pipeline and report disabled/skipped behavior.

## Evidence

- `backend/rag/utils.py::finish_retrieval_pipeline`
- `backend/rag/candidate_strategy.py`
- `backend/rag/types.py`
- `backend/contracts/schemas.py`
- `docs/rag-postprocess-evidence/evaluation.md`

