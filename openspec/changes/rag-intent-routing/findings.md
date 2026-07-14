---
document_type: finding_ledger
change: rag-intent-routing
last_verified_commit: 62e642d480eec282833c51c30ed881ae7727675b
last_verified_date: 2026-07-14
---

# Change Findings

## RAG-INTENT-F001

- Kind: design_ambiguity
- Primary scope: rag.retrieval
- Evidence status: confirmed
- Observation: The change simultaneously placed intent parsing inside `run_rag_graph()`, kept Chat Agent unaware of intent routing, and required Chat Agent multi-turn tool calls that consume and adjust the resulting sub-queries. The current knowledge-base tool also permits only one call per chat turn.
- Inference: Implementing the written requirements literally would either leak retrieval orchestration into Chat Agent or require an unplanned stateful interface outside the RAG graph.
- Decision: Limit this change to parallel sub-query search and deterministic merge inside a single RAG graph invocation. Do not design multi-turn here. Treat rewrite, replace, and decompose of an unsuccessful sub-query as future fallback Level 1 behavior.
- Residual risk: Parallel search cannot adapt later sub-queries from intermediate results; this is an accepted limitation and separately recorded as a candidate enhancement that requires A/B evidence before rollout.
- Evidence: `openspec/changes/rag-intent-routing/design.md` decision 1 placed parsing inside the graph; former decision 6 and task 4.1 assigned multi-turn scheduling to Chat Agent; `backend/chat/tools.py` enforces one `search_knowledge_base` call per turn; user decision on 2026-07-14 removed multi-turn from this change.
- Disposition: enhancement
- Disposition target: docs/enhancements/rag-adaptive-multiturn-search.md
- Resolution evidence: The proposal, design, capability spec, and tasks now specify graph-internal parallel search only, and ENH-RAG-0003 records the unscheduled multi-turn opportunity and A/B prerequisite.

## RAG-INTENT-F002

- Kind: design_ambiguity
- Primary scope: rag.retrieval
- Evidence status: confirmed
- Observation: The change claimed that disabling `RAG_INTENT_CLASSIFIER_ENABLED` and running a new rule fallback would be behaviorally equivalent to the current system, while current query planning is independently controlled by `QUERY_PLAN_ENABLED` and defaults to raw query + global routing.
- Inference: Unconditionally applying new entity, keyword, anchor, or scope rules while the classifier is disabled could change default retrieval despite the stated compatibility guarantee.
- Decision: Keep `intent_parse` as the graph entry but construct a compatibility PreciseQueryPlan that preserves current `QUERY_PLAN_ENABLED` semantics. Use the same compatibility adapter when an enabled classifier fails.
- Residual risk: none
- Evidence: `backend/rag/utils.py:1049-1079` returns a raw global QueryPlan when `QUERY_PLAN_ENABLED` is false; the former change design and task 1.2 proposed unconditional new rule behavior; user decision on 2026-07-14 accepted strict compatibility.
- Disposition: change
- Disposition target: openspec/changes/rag-intent-routing/
- Resolution evidence: The proposal, design decision 4, capability scenarios, tasks 1.1-1.4, and task 6.4 now define and test the compatibility mapping and distinguish disabled operation from runtime failure.

## RAG-INTENT-F003

