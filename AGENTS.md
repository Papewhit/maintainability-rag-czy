# Repository Instructions

## Review Guidelines

When reviewing pull requests in this repository, use an OpenSpec-aware review stance.

If the PR body contains `OpenSpec-Change: <change-name>`, review the implementation against these artifacts when they exist:

- `openspec/changes/<change-name>/proposal.md`
- `openspec/changes/<change-name>/design.md`
- `openspec/changes/<change-name>/tasks.md`
- `openspec/changes/<change-name>/specs/**/*.md`

Follow the verification dimensions used by `openspec-verify-change`: completeness, correctness, and coherence.

### OpenSpec Verification Protocol

For PRs with `OpenSpec-Change: <change-name>`, run the OpenSpec verification protocol before forming review conclusions.

1. Run `openspec status --change "<change-name>" --json`.
   - Use the result to identify the schema and available artifacts.
   - If this command fails, report it as an environment or OpenSpec setup issue instead of silently skipping OpenSpec review.
2. Run `openspec instructions apply --change "<change-name>" --json`.
   - Read every file listed in `contextFiles`.
   - Use those concrete paths as the source of truth for proposal, design, tasks, and specs.
3. If delta specs exist under `openspec/changes/<change-name>/specs/`, inspect every requirement and scenario.
   - Requirements are marked with `### Requirement:`.
   - Scenarios are marked with `#### Scenario:`.
4. Compare those artifacts against the PR diff and the relevant implementation files.
5. Produce findings using the completeness, correctness, and coherence dimensions below.

If the PR does not contain `OpenSpec-Change: <change-name>`, do a normal code review and note that OpenSpec verification was skipped because no change name was provided.

### Completeness

- Verify completed tasks in `tasks.md` are actually implemented.
- Treat incomplete required tasks as high priority if the PR claims the change is ready.
- Verify each delta spec requirement has implementation evidence.
- Flag missing requirement implementation as a high-priority finding.
- Report incomplete tasks separately from missing implementation evidence.

### Correctness

- For each requirement and scenario, check whether the implementation matches the stated behavior.
- Check whether tests cover the important scenarios.
- Flag implementation/spec divergence when it can cause incorrect behavior.
- Flag missing scenario coverage unless the gap is clearly low risk.
- Prefer concrete file and line references from the implementation or tests.

### Coherence

- Check whether implementation follows `design.md`.
- If code intentionally diverges from design, require either implementation correction or an OpenSpec artifact update.
- Check that new code follows existing project layering and patterns.
- Treat broad, unrelated refactors as review findings unless they are required by the OpenSpec change.

### Output Expectations

- Lead with actionable findings.
- Prioritize correctness, regressions, missing tests, and OpenSpec mismatches over style.
- Include file and line references when possible.
- Avoid speculative findings; when uncertain, call out the uncertainty and lower the priority.
- If no serious issues are found, say so briefly and mention any remaining test or OpenSpec coverage gaps.

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
