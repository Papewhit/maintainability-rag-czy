---
document_type: validation_report
validation_id: VAL-RAG-INTENT-001
status: partial
scope: evaluation.rag.intent_routing
source_commit: d77ae8f97e372657b5aa69ba178b2cc6e04581fd
source_fingerprint: sha256:1a2dbc442e46729a1db1122c99d8b7e1d52231e5d1c57a2f3b15d9d34553b552
executed_at: 2026-07-14T15:33:56Z
source_findings: [RAG-INTENT-F012, RAG-INTENT-F013]
supersedes: []
---

# RAG intent routing evaluation and rollout gate

## Scope

This report validates the repeatable evaluation contracts for intent classification, comprehensive parallel retrieval cost/quality comparison, terminology-to-rerank boundaries, and rollout observability. It does not claim that the current FAST_MODEL or production retrieval infrastructure meets an activation threshold.

The bound source fingerprint normalizes line endings to LF and covers the intent/query-plan implementation, graph and postprocess policies, rerank boundary, runtime configuration, evaluation/observability code, OpenSpec design/spec, and both annotated intent datasets. `source_commit` is the committed implementation anchor at the time of this working-tree validation; the fingerprint is the stronger binding for the reviewed source set and must be regenerated after any covered file changes.

## Method

### Intent classification

`tests/eval/data/intent_routing/` contains exactly 100 unique annotated queries:

- 70 `precise_lookup` samples covering `filter`, `boost`, and `none` scope expectations plus paragraph, table, step-list, and figure granularity;
- 30 `comprehensive_analysis` samples covering design reuse, comparison, procedure synthesis, and general analysis with human reference dimensions.

`backend/evaluation/intent_routing.py` validates the sample schema and reports intent accuracy, plan validity, and 1–5 sub-query quality. Scope-bearing synthetic samples use the reviewed `filename_registry.json`; its fingerprint is written into each real-model report so filename resolution cannot silently run against an empty or unrelated registry. The real-model path uses the current `IntentClassifier`; comprehensive sub-queries are scored by a separate structured-output LLM judge against the annotated reference dimensions. Reports are written to ignored runtime output under `eval/intent/{date}_{model}.json`.

The deterministic test path verifies the evaluator contract only and always reports `partial`; it is not model-quality evidence. A release evaluation requires:

```powershell
$env:RAG_INTENT_EVAL_RUN_REAL_MODEL = "1"
uv run pytest tests/eval/rag/test_intent_classifier_eval.py -m "eval and requires_models" -q
```

### Comprehensive cost/quality comparison

`backend/evaluation/comprehensive_routing.py` executes and compares paired cases under `quality_first_v1` and the evaluation-only `eval_no_crossencoder_v1`. The harness rejects unpaired case IDs or differing source/config fingerprints. It aggregates:

- sub-query and retrieval-branch buckets;
- baseline hit and final-selection rates;
- dense/sparse embedding, hybrid/split search, and CrossEncoder pair counts;
- branch, merged, and final candidate pools;
- per-stage and end-to-end P50/P95;
- process RSS and CUDA peak memory;
- stage error, degradation, and budget-exhaustion rates;
- generated-branch representation, citation validity, and answer quality.

The opt-in real runner classifies the 30 comprehensive samples once, reuses the same generated plan for both profiles, runs the same graph node sequence and source/config fingerprint, and writes an ignored JSON comparison under `eval/comprehensive-intent-routing/`. Citation validity is the fraction of generated `[filename p.page]` citations that match a retrieved document and page; an uncited answer scores zero. It is distinct from reference-qrel citation coverage. The source fingerprint covers the answer evaluator, while the config fingerprint binds intent/answer/judge models, Milvus collection and explicit release corpus/index fingerprints, embedding model, BM25 state path and content hash, and retrieval runtime configuration.

```powershell
$env:RAG_COMPREHENSIVE_EVAL_RUN_REAL = "1"
$env:RAG_EVAL_MILVUS_INDEX_VERSION = "<release-index-version>"
$env:RAG_EVAL_CORPUS_FINGERPRINT = "<release-corpus-fingerprint>"
uv run python tests/eval/rag/run_comprehensive_intent_routing_evaluation.py
```

### Terminology and monitoring

The rerank query contract accepts only `query_term_matches`, populated from terminology `term_matches` after structural query preparation. Legacy `query_entities` input is ignored and omitted from trace/API schemas. Chunk `entity_types` and `term_match_count` remain available; the latter is explicitly measured as all terminology matches in a chunk, not query-specific exact matches. The response keys `entity_metadata_score_applied`, `entity_type_coverage`, and `entity_match_density` remain as wire-compatible historical terminology names; they do not represent semantic entity matching.

