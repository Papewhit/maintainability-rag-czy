---
document_type: finding_ledger
change: rag-intent-routing
last_verified_commit: 3fcf876069d22a54ca654a49d7b9ae5ef2941591
last_verified_date: 2026-07-15
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

## RAG-INTENT-F007

- Kind: behavior_defect
- Primary scope: rag.retrieval.query_preparation
- Evidence status: confirmed
- Observation: The first M3A implementation consumed chapter-like text nested inside an unresolved document hint and removed every model number whenever any document scope existed, even when that model number did not establish the scope.
- Inference: Retrieval text could lose unresolved filename content or model identifiers without a corresponding scope/anchor owner, violating the consumed-span contract.
- Decision: Exclude nested chapter/LLM-anchor matches from anchor ownership, and consume a model-number span only when that model independently matches a filename in the final effective scope.
- Residual risk: none
- Evidence: Stage-one review on 2026-07-14; `tests/unit/backend/rag/query_plan/test_intent_query_plan.py` reproduces unresolved nested anchors and unrelated scoped model numbers.
- Disposition: closed_in_place
- Disposition target: null
- Resolution evidence: `backend/rag/query_plan.py` now retains unowned spans and records owned model spans; the targeted query-plan tests and stage-one regression pass.

## RAG-INTENT-F008

- Kind: behavior_defect
- Primary scope: rag.retrieval.query_plan_activation
- Evidence status: confirmed
- Observation: A prebuilt PreciseQueryPlan made retrieval planning active, but filename boost and heading scoring still checked only the import-time legacy `QUERY_PLAN_ENABLED` value.
- Inference: Classifier-produced boost plans were silently ignored whenever the legacy query-plan switch remained off.
- Decision: Pass request-level plan activation into candidate adjustment and use the legacy global only when no explicit activation state is supplied.
- Residual risk: none
- Evidence: Stage-one review on 2026-07-14; `tests/unit/backend/rag/retrieval/test_query_preparation.py` covers a prebuilt boost plan with the legacy flag disabled.
- Disposition: closed_in_place
- Disposition target: null
- Resolution evidence: `backend/rag/utils.py` now propagates `query_plan_active` into candidate adjustment; targeted retrieval preparation tests pass.

## RAG-INTENT-F009

- Kind: delivery_risk
- Primary scope: rag.intent.classifier_runtime
- Evidence status: confirmed
- Observation: Per-request ThreadPoolExecutor timeout stopped waiting but could not cancel an already running provider call, allowing timed-out requests to accumulate threads and billable model work.
- Inference: Repeated provider hangs could cause unbounded local resource growth and duplicate latency/cost exposure despite graph fallback.
- Decision: Configure the provider request timeout with retries disabled and submit calls through one bounded shared executor guarded by non-blocking capacity slots. Exhaustion degrades through the same rule fallback path.
- Residual risk: A running injected/non-cooperative call can continue until it returns, but concurrency is bounded; the production provider also receives the HTTP timeout.
- Evidence: Stage-one review on 2026-07-14; timeout, provider configuration, no-retry, and capacity-exhaustion tests in `tests/unit/backend/rag/pipeline/test_intent_classifier.py`.
- Disposition: change
- Disposition target: openspec/changes/rag-intent-routing/
- Resolution evidence: `backend/rag/intent.py` uses bounded shared execution plus provider timeout; targeted intent tests pass.

## RAG-INTENT-F010

- Kind: evidence_gap
- Primary scope: rag.retrieval.trace
- Evidence status: confirmed
- Observation: Terminology preflight outputs existed in retrieval meta but the graph state did not propagate them, and the initial trace whitelist retained only term_matches.
- Inference: Downstream diagnostics could not establish the semantic-query coordinate base or inspect dense/BM25 composition inputs.
- Decision: Propagate semantic_query, term_matches, normalized_query, sparse_expansion, and protected_tokens through precise retrieval state and initial trace.
- Residual risk: none
- Evidence: Stage-one review on 2026-07-14; `tests/unit/backend/rag/pipeline/test_intent_state.py` asserts state and trace propagation.
- Disposition: closed_in_place
- Disposition target: null
- Resolution evidence: `backend/rag/pipeline.py` and `backend/rag/trace.py` preserve the terminology/query preparation evidence; targeted state tests pass.

