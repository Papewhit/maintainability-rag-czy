---
document_type: known_issue
issue_id: KI-RAG-0006
status: open
scope: rag.anchor-routing
severity: high
first_confirmed: 2026-07-15
last_verified_commit: c915b535c6270dd7824e2ff2cfad1716ec628d59
last_verified_date: 2026-07-15
source_findings:
  - RAG-INTENT-F034
  - RAG-INTENT-F035
---

# Anchor Routing Lacks an Atomic Capability Configuration

## Observed Behavior

Successfully parsed anchors are removed from the semantic query and retained as structured QueryPlan data. Their downstream use is split across independent runtime switches: heading lexical scoring reranks existing candidates, the confidence gate checks anchor agreement, and fallback may compensate after an anchor mismatch. No startup validation or atomic capability profile guarantees that these consumers are enabled together.

The anchor contract is also inconsistent across stages. Query preparation recognizes chapter/appendix anchors plus model-supplied exact spans, while confidence extraction and chunk heading normalization recognize a broader, different grammar. The stages do not share a canonical anchor representation or normalization function.

Current fallback compounds the mismatch: precise confidence re-extracts anchors from raw query, rewritten text can put a consumed anchor back into semantic retrieval text, and the planned Level 2 scope relaxation has no explicit invariant preserving an anchor consumer after scope is widened. Comprehensive confidence can emit fallback reasons, but the comprehensive graph currently ends after shared postprocess and does not enter the precise grade/rewrite fallback path.

## Impact

Individually valid switch settings can produce a partially active anchor workflow. Results and traces can therefore vary because an anchor was consumed by query preparation but only some later consumers were active. Extraction differences can also cause QueryPlan, confidence, and chunk metadata to disagree about whether two anchors match. Fallback behavior is not yet a reliable general remedy, especially for comprehensive queries.

## Evidence or Reproduction

- `backend/rag/runtime_config.py:148-153,190,200` defines the independent confidence, anchor gate, QueryPlan, heading lexical, and fallback switches.
- `backend/rag/query_plan.py:39,478-501,594` extracts a limited anchor set plus model-supplied spans and removes consumed spans.
- `backend/rag/utils.py:126,918-935`, `backend/rag/confidence.py:7-13,76-81`, and `backend/documents/normalizer/heading_normalizer.py:22,70` use separate extraction/matching/normalization contracts.
- `backend/rag/pipeline.py:904-969,985-993` rewrites from the raw question and replaces semantic query text for precise fallback.
- `backend/rag/pipeline.py:1437-1451` connects fallback only to the precise path; comprehensive shared postprocess terminates at `END`.
- `openspec/changes/rag-multilevel-fallback/` plans Level 1 rewrite and Level 2 scope relaxation but is not implemented.

## Workaround

Use `.env.rag-intent-routing-workflow.example` only for controlled workflow validation. It group-enables intent routing, QueryPlan, heading lexical scoring, confidence plus its anchor gate, and existing fallback. This file is not a production recommendation: real-model/release-index A/B evaluation and explicit fallback behavior validation remain required.

Do not retain a successfully parsed anchor in semantic query merely to compensate for a disabled consumer. The original structural ownership rule remains authoritative: once parsed, the anchor is removed from semantic retrieval text and carried as structured data.

## Resolution Criteria

- Introduce one validated capability configuration (or equivalent startup constraints) that prevents unsupported partial anchor workflows.
- Define and test one shared anchor type grammar and canonical normalization contract for query preparation, confidence matching, and chunk metadata.
- Ensure fallback consumes structured anchors without re-extracting divergent values, prevents accidental anchor reinsertion during rewrite, and preserves an explicit anchor consumer across scope relaxation.
- Connect and validate comprehensive fallback, then complete paired A/B and fallback behavior evaluation before describing any grouped configuration as production-ready.
