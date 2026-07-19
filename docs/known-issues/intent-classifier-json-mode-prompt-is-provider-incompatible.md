---
document_type: known_issue
issue_id: KI-RAG-0017
status: open
scope: rag.intent.provider-compatibility
severity: high
first_confirmed: 2026-07-19
last_verified_commit: 5e49a4669f78dbaddf00ee97f1f76c7960bba419
last_verified_date: 2026-07-19
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

Do not infer successful intent classification from the enable switch alone.
Inspect `intent_fallback_to_rules`, `intent_llm_error`, and
`intent_confidence`. For validation that requires true classifier output, use
a model/provider/structured-output combination already proven compatible, or
disable the classifier and label the run as rules-only.

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