- Kind: design_ambiguity
- Primary scope: rag.retrieval
- Evidence status: confirmed
- Observation: The original fusion design reserved product/equipment/component/action/parameter metadata for a later knowledge-graph direction, while `rag-intent-routing` turned that reservation into a mandatory LLM `EntityMatch` output and QueryPlan field. No runtime intent classifier or EntityMatch producer exists. The only current producer is terminology preflight/chunk scanning, whose `term_matches`, `entity_types`, and `term_match_count` are already consumed as terminology signals; chunk metadata stores types and density, not query-matchable entity instances.
- Inference: Keeping semantic entities in QueryPlan would preserve a scenario-specific future vision without an upstream instance contract or a current consumer. Passing such values into the existing type-only fusion would not provide precise entity matching and would blur terminology with knowledge-graph entities.
- Decision: Remove semantic entity extraction, EntityMatch, entities, normalization, confidence, trace, and evaluation requirements from intent-routing and dependent fallback design. Keep terminology as an independent preflight and preserve its existing query expansion plus optional rerank consumption of `entity_types` and `term_match_count`. QueryPlan owns intent and retrieval orchestration only.
- Residual risk: Legacy terminology field names such as `query_entities`, `entity_types`, and `entity_type_coverage` can still suggest instance-level entity semantics. Renaming them would cross persisted metadata, trace, cache, and compatibility boundaries and is not required by this change. `term_match_count` remains a coarse chunk-wide terminology density signal rather than a query-specific exact-match count.
- Evidence: `docs/superpowers/specs/2026-05-20-rag-fusion-design.md:174-181` labels generic entities as a knowledge-graph reservation; commit `85be834` first introduced `Intent + Entity Parser` and `EntityMatch`; `backend/rag/pipeline.py:916-958` has no intent producer in the production graph; `backend/rag/rerank.py:89-101` consumes only query/chunk type overlap and chunk-wide `term_match_count`; `docs/rag-postprocess-evidence/implementation-notes.md:48-50` states current entities come from terminology and future intent routing is only a compatibility hook; user decisions on 2026-07-14 removed semantic entities while retaining terminology metadata consumption.
- Disposition: change
- Disposition target: openspec/changes/rag-intent-routing/
- Resolution evidence: The proposal, design, capability spec, tasks, postprocess delta, and dependent `rag-multilevel-fallback` artifacts now remove semantic entities and retain terminology-only retrieval signals.

## RAG-INTENT-F004

- Kind: behavior_defect
- Primary scope: rag.retrieval.query_preparation
- Evidence status: confirmed
- Observation: QueryPlan deterministically constructs `clean_query` / `semantic_query`, while terminology preflight independently scans `raw_query`. In `prepare_candidate_retrieval`, any loaded terminology table returns a preflight result even when no term matches, and the resulting raw-based `normalized_query` / `sparse_expansion` overwrite `query_plan.semantic_query` before dense and BM25 embedding. The existing tests cover QueryPlan parsing and terminology preflight separately but do not cover their composition.
- Inference: Successful document-name or model-number cleaning is discarded whenever terminology initialization succeeds; structure text can be duplicated as both scope/anchor and terminology input. Conversely, deleting structure-looking text before confirming it resolved to scope can lose retrieval terms when filename matching fails. The documented claim that semantic_query enters vector embedding is therefore not reliable under the current composition order.
- Decision: Make query preparation sequential and deterministic. Only spans successfully consumed as scope or anchor may be removed; unresolved document hints remain in semantic query. Run terminology preflight on the resulting semantic query (and independently on each comprehensive sub-query), route normalized_query to dense and sparse_expansion to BM25, and never restore raw query on a no-hit result. Intent LLM does not perform terminology normalization.
- Residual risk: Existing query term offsets will become relative to the actual preflight input rather than raw query unless the implementation adds explicit source/offset mapping. No current retrieval or rerank consumer depends on raw offsets; trace documentation and tests must state the chosen coordinate space.
- Evidence: `backend/rag/query_plan.py:262-325` builds structure fields and semantic_query; `backend/rag/terminology/table.py:141-195` scans and expands its input; `backend/rag/utils.py:1665-1676` overwrites semantic_query with raw-based terminology output; `backend/infra/embedding.py:279-284` builds BM25 sparse vectors; `backend/infra/vector_store/milvus_client.py:284-324` performs dense+sparse hybrid RRF; only `tests/unit/backend/rag/query_plan/test_query_plan_parser.py` and `tests/unit/backend/rag/terminology/test_terminology_m3.py` exercise the two behaviors separately; user decisions on 2026-07-14 require vector+BM25 term delivery and assign successfully consumed structure spans to scope/anchor rather than terminology.
- Disposition: change
- Disposition target: openspec/changes/rag-intent-routing/
- Resolution evidence: Proposal, design decision 5, capability requirements, M3A tasks, terminology delta spec, and fallback Level 0 wording define the corrected ordering and combined regression coverage.

## RAG-INTENT-F005

