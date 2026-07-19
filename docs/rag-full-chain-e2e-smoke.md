# Full-chain RAG E2E smoke run

This runbook exercises the implemented standard RAG path with the
validation-only `.env.rag-full-chain-e2e.example` overlay. It is a functional
reachability check, not a production configuration recommendation, latency
SLO, threshold evaluation, or completion evidence for real-model tuning.

## Scope

The overlay enables the composable standard path: v4 document indexing,
dense+sparse retrieval, layered candidates, rerank and score fusion, intent
routing, QueryPlan, scope/anchor consumers, confidence, Level 1/2 fallback,
Level 3 delivery, citation verification, and frontend trace events.

Deep mode and reserved legacy routing flags remain off because they are
alternate or inert paths rather than additional stages in the standard L0-L3
graph. The base `.env` remains the authority for secrets, model endpoints,
database, Redis, and Milvus connectivity.

## Start the backend with the overlay

Run this in the same PowerShell process that will start the backend:

```powershell
Get-Content -LiteralPath .env.rag-full-chain-e2e.example | ForEach-Object {
    $e2eLine = $_.Trim()
    if ($e2eLine -and -not $e2eLine.StartsWith('#')) {
        $e2eName, $e2eValue = $e2eLine -split '=', 2
        [Environment]::SetEnvironmentVariable($e2eName, $e2eValue, 'Process')
    }
}

# A new isolated collection name is configuration only; initialize its empty
# schema before the backend can service any registry or retrieval read.
uv run python -c "from backend.infra.vector_store.milvus_client import MilvusManager; MilvusManager().init_collection()"

uv run uvicorn backend.app:app --host 127.0.0.1 --port 8000 --reload
```

Process environment variables take precedence over values loaded from
`.env`. Restart the backend after any overlay change because several modules
read configuration during import.

Verify the restarted process reports LangSmith project
`superhermes-rag-full-chain-e2e`, profile `v4_full`, and collection
`embeddings_collection_v4_full_e2e`. Seeing project `default` or profile
`v3_quality` means the running backend did not inherit this overlay.

The current runtime still requires `RAG_FALLBACK_ENABLED=true`, so deprecation
warnings for that master switch are expected during the smoke run. LangSmith
tracing is enabled under project `superhermes-rag-full-chain-e2e`; the base
`.env` must provide a valid `LANGSMITH_API_KEY` and endpoint.

`LANGCHAIN_TRACING_V2=true` is the historical LangChain name for enabling the
v2 LangSmith callback tracer. In the installed LangSmith/LangChain versions,
`LANGSMITH_TRACING=true` is the canonical equivalent and already enables the
same tracer; setting both is redundant but does not create two tracers because
the callback manager avoids adding a second `LangChainTracer`. It does not
change trace parentage or merge multiple root runs into one request tree.

## Build isolated evidence

The overlay selects all three authorities explicitly:

- `RAG_INDEX_PROFILE=v4_full`
- `MILVUS_COLLECTION=embeddings_collection_v4_full_e2e`
- `BM25_STATE_PATH=data/bm25_state_v4_full_e2e.json`

`MilvusManager.init_collection()` is idempotent. Run it once with the overlay
active before the first query. The configuration value itself does not create
the collection, and retrieval reads do not currently initialize a missing
collection. The frontend knowledge-base list/upload paths do initialize it,
but relying on that UI order makes the E2E path nondeterministic.

Do not reuse chunks uploaded under `v3_quality` or another collection. With
the overlay active, upload `tests/fixtures/documents/SCM优化方案.pdf` again and
wait until its terminal state is completed. The v4 profile is required for
table-aware chunks and terminology metadata. The isolated collection and
BM25 file avoid mixing chunks or sparse statistics from another profile.

## Run the smoke questions

First run the deterministic forced-preload path by attaching the uploaded
file to the turn and asking:

```text
根据已上传的《SCM优化方案》，统一源图是什么？
```

Then run the global unified-execution path without an attachment:

```text
根据知识库，统一源图是什么？
```

The word `根据`/`知识库` is intentional. The bare question
`统一源图是什么？` is still eligible for the optional-tool policy; enabling
unified execution does not force the agent to call RAG for a query with no
attachment and no document-intent marker.

For a table-delivery check, ask a question that explicitly targets the table
following the `2.2 交付物` paragraph. Treat the result as diagnostic evidence:
the v4 profile makes table chunks indexable, but this smoke run does not by
itself prove table selection or answer completeness.

## Inspect the trace

While the streamed answer is active, open browser developer tools and inspect
the `POST /chat/stream` response. The SSE stream should include zero or more
`rag_step` events followed by a final `trace` event. A successful Level 0
answer is allowed to have no fallback level events; Level 1 and Level 2 appear
only when their router signals select them.

After a page refresh, inspect `GET /sessions/<session_id>` in the Network tab.
The authenticated response persists `rag_trace` on the assistant message even
though transient `rag_step` events are not reconstructed. This is also the
human-readable source for comparing `query_plan_type`, confidence reasons,
attempted levels, candidate strategy, effective scope, timings, stage errors,
and final fallback level.

## Minimal acceptance record

Record the following without treating a single route as proof of every
branch:

- backend commit and overlay file hash;
- session id and exact question;
- document terminal ingestion state and active profile/collection;
- ordered `rag_step` events visible before answer completion;
- persisted `rag_trace` after refresh;
- LangSmith intent/retrieval/model spans, including the interval between the
  final RAG event and the first answer token;
- effective intent model, confidence, rules-fallback flag, and classifier
  error; `RAG_INTENT_CLASSIFIER_ENABLED=true` alone does not prove that the
  model executed;
- final source snippets, including whether the `2.2 交付物` table is present;
- browser responsiveness during repeated fallback.

M8.5 remains a human UX validation item until this evidence is actually
collected. M10.3-M10.5 still require a real query set, metrics, and
data-driven tuning rather than this smoke configuration.