## RAG-INTENT-F011

- Kind: behavior_defect
- Primary scope: rag.intent.precise_plan
- Evidence status: confirmed
- Observation: The strict intent schema exposed scope_hint but the precise plan builder ignored it, so filter, boost, and none produced identical scope behavior.
- Inference: A documented plan hint had no consumer and could create false expectations in classifier evaluation.
- Decision: Apply scope_hint only after deterministic filename resolution; unresolved hints cannot create scope, explicit context files remain hard filters, and `none` retains the document text because no scope owns it.
- Residual risk: none
- Evidence: Stage-one review on 2026-07-14; `tests/unit/backend/rag/pipeline/test_intent_classifier.py` covers resolved boost and none behavior.
- Disposition: closed_in_place
- Disposition target: null
- Resolution evidence: `backend/rag/intent.py` passes the hint to deterministic parsing and `backend/rag/query_plan.py` resolves it within ownership constraints; targeted tests pass.

## RAG-INTENT-F012

- Kind: evaluation_result
- Primary scope: evaluation.rag.postprocess
- Evidence status: confirmed
- Observation: The historical `VAL-RAG-POSTPROCESS-001` current-result fingerprint covers `backend/rag/utils.py`, `backend/rag/context.py`, and `backend/rag/rerank.py`; intent routing changes two of those files, so the recorded fingerprint no longer matches the working implementation.
- Inference: Keeping the old report presented as current would let maintainers reuse deterministic quality and latency claims against a materially different postprocess contract.
- Decision: Retain the paired result only as historical evidence bound to revision `8babe339cda636936c6c0af3c95a99e7c77c2f19`; require the new intent-routing validation gate for current claims.
- Residual risk: Current real-model and real-retrieval quality/cost evidence is still unavailable, so intent routing remains default disabled until task 5B.3 is completed.
- Evidence: `tests/eval/rag/test_postprocess_revision_evidence.py` detects that the recorded `faf0e2b0…37e6c1` fingerprint differs from the current postprocess source fingerprint; `docs/rag-postprocess-evidence/evaluation.md` records the original revision and source set.
- Disposition: change
- Disposition target: openspec/changes/rag-intent-routing/
- Resolution evidence: `docs/rag-postprocess-evidence/evaluation.md` is marked `historical`, and the governed intent-routing report is `partial` with activation blocked.

## RAG-INTENT-F013

- Kind: behavior_defect
- Primary scope: evaluation.rag.intent_routing
- Evidence status: confirmed
- Observation: The first evaluation implementation invoked query-plan construction without the synthetic filename registry, passed no citation target to an evaluator that only measured qrel coverage, omitted the answer evaluator and key model/retrieval settings from fingerprints, and renamed three historical terminology trace keys despite the delta spec retaining them as wire-compatible names.
- Inference: A real run would systematically mark labeled filter/boost plans invalid, could never produce citation validity, could reuse a fingerprint across materially different judges or retrieval stores, and would break existing trace consumers.
- Decision: Add and fingerprint a curated evaluation filename registry; bind it to real intent reports; measure generated citation consistency against retrieved filename/page evidence; expand source/config fingerprints; and retain `entity_metadata_score_applied`, `entity_type_coverage`, and `entity_match_density` as terminology-only historical response keys while keeping query-side inputs terminology-typed.
- Residual risk: The synthetic filename registry proves parsing and plan validity, not that the release Milvus corpus contains those documents. Citation validity measures precision against retrieved evidence rather than recall against human qrels. Both limitations remain explicit in the partial validation report and 5B.3 stays incomplete.
- Evidence: Third-stage independent review on 2026-07-14 and `@codex` review on 2026-07-15; `tests/eval/rag/test_intent_classifier_eval.py`, `tests/eval/rag/test_comprehensive_intent_routing_eval.py`, `tests/unit/backend/evaluation/test_answer_eval.py`, and success/failure trace contract tests cover the corrections.
- Disposition: change
- Disposition target: openspec/changes/rag-intent-routing/
- Resolution evidence: The real runners now carry registry/model/retrieval fingerprints and a constructible citation-validity metric; all retrieval/rerank failure paths retain the historical terminology metadata response keys; targeted evaluation and contract tests pass.

