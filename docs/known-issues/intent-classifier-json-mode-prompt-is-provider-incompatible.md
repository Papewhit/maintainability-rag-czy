---
document_type: known_issue
issue_id: KI-RAG-0017
status: resolved
scope: rag.intent.provider-compatibility
severity: high
first_confirmed: 2026-07-19
last_verified_commit: bbb244973037bc357d9bf71edf412d07a5081244
last_verified_date: 2026-07-21
source_findings: []
---

# Intent classifier JSON mode prompt is incompatible with the active provider

## Observed Behavior

With `RAG_INTENT_CLASSIFIER_ENABLED=true` and
`RAG_INTENT_CLASSIFIER_MODEL=qwen3.6-plus`, every inspected classifier attempt
failed before producing a decision. LangSmith recorded HTTP 400
`InternalError.Algo.InvalidParameter`: messages must contain the word `json` to
use `response_format` type `json_object`.

`IntentClassifier.classify()` uses
`model.with_structured_output(IntentDecision)`. With the active OpenAI-compatible
provider, that binding selected JSON-object response formatting. The classifier
system prompt asks for schema-constrained output but never contains the literal
word `json`, so the provider rejects the request.

The exception is caught by `parse_intent()`. The chat request therefore
continues with a rule-built precise plan, `intent_confidence=0`,
`intent_fallback_to_rules=true`, and the provider error stored in
`intent_llm_error`. Enabling the switch and configuring a model does not, in
this environment, make LLM intent classification effective.

## Impact

Precise/comprehensive routing silently degrades to the compatibility rules on
every attempted classifier call. The UI currently omits those intent fields,
so a user sees neither the repeated 400 nor the rules fallback. LangSmith, in
turn, presents the classifier failure as an independent root trace because of
[KI-RAG-0016](langsmith-chat-turns-fragment-across-root-traces.md).

This can materially alter the query plan and downstream fallback behavior even
though the final chat request returns HTTP success.

## Evidence or Reproduction

On 2026-07-19, the authenticated LangSmith project showed repeated failures for
"根据知识库，什么是统一源图？" and "配置管理系统出库如何触发". The selected
11:04:06 classifier trace contained:

```text
BadRequestError: 'messages' must contain the word 'json' in some form, to use
'response_format' of type 'json_object'
```

Its trace tree contained `RunnableSequence -> ChatOpenAI qwen3.6-plus`, had no
output, and showed the current intent system prompt without a JSON-mode
instruction. `backend/rag/intent.py` confirms the structured-output call and
the exception-to-rules degradation path.

## Workaround

For revisions before the resolution, do not infer successful intent
classification from the enable switch alone. Inspect
`intent_fallback_to_rules`, `intent_llm_error`, and `intent_confidence`, or use
a model/provider/structured-output combination already proven compatible.

## Resolution

The classifier system message now explicitly requires a schema-conformant
JSON object and lists the allowed enum values and intent-specific field
conditions. `with_structured_output(IntentDecision)` remains the only schema
binding and validation path; the implementation does not add a permissive
parser or a second handwritten response contract.

On 2026-07-21, the opt-in integration smoke called the configured
`qwen3.6-plus` endpoint and returned a schema-valid, non-fallback intent result:

```powershell
$env:RAG_INTENT_PROVIDER_SMOKE='1'
$env:RAG_INTENT_PROVIDER_SMOKE_TIMEOUT_SECONDS='90'
Remove-Item Env:ALL_PROXY -ErrorAction SilentlyContinue
Remove-Item Env:all_proxy -ErrorAction SilentlyContinue
uv run pytest tests/integration/rag/test_intent_classifier_provider.py -q
```

The result was `1 passed`; the deterministic classifier/evaluation suite was
`31 passed, 1 skipped`.
The two proxy variables were cleared only for this process because the current
workstation advertises a SOCKS proxy without the optional HTTPX SOCKS package;
the configured HTTP(S) proxy remained available.
The relaxed smoke timeout isolates provider/schema compatibility and is not a
latency or activation gate. Runtime defaults remain disabled, and the later
activation development runs must separately freeze model identity and prove an
acceptable classifier timeout. Frontend progress visibility remains governed
by [KI-RAG-0012](rag-progress-ui-omits-intent-and-answer-handoff.md), while
runtime trace already distinguishes model success from rules fallback.

A subsequent full-chain E2E run confirmed that this distinction matters.
LangSmith run `019f82cb-b723-7852-8bed-b62b25c6a721` no longer failed with the
former JSON-mode 400, but `qwen3.6-plus` exceeded the E2E 5-second HTTP read
timeout and correctly fell back to a precise rules plan. That result does not
reopen this JSON-request issue; it blocks activation `model_success` for the
current E2E identity and is routed to
`openspec/changes/rag-intent-routing-activation/` as
`INTENT-PROVIDER-F001`.

Provider comparison also exposed an additional conditional-schema ambiguity:
`qwen-flash` initially emitted the precise enum string `"none"` where a
comprehensive decision requires JSON `null`. The prompt now makes that
distinction explicit, after which the strict real-provider smoke passed under
the 5-second invocation deadline. This is candidate evidence only, not a frozen
FAST_MODEL choice or latency gate. The independent inability of the outer
thread timeout to cancel an in-flight provider request is tracked by
[KI-RAG-0021](intent-classifier-timeout-cannot-cancel-provider-call.md).

## Resolution Criteria

- The configured classifier completes against every supported provider using
  a provider-compatible structured-output method and prompt.
- A successful run records a non-fallback intent decision and schema-valid
  output; an incompatible combination is detected before or clearly at
  runtime rather than silently looking enabled.
- Tests cover the active OpenAI-compatible provider's JSON-object constraint
  without defining a second intent contract.
- The frontend/runtime diagnostics make classifier degradation distinguishable
  from a successful classifier decision.
