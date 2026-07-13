---
document_type: finding_ledger
change: documentation-tooling-boundaries
last_verified_commit: cdeb4f4628ffb2e6586246c3e0633ea9e386cb40
last_verified_date: 2026-07-13
---

# Change Findings

## DOC-TOOL-F001

- Kind: design_ambiguity
- Primary scope: documentation.validation
- Evidence status: confirmed
- Observation: The legacy delivery check scanned every ignored file under `docs/` and `scripts/`, then required a tracked per-file baseline to suppress unrelated historical documents and experiments.
- Inference: The baseline encoded incidental local contents rather than the governance boundary and would grow without improving semantic coverage.
- Decision: Use the existing authority paths as the complete non-recursive governed discovery and delivery scope, with no full-repository mode or per-file suppression list.
- Residual risk: A document placed outside its governed authority path is not discovered; placement remains an Authority Routing responsibility.
- Evidence: User design review; fixed-path discovery and unrelated-file exclusion tests in `tests/unit/docs/test_documentation_governance.py`.
- Disposition: change
- Disposition target: openspec/changes/documentation-tooling-boundaries/
- Resolution evidence: The shared governance module defines the fixed source set, the baseline is removed, and deterministic scope tests pass.

## DOC-TOOL-F002

- Kind: design_ambiguity
- Primary scope: delivery.documentation
- Evidence status: confirmed
- Observation: An ignored and untracked governed document can represent either an accidental PR omission or a user's intentional choice not to disclose local detail.
- Inference: Treating every such path as a validation error would collapse delivery visibility into a disclosure requirement.
- Decision: Report each structurally governed ignored/untracked path as a warning that never changes the correctness exit code.
- Residual risk: none
- Evidence: User design decision; warning-severity and read-only command tests in `tests/unit/docs/test_documentation_governance.py`.
- Disposition: change
- Disposition target: openspec/changes/documentation-tooling-boundaries/
- Resolution evidence: General validation separates errors from delivery warnings and returns failure only for governance contract errors.

## DOC-TOOL-F003

- Kind: technical_debt
- Primary scope: documentation.tooling
- Evidence status: confirmed
- Observation: `scripts/validate_documentation.py` switched among source validation, change closure, catalog mutation, and inbox reporting through unrelated flags despite its validator-only name.
- Inference: The interface was misleading for humans and would require a future skill to understand flag combinations rather than call purpose-specific operations.
- Decision: Expose three cohesive command files over one shared model: validation, change evidence checking, and catalog access with explicit `build` and `inbox` subcommands.
- Residual risk: none
- Evidence: User design review; command-level no-write, atomic-build, summary, closure, and inbox tests.
- Disposition: change
- Disposition target: openspec/changes/documentation-tooling-boundaries/
- Resolution evidence: The three entrypoints exist under `scripts/documentation/`, the legacy multipurpose entrypoint is removed, and current governance documents each command.

## DOC-TOOL-F004

- Kind: system_limitation
- Primary scope: documentation.catalog
- Evidence status: confirmed
- Observation: The generated catalog renders one row for every Finding in every active change ledger, and the three completed governance changes already produce a long Findings section.
- Inference: Archive hygiene removes archived ledgers from discovery, but many concurrent or completed-yet-unarchived changes can still make the catalog harder to consume.
- Decision: Preserve the concern as a candidate catalog-consumption enhancement and defer a concrete presentation mechanism until post-archive usage evidence justifies it.
- Residual risk: none
- Evidence: Human inspection of the catalog generated at `cdeb4f4628ffb2e6586246c3e0633ea9e386cb40`; shared discovery includes direct active `openspec/changes/*/findings.md` ledgers and excludes nested archives.
- Disposition: enhancement
- Disposition target: docs/enhancements/evidence-catalog-finding-history-scaling.md
- Resolution evidence: `ENH-DOC-0001` records the scaling opportunity, possible consumption strategies, archive mitigation, and candidate-only planning status.

## DOC-TOOL-F005

- Kind: documentation_drift
- Primary scope: documentation.specs
- Evidence status: confirmed
- Observation: Sync assessment showed that earlier governance delta specs still required validator-owned catalog writes, blocking ignored-file decisions, and the legacy `--finding-inbox` interface, while this change initially declared only a new capability.
- Inference: Chronological sync would leave stable main specs with obsolete command and warning-severity contracts alongside the new tooling capability.
- Decision: Add explicit modified-capability deltas for `documentation-evidence-governance` and `agent-architecture-consumption` before syncing or archiving any of the three changes.
- Residual risk: none
- Evidence: Side-by-side sync review of all three changes' delta specs and the implemented commands under `scripts/documentation/`.
- Disposition: change
- Disposition target: openspec/changes/documentation-tooling-boundaries/
- Resolution evidence: The proposal now declares both modified capabilities and full replacement requirements specify `catalog.py build`, `catalog.py inbox`, and non-blocking structural delivery warnings.
