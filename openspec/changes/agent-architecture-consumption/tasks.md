## 1. Agent Routing and Governance Workflows

- [ ] 1.1 Add the thin architecture/evidence routing section, optional navigation hints, scope-expansion rule, and two handoff judgments to root `AGENTS.md`.
- [ ] 1.2 Restructure `docs/evidence-governance.md` so precise terminology precedes authority routing, two producer workflows and one human/agent lookup workflow replace the universal phase narrative, and inbox reporting is a separate operational procedure.
- [ ] 1.3 Document the material-finding, typed-document granularity, architecture-impact, and global three-state lifecycle tests with concrete examples.
- [ ] 1.4 Align `docs/findings/README.md`, Finding templates, and gate wording with the Global Finding Inbox and producer-workflow contracts without introducing a competing agent guide.

## 2. Finding Inbox Query and Validation

- [ ] 2.1 Refactor the documentation validator to identify global versus change-local Finding Records and enforce the three valid global state combinations.
- [ ] 2.2 Implement one reusable Global Finding Inbox selector with deterministic oldest-first `last_verified_date` ordering.
- [ ] 2.3 Add the read-only `--finding-inbox` CLI output with the required columns, successful empty output, and no catalog/report writes.
- [ ] 2.4 Make the generated catalog human-readable with authority entry points, regeneration guidance, governance/status context, clickable relative source links, source fingerprint, and a `Global Finding Inbox` section using the shared selector.
- [ ] 2.5 Validate root `AGENTS.md` authority links and the named governance workflow/template paths.

## 3. Deterministic Acceptance Coverage

- [ ] 3.1 Add unit fixtures for every valid and invalid global Finding state combination while preserving change-local in-progress behavior.
- [ ] 3.2 Add unit coverage for inbox membership, ordering, required columns, empty success, and no-write behavior.
- [ ] 3.3 Add tests proving catalog and standalone inbox membership remain identical and generated source links are valid and clickable.
- [ ] 3.4 Add routing-link, workflow/procedure anchor, and catalog instruction validation tests under `tests/unit/docs/`.
- [ ] 3.5 Run the documentation-governance unit suite and strict change closure validation.

## 4. Isolated Agent Comprehension Validation

- [ ] 4.1 Define business-only prompts and a rubric for local refactor, uncertain non-OpenSpec evidence, confirmed non-OpenSpec defect, OpenSpec ambiguity, planned/current boundary, and existing-known-issue evidence scenarios.
- [ ] 4.2 After an implementation commit is available, create separate clean detached worktrees at that commit and launch independent agents without inherited discussion context.
- [ ] 4.3 Capture each agent response and disposable worktree diff, score authority/workflow/destination/judgment/evidence treatment, and safely remove verified worktrees through Git.
- [ ] 4.4 Publish a validation report under `docs/validation/` bound to the tested commit and scenario fingerprint.

## 5. Verification and Evidence Disposition Gate

- [ ] 5.1 Use an independent agent to review whether root routing, producer/lookup workflows, operational procedure, and generated catalog are understandable to humans and agents without this discussion context.
- [ ] 5.2 Use an independent agent to review Finding lifecycle, inbox selection, and validator path coverage.
- [ ] 5.3 Run `openspec-verify-change` and resolve every critical finding.

## 6. Evidence Disposition Gate

- [ ] 6.1 New findings classified, or `No new findings` recorded.
- [ ] 6.2 Code, test, review, runtime, or invalidation evidence linked.
- [ ] 6.3 Every confirmed Finding has a durable disposition or evidenced in-place closure.
- [ ] 6.4 Residual risks have durable typed destinations.
- [ ] 6.5 Planned work has an OpenSpec change or issue owner where required.
- [ ] 6.6 ARCHITECTURE impact assessed and applied.
- [ ] 6.7 No undispositioned design ambiguity remains.
