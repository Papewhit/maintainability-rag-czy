---
document_type: known_issue
issue_id: KI-RAG-0013
status: open
scope: rag.confidence
severity: high
first_confirmed: 2026-07-19
last_verified_commit: 5e49a4669f78dbaddf00ee97f1f76c7960bba419
last_verified_date: 2026-07-19
source_findings: []
---

# Confidence gate can reject corroborating high-score evidence

## Observed Behavior

In session `session_1784426649833`, the precise question
`根据知识库，统一源图事件节点怎么和变更索引表结合？` retrieved five visibly
relevant final source snippets. The leading page-32 snippet directly explained
that `change_id` links graph event nodes one-to-one with the external change
index table and described why detailed text remains outside the graph.

Despite this evidence, confidence produced only `weak_margin_and_root`, Level
2 retained `scope_mode: none -> none`, and the path terminated at Level 3 as
`[2, 3]`. The final answer stated that the knowledge base contained no
specific explanation.

## Impact

A user can receive an explicit no-evidence answer while the same response UI
shows source chunks that directly answer the question. This is more harmful
than a ranking-quality miss because the delivery contradicts its own evidence
and encourages the user to distrust both the answer and source panel.

## Evidence or Reproduction

The persisted trace recorded:

- `top_score=0.8757108267`
- `top_margin=0.0081705620`
- `dominant_root_share=0.2039283543`
- `confidence_reasons=["weak_margin_and_root"]`
- `fallback_path=[2, 3]`
- `fallback_total_ms=3224.826`
- no stage errors

The rendered source scores ranged from approximately 0.8496 to 0.8772 and
covered the same design concept across pages 18, 31, and 32. A small top-score
margin and low dominant-root share can therefore occur when several distinct
chunks corroborate one answer, not only when candidates are ambiguous.

This run is not a clean threshold experiment. The active backend still used
`RAG_INDEX_PROFILE=v3_quality` and
`MILVUS_COLLECTION=embeddings_collection_v3_quality`, and the source panel
included both `SCM优化方案.pdf` and an older
`e2e_20260625235358_SCM优化方案.pdf`. Shared-collection duplication may have
changed margin and root-share values. An isolated `v4_full` rerun is required
before assigning the defect solely to the confidence formula or changing any
threshold.

## Workaround

For validation, inspect the final source chunks whenever Level 3 is reached;
do not treat the Level 3 label alone as proof that evidence is absent. Restart
with `.env.rag-full-chain-e2e.example`, reindex into its isolated collection,
and preserve the complete trace and answer for comparison.

## Resolution Criteria

- Reproduce or invalidate the contradiction using a clean isolated index and
  the same question.
- Confidence evidence distinguishes genuinely ambiguous close scores from
  multiple high-score chunks that independently corroborate the answer.
- When final top-k evidence directly supports the requested fact, Level 3
  delivery does not claim that the knowledge base lacks that information.