## RAG-INTENT-F014

- Kind: behavior_defect
- Primary scope: rag.retrieval.comprehensive_scope
- Evidence status: confirmed
- Observation: Comprehensive intent parsing consumed a successfully resolved document hint into `clean_query`, but the six-field ComprehensiveQueryPlan did not retain matched_files/scope_mode and fan-out passed only each branch query plus context_files. A resolved document constraint could therefore disappear before retrieval.
- Inference: Explicit document-oriented comprehensive requests could remove their strongest retrieval cue and search unrelated global evidence, while naively sharing every resolved document as a hard filter would over-constrain ordinary cross-source analysis.
- Decision: Add typed `retrieval_scope` to ComprehensiveQueryPlan and share it across baseline and all generated branches. Ordinary resolved document hints default to boost; only explicit closed wording or context_files produce filter. No branch relaxes filter inside intent-routing; that remains fallback Level 2.
- Residual risk: Closed-scope wording is recognized by a conservative deterministic phrase set. Unrecognized user phrasing remains boost rather than being incorrectly promoted to a hard filter; extending the phrase set requires examples and regression tests.
- Evidence: `@codex` PR review on 2026-07-14 identified lost comprehensive scope; user decision on 2026-07-15 fixed boost/filter/Level-2 boundaries; intent, comprehensive graph, and retrieval preparation tests cover all three scope sources, branch propagation, negative wording, and strict filtered retrieval without a global reserve.
- Disposition: change
- Disposition target: openspec/changes/rag-intent-routing/
- Resolution evidence: QueryPlan/spec/design now define shared RetrievalScope; graph fan-out constructs each branch retrieval plan from that immutable scope; explicit closed scope uses a strict filename-filtered retrieval path while ordinary document hints retain global boost behavior.

## RAG-INTENT-F015

- Kind: behavior_defect
- Primary scope: rag.retrieval.telemetry
- Evidence status: confirmed
- Observation: `prepare_candidate_retrieval()` treated the mere presence of a compatibility PreciseQueryPlan as proof that QueryPlan rules were enabled. With both runtime switches false, default raw/global traffic was emitted as `query_plan_enabled=true`.
- Inference: Rollout and evaluation telemetry could misclassify the default compatibility cohort even though retrieval output remained compatible.
- Decision: Resolve request-level plan activation separately from plan object presence. A raw compatibility plan remains disabled; classifier/legacy/scoped plans remain active, and explicit callers may pass the activation state.
- Residual risk: none
- Evidence: `@codex` PR review on 2026-07-14; retrieval preparation tests compare legacy and routed default-off traces; output trace tests prove the field survives into final `rag_trace`.
- Disposition: closed_in_place
- Disposition target: null
- Resolution evidence: Both default-off paths emit `query_plan_enabled=false`, and `build_initial_rag_trace()` preserves that value for downstream observability consumers.

## RAG-INTENT-F016

- Kind: behavior_defect
- Primary scope: rag.api.trace_contract
- Evidence status: confirmed
- Observation: The graph produced the intent-routing and comprehensive cost/diagnostic fields required by the delta spec, but the public `RagTrace` Pydantic response model did not declare them. FastAPI response-model serialization therefore removed those fields from non-stream chat and historical-message responses.
- Inference: Rollout monitors, evaluation tooling, and API clients could not observe the very cohort, branch, budget, and cost telemetry required to assess this default-disabled capability.
- Decision: Explicitly type the intent, query-plan, comprehensive profile/strategy, branch diagnostics, budget/cost, representation, and scope fields in both internal and public trace contracts. Include the public response schema in the governed routing source fingerprint rather than allowing arbitrary extra response keys.
- Residual risk: Future trace fields still require an intentional response-contract update and regression test; this is preferred to exposing unbounded internal extras.
- Evidence: `@codex` review on 2026-07-15; `tests/unit/backend/contracts/test_rag_trace_schema.py` round-trips representative comprehensive telemetry through `ChatResponse`; the source-fingerprint contract asserts coverage of `backend/contracts/schemas.py`.
- Disposition: change
- Disposition target: openspec/changes/rag-intent-routing/
- Resolution evidence: Public and internal RagTrace schemas now retain the required intent-routing trace, and the evaluation fingerprint binds that wire contract.
