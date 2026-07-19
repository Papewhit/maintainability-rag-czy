---
document_type: validation_report
validation_id: VAL-RAG-FALLBACK-001
status: passed
scope: validation.rag.fallback.ui
source_commit: 5e49a4669f78dbaddf00ee97f1f76c7960bba419
source_fingerprint: sha256:ccdf9f9fe2b04fbc0d5140f524f00da5aee8f4bba16427c08f41c577175bef11
executed_at: 2026-07-19T00:00:00+08:00
source_findings: [RAG-MF-F026, RAG-MF-F027]
supersedes: []
---

# Multilevel fallback M8 frontend validation

## Scope

This report closes the narrow M8.5 manual UX gate: a live fallback request can
render multiple RAG steps, remain interactive, and deliver its final answer
without page lock-up or visible flicker. It does not validate retrieval
quality, confidence thresholds, upload observability, answer time-to-first-
token, or the real-corpus activation gates now owned by
`openspec/changes/rag-multilevel-fallback-activation/`.

## Method

The backend ran from commit `5e49a4669f78dbaddf00ee97f1f76c7960bba419`
with `.env.rag-full-chain-e2e.example` overlaid on the user's secret-bearing
base environment. The overlay SHA-256 was
`ee11c600e40b04d9e4f9ed5ede28d6c20696607dd2fb800c2321f03cfec38a65`.
`SCM优化方案.pdf` had completed ingestion before the query. The user observed
the live Chrome UI, expanded the default-collapsed thinking process, and then
inspected the persisted session trace after delivery.

## Inputs

- Session: `session_1784383996604`
- Assistant message: `13`
- Query: `统一源图是什么？`
- Active behavior: precise retrieval, signal-directed Level 2, then Level 3
- Persisted path: `[2, 3]`

## Results

- The UI rendered `思考过程 · 8 步` and remained responsive when expanded.
- The visible sequence included Level 2 entry and completion for
  `weak_margin_and_root`, followed by Level 3 entry and completion for
  `levels_exhausted`.
- The Level 2 detail showed the effective scope transition `none → none`.
- The final response was delivered without a page lock-up, component crash,
  or visible fallback-step flicker.
- Refresh removed transient step-event presentation, but the assistant message
  retained `rag_trace`; this persistence boundary did not block the live M8.5
  interaction.

The M8.5 functional gate therefore passes for the exercised multi-level path.

## Limitations

This is one manual path, not a statistical UX or latency study. The upload and
document-processing interval remains unobservable, and a noticeable silent
handoff remains between the final RAG event and the first answer token. Those
separate limitations remain governed outside this validation report. The run
also exposed confidence, routing-order, and candidate-cap behavior; only the
candidate-cap contradiction is remediated in the current change.

## Findings

- RAG-MF-F026 retains the observed signal-directed `[2, 3]` order as input to
  a separately governed routing-order evaluation.
- RAG-MF-F027 records the observed `candidate_k: 120 → 50` contract violation;
  task 5.11 resolves it without changing the routing order.
