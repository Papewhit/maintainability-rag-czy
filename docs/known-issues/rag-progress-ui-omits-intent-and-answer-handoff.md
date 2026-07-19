---
document_type: known_issue
issue_id: KI-RAG-0012
status: open
scope: rag.observability
severity: medium
first_confirmed: 2026-07-19
last_verified_commit: 5e49a4669f78dbaddf00ee97f1f76c7960bba419
last_verified_date: 2026-07-19
source_findings: []
---

# RAG progress UI omits intent and answer-generation handoff

## Observed Behavior

During a manual full-chain UI run, cold startup was visibly slow. LangSmith
showed retrieval taking approximately 3-4 seconds, which was acceptable for
the run, while answer-model output took approximately 5-15 seconds with
substantial variation. After the final visible RAG event and before answer
text began streaming, the UI showed a noticeable interval with no new stage
or progress information.

The same run had `RAG_INTENT_CLASSIFIER_ENABLED=true`. The persisted RAG trace
contained intent-parse output, but the frontend did not show whether the
classifier ran successfully, which plan type it selected, how confident it
was, or whether it fell back to rules.

In session `session_1784426649833`, this missing distinction was material:
the trace recorded `intent_classifier_enabled=true` but also
`intent_confidence=0`, `intent_fallback_to_rules=true`, and
`intent_llm_error="intent classifier model is not configured"`. The active
`.env` had neither `FAST_MODEL` nor `RAG_INTENT_CLASSIFIER_MODEL`, so the
enabled switch did not produce a classifier model call.

A later run configured `RAG_INTENT_CLASSIFIER_MODEL=qwen3.6-plus`, but the
classifier still degraded: the provider rejected the structured-output call
because its JSON-object mode requires the messages to contain the word `json`.
That provider-compatibility defect is tracked separately as
[KI-RAG-0017](intent-classifier-json-mode-prompt-is-provider-incompatible.md);
the normal UI also failed to distinguish this second degraded state.

## Impact

Users cannot distinguish active answer generation from a stalled request
during model time-to-first-token. Operators also cannot verify intent-routing
activation from the normal UI, so configuration mistakes, classifier fallback,
and a valid precise/comprehensive decision look the same.

The observed 5-15 second model interval is not yet attributed to one cause. It
may include upstream model TTFT, prompt size, provider variance, or agent/tool
transition overhead; the current evidence does not justify choosing among
them.

## Evidence or Reproduction

With the full-chain E2E overlay active, submit a knowledge-dependent question
through the streaming UI and compare the visible timeline with LangSmith and
the persisted session trace.

The 2026-07-19 LangSmith trace for session `session_1784426649833` measured
21.74 seconds total: an initial agent model span of 3.39 seconds, the knowledge
tool at 3.23 seconds (initial retrieval 2.14 seconds plus Level 2 at 1.04
seconds), and the final answer model at 15.11 seconds. The root trace's
0.86-second first-token value belongs to the earlier agent/tool-decision
stream and does not represent final-answer TTFT.

- `backend/rag/pipeline.py::intent_parse_node()` writes intent fields into the
  trace but emits no `rag_step` event.
- `backend/chat/agent.py::chat_with_agent_stream()` forwards RAG steps and
  non-empty model content only. After retrieval, `_agent_worker()` enters
  `stream_answer_with_rag_context()` without emitting an answer-generation
  transition.
- `backend/chat/rag_execution.py::stream_answer_with_rag_context()` waits on
  `model_instance.astream()` for forced preload or `agent_instance.astream()`
  for optional tool execution. No SSE event is produced before the first
  non-empty answer chunk.
- `frontend/index.html` renders a small legacy subset of `ragTrace` and does
  not render `intent_classifier_enabled`, `intent_confidence`,
  `query_plan_type`, `intent_llm_ms`, `intent_fallback_to_rules`, or
  `intent_llm_error`.
- `frontend/script.js::currentThinkingLabel()` repeats the last RAG step label
  until content arrives, so the quiet handoff is not represented as a new
  phase.

## Workaround

Use the LangSmith project `superhermes-rag-full-chain-e2e` together with the
`POST /chat/stream` SSE response and persisted `GET /sessions/<session_id>`
trace. Compare intent timing, retrieval timing, model span start, and first
answer token rather than treating the last visible RAG step as request
completion.

## Resolution Criteria

- The UI exposes the effective intent result, including classifier versus
  rules fallback and precise versus comprehensive plan.
- The streaming timeline represents the transition from completed RAG
  delivery to active answer generation before the first text token arrives.
- Runtime evidence can separate retrieval completion, model request start,
  time-to-first-token, and answer completion without relying solely on an
  external tracing service.
