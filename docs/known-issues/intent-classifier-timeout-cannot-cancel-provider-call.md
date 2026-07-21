---
document_type: known_issue
issue_id: KI-RAG-0021
status: open
scope: rag.intent.timeout
severity: high
first_confirmed: 2026-07-21
last_verified_commit: bbb244973037bc357d9bf71edf412d07a5081244
last_verified_date: 2026-07-21
source_findings:
  - INTENT-PROVIDER-F002
---

# Intent classifier timeout cannot cancel an in-flight provider call

## Observed Behavior

`IntentClassifier.classify()` submits synchronous structured-output I/O to a
`ThreadPoolExecutor` and waits with `future.result(timeout=...)`. When that wait
expires, `future.cancel()` cannot stop a thread that has already started. The
classifier returns a rules fallback, but its semaphore slot is released only
when the provider future eventually finishes.

In a controlled `qwen3.6-flash` smoke with a 5-second outer deadline, the
runtime reported `intent classifier timed out after 5.000s` and fell back, while
the pytest process did not complete until 29.57 seconds.

## Impact

The configured timeout bounds when the request path can fall back, not how long
the provider work or classifier capacity remains occupied. Several concurrent
slow calls can fill all four intent slots, after which later classifications
degrade immediately with `intent classifier capacity exhausted`. A successful
fallback therefore is not evidence of bounded provider resource use.

## Evidence or Reproduction

Run the opt-in provider smoke against a model whose response exceeds the outer
deadline:

```powershell
$env:RAG_INTENT_PROVIDER_SMOKE='1'
$env:RAG_INTENT_PROVIDER_SMOKE_MODEL='qwen3.6-flash'
$env:RAG_INTENT_PROVIDER_SMOKE_TIMEOUT_SECONDS='5'
uv run pytest tests/integration/rag/test_intent_classifier_provider.py -vv -s
```

The code path is visible in `backend/rag/intent.py`: the provider HTTP timeout
and `future.result()` use the same numeric setting, but only the provider future
completion callback releases `_INTENT_SLOTS`.

## Workaround

Keep the classifier default disabled until activation runs freeze and verify a
model/provider identity with acceptable latency and fallback rate. Operators
should inspect both timeout and capacity-exhaustion traces. Do not interpret the
outer timeout as cancellation of the in-flight provider request.

## Resolution Criteria

- A timed-out classifier call no longer retains a capacity slot beyond a
  documented, bounded cancellation/cleanup interval.
- Tests cover timeout, provider completion after timeout, slot recovery, and
  concurrent saturation without relying on process exit behavior.
- The runtime and activation report distinguish request-path fallback latency
  from provider-work lifetime and cold model-construction time.
