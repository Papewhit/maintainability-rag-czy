## 1. Evidence and Level 3 Contracts

- [x] 1.1 Add typed candidate, final, and answer-consumed evidence identities with stable IDs and explicit containment semantics.
- [x] 1.2 Add the typed Level 3 delivery contract for partial synthesis, full-coverage low confidence, baseline-only, no-evidence, and precise-insufficient modes.
- [x] 1.3 Make the legacy `level3_answer` a deterministic compatibility projection of the typed contract instead of a control input.

## 2. Comprehensive Graph Observability

- [x] 2.1 Emit ordered aggregate `rag_step` events at decomposition/fanout, branch processing, merge, and shared-postprocess node boundaries.
- [x] 2.2 Keep parallel workers from emitting unordered user events and include only aggregate counts and safe public detail.
- [x] 2.3 Preserve final evidence, branch provenance, answer evidence, and Level 3 refs in stream, non-stream, and persisted traces.
- [x] 2.4 Emit one explicit final precise/comprehensive route `rag_step` from `intent_parse`, with safe degradation wording based on the effective typed plan.

## 3. Mode-specific Level 3 Delivery

- [x] 3.1 Return evidence refs alongside Level 3 excerpts and derive deduplicated answer evidence only from final top-k documents actually consumed.
- [x] 3.2 Route both forced-preload and optional-tool delivery through the same typed contract and renderer.
- [x] 3.3 Restrict answer-model synthesis to `0 < X < Y` partial coverage and keep Y/Y low-confidence, baseline-only, no-evidence, and precise-insufficient on their specified evidence-only boundaries without adding model calls.

## 4. API and Frontend Consumption

- [x] 4.1 Extend public schemas compatibly so typed delivery and evidence identities survive SSE, non-stream responses, and history persistence.
- [x] 4.2 Render “最终来源片段” from answer-consumed evidence, show initial/expanded candidates only in a separately labelled diagnostic area, and use only `retrieved_chunks` as the old-trace fallback.
- [x] 4.3 Show ordered comprehensive progress independently of fallback events and preserve compatibility with historical traces.

## 5. Verification

- [x] 5.1 Add graph tests for aggregate event order and count stability under differently ordered parallel branch completion.
- [x] 5.2 Add evidence-identity tests proving candidate elimination, final selection, answer consumption, deduplication, and frontend source display remain aligned.
- [x] 5.3 Add typed Level 3 tests for partial, Y/Y, baseline-only, no-evidence, and precise cases across both delivery paths.
- [x] 5.4 Run affected unit, integration, frontend, real-model E2E, documentation, and strict OpenSpec validation without changing confidence or fallback routing algorithms.
- [x] 5.5 Add intent-route event tests for precise, comprehensive, and forced-comprehensive degradation before downstream retrieval events.

## 6. Evidence Disposition Gate

- [x] New findings classified, or `No new findings` recorded
- [x] Code, test, review, runtime, or invalidation evidence linked
- [x] Every confirmed Finding has a durable disposition or evidenced in-place closure
- [x] Residual risks have durable typed destinations
- [x] Planned work has an OpenSpec change or issue owner where required
- [x] ARCHITECTURE impact assessed
- [x] No undispositioned design ambiguity remains

Review finding `RAG-CDO-F001` was classified and closed in place; see `findings.md`.

## Validation Evidence

- Intent-route observability extension: `35 passed` across intent state/mode, comprehensive graph, and RAG-step unit tests; all 21 frontend checks passed. Tests cover precise, comprehensive, forced-comprehensive degradation, safe error redaction, and route-before-fanout ordering.
- Affected backend unit/integration regression: `568 passed, 2 skipped` from `tests/unit/backend/rag`, `tests/unit/backend/contracts`, `tests/unit/backend/routers`, and `tests/integration/rag -m "not slow"`; skips were registered environment conditions.
- Deterministic compiled RAG E2E: `2 passed` from `tests/e2e/rag`.
- Frontend: all 21 checks passed in `tests/unit/frontend/ui-redesign.test.mjs`, including answer-evidence-only final sources and candidate diagnostics.
- Documentation: `43 passed` in `tests/unit/docs`; `scripts/documentation/validate.py` passed with one pre-existing ignored/untracked governed-path warning for `docs/validation/codebase-size-and-complexity-audit.md`.
- OpenSpec: `openspec validate rag-comprehensive-delivery-observability --strict` passed.
- Runtime: the configured main answer model passed a partial-delivery check, answering only the sourced covered dimension, disclosing the missing dimension, omitting internal labels, and refusing a cross-dimension conclusion. The repository's separate `FAST_MODEL` intent eval remained skipped because `FAST_MODEL` is unset and is not claimed as evidence for this delivery contract.
- Independent Codex OpenSpec verification mapped 6/6 requirements and 18/18 scenarios with no functional Warning. Its only blocking result was this then-pending Evidence Disposition Gate; its SSE-to-history-to-frontend mega-test suggestion is recorded as non-blocking because schema/persistence/frontend boundary tests already cover the contract.
- Final independent spec-loyalty review found one blocking typed-schema gap; `RAG-CDO-F001` records its strict internal/public contract fix and the same reviewer confirmed `Blocking Fixed`. Independent code review reported no blocking findings and classified its three observations as non-blocking P2.
- Architecture impact: yes; `docs/ARCHITECTURE.md` now records typed Level 3 delivery, ordered comprehensive progress, and `rag-evidence-v1` final/answer evidence semantics.
- Residual activation/evaluation work remains owned by `openspec/changes/rag-multilevel-fallback-activation/` and `openspec/changes/rag-intent-routing-activation/`; no new residual risk or planned work was created by this implementation.
- New Finding: yes. `RAG-CDO-F001` records the review-discovered typed-schema gap and its evidenced in-place closure.
