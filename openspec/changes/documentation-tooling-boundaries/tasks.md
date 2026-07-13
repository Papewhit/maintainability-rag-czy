## 1. Shared Governance Model

- [x] 1.1 Create `scripts/documentation/` and move parsing, data models, Finding lifecycle, relationship, architecture-boundary, agent-routing, and rendering logic into the shared internal module.
- [x] 1.2 Implement the fixed non-recursive governed-source discovery contract for named authorities, typed directories, templates, and active change ledgers.
- [x] 1.3 Replace baseline matching with structural ignored/untracked discovery for governed paths and documentation tooling, returning non-blocking delivery warnings.

## 2. User-facing Commands

- [x] 2.1 Implement read-only `scripts/documentation/validate.py` with separate error and warning output and correctness-only exit status.
- [x] 2.2 Implement read-only `scripts/documentation/check_change.py <change-name>` for Evidence Disposition Gate and change-local Finding closure.
- [x] 2.3 Implement `scripts/documentation/catalog.py build` with validated atomic replacement and concise build summary.
- [x] 2.4 Implement `scripts/documentation/catalog.py inbox` from the shared selector with deterministic ordering and no writes.

## 3. Governance and Migration

- [x] 3.1 Update current governance workflows, catalog instructions, and operational commands to the three-command interface and fixed scan boundary.
- [x] 3.2 Remove `docs/documentation-ignore-baseline.txt` and `scripts/validate_documentation.py` after current references and tests migrate.
- [x] 3.3 Record the scope, warning-severity, and command-boundary decisions in this change's Finding ledger with disposition evidence.

## 4. Deterministic Coverage

- [x] 4.1 Migrate existing governance tests to the shared module and new command entrypoints without losing prior lifecycle, link, metadata, relationship, architecture, or gate coverage.
- [x] 4.2 Add tests proving unrelated Markdown and ignored files are omitted while governed direct children are discovered and validated.
- [x] 4.3 Add tests proving ignored/untracked governed files warn without failing and no baseline file is consulted.
- [x] 4.4 Add command tests for validation no-write behavior, change closure, catalog build failure atomicity, concise build output, and inbox no-write behavior.
- [x] 4.5 Prove catalog and inbox use identical membership and ordering from the shared source model.

## 5. Verification

- [x] 5.1 Run documentation-governance unit tests and all three command paths against the repository.
- [x] 5.2 Run strict OpenSpec validation and `openspec-verify-change`; resolve every critical finding.

## 6. Evidence Disposition Gate

- [x] 6.1 New findings classified, or `No new findings` recorded.
- [x] 6.2 Code, test, review, runtime, or invalidation evidence linked.
- [x] 6.3 Every confirmed Finding has a durable disposition or evidenced in-place closure.
- [x] 6.4 Residual risks have durable typed destinations.
- [x] 6.5 Planned work has an OpenSpec change or issue owner where required.
- [x] 6.6 ARCHITECTURE impact assessed and applied.
- [x] 6.7 No undispositioned design ambiguity remains.