- Kind: design_ambiguity
- Primary scope: rag.postprocess.comprehensive
- Evidence status: confirmed
- Observation: The change required parallel sub-query retrieval and named union/weighted/hierarchical merge strategies, but did not place merge relative to rerank, auto_merge, step-chain, structure rerank, final top-k, or confidence. The production postprocess accepts a single query and runs the complete fixed sequence once, while the candidate-only API exposes a natural pre-postprocess boundary. Running the complete sequence independently per branch would duplicate expensive stages, truncate candidates before cross-query comparison, and produce scores/confidence that are not globally meaningful.
- Inference: A literal implementation could multiply CrossEncoder and structural work by sub-query count, compare non-comparable raw scores across queries, duplicate parent/step repair, and still collapse final evidence onto one branch. Scattered per-node strategy switches would make later cost/quality tuning unsafe and create untested combinations.
- Decision: Use branch-local hybrid retrieval and query-local rerank, then priority-weighted RRF over local ranks, chunk/provenance dedupe, and one shared global auto_merge → step-chain → structure rerank → branch-aware top-k → comprehensive confidence sequence. Treat RERANK_CANDIDATE_POOL_SIZE as the shared global output budget and the device-tier RERANK_INPUT_K cap as the independent shared CrossEncoder pair budget. Resolve the full behavior through a typed, versioned ComprehensivePostprocessPolicy registry; v1 production profile is quality_first_v1, and LLM output does not select algorithms. Final selection statically reserves branch representation when capacity permits; this is not an evidence ledger or multi-turn loop.
- Residual risk: The accepted quality-first profile still performs one dense/BM25 hybrid search per sub-query and query-local relevance work, so latency and resource cost may be unacceptable at larger sub-query counts. Default enablement is blocked on a reproducible quality/cost comparison against a no-CrossEncoder ablation profile; thresholds must be derived from evidence rather than asserted in design.
- Evidence: `backend/rag/utils.py:284-458` implements the single-query fixed postprocess and single-query rerank input; `backend/rag/utils.py:1778-1826` exposes candidate-only retrieval; `openspec/specs/rag-postprocess-pipeline/spec.md` fixes the existing order and global top-k semantics; the former intent-routing artifacts only said merge by merge_strategy without executable stage ownership; user decision on 2026-07-14 accepts the quality-first split provisionally, requires explicit cost evaluation, and requires maintainable strategy composition.
- Disposition: change
- Disposition target: openspec/changes/rag-intent-routing/
- Resolution evidence: Design decisions 8-10, comprehensive and postprocess capability deltas, M4/M5B tasks, profile trace/monitoring requirements, and fallback profile preservation define the implementation and evaluation boundary.

## RAG-INTENT-F006

- Kind: design_ambiguity
- Primary scope: rag.retrieval.comprehensive_baseline
- Evidence status: confirmed
- Observation: A comprehensive plan that retrieves only LLM-generated sub-queries can lose useful wording and constraints from the deterministically cleaned original query. Adding that query naively as another ordinary sub-query would inflate the apparent coverage count, compete for a reserved final slot, obscure one real retrieval call in cost metrics, and make fallback eligible to rewrite a branch that is meant to remain an invariant safety net.
- Inference: The original clean query needs an explicit branch identity and lifecycle rather than being appended to `sub_queries`. Its cost and provenance must remain visible, while generated coverage guarantees must remain based only on planned analysis domains.
- Decision: Every valid ComprehensiveQueryPlan carries runtime-produced `clean_query`. Fan-out constructs exactly one stable `baseline` retrieval branch from it, then runs the same branch query preparation, terminology preflight, hybrid retrieval and local rerank as generated branches. Baseline participates in the shared budgets and priority-weighted RRF with neutral effective priority 2, but does not add a coverage domain or receive a final reservation slot; it can enter final top-k only through global rank. `sub_query_count` remains the LLM count and `retrieval_branch_count=sub_query_count+1` exposes real work. Provenance is branch-based and Level 1 never rewrites baseline.
- Residual risk: Baseline fixes one additional hybrid retrieval and may add CrossEncoder pairs on every comprehensive request. Cost/quality evaluation must report baseline hit and final-selection rates so a branch that rarely contributes cannot remain hidden as unavoidable overhead.
- Evidence: User decision on 2026-07-14 explicitly includes the original clean-query baseline; the existing comprehensive schema previously had no clean_query or baseline identity, and its branch reservation/counting language treated every successful branch as a coverage branch.
- Disposition: change
- Disposition target: openspec/changes/rag-intent-routing/
- Resolution evidence: ComprehensiveQueryPlan schema, clean-query baseline requirement/scenarios, branch provenance, budget/selection rules, trace/evaluation fields, M1/M3A/M4/M5B tasks, and fallback exclusion define the durable contract.
