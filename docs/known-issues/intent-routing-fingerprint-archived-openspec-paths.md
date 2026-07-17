---
document_type: known_issue
issue_id: KI-RAG-0007
status: open
scope: rag.evaluation
severity: low
first_confirmed: 2026-07-17
last_verified_commit: cbcd3de07c3b0544701d778e6315b0216a857027
last_verified_date: 2026-07-17
source_findings:
  - RAG-MF-F024
---

# Intent-routing fingerprint references archived OpenSpec paths

## Observed Behavior

`routing_source_fingerprint()` unconditionally reads two files under
`openspec/changes/rag-intent-routing/`. Those paths are absent from the
`rag-fusion-design` merge-base, so the source-fingerprint unit and evaluation
tests fail with `FileNotFoundError` in a clean isolated worktree.

## Impact

The non-slow, non-e2e regression suite reports two failures before it can
assert the fingerprint contents. Runtime RAG behavior is not affected.

## Evidence or Reproduction

From a clean worktree based on commit
`cbcd3de07c3b0544701d778e6315b0216a857027`, run:

```powershell
uv run pytest tests/unit/backend/evaluation/test_source_fingerprint.py tests/eval/rag/test_comprehensive_intent_routing_eval.py -q
```

The implementation and both failing tests are unchanged by
`rag-multilevel-fallback`, and the merge-base tree has no
`openspec/changes/rag-intent-routing/design.md` entry.

## Workaround

Run these fingerprint tests only in a checkout that still contains the
historical change artifacts, or exclude them while validating an unrelated
change. Do not synthesize placeholder artifacts because that would produce a
misleading fingerprint.

## Resolution Criteria

Bind the evaluation fingerprint to durable current authorities (or explicitly
versioned archived artifacts), then prove the two tests pass in a clean
worktree without compatibility fallbacks for missing files.
