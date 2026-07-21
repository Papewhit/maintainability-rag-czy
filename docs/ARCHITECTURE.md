---
document_type: current_architecture
status: current
verified_commit: bbb244973037bc357d9bf71edf412d07a5081244
last_verified_date: 2026-07-21
authority: current-system-overview
---

# Ragtenance Architecture

## Purpose and Evidence Boundary

This is the single current-system overview for Ragtenance. Stable contracts live in `openspec/specs/`; rationale, known issues, enhancements, and reproducible evidence live in the governed locations defined by [Evidence Governance](evidence-governance.md).

**Editing rule:** Before changing this overview, apply the
[Architecture Content Boundary](evidence-governance.md#architecture-content-boundary);
keep findings, detailed issue evidence, workarounds, and intended work in their
governed authorities.

Current facts were verified against the working tree based on commit `bbb244973037bc357d9bf71edf412d07a5081244` on 2026-07-21 (Asia/Hong_Kong). **Default enabled** means active with unset environment; **implemented, default disabled** requires configuration; **planned** means an unimplemented OpenSpec change and is excluded from active flows.

## System Context and Components

```text
Browser UI -> HTTP/SSE -> FastAPI -> routers -> services
                                      |-> document ingestion
                                      |-> chat agent -> RAG runtime
                                      `-> PostgreSQL / Redis / Milvus / BM25 state
```

| Component | Responsibility | Implementation |
| --- | --- | --- |
| Application | FastAPI lifecycle, CORS, static UI | `backend/application/main.py` |
| HTTP | Router registry, auth, documents, sessions, chat/SSE | `backend/api.py`, `backend/routers/` |
| Services | Upload/delete and chat use cases | `backend/services/` |
| Chat | Tool invocation and answer workflow | `backend/chat/` |
| Documents | Parse, normalize, chunk, annotate | `backend/documents/` |
| RAG | Candidates, rerank, postprocess, trace | `backend/rag/` |
| Infrastructure | Embedding, database, cache, vector/parent storage | `backend/infra/` |

Canonical imports use `backend.*`. The backend root contains only `backend/__init__.py`, `backend/api.py`, `backend/app.py`, data, and real packages; legacy bare-module aliases are unsupported.

## Ingestion Pipeline

```text
DocumentService
  -> Adapter Registry
  -> DeepDoc Parse Adapter (PDF/DOCX; DOC registered but limited) or Excel Parse Adapter (XLS/XLSX)
  -> ParsedDocument
  -> Structure Normalizer
       heading tree -> list groups -> figure associations
       -> table validation -> nearby-block association
  -> Maintainability Chunker
  -> terminology scan (profile/table availability gated)
  -> parent/leaf split
       level 1/2 -> ParentChunkStore -> PostgreSQL (+ Redis read cache)
       level 3   -> dense+sparse embedding -> MilvusWriter -> Milvus
                   `-> incremental BM25 statistics
```

| Stage | Path | Contract |
| --- | --- | --- |
| Registry | `backend/documents/parse_adapter/registry.py` | Extension dispatch. Registered adapter failure is fatal; it does not fall back to the legacy loader. |
| DeepDoc | `backend/documents/parse_adapter/deepdoc/adapter.py` | PDF/DOCX parsing, OCR, layout, tables, figures, and parse metadata. `.doc` is registered but currently routed through the DOCX parser without legacy-DOC conversion ([KI-RAG-0005](known-issues/legacy-doc-ingestion.md)). |
| Excel | `backend/documents/parse_adapter/excel.py` | XLS/XLSX parsing into the common parsed model. |
| Parse contract | `backend/documents/parse_adapter/base.py` | Parsed document, blocks, tables, figures, parse metadata. |
| Normalizer | `backend/documents/normalizer/pipeline.py` | Deterministic structural enrichment. |
| Chunker | `backend/documents/chunker/step_chunker.py` | Maintainability-aware root/leaf emission. |
| Conversion | `backend/documents/parse_adapter/converters.py` | Runs normalizer/chunker, tables, figures, terminology. |
| Storage split | `backend/services/document_service.py` | Requires leaves; replaces filename/profile data; stores parents before leaves. |

Only an unregistered extension can reach the legacy `DocumentLoader`. Parse metadata persistence is best-effort; adapter parsing and leaf generation are required for upload success.

DeepDoc native-text parsing can lose a visible heading boundary or treat a
three-level numeric section heading as a list item, so section identity may not
reach chunks; see
[KI-RAG-0018](known-issues/deepdoc-native-text-can-merge-paragraphs-across-section-headings.md)
and
[KI-RAG-0019](known-issues/three-level-section-headings-are-treated-as-list-items.md).

The document list read immediately after an upload batch can temporarily omit
the most recent successful upload until refresh; see
[KI-RAG-0015](known-issues/document-list-can-lag-completed-multi-upload.md).

The administrator document endpoint is a capped, current-profile Milvus-leaf
projection rather than a durable upload inventory, and complete leaf-embedding
failure can still be reported as upload success; see
[KI-RAG-0020](known-issues/document-inventory-is-not-a-durable-upload-authority.md).

### Terminology and Rescan

`backend/rag/terminology/` owns the database-backed terminology table, Aho-Corasick matching, jieba dictionary, query preflight, and rescan. Inline scan writes `entity_types`, `term_match_count`, `term_matches`, and `protected_tokens` when `v4_full` is active and the table is loaded; otherwise it safely leaves empty signals.

`backend/rag/terminology/rescan.py` is intended to update existing Milvus and ParentChunkStore metadata without re-chunking. Its current implementation snapshots Milvus and BM25 state, but uses leaf IDs when reading/writing ParentChunkStore; that violates the level 1/2 parent-only contract and makes parent rollback unreliable. Treat rescan as unsafe for parent metadata until [KI-RAG-0003](known-issues/terminology-rescan-parent-contract.md) is resolved.

## Chunk Metadata and Storage Contract

`MaintenanceChunk` in `backend/documents/chunker/base.py` is the canonical model.

| Field | Contract |
| --- | --- |
| `chunk_id` | Stable display identity; non-legacy profiles may prefix storage identity. |
| `chunk_level` | `1` root, `2` optional middle/parent, `3` retrieval leaf. |
| `chunk_role` | `root` context or `leaf` retrieval unit. |
| `parent_chunk_id`, `root_chunk_id` | Immediate context parent and top evidence root. |
| `text`, `retrieval_text` | Evidence body and search-oriented leaf text. |
| section/anchor fields | `section_title`, `section_type`, `section_path`, `anchor_id`. |
| list fields | `list_group_id`, `list_order`, `parent_list_order`, `list_marker`, `list_level`, `list_complete`. Parent subgroup order is 1-based for step-chain repair. |
| table/figure fields | IDs and roles for structured evidence. |
| terminology fields | Entity types, match count, detailed matches, protected tokens. |
| `parent_extras` | Rich parent-only payload not guaranteed in Milvus. |

`ParentChunkStore` (`backend/infra/vector_store/parent_chunk_store.py`) stores level 1/2 context in PostgreSQL and caches reads in Redis. `MilvusWriter` (`backend/infra/vector_store/milvus_writer.py`) writes only level 3 leaves with dense and sparse vectors.

Step-chain repair uses two hops: query Milvus leaf metadata by `filename + index_profile + list_group_id + parent_list_order`, deduplicate `parent_chunk_id`, then hydrate complete parents from ParentChunkStore. Milvus is not the complete-parent authority.

## Embedding and Candidate Retrieval

`backend/infra/embedding.py` produces configured dense embeddings and BM25-style sparse vectors using jieba and persisted corpus statistics. `BM25_STATE_PATH` selects the JSON state. `RAG_INDEX_PROFILE` does not automatically change this path, so profile isolation requires an explicitly distinct `BM25_STATE_PATH`; see [KI-RAG-0004](known-issues/bm25-profile-isolation.md). Upload/delete/rescan update or rebuild statistics. Unreadable state degrades to empty in-memory statistics.

`backend/infra/vector_store/milvus_client.py`, `backend/rag/retrieval.py`, and `backend/rag/utils.py` perform dense+sparse hybrid search, RRF, document-scope filtering/boosting, normalization, dedupe, and dense fallback when hybrid retrieval fails.

Table parents and leaves are emitted only when the active profile allows
`v4_table_aware`; lower profiles can successfully parse and ingest a document
while retaining only surrounding narrative blocks. Upload success and parse
warnings therefore do not prove that table evidence is retrievable; see
[KI-RAG-0010](known-issues/table-evidence-is-not-indexed-below-v4-table-aware.md).

Candidate strategies:

- **standard** (default): global/scoped hybrid candidates, then shared rerank/postprocess.
- **layered** (implemented, default disabled): `backend/rag/layered_candidates.py` builds file-aware L0/L1 pools with scope, anchor, route, and diversity guarantees, then uses the same shared L2 rerank and L3 postprocess.

Invalid `RAG_CANDIDATE_STRATEGY` values fall back to standard with a trace warning. `dense_fallback` is an effective failure mode, not a configured strategy.

### Intent Routing and Comprehensive Retrieval

`run_rag_graph()` enters through `intent_parse`. `RAG_INTENT_CLASSIFIER_ENABLED=false` is the current code default: no model is called, and the node creates a compatibility `PreciseQueryPlan` that preserves the legacy raw/global behavior unless the independent legacy `QUERY_PLAN_ENABLED` switch is enabled. Model failure, timeout, schema failure, or bounded-capacity exhaustion also degrades to a precise compatibility plan without retrying.

Before graph entry, `plan_rag_turn()` retains the existing session-level RAG trigger based on attached context files and generic document-retrieval markers. That deterministic gate may choose forced preload versus optional tool use, but it does not classify precise/comprehensive intent, construct a QueryPlan, generate sub-queries, or select postprocess behavior.

When explicitly enabled, the classifier produces either a precise plan or a comprehensive plan. It does not produce semantic entities, terminology normalization, `semantic_query`, or postprocess strategy choices. Deterministic query preparation owns structural span consumption; terminology preflight then consumes the resulting retrieval text and independently supplies `term_matches`, `normalized_query`, `sparse_expansion`, and `protected_tokens`.

Successfully parsed anchors follow the same structural ownership rule as other consumed spans: they are removed from semantic retrieval text and carried in the typed plan. Anchor consumption is currently distributed across independently configured capabilities. Heading lexical scoring reranks existing candidates, the confidence anchor gate checks agreement, and precise fallback may react to `anchor_mismatch`; no single switch establishes the complete workflow. `.env.rag-intent-routing-workflow.example` group-enables these capabilities only for controlled workflow validation and is explicitly not a production recommendation. Runtime defaults remain unchanged.

`.env.rag-full-chain-e2e.example` is a second validation-only overlay for functional reachability of the composable standard RAG path. It enables intent routing through Level 3 delivery, selects the `v4_full` parser/chunker profile, and names an isolated Milvus collection and BM25 state file. It deliberately excludes deep-mode and reserved legacy routing flags because they are alternate or inert paths, not additional stages in the standard L0-L3 graph. The overlay does not contain secrets, does not replace the base `.env`, and is not rollout, latency, quality, or production-tuning evidence.

```text
intent_parse
  |-- precise --> retrieve_initial --> grade --> fallback_router
  `-- comprehensive
        --> clean-query baseline + generated sub-query fan-out (parallel)
        --> branch-local rerank under one shared output/pair budget
        --> priority-weighted RRF merge + provenance union
        --> one shared postprocess + branch-aware final selection
        --> grade --> fallback_router

fallback_router
  |-- confidence passed --> answer with the current round final top-k
  |-- Level 1 --> plan-specific query rewrite --> full retrieval/postprocess/confidence --> router
  |-- Level 2 --> rule-only scope/candidate relaxation --> full retrieval/postprocess/confidence --> router
  `-- Level 3 --> deterministic insufficient-evidence template --> scope-aware chat/tool delivery
```

`backend/rag/comprehensive_postprocess.py` resolves a frozen, versioned strategy composition. `quality_first_v1` is the primary Ragtenance profile and `eval_no_crossencoder_v1` is evaluation-only. Unknown profiles atomically fall back to `quality_first_v1`. Before embedding/search, graph fanout keeps at most four generated sub-queries by priority (stable original order for ties); `RAG_COMPREHENSIVE_MAX_SUB_QUERIES` is bounded to 1-8, baseline is additional, and public trace records requested/executed/truncated items (`RAG-INTENT-F032`). Output-candidate and CrossEncoder-pair budgets are allocated independently across all executed branches; when a branch pair quota is smaller, reranked pairs lead and the unpaired Milvus-ranked tail fills the remaining output quota (`RAG-INTENT-F021`). Retrieval failures, normal zero-candidate generated branches, and CrossEncoder failures are branch degradations: usable candidates remain where available, branch diagnostics record errors, and an empty generated branch feeds comprehensive confidence/fallback (`RAG-INTENT-F024`, `RAG-INTENT-F026`). The Chat Agent still invokes `search_knowledge_base(query)` once; it never receives or iterates sub-queries, and this capability has no multi-turn mode. When fallback is explicitly enabled, Level 1 may rewrite a bounded priority-ordered window of failed generated sub-queries while keeping the clean-query baseline immutable.

`ComprehensiveQueryPlan.retrieval_scope` carries one deterministic document-scope meaning across the baseline and every generated branch. Ordinary resolved `《document》` hints are shared boosts, so branches may still search the global corpus. Explicitly closed wording and `context_files` produce a shared hard filter. Branches never relax that filter inside intent routing; scope relaxation belongs to fallback Level 2.

On the precise path, HyDE and step-back fallback retrievals replace only the plan's semantic retrieval text. They retain the original raw query and deterministic file/scope/anchor constraints, so Level 1 query expansion cannot silently become scope relaxation; expanded text performs its own terminology preflight. Expanded retrieval also inherits the initial retrieval's authoritative `query_plan_enabled` state, so replacing `semantic_query` cannot activate a default-off compatibility plan (`RAG-INTENT-F033`). A precise `scope_mode="filter"` is passed as a strict filter for initial, full expanded, and candidate-only expanded retrieval, while `boost` alone permits an unfiltered global reserve (`RAG-INTENT-F027`).

This is not yet a unified anchor/fallback contract. Query preparation, confidence, and chunk normalization use different anchor grammars and surface normalization, and precise confidence re-extracts from raw query. The multilevel graph preserves typed scope and Level 0 semantic retrieval input across Level 1/2 rounds. Level 3 creates deterministic precise/comprehensive templates without retrieval or a template-generation LLM; comprehensive output distinguishes generated-dimension evidence from non-covering baseline background. Only partial final-top-k coverage (`0 < X < Y`) authorizes the existing answer model to generate source-bound, per-dimension partial answers, with uncovered and cross-dimension conclusions prohibited; full-coverage/low-confidence, baseline-only, and no-evidence modes remain evidence-only. forced-preload delivers Level 2/3 constraints through system messages, while optional-tool prepends the same shared instruction to the tool response before the existing agent model completes the answer. Structured level events and the default-collapsed frontend path display are implemented, as are the compatibility switches, legacy timeout mapping, deprecation warning, and migration guide. The narrow manual M8.5 UX gate passed under `VAL-RAG-FALLBACK-001`; mixed synthetic/authorized-real evaluation, project-level thresholds, reference budget tuning, and local rehearsal are owned by the planned [fallback activation change](../openspec/changes/rag-multilevel-fallback-activation/). The broader configuration and extraction gaps remain governed by [KI-RAG-0006](known-issues/anchor-capability-configuration.md) (`RAG-INTENT-F034`, `RAG-INTENT-F035`).

## Shared Evidence Postprocess

`finish_retrieval_pipeline()` in `backend/rag/utils.py` fixes this order:

```text
rerank
  -> auto_merge
  -> step_chain_check
  -> structure_rerank
  -> top_k_truncate
  -> confidence_gate
```

| Stage | Responsibility | Default |
| --- | --- | --- |
| rerank | Optional local CrossEncoder; optional terminology-metadata score fusion/cache. | Disabled until `RERANK_MODEL` is set. |
| auto merge | Replace same-parent leaves with complete parent context. | Enabled. |
| step-chain check | Repair incomplete list/step evidence through two-hop lookup. | Disabled. |
| structure rerank | Root/leaf structure scoring and same-root cap. | Enabled. |
| top-k truncate | Select evidence delivered to answer generation. | Always. |
| confidence gate | Evaluate the final top-k margin, concentration, score, anchors. | Disabled. |

Every recoverable stage catches its own failure, passes the preceding output to later safe stages, and records a structured stage error, skip/error state, and timing. A single postprocess failure must not erase usable evidence.

### Terminology Fusion and Codec Boundary

Query-side `term_matches` from terminology preflight feed `backend/rag/rerank.py`; intent output and legacy `query_entities` are not accepted as rerank inputs. Fusion compares terminology entity types with chunk `entity_types`. `term_match_count` remains the count of all terminology matches in the chunk and therefore contributes a chunk-density signal, not a query-specific exact-match count. Optional score fusion combines normalized rerank, RRF, scope, and this metadata signal. When terminology signals are absent, established generic metadata behavior remains.

Runtime `entity_types` is `list[str]`. `backend/infra/vector_store/metadata_codec.py` encodes compact JSON text for the Milvus wire boundary with a 512-byte maximum. Retrieval accepts JSON strings and legacy array-like values, deduplicates values, and degrades malformed/scalar/nested data to `[]`.

## State Responsibilities

| System | Responsibility |
| --- | --- |
| PostgreSQL | Users, sessions/messages, document records, parse metadata, terminology/rescan tasks, durable parents. |
| Redis | Session/data caches, parent read cache, rerank cache, index/filename signals; never durable authority. |
| Milvus | Dense+sparse leaf vectors and retrieval metadata; not complete parent bodies. |
| BM25 state | Sparse corpus statistics for the selected state file; not a document or vector store. |

The unset index profile is backward-compatible `legacy`. Parent keys and trace
identity are profile-aware, but ordinary Milvus candidate filters do not
currently enforce the stored `index_profile`; a collection containing mixed
profiles can therefore return cross-profile rows. Collection cleanliness is an
operational prerequisite until [KI-RAG-0011](known-issues/milvus-retrieval-does-not-enforce-index-profile-isolation.md)
is resolved. A new collection name is not created by configuration alone:
writer and document-management paths initialize it, while registry/retrieval
reads require the schema to exist already ([KI-RAG-0014](known-issues/milvus-read-path-requires-preinitialized-collection.md)).
BM25 isolation is manual through `BM25_STATE_PATH`.

## Trace, Evaluation, and Degradation

Internal contracts are in `backend/rag/types.py`; API schemas in `backend/contracts/schemas.py`; normalization/serialization in `backend/rag/trace.py` and `backend/rag/formatting.py`. Trace covers intent/model fallback, requested/effective strategy, per-branch and aggregate embedding/search/rerank costs, stage status/errors/timings, terminology fusion coverage, final representation, and confidence. Comprehensive trace and every branch retrieval diagnostic retain the resolved shared retrieval scope mode/source/matched files so boost scope remains distinguishable from no scope across API/history boundaries (`RAG-INTENT-F029`). Public trace retains the complete terminology preflight context: `semantic_query`, `term_matches`, `normalized_query`, `sparse_expansion`, and `protected_tokens` (`RAG-INTENT-F019`, `RAG-INTENT-F023`). Public retrieved-chunk schemas also retain branch ids, per-branch ranks/scores, baseline match state, best local rank, coverage count, and multi-query RRF score (`RAG-INTENT-F025`); auto-merged parents inherit the maximum contributing multi-query RRF score alongside unioned branch provenance (`RAG-INTENT-F031`). A failed multi-query merge preserves the undeduplicated branch union, aggregates all known branch provenance by candidate identity onto every retained duplicate, and reports the skipped/error state plus all knowable candidate counts before branch-aware shared postprocess continues (`RAG-INTENT-F020`, `RAG-INTENT-F022`). `backend/rag/observability.py` defines pure aggregation over supplied traces for rollout metrics including classifier and graph P50/P95, failure/fallback rates, intent share, profile/bucket counts, baseline rates, retrieval calls, rerank pairs, and budget exhaustion. Comprehensive evaluation error/degradation rates count top-level stage errors as well as branch errors and diagnostic errors (`RAG-INTENT-F030`). The observability module is not yet connected to a persisted trace reader, exporter, dashboard, or alerting path.

The frontend renders requested versus effective routing mode (including forced-mode degradation), but it still does not surface classifier intent/confidence or add an SSE handoff event between the last RAG step and the first answer token. Model time-to-first-token is therefore a user-visible silent interval, while classifier activation still requires direct trace or external telemetry inspection; see [KI-RAG-0012](known-issues/rag-progress-ui-omits-intent-and-answer-handoff.md).

LangSmith does not currently have a stable application request root, so one
chat turn can fragment across multiple root traces; see
[KI-RAG-0016](known-issues/langsmith-chat-turns-fragment-across-root-traces.md).
The intent classifier requests schema-conformant JSON and degrades to rules on
model failure or timeout; it remains default disabled. A timed-out synchronous
provider call can continue running and retain a classifier capacity slot; see
[KI-RAG-0021](known-issues/intent-classifier-timeout-cannot-cancel-provider-call.md).

Each chat request may carry the default-false `force_comprehensive` override.
The intent-node boundary resolves it once with the server classifier setting:
an explicit user override selects `forced_comprehensive`, otherwise an enabled
classifier selects `auto_classifier`, and the default is `precise_only` with no
intent-model call. Forced mode reuses the same classifier schema and
comprehensive graph; unavailable, timed-out, invalid, or contradictory output
degrades explicitly to the precise compatibility plan. Public and persisted
trace records requested/effective mode, source, invocation, forced success, and
degradation error. The composer persists the override per user message and
regenerate reuses that historical value. This request control does not change
the default classifier activation state or constitute classifier-quality
evidence.

The confidence gate can reject mutually corroborating high-score evidence and
produce a Level 3 no-evidence answer; see
[KI-RAG-0013](known-issues/rag-confidence-rejects-corroborating-evidence.md).

Evaluation lives under `tests/eval/`, `tests/regression/`, and `backend/evaluation/`. Reports must bind a commit and source fingerprint and distinguish deterministic substitutes from real models/infrastructure. Intent-routing source fingerprint version 2 is intended to bind a sorted manifest containing all RAG, infrastructure, and shared Python runtime files plus the API schema, evaluation code/runner, OpenSpec design/spec, and annotated datasets, so transitive retrieval/preflight/merge changes invalidate paired evidence (`RAG-INTENT-F028`). Its current manifest still names historical change-artifact paths that are absent from clean worktrees, so fingerprint evaluation currently fails before producing that evidence ([KI-RAG-0007](known-issues/intent-routing-fingerprint-archived-openspec-paths.md)). Microbenchmarks are not production-capacity evidence.

Degradation rules include hybrid-to-dense fallback, candidate preservation when rerank is absent/fails, preceding-output preservation across postprocess failures, malformed entity data to `[]`, no-op terminology when unavailable, and fatal registered-adapter parse failure.

## Feature Status Matrix

| Capability | Status | Code/default evidence |
| --- | --- | --- |
| Adapter Registry + DeepDoc/Excel | Default enabled | registry registrations |
| Normalizer + Maintainability Chunker | Default enabled | `parsed_to_chunks()` |
| Legacy index profile | Default enabled | unset `RAG_INDEX_PROFILE` |
| Dense+sparse retrieval and dense failure fallback | Default enabled | retrieval pipeline |
| Standard candidate strategy | Default enabled | unset strategy |
| Auto merge | Default enabled | `AUTO_MERGE_ENABLED=true` |
| Structure rerank | Default enabled | `STRUCTURE_RERANK_ENABLED=true` |
| Rerank cache | Default enabled when rerank exists | `RERANK_CACHE_ENABLED=true` |
| CrossEncoder rerank | Implemented, default disabled | `RERANK_MODEL` unset |
| Layered candidates | Implemented, default disabled | `RAG_CANDIDATE_STRATEGY=layered` |
| Step-chain check | Implemented, default disabled | `STEP_CHAIN_CHECK_ENABLED=false` |
| Confidence gate | Implemented, default disabled | `CONFIDENCE_GATE_ENABLED=false` |
| Rerank score fusion | Implemented, default disabled | `RERANK_SCORE_FUSION_ENABLED=false` |
| Pair enrichment / heading lexical | Implemented, default disabled | both flags false |
| Query plan | Implemented, default disabled | `QUERY_PLAN_ENABLED=false` |
| Unified execution/fallback scaffolding | Implemented, default disabled | both runtime flags false |
| Citation verification | Implemented, default disabled | citation flag false |
| Intent routing | Implemented, automatic classifier default disabled; explicit request override available | `RAG_INTENT_CLASSIFIER_ENABLED=false`; `force_comprehensive=false`; mixed synthetic + authorized-real [activation change](../openspec/changes/rag-intent-routing-activation/) |
| Anchor workflow validation bundle | Validation-only | `.env.rag-intent-routing-workflow.example`; not production guidance |
| Full-chain RAG E2E bundle | Validation-only | `.env.rag-full-chain-e2e.example`; isolated `v4_full` index authorities; not production guidance |
| Comprehensive parallel retrieval | Implemented, gated by intent routing | `quality_first_v1`; classifier default disabled |
| No-CrossEncoder comprehensive ablation | Evaluation-only | `eval_no_crossencoder_v1` |
| Multilevel fallback | Implemented, default disabled; manual M8 UX validated, Ragtenance project-level activation planned | Implementation and deterministic regressions are complete; `RAG_FALLBACK_ENABLED=false`; `VAL-RAG-FALLBACK-001` closes M8.5; mixed evaluation, project-level thresholds, reference budget tuning and local rehearsal belong to [fallback activation](../openspec/changes/rag-multilevel-fallback-activation/) |

Planned changes are excluded from active diagrams and do not override current defaults. Implemented-but-disabled capabilities remain outside the default execution path until their project-level validation and local rehearsal gates are satisfied. Ragtenance is a student portfolio/research-collaboration derivative project above demo level, not a production service: intent-routing activation is based on real-model runs over a versioned synthetic set plus a small public/authorized real-document subset, followed by a fixed local rehearsal. This evidence can support Ragtenance reference defaults but makes no production-readiness, SLA, capacity, or domain-representativeness claim.

## Governed Evidence Navigation

Use [Evidence Governance](evidence-governance.md) to select the authoritative
source for a question. Current rationale lives in [ADRs](architecture/decisions/);
confirmed unresolved problems in [known issues](known-issues/); future
opportunities in [enhancements](enhancements/); reproducible evidence in
[validation](validation/); intended work in [OpenSpec changes](../openspec/changes/);
and stable contracts in [OpenSpec specs](../openspec/specs/). The
[postprocess pipeline](rag-postprocess-evidence/pipeline.md) provides supporting
technical detail for the shared retrieval stages.

## Architecture Verification

```powershell
uv run python scripts/documentation/validate.py
uv run pytest tests/unit/docs -q
uv run pytest tests/unit/backend/documents tests/unit/backend/rag tests/unit/backend/infra/vector_store -q
openspec status --change documentation-evidence-governance --json
uv run python -c "from backend.rag.runtime_config import load_runtime_config; print(load_runtime_config({}))"
```
