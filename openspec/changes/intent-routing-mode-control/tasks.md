## 1. Mode Contract and Resolver

- [ ] 1.1 Add the typed `forced_comprehensive | auto_classifier | precise_only` mode and a pure resolver that combines `force_comprehensive` with the existing classifier-enabled setting.
- [ ] 1.2 Add the default-false request override to chat/RAG request context and optional-tool turn context without exposing server policy modes to clients.

## 2. Intent Routing Integration

- [ ] 2.1 Inject the resolver once at the intent-node boundary and reuse the existing precise planner, intent model, `IntentDecision` schema, query preparation, and comprehensive graph.
- [ ] 2.2 Implement forced-comprehensive constrained production and explicit safe degradation to precise for unavailable, timed-out, invalid, or contradictory model output without adding retries or a second model call.
- [ ] 2.3 Propagate the same request override through forced-preload, optional-tool, synchronous, streaming, attachment, and no-attachment paths; force preload when the user selects comprehensive.
- [ ] 2.4 Emit requested/effective mode, source, classifier invocation, forced success, and degradation error in the public trace and persisted message contract.

## 3. Frontend Request Control

- [ ] 3.1 Add the “为我启用综合查询” composer control and send only the default-false `force_comprehensive` request field.
- [ ] 3.2 Persist the selection on each user message, reuse that value for regenerate, and display requested versus effective mode without claiming success after degradation.

## 4. Verification and Compatibility

- [ ] 4.1 Add resolver and intent-node unit tests for all three modes, including precise-only no-call behavior and forced invalid/timeout degradation.
- [ ] 4.2 Add chat/API contract tests covering sync/stream, forced-preload/optional-tool, attachments, old-client defaults, and persisted trace identity.
- [ ] 4.3 Add frontend tests for payloads, per-message regenerate behavior, checkbox interaction, and degraded-mode display.
- [ ] 4.4 Run affected unit, integration, frontend, documentation, and strict OpenSpec validation; record that classifier accuracy and activation evidence remain outside this change.

## 5. Evidence Disposition Gate

- [ ] New findings classified, or `No new findings` recorded
- [ ] Code, test, review, runtime, or invalidation evidence linked
- [ ] Every confirmed Finding has a durable disposition or evidenced in-place closure
- [ ] Residual risks have durable typed destinations
- [ ] Planned work has an OpenSpec change or issue owner where required
- [ ] ARCHITECTURE impact assessed
- [ ] No undispositioned design ambiguity remains
