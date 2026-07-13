## Context

The documentation-governance implementation currently discovers every Markdown file beneath `docs/`, then separately scans every ignored/untracked file beneath `docs/` and `scripts/`. A tracked `docs/documentation-ignore-baseline.txt` suppresses unrelated historical documents and experiments one path at a time. The same `scripts/validate_documentation.py` command validates sources, checks change closure, emits delivery warnings, writes the generated catalog, and prints the Finding Inbox depending on flags.

The governance authority already defines typed destinations and their paths. The tooling can therefore use those paths as its complete discovery contract instead of attempting to infer the purpose of arbitrary Markdown. This change keeps `.gitignore` unchanged and preserves ignored catalog output.

## Goals / Non-Goals

**Goals:**

- Make governed-source discovery fixed, structural, and shared by validation and catalog access.
- Remove per-file delivery exceptions while retaining visible, non-blocking warnings for ignored/untracked governed artifacts.
- Give humans and future skills three cohesive, predictably named commands.
- Keep validation and query operations read-only and catalog mutation explicit.
- Preserve all existing metadata, lifecycle, relationship, link, architecture-boundary, and change-gate checks within the new boundary.

**Non-Goals:**

- Scanning arbitrary repository Markdown to infer whether it should have been governed.
- Offering full-repository versus governed-only scanning modes.
- Changing typed-document ownership, metadata vocabularies, Finding lifecycle, or `.gitignore`.
- Retrofitting completed OpenSpec artifacts that accurately describe their historical implementation context.

## Decisions

### 1. Use one fixed governed source set

The shared governance module will discover only:

- `docs/ARCHITECTURE.md` and `docs/evidence-governance.md`;
- Markdown directly under `docs/findings/`, `docs/architecture/decisions/`, `docs/known-issues/`, `docs/enhancements/`, `docs/validation/`, and `docs/templates/`;
- active `openspec/changes/*/findings.md` ledgers.

Template files are validated as support contracts but are not catalog authority rows. The generated `docs/evidence-catalog.md` is output, never an input. Discovery does not recurse into unrelated documentation trees and has no scan-scope option.

Alternative rejected: scan all Markdown and identify governed documents from `document_type`. It would preserve noise from historical and generated documents, and it still could not identify a misplaced document lacking metadata.

### 2. Define delivery scope structurally

Delivery inspection will query Git only for ignored/untracked files matching the governed source set plus Python files directly under `scripts/documentation/`. Every match produces a warning with its path. Warnings never change the validation exit code, because a user may intentionally keep sensitive or local detail outside version control.

No file-level suppression list replaces the baseline. A new governed document class requires an explicit change to the shared path contract, governance authority, and tests.

Alternative rejected: preserve a tracked allowlist. It makes incidental local files part of the repository contract and grows without clarifying why a path is governed.

### 3. Expose three commands over one internal model

The user-facing commands will be:

```text
scripts/documentation/validate.py
scripts/documentation/check_change.py
scripts/documentation/catalog.py
```

`scripts/documentation/_governance.py` owns discovery, parsing, validation models, inbox selection, and catalog rendering. Command modules remain thin adapters.

- `validate.py` validates the complete governed source set and emits delivery warnings. It never writes repository files.
- `check_change.py <change-name>` evaluates that change's Evidence Disposition Gate and ledger using the shared governed validation result. It never writes repository files.
- `catalog.py build` validates source syntax, writes `docs/evidence-catalog.md`, and prints a concise build summary. `catalog.py inbox` prints the read-only Global Finding Inbox and never writes files.

Positional catalog subcommands communicate distinct operations more clearly than behavior-switching flags on a validator. Output-format parameters may alter representation but not command responsibility.

### 4. Keep errors and delivery warnings distinct

Governance contract violations produce errors and a nonzero exit code. Ignored/untracked governed paths produce delivery warnings and a zero exit code when no contract error exists. Text output is human-readable; the internal result keeps errors, warnings, documents, and Findings separately addressable for future skill adapters.

### 5. Make catalog generation explicit

Catalog generation uses the same fixed discovery result and Finding Inbox selector as validation and inbox output. `catalog.py build` is the only command that writes the fixed catalog path. The builder refuses to write when governed-source errors exist, preventing invalid navigation from replacing a previous catalog.

## Risks / Trade-offs

- [A governed document placed outside its authority path is not discovered] → Authority Routing remains the placement contract; the validator deliberately does not guess semantics outside that contract.
- [Non-blocking delivery warnings may be overlooked] → Give warnings a stable prefix and include them in human output without conflating them with correctness failures.
- [Command migration can leave stale instructions] → Search tracked current authorities, templates, tests, and executable help for the legacy command and add regression coverage for current command references.
- [Shared internals could become another monolith] → Keep policy/data operations in the internal module while maintaining narrow command entrypoints and command-level tests.

## Migration Plan

1. Introduce the internal module and three command entrypoints while preserving current validation behavior within governed paths.
2. Migrate tests and current governance instructions to the new commands.
3. Add fixed-scope, non-blocking-warning, no-write, catalog-build, and inbox tests.
4. Remove `scripts/validate_documentation.py` and `docs/documentation-ignore-baseline.txt`.
5. Run documentation validation, change closure validation, catalog generation, unit tests, and strict OpenSpec verification.

Rollback restores the legacy script and baseline from version control. The ignored catalog can always be regenerated.

## Open Questions

None.
