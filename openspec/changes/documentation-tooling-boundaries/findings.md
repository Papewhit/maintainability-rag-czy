---
document_type: finding_ledger
change: documentation-tooling-boundaries
last_verified_commit: a5d5987b6529dfbcb18b6c8b9c75da5bcdf15188
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
