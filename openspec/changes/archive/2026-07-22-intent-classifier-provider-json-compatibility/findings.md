---
document_type: finding_ledger
change: intent-classifier-provider-json-compatibility
last_verified_commit: bbb244973037bc357d9bf71edf412d07a5081244
last_verified_date: 2026-07-21
---

# Change Findings

## INTENT-PROVIDER-F001

- Kind: evaluation_result
- Primary scope: rag.intent.activation
- Evidence status: confirmed
- Observation: LangSmith run `019f82cb-b723-7852-8bed-b62b25c6a721` used the full-chain E2E identity `qwen3.6-plus` with a 5-second classifier timeout. The structured-output call no longer received the former JSON-mode HTTP 400, but failed after 5.11 seconds with `openai.APITimeoutError`; the downstream graph correctly fell back to a precise rules plan. A controlled `qwen3.6-flash` comparison also missed the 5-second outer deadline. After the prompt's JSON-null condition was made explicit, a controlled `qwen-flash` smoke returned a schema-valid non-fallback decision under the 5-second invocation deadline, although its cold classifier measurement including model construction was 7.20 seconds.
- Inference: Request/schema compatibility is repaired, but the current `qwen3.6-plus` E2E identity cannot supply activation `model_success` at the configured budget. `qwen-flash` is only a development candidate until repeated development and frozen-gate runs establish its quality and latency distribution.
- Decision: Keep the classifier default disabled. Freeze the classifier model, provider, timeout semantics, cold/warm measurement boundary, and gate thresholds in `rag-intent-routing-activation`; require non-fallback `model_success` in the normal gate and do not substitute the relaxed 90-second compatibility smoke.
- Residual risk: A single `qwen-flash` success does not establish P95 latency, intent quality, model stability, or acceptable cold-start behavior.
- Evidence: User-supplied E2E traceback; LangSmith run `019f82cb-b723-7852-8bed-b62b25c6a721`; `.env.rag-full-chain-e2e.example`; real-provider smoke runs for `qwen3.6-plus`, `qwen3.6-flash`, and `qwen-flash`; `backend/rag/intent.py::IntentClassifier.classify`.
- Disposition: change
- Disposition target: openspec/changes/rag-intent-routing-activation/
- Resolution evidence: The activation design and tasks now bind normal-gate success to the exact frozen model/budget identity, include cold/warm timing boundaries, and retain default-off on fallback.

## INTENT-PROVIDER-F002

- Kind: behavior_defect
- Primary scope: rag.intent.timeout
- Evidence status: confirmed
- Observation: `IntentClassifier.classify()` runs synchronous provider I/O in a `ThreadPoolExecutor`, waits with `future.result(timeout=...)`, and calls `future.cancel()` after an outer timeout. Python cannot cancel an already-running thread; the semaphore slot is released only by the future's completion callback. In the controlled `qwen3.6-flash` 5-second smoke, the classifier returned a rules fallback for the outer timeout while the pytest process completed only after 29.57 seconds.
- Inference: The timeout protects request-path fallback latency but is not a hard cancellation boundary for provider work. Repeated slow calls can continue consuming the four classifier slots and make later requests fail with capacity exhaustion.
- Decision: Preserve the existing fallback behavior in this JSON-compatibility change and document the cancellation/capacity defect separately.
- Residual risk: Slow or wedged provider calls may outlive their user-visible fallback and temporarily exhaust intent capacity.
- Evidence: `backend/rag/intent.py::IntentClassifier.classify`; controlled `qwen3.6-flash` provider smoke with `RAG_INTENT_PROVIDER_SMOKE_TIMEOUT_SECONDS=5`; pytest failure and elapsed-time output on 2026-07-21.
- Disposition: known_issue
- Disposition target: docs/known-issues/intent-classifier-timeout-cannot-cancel-provider-call.md
- Resolution evidence: KI-RAG-0021 records the behavior, operational impact, workaround, and closure criteria.

## INTENT-PROVIDER-F003

- Kind: behavior_defect
- Primary scope: rag.intent.provider-compatibility
- Evidence status: confirmed
- Observation: In a controlled `qwen-flash` structured-output call, the model returned `scope_hint="none"` for a comprehensive decision even though `IntentDecision` requires `scope_hint` to be JSON null for that intent. Schema validation correctly rejected the response and the runtime fell back to rules.
- Inference: The prompt's earlier wording did not distinguish the allowed precise enum string `"none"` strongly enough from JSON null in the comprehensive conditional contract.
- Decision: State explicitly that comprehensive `scope_hint` must be JSON null and is not the string `"none"`; retain strict `IntentDecision` validation rather than coercing provider output.
- Residual risk: none
- Evidence: Controlled loose-schema reproduction showing `{"intent":"comprehensive_analysis","scope_hint":"none",...}`; updated prompt unit assertion; successful strict-schema `qwen-flash` 5-second provider smoke.
- Disposition: closed_in_place
- Disposition target: null
- Resolution evidence: `backend/rag/intent.py::INTENT_SYSTEM_PROMPT`, `tests/unit/backend/rag/pipeline/test_intent_classifier.py`, and `tests/integration/rag/test_intent_classifier_provider.py`; deterministic suite `31 passed, 1 skipped` and real-provider smoke `1 passed` on 2026-07-21.
