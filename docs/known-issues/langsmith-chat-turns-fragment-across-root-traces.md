---
document_type: known_issue
issue_id: KI-RAG-0016
status: open
scope: rag.observability.tracing
severity: medium
first_confirmed: 2026-07-19
last_verified_commit: 5e49a4669f78dbaddf00ee97f1f76c7960bba419
last_verified_date: 2026-07-19
source_findings: []
---

# One chat turn can fragment across multiple LangSmith root traces

## Observed Behavior

The LangSmith project `superhermes-rag-full-chain-e2e` no longer consistently
shows one root trace for one UI chat turn. For the 2026-07-19 11:00 run of
"根据知识库，什么是统一源图？", the Traces view showed three independent
roots:

- a RAG `LangGraph` run starting at 11:00:30 and lasting 7.54 seconds;
- a failing intent-classifier `RunnableSequence` starting at 11:00:31 and
  lasting 0.20 seconds;
- the final-answer `ChatOpenAI` run starting at 11:00:38 and lasting 8.67
  seconds.

A later optional-tool turn appeared as one 20.43-second agent `LangGraph` root,
but its 0.27-second intent-classifier `RunnableSequence` still appeared as a
separate root. Trace topology therefore changes with the RAG execution policy
and does not provide a stable request-level envelope.

## Impact

Operators cannot directly read end-to-end latency, parent/child ordering, or
one authoritative error state for a UI request. Runs with the same input and
nearby timestamps must be manually correlated, which is ambiguous when users
retry the same question. Dashboards can also count one chat turn as several
unrelated traces.

The fragmented classifier run may be an expected degraded child operation, but
as a root it resembles an independent failed request. This obscures the fact
that the main RAG path caught the error and continued with rule-based intent.

## Evidence or Reproduction

- `backend/chat/agent.py::chat_with_agent_stream()` executes forced-preload RAG
  with `asyncio.to_thread()` before starting the answer worker. There is no
  explicit request-level traced runnable around both phases.
- `backend/chat/rag_execution.py::stream_answer_with_rag_context()` calls the
  final `model_instance.astream()` directly for forced preload, outside the RAG
  graph root.
- `backend/rag/intent.py::IntentClassifier.classify()` submits the structured
  model call to a process-global `ThreadPoolExecutor` without copying the
  active tracing context, so the classifier chain is recorded at root depth.
- The retained LangSmith Traces view displayed the independent roots and the
  selected classifier run reported `ls_run_depth=0`.

The shell's LangSmith client credentials were stale and returned 401 during
this investigation, so the evidence was read from the user's authenticated
Chrome session rather than reconstructed through a second API client.

## Workaround

Correlate adjacent roots by exact input and start time, then verify the final
result against the persisted session RAG trace. Treat a root classifier error
as a potentially degraded sub-operation until `intent_fallback_to_rules` and
the main chat result are checked.

## Resolution Criteria

- Every UI chat turn has one durable request-level root trace carrying the
  application session/turn identity.
- Forced-preload RAG, intent classification, answer generation, and optional
  tool execution appear beneath that root with preserved parentage.
- A classifier failure remains visible as a child error while the root records
  whether the request degraded successfully or failed overall.
- End-to-end latency and phase latency can be measured without timestamp-based
  manual correlation.
