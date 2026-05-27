# Repository Instructions

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
