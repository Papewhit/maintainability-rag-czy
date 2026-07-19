---
document_type: enhancement
enhancement_id: ENH-DELIVERY-0001
status: candidate
scope: delivery.pull_request_history
motivation: Keep the target-branch timeline concise and understandable after merging review-heavy pull requests without weakening validation evidence binding.
last_verified_commit: 0d01ee0fb4c72a5399a52e9b26683ef5c46df033
last_verified_date: 2026-07-16
source_findings: []
related_issues: []
---

# Keep Pull Request Merge History Concise

## Opportunity

Review-heavy pull requests can accumulate implementation commits, follow-up
fixes, and validation evidence-binding commits. Merging that branch without
consolidation preserves the full working sequence in the pull request and
target history, making the post-merge timeline harder to scan than the final
change requires.

Future delivery workflow design should evaluate pre-merge consolidation into
a small number of logical commits. For governed changes, the likely minimum
shape is one implementation commit followed by one evidence-binding commit;
alternative squash workflows must still leave `source_commit` and
`source_fingerprint` pointing to durable, verifiable source history.

## Guiding Principle

After a pull request is merged, the target-branch timeline should be concise,
clear, and organized around the final logical change rather than the sequence
of review iterations. Cleanup must preserve review traceability, required
validation evidence, and the meaning of commit-bound reports.

## Expected Value

- Make merged feature history easier to understand and bisect.
- Keep review-fix noise out of the primary target-branch narrative.
- Preserve trustworthy source bindings for governed validation reports.
- Establish a consistent merge choice for ordinary and evidence-bound pull
  requests.

## Non-Goals

- Rewriting or force-pushing the history of pull requests that are already
  merged.
- Hiding material design decisions, behavior changes, or validation gaps.
- Dropping commits selectively in a way that omits required implementation or
  evidence.
- Choosing or enforcing a merge strategy in this candidate document.

## Dependencies

- Commit and pull-request conventions for the repository.
- Branch-protection and allowed merge-method configuration on GitHub.
- Validation source-binding requirements in `docs/evidence-governance.md`.
- A future OpenSpec change or tracked issue before workflow automation or
  enforcement is introduced.

## Planning Status

Candidate only. The current merged history remains unchanged. Before planning
implementation, compare at least pre-merge logical-commit consolidation and
squash-merge-plus-post-merge-evidence-binding against the guiding principle.
