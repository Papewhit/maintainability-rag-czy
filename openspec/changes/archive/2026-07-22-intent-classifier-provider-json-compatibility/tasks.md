## 1. Runtime compatibility contract

- [x] 1.1 Update the intent classifier system prompt to require a schema-conformant JSON object without changing classification or fallback semantics
- [x] 1.2 Add unit coverage for the JSON message requirement, structured schema binding, and existing fallback behavior

## 2. Provider verification

- [x] 2.1 Add an explicitly enabled real-provider smoke test that skips without credentials/config and rejects rules fallback as success
- [x] 2.2 Run the deterministic intent test baseline and, when the configured Qwen environment is available, record a schema-valid real-provider success or retain the blocker

## 3. Governed documentation and validation

- [x] 3.1 Update KI-RAG-0017 and `docs/ARCHITECTURE.md` to match the verified provider compatibility state and preserve unrelated UI/trace limitations
- [x] 3.2 Run affected unit/eval tests, OpenSpec validation, and documentation validation; retain exact failures as evidence

## 4. Evidence Disposition Gate

- [x] New findings classified, or `No new findings` recorded
- [x] Code, test, review, runtime, or invalidation evidence linked
- [x] Every confirmed Finding has a durable disposition or evidenced in-place closure
- [x] Residual risks have durable typed destinations
- [x] Planned work has an OpenSpec change or issue owner where required
- [x] ARCHITECTURE impact assessed
- [x] No undispositioned design ambiguity remains

## Validation Evidence

- Unit and intent evaluation contract: `31 passed, 1 skipped` from `tests/unit/backend/rag/pipeline/test_intent_classifier.py` plus `tests/eval/rag/test_intent_classifier_eval.py`.
- Comprehensive evaluation regression excluding governed KI-RAG-0007: `7 passed, 1 deselected`; the full selection was `38 passed, 1 skipped, 1 known fingerprint failure`.
- Real provider compatibility: opt-in `qwen3.6-plus` smoke returned `1 passed` with a schema-valid non-fallback result under a relaxed 90-second compatibility budget; after clarifying JSON `null`, `qwen-flash` returned `1 passed` under the 5-second invocation deadline.
- Activation boundary: full-chain LangSmith run `019f82cb-b723-7852-8bed-b62b25c6a721` timed out with `qwen3.6-plus + 5s` and correctly fell back; this is not normal-gate `model_success` and is dispositioned as `INTENT-PROVIDER-F001` to `rag-intent-routing-activation`.
- Timeout lifecycle: the 5-second `qwen3.6-flash` comparison exposed that the outer thread timeout cannot cancel an in-flight provider call; `INTENT-PROVIDER-F002` is dispositioned to KI-RAG-0021.
- Conditional schema: `qwen-flash` initially returned `scope_hint="none"` instead of comprehensive JSON `null`; strict prompt clarification and real-provider rerun close `INTENT-PROVIDER-F003` in place.
- OpenSpec strict validation: `intent-classifier-provider-json-compatibility` valid.
- Documentation validation: passed with one pre-existing ignored/untracked governed-path warning unrelated to this change.
- Architecture impact: yes; current provider compatibility behavior and KI status were updated.
- New Finding: yes; `findings.md` records and dispositions `INTENT-PROVIDER-F001` through `INTENT-PROVIDER-F003`.
