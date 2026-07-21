## 1. Mode Contract and Resolver

- [x] 1.1 Add the typed `forced_comprehensive | auto_classifier | precise_only` mode and a pure resolver that combines `force_comprehensive` with the existing classifier-enabled setting.
- [x] 1.2 Add the default-false request override to chat/RAG request context and optional-tool turn context without exposing server policy modes to clients.

## 2. Intent Routing Integration

- [x] 2.1 Inject the resolver once at the intent-node boundary and reuse the existing precise planner, intent model, `IntentDecision` schema, query preparation, and comprehensive graph.
- [x] 2.2 Implement forced-comprehensive constrained production and explicit safe degradation to precise for unavailable, timed-out, invalid, or contradictory model output without adding retries or a second model call.
- [x] 2.3 Propagate the same request override through forced-preload, optional-tool, synchronous, streaming, attachment, and no-attachment paths; force preload when the user selects comprehensive.
- [x] 2.4 Emit requested/effective mode, source, classifier invocation, forced success, and degradation error in the public trace and persisted message contract.

## 3. Frontend Request Control

- [x] 3.1 Add the “为我启用综合查询” composer control and send only the default-false `force_comprehensive` request field.
- [x] 3.2 Persist the selection on each user message, reuse that value for regenerate, and display requested versus effective mode without claiming success after degradation.

## 4. Verification and Compatibility

- [x] 4.1 Add resolver and intent-node unit tests for all three modes, including precise-only no-call behavior and forced invalid/timeout degradation.
- [x] 4.2 Add chat/API contract tests covering sync/stream, forced-preload/optional-tool, attachments, old-client defaults, and persisted trace identity.
- [x] 4.3 Add frontend tests for payloads, per-message regenerate behavior, checkbox interaction, and degraded-mode display.
- [x] 4.4 Run affected unit, integration, frontend, documentation, and strict OpenSpec validation; record that classifier accuracy and activation evidence remain outside this change.

## 5. Evidence Disposition Gate

- [x] New findings classified, or `No new findings` recorded
- [x] Code, test, review, runtime, or invalidation evidence linked
- [x] Every confirmed Finding has a durable disposition or evidenced in-place closure
- [x] Residual risks have durable typed destinations
- [x] Planned work has an OpenSpec change or issue owner where required
- [x] ARCHITECTURE impact assessed
- [x] No undispositioned design ambiguity remains

`No new findings`

## Validation Evidence

- Affected backend unit and storage integration regression: `564 passed` from `tests/unit/backend/rag`, `tests/unit/backend/contracts`, `tests/unit/backend/routers`, `tests/unit/backend/application`, and `tests/integration/db/test_conversation_storage.py`.
- Intent-mode and chat-router contract rerun: `16 passed` from `tests/unit/backend/rag/pipeline/test_intent_mode_control.py` and `tests/unit/backend/routers/test_chat_intent_mode.py`, including optional-tool true/false override propagation.
- RAG integration: `2 passed, 2 skipped` from `tests/integration/rag -m "not slow"`; environment/provider-dependent cases skipped under their registered conditions.
- Frontend: all 20 checks passed in `tests/unit/frontend/ui-redesign.test.mjs`.
- Documentation: `43 passed` in `tests/unit/docs`; `scripts/documentation/validate.py` passed with one pre-existing ignored/untracked governed-path warning for `docs/validation/codebase-size-and-complexity-audit.md`.
- OpenSpec: `openspec validate intent-routing-mode-control --strict` passed.
- Independent reviews: spec loyalty mapped 4/4 requirements and 13/13 scenarios with no functional blocking defect; code review reported no blocking or non-blocking P2 findings. Remaining test-depth comments were classified non-blocking P2 and do not trigger another review loop.
- Classifier accuracy, activation thresholds, real-model quality evidence, and rollout defaults remain owned by `openspec/changes/rag-intent-routing-activation/`; this change does not claim activation evidence.
- Architecture impact: yes; `docs/ARCHITECTURE.md` and the partial UI status in `docs/known-issues/rag-progress-ui-omits-intent-and-answer-handoff.md` were updated.
- New Finding: no. No change-local `findings.md` is required.
