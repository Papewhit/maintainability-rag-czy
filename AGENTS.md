# Repository Instructions

## Review Guidelines

When reviewing pull requests in this repository, use an OpenSpec-aware review stance.

If the PR body contains `OpenSpec-Change: <change-name>`, review the implementation against these artifacts when they exist:

- `openspec/changes/<change-name>/proposal.md`
- `openspec/changes/<change-name>/design.md`
- `openspec/changes/<change-name>/tasks.md`
- `openspec/changes/<change-name>/specs/**/*.md`

Follow the verification dimensions used by `openspec-verify-change`: completeness, correctness, and coherence.

### Completeness

- Verify completed tasks in `tasks.md` are actually implemented.
- Treat incomplete required tasks as high priority if the PR claims the change is ready.
- Verify each delta spec requirement has implementation evidence.
- Flag missing requirement implementation as a high-priority finding.

### Correctness

- For each requirement and scenario, check whether the implementation matches the stated behavior.
- Check whether tests cover the important scenarios.
- Flag implementation/spec divergence when it can cause incorrect behavior.
- Flag missing scenario coverage unless the gap is clearly low risk.

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
