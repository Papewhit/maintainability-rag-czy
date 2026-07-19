---
document_type: known_issue
issue_id: KI-RAG-0006
status: open
scope: rag.anchor-routing
severity: high
first_confirmed: 2026-07-15
last_verified_commit: 43985b0591a2f80a7b55137b3a8764d4276657a3
last_verified_date: 2026-07-19
source_findings:
  - RAG-INTENT-F034
  - RAG-INTENT-F035
  - RAG-MF-F029
---

# Anchor Routing Lacks an Atomic Capability Configuration

## Observed Behavior

Successfully parsed anchors are removed from the semantic query and retained as structured QueryPlan data. Their downstream use is split across independent runtime switches: heading lexical scoring reranks existing candidates, the confidence gate checks anchor agreement, and fallback may compensate after an anchor mismatch. No startup validation or atomic capability profile guarantees that these consumers are enabled together.

The anchor contract is also inconsistent across stages. Query preparation recognizes chapter/appendix anchors plus model-supplied exact spans, while confidence extraction and chunk heading normalization recognize a broader, different grammar. The stages do not share a canonical anchor representation or normalization function.

Multilevel fallback is now implemented for precise and comprehensive plans and remains disabled by default. It preserves typed scope and structured anchors across Level 1/2 rounds, but it does not unify the anchor contract: precise confidence still re-extracts anchors from the raw query, rewrite remains model-mediated, and no atomic capability profile guarantees that every anchor consumer is enabled together. Representative real-corpus activation evidence is also still pending.

## Impact

Individually valid switch settings can produce a partially active anchor workflow. Results and traces can therefore vary because an anchor was consumed by query preparation but only some later consumers were active. Extraction differences can also cause QueryPlan, confidence, and chunk metadata to disagree about whether two anchors match. The implemented fallback wiring covers precise and comprehensive plans, but is not a general remedy for this configuration and grammar mismatch.

## Evidence or Reproduction

- `backend/rag/runtime_config.py:148-153,190,200` defines the independent confidence, anchor gate, QueryPlan, heading lexical, and fallback switches.
- `backend/rag/query_plan.py:39,478-501,594` extracts a limited anchor set plus model-supplied spans and removes consumed spans.
- `backend/rag/utils.py:126,918-935`, `backend/rag/confidence.py:7-13,76-81`, and `backend/documents/normalizer/heading_normalizer.py:22,70` use separate extraction/matching/normalization contracts.
- `backend/rag/pipeline.py` implements shared multilevel fallback nodes for precise and comprehensive plans while retaining plan-scoped query and evidence state.
- `openspec/changes/rag-multilevel-fallback/` defines and verifies the default-disabled implementation contract, including Level 1 rewrite, Level 2 scope relaxation, and comprehensive routing.
- `openspec/changes/rag-multilevel-fallback-activation/` owns representative real-corpus evaluation, release thresholds, budget tuning, canary, and default-change evidence.

## Workaround

Use `.env.rag-intent-routing-workflow.example` only for controlled workflow validation. It group-enables intent routing, QueryPlan, heading lexical scoring, confidence plus its anchor gate, and existing fallback. This file is not a production recommendation: real-model/release-index A/B evaluation and explicit fallback behavior validation remain required.

Do not retain a successfully parsed anchor in semantic query merely to compensate for a disabled consumer. The original structural ownership rule remains authoritative: once parsed, the anchor is removed from semantic retrieval text and carried as structured data.

## Resolution Criteria

- Introduce one validated capability configuration (or equivalent startup constraints) that prevents unsupported partial anchor workflows.
- Define and test one shared anchor type grammar and canonical normalization contract for query preparation, confidence matching, and chunk metadata.
- Ensure fallback consumes structured anchors without re-extracting divergent values, prevents accidental anchor reinsertion during rewrite, and preserves an explicit anchor consumer across scope relaxation.
- Validate precise and comprehensive fallback against a representative real corpus under `rag-multilevel-fallback-activation` before describing any grouped configuration as production-ready.
