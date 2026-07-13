## Why

Documentation governance currently scans all Markdown under `docs/`, maintains a tracked per-file ignore baseline for unrelated ignored files, and exposes validation, change closure, catalog generation, and Finding Inbox queries through one mode-switching script. This makes governance scope noisy, delivery behavior difficult to explain, and the human/skill command surface misleading.

## What Changes

- Replace repository-wide documentation discovery and the per-file `documentation-ignore-baseline.txt` with one fixed set of governed paths derived from the existing authority structure.
- Limit validation, catalog discovery, and ignored/untracked delivery warnings to that governed source set; delivery omissions remain warnings and do not change the validation exit code.
- Split the user-facing tooling into three cohesive commands under `scripts/documentation/`: general validation, OpenSpec change-evidence closure checking, and catalog/inbox access.
- Make validation and change checking read-only; make catalog writes explicit through a `build` subcommand while preserving a read-only `inbox` subcommand.
- Keep parsing, discovery, lifecycle, relationship, and rendering logic in one shared internal governance module.
- Update governance instructions, generated command references, and deterministic tests; remove the obsolete baseline and legacy multipurpose entrypoint.

## Capabilities

### New Capabilities

- `documentation-tooling-boundaries`: Defines governed-source discovery, non-blocking delivery warnings, narrow documentation command responsibilities, and deterministic catalog/inbox behavior.

### Modified Capabilities

- `documentation-evidence-governance`: Replace validator-owned catalog generation and blocking ignored-file manifest behavior with explicit catalog build and non-blocking structural delivery warnings.
- `agent-architecture-consumption`: Replace the legacy validator flag and implicit catalog regeneration contract with the dedicated catalog `inbox` and `build` subcommands.

## Impact

- `scripts/validate_documentation.py` is replaced by three entrypoints and a shared module under `scripts/documentation/`.
- `docs/documentation-ignore-baseline.txt` is removed without changing `.gitignore`.
- `docs/evidence-governance.md`, generated catalog instructions, OpenSpec closure commands, and documentation-governance tests are migrated.
- Existing historical or generated documents outside governed paths are no longer scanned, indexed, or individually allowlisted.
