---
document_type: finding_ledger
change: rag-multilevel-fallback-activation
last_verified_commit: fd9fb5ea22ecdbf9fe28b9b4915762b1cc0f4267
last_verified_date: 2026-07-21
---

# Change Findings

## RAG-FB-ACT-F001

- Kind: evaluation_result
- Primary scope: evaluation.rag-confidence
- Evidence status: confirmed
- Observation: Multiple real-model traces have routed relevant final evidence toward Level 3 when `weak_margin_and_root` fired. In run `019f8374-f02f-7460-9850-10663866f655`, all five final documents represented both generated subqueries, yet Level 2 recorded `weak_margin_and_root` together with `low_score_and_margin` before `levels_exhausted` reached Level 3. An earlier run recorded `weak_margin_and_root` alone while presenting high-score corroborating evidence.
- Inference: `weak_margin_and_root` has insufficient demonstrated specificity as a standalone activation trigger. The new run cannot establish the specificity of `low_score_and_margin` because both reasons co-occurred; that signal may still be strong and must be evaluated independently.
- Decision: Add signal-stratified and ablation evidence to the fallback activation gate. Do not activate `weak_margin_and_root` as a standalone trigger unless it passes a frozen specificity gate; otherwise disable or retune that reason in the activation candidate. Preserve and assess `low_score_and_margin` separately rather than weakening both signals together.
- Residual risk: Until the signal-specific gate is complete, the reference confidence/fallback path remains disabled and the two co-occurring reasons cannot be assigned causal responsibility from this run alone.
- Evidence: LangSmith run `019f8374-f02f-7460-9850-10663866f655` structured Level 3 input; prior trace and measurements retained in `docs/known-issues/rag-confidence-rejects-corroborating-evidence.md`.
- Disposition: known_issue
- Disposition target: docs/known-issues/rag-confidence-rejects-corroborating-evidence.md
- Resolution evidence: The known issue now separates the two signals, and the owning activation design, spec, and tasks require signal-specific evaluation before enabling the fallback reference path.
