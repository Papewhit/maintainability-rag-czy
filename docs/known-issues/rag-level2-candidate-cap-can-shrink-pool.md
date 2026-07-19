---
document_type: known_issue
issue_id: KI-RAG-0009
status: mitigated
scope: rag.fallback.level2
severity: medium
first_confirmed: 2026-07-18
last_verified_commit: 5e49a4669f78dbaddf00ee97f1f76c7960bba419
last_verified_date: 2026-07-18
source_findings:
  - RAG-MF-F027
---

# Level 2 Candidate Cap Can Shrink the Retrieval Pool

## Observed Behavior

Level 2 computes its candidate count as the smaller of the configured ceiling
and 1.5 times the completed prior-round candidate count. When the prior count
already exceeds `RAG_FALLBACK_EXPANDED_CANDIDATE_K`, this calculation reduces
the candidate pool even though the Level 2 contract describes the operation as
an enlargement.

During a real precise-query run, the trace recorded:

```text
candidate_k: 120 -> 50
scope_mode: none preserved
same_root_cap: 3 -> 4
```

The query then retained `weak_margin_and_root` and terminated at Level 3.

## Impact

Level 2 may narrow candidate eligibility instead of relaxing it. In a
`scope_mode=none` run, candidate expansion and the same-root cap are the only
available relaxation dimensions; reducing one of them can make the retry less
capable than the completed initial round and can contribute to an unnecessary
Level 3 result.

## Evidence or Reproduction

The persisted trace for assistant message `13` in session
`session_1784383996604` records `candidate_k: 120 -> 50`, followed by
`fallback_path=[2, 3]` and `level3_reason="available fallback levels already
attempted"`.

The calculation in `backend/rag/fallback_scope.py` is:

```python
min(max_candidate_k, math.ceil(current_candidate_k * 1.5))
```

With `current_candidate_k=120` and the default
`RAG_FALLBACK_EXPANDED_CANDIDATE_K=50`, the result is 50. Existing unit cases
cover only `current_candidate_k <= max_candidate_k`, so they do not exercise
this supported runtime relationship.

## Workaround

Configure `RAG_FALLBACK_EXPANDED_CANDIDATE_K` no lower than the normal
`RAG_CANDIDATE_K`. To retain the intended 1.5x expansion, configure the ceiling
at or above the expected expanded value. This avoids the observed shrink but
does not correct the implementation invariant.

## Resolution Criteria

- A Level 2 completed round never uses a candidate count below the completed
  prior round solely because the configured expansion ceiling is lower.
- Tests cover `current_candidate_k > max_candidate_k` as well as equality and
  ordinary capped growth.
- Trace describes the effective action accurately and does not label a reduced
  pool as a relaxation.
- A real or integration reproduction confirms that Level 2 preserves or
  enlarges the candidate pool under the formerly failing configuration.

## Resolution

The active `rag-multilevel-fallback` change now defines the reused setting as
an expansion ceiling, not permission to shrink a completed prior pool. The
effective Level 2 value is the larger of the completed prior value and the
capped 1.5x growth target. A focused regression covers the observed
`current_candidate_k=120`, `max_candidate_k=50` relationship and requires an
effective value of 120.

The code and deterministic graph path are corrected. The issue remains
`mitigated` until a live E2E rerun records `120 → 120` (or a genuine increase)
under the formerly failing configuration.
