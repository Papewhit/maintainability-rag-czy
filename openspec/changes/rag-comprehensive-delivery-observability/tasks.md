## 1. Evidence and Level 3 Contracts

- [ ] 1.1 Add typed candidate, final, and answer-consumed evidence identities with stable IDs and explicit containment semantics.
- [ ] 1.2 Add the typed Level 3 delivery contract for partial synthesis, full-coverage low confidence, baseline-only, no-evidence, and precise-insufficient modes.
- [ ] 1.3 Make the legacy `level3_answer` a deterministic compatibility projection of the typed contract instead of a control input.

## 2. Comprehensive Graph Observability

- [ ] 2.1 Emit ordered aggregate `rag_step` events at decomposition/fanout, branch processing, merge, and shared-postprocess node boundaries.
- [ ] 2.2 Keep parallel workers from emitting unordered user events and include only aggregate counts and safe public detail.
- [ ] 2.3 Preserve final evidence, branch provenance, answer evidence, and Level 3 refs in stream, non-stream, and persisted traces.

## 3. Mode-specific Level 3 Delivery

- [ ] 3.1 Return evidence refs alongside Level 3 excerpts and derive deduplicated answer evidence only from final top-k documents actually consumed.
- [ ] 3.2 Route both forced-preload and optional-tool delivery through the same typed contract and renderer.
- [ ] 3.3 Restrict answer-model synthesis to `0 < X < Y` partial coverage and keep Y/Y low-confidence, baseline-only, no-evidence, and precise-insufficient on their specified evidence-only boundaries without adding model calls.

## 4. API and Frontend Consumption

- [ ] 4.1 Extend public schemas compatibly so typed delivery and evidence identities survive SSE, non-stream responses, and history persistence.
- [ ] 4.2 Render “最终来源片段” from answer-consumed evidence, show initial/expanded candidates only in a separately labelled diagnostic area, and use only `retrieved_chunks` as the old-trace fallback.
- [ ] 4.3 Show ordered comprehensive progress independently of fallback events and preserve compatibility with historical traces.

## 5. Verification

- [ ] 5.1 Add graph tests for aggregate event order and count stability under differently ordered parallel branch completion.
- [ ] 5.2 Add evidence-identity tests proving candidate elimination, final selection, answer consumption, deduplication, and frontend source display remain aligned.
- [ ] 5.3 Add typed Level 3 tests for partial, Y/Y, baseline-only, no-evidence, and precise cases across both delivery paths.
- [ ] 5.4 Run affected unit, integration, frontend, real-model E2E, documentation, and strict OpenSpec validation without changing confidence or fallback routing algorithms.

## 6. Evidence Disposition Gate

- [ ] New findings classified, or `No new findings` recorded
- [ ] Code, test, review, runtime, or invalidation evidence linked
- [ ] Every confirmed Finding has a durable disposition or evidenced in-place closure
- [ ] Residual risks have durable typed destinations
- [ ] Planned work has an OpenSpec change or issue owner where required
- [ ] ARCHITECTURE impact assessed
- [ ] No undispositioned design ambiguity remains
