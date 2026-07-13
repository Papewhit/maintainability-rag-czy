# Repository Instructions

## Test Taxonomy

Tests are grouped by execution cost first and product area second. Do not add new
test files directly under `tests/`.

- `tests/unit/`: pure unit tests using fakes, mocks, temp files, or in-memory stores.
- `tests/integration/`: cross-component tests, real document parsers, real sample files,
  or real DB/infrastructure dependencies.
- `tests/e2e/`: full validation scripts that require a running service or complete
  document ingestion flow.
- `tests/eval/`: RAG dataset, qrels, metric, and evaluation helper tests.
- `tests/regression/`: historical bug fixes or quality drift checks.
- `tests/fixtures/documents/`: shared PDF/DOCX/XLSX samples.

Use pytest markers registered in `pyproject.toml` to state runtime requirements:
`unit`, `integration`, `e2e`, `eval`, `regression`, `slow`, `requires_db`,
`requires_redis`, `requires_milvus`, and `requires_models`.

Common commands:

```powershell
uv run pytest tests/unit -q
uv run pytest tests/integration -m "not slow" -q
uv run pytest tests/eval tests/regression -q
uv run pytest tests -m "not slow and not e2e" -q
node tests/unit/frontend/ui-redesign.test.mjs
```

DeepDoc parse metadata validation scripts live under
`tests/e2e/deepdoc_parse_metadata/`; do not recreate milestone-numbered
validation scripts at the repository root.

## Architecture and Evidence Routing

Use [the current architecture](docs/ARCHITECTURE.md) when work may assess or
change component responsibilities, cross-module flows, storage boundaries,
metadata or wire contracts, runtime defaults, feature status, degradation,
trace behavior, or evaluation contracts. The evidence boundary, relevant
component sections, feature status matrix, and known limitations are useful
starting points; expand reading when the impact is broader or unclear.

For design, OpenSpec, review, governed documentation, known limitations,
technical debt, enhancements, or validation evidence, first read
[documentation evidence governance](docs/evidence-governance.md) and follow
the applicable named workflow. Re-evaluate both routes if task scope expands
during implementation.

Before handing off work, report:

- `Architecture impact: yes/no` — would leaving `docs/ARCHITECTURE.md`
  unchanged materially mislead readers about the current system or its
  explicit planning boundary?
- `New Finding: yes/no` — did the task produce material knowledge whose loss
  could cause a future maintainer to misjudge behavior, boundaries, risk, or
  evidence confidence?

When either answer is `yes`, include the governed destination or updated
authority path in the handoff.

## Review Guidelines

When reviewing pull requests in this repository, use a normal code-review stance unless
the PR or task explicitly identifies an OpenSpec change.

If the PR body contains `OpenSpec-Change: <change-name>`, or the user explicitly asks
for OpenSpec verification of a change, use an OpenSpec-aware review stance. Treat
`openspec-verify-change` as the authoritative workflow for detailed verification
heuristics.

### OpenSpec Verification Protocol

For OpenSpec-aware reviews:

1. Run `openspec status --change "<change-name>" --json` to identify the workflow
   schema and available artifacts.
2. Run `openspec instructions apply --change "<change-name>" --json`.
   Read every file listed in `contextFiles`; those concrete paths are the source of
   truth for proposal, design, tasks, and specs.
3. Compare the OpenSpec artifacts against the PR diff and relevant implementation
   files using these dimensions: completeness, correctness, and coherence.
4. Report actionable findings first, prioritizing correctness, regressions, missing
   tests, and OpenSpec mismatches over style.

If any required OpenSpec command fails, report it as an environment or OpenSpec setup
issue instead of silently skipping OpenSpec verification.

If a PR does not contain `OpenSpec-Change: <change-name>`, do a normal code review and
note that OpenSpec verification was skipped because no change name was provided.

For explicit OpenSpec verification tasks, use this report shape:

```markdown
## OpenSpec Verification Report: <change-name>

### Summary
| Dimension | Status |
| --- | --- |
| Completeness | <tasks and requirement coverage> |
| Correctness | <requirement and scenario coverage> |
| Coherence | <design and pattern consistency> |

### Critical
- <must-fix issues before archive, or "None">

### Warnings
- <should-fix issues, or "None">

### Suggestions
- <nice-to-fix issues, or "None">

### Final Assessment
<ready/not ready, with concise rationale>
```