`backend/rag/observability.py` provides pure aggregation over supplied `rag_trace` records into classifier P50/P95, failure/fallback rates, intent share, comprehensive profile and fan-out buckets, baseline rates, retrieval/rerank costs, budget exhaustion, and merge/postprocess/end-to-end P50/P95. This change does not connect a persisted trace reader, exporter, dashboard, or alerting sink.

## Inputs

- Source commit anchor: `d77ae8f97e372657b5aa69ba178b2cc6e04581fd`
- Source fingerprint: `sha256:1a2dbc442e46729a1db1122c99d8b7e1d52231e5d1c57a2f3b15d9d34553b552`
- Dataset: 100 annotated intent samples (70 precise / 30 comprehensive)
- Profiles: `quality_first_v1` and `eval_no_crossencoder_v1`
- Environment: Windows, Python 3.12; no FAST_MODEL credentials, Milvus release corpus, or answer/judge model were configured for this run

## Results

| Evidence | Result | Interpretation |
| --- | --- | --- |
| RAG evaluation suite | 63 passed, 1 real-model test skipped, 10 parameterized subtests passed | Harness, schema, pairing, aggregation, report path, resource/config binding, and historical-evidence checks work; no real-model quality claim |
| Terminology boundary and related postprocess tests | 77 passed | Terminology signals remain consumed; semantic entity compatibility input is removed |
| RAG + API + evaluation unit suites | 385 passed | Default-disabled compatibility and terminology-compatible trace contracts have no unit regression |
| Real FAST_MODEL intent baseline | Not executed | Credentials were unavailable |
| Paired real retrieval profile comparison | Not executed | Model credentials and release retrieval infrastructure were unavailable |

Status is `partial`. The implementation and repeatable evidence paths are present, but this run cannot answer how much answer/citation quality `quality_first_v1` gains over the ablation or how much production latency/resource cost it adds.

## Activation thresholds

Numeric thresholds are intentionally unset until a reviewed real-model and real-retrieval baseline exists. A deterministic substitute or synthetic trace must not establish them. The first release-candidate run must record proposed thresholds for:

- intent accuracy overall and false-comprehensive rate on the 70 precise samples;
- plan validity and mean LLM-judged sub-query quality;
- generated-branch representation and citation/answer quality deltas versus ablation;
- classifier, merge/postprocess, and end-to-end P50/P95;
- embedding/search calls, rerank pairs, CPU/GPU peaks, error/degradation, and budget exhaustion.

Until those thresholds are reviewed and met, `RAG_INTENT_CLASSIFIER_ENABLED` remains `false`; `eval_no_crossencoder_v1` remains evaluation-only. Enabling by default belongs to a separate small change with this report updated to `passed` or a succeeding passed report.

## Rollout gate

After a passed evaluation, rollout is controlled outside the graph by deployment traffic allocation:

1. Keep the default off and verify the compatibility cohort against the existing precise path.
2. Enable intent routing for 10% of RAG traffic. Compare enabled and disabled cohorts by the metrics above, bucketed by intent, sub-query count, retrieval-branch count, and profile.
3. Hold or roll back immediately if an approved quality, latency, resource, failure, fallback, or budget threshold is breached. Disabling the flag restores the compatibility `PreciseQueryPlan` path without a model call.
4. Increase traffic only after the 10% cohort has sufficient reviewed samples and no threshold breach; repeat the same gate at each deployment-defined step before full traffic.

Multi-turn retrieval is not part of this rollout. Any future multi-turn enhancement requires an independent design and A/B evaluation. Sub-query adjustment remains fallback Level 1 work.

## Limitations

- No model or retrieval production-capacity evidence was available in this environment.
- CPU RSS sampling is process-level; concurrent unrelated work must be controlled during release runs.
- CUDA peak memory is reported only when CUDA is available.
- Citation validity measures consistency with retrieved evidence, not recall against human citation qrels; answer quality remains unavailable if the configured answer or judge model does not run.
- Thresholds and production-profile acceptance remain unresolved by design, so default enablement is blocked.

## Findings

`RAG-INTENT-F012` records that the prior postprocess report is now historical because its source fingerprint no longer matches this implementation. The unresolved current evaluation evidence is an explicit activation gate owned by this OpenSpec change and is preserved here as a typed partial validation result.
