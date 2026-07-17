---
document_type: finding_ledger
change: rag-multilevel-fallback
last_verified_commit: 70decc4f9fdc01f25e981b595b5b584bdb89693a
last_verified_date: 2026-07-17
---

# Change Findings

## RAG-MF-F001

- Kind: design_ambiguity
- Primary scope: rag.retrieval
- Evidence status: confirmed
- Observation: `retrieve_initial()` already sends `context_files` into the main filtered retrieval and then separately calls `retrieve_context_documents()` once per file, appending those directly queried leaf chunks after the main postprocess/confidence result. The change spec also proposed relaxing every filter to boost/none and described disabled fallback as Level 3, conflicting with the explicit attachment boundary and current disabled-path behavior.
- Inference: Without a single evidence lifecycle, the router evaluates a different document set from the answer generator; relaxing an explicit attachment filter can also escape the user-selected evidence domain.
- Decision: Treat `context_files` as an immutable hard retrieval domain, remove the direct attachment supplement, run all candidates through one postprocess/confidence lifecycle per retrieval round, and preserve direct Level 0 answer generation when fallback is disabled.
- Residual risk: Requests with many attachments can enlarge the filtered candidate domain and may require candidate budget tuning; comprehensive intent still incurs its planned fan-out cost, but attachments must not introduce additional branches or per-file supplement queries.
- Evidence: `backend/rag/pipeline.py::retrieve_initial`; `backend/rag/utils.py::retrieve_context_documents`; `backend/rag/query_plan.py` context-files scope construction; `tests/unit/backend/rag/query_plan/test_document_scope_matching.py`; updated change design and delta spec.
- Disposition: change
- Disposition target: openspec/changes/rag-multilevel-fallback/
- Resolution evidence: The design, delta spec, and tasks now state the immutable attachment boundary, unified per-round evidence lifecycle, and disabled-path compatibility behavior.

## RAG-MF-F002

- Kind: design_ambiguity
- Primary scope: rag.query_plan
- Evidence status: confirmed
- Observation: `parse_query_plan()` currently emits filter when filename similarity reaches `DOC_SCOPE_MATCH_FILTER` (default 0.85), and applies `preferred_scope_mode` before score-based classification. `_precise_plan_from_decision()` passes classifier `scope_hint` as that preferred mode, while the classifier prompt does not define filter/boost/none semantics. `PreciseQueryPlan` has no source field; comprehensive `RetrievalScope.source` exists for provenance.
- Inference: If Level 2 preserves every filter without first hardening filter production, an incorrect classifier hint or high lexical filename match can lock all fallback attempts inside a file the user did not hard-select, and Level 3 can falsely attribute that boundary to the user.
- Decision: Define filter as the authoritative hard-scope behavior contract; allow only deterministic hard-range signals to produce it; prevent classifier hints and filename score alone from creating it. Fallback consumes only scope_mode. Keep comprehensive source as non-authoritative trace/provenance and do not add precise scope_source.
- Residual risk: Deterministic recognition of forms such as “《A》中……” needs negative and ambiguity coverage so ordinary document mentions are not overclassified as hard scope.
- Evidence: `backend/rag/query_plan.py::parse_query_plan` score/preferred-mode ordering; `backend/rag/intent.py::_precise_plan_from_decision`; `backend/rag/intent.py::INTENT_SYSTEM_PROMPT`; `backend/rag/query_plan.py::PreciseQueryPlan`; `backend/rag/query_plan.py::RetrievalScope`; updated change design, delta spec, and prerequisite tasks.
- Disposition: change
- Disposition target: openspec/changes/rag-multilevel-fallback/
- Resolution evidence: The change now makes trustworthy filter production an explicit prerequisite and specifies mode-only Level 2 behavior and scope-correct Level 3 disclosure.
