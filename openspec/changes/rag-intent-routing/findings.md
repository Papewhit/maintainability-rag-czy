---
document_type: finding_ledger
change: rag-intent-routing
last_verified_commit: 1c7a78291d9a01d9acaa445c517706f4b9ec32a5
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
- Evidence: `backend/rag/query_plan.py:262-325` builds structure fields and semantic_query; `backend/rag/terminology/table.py:141-195` scans and expands its input; `backend/rag/utils.py:1665-1676` overwrote semantic_query with raw-based terminology output; `backend/infra/embedding.py:279-284` builds BM25 sparse vectors; `backend/infra/vector_store/milvus_client.py:284-324` performs dense+sparse hybrid RRF; user decisions on 2026-07-14 require vector+BM25 term delivery and assign successfully consumed structure spans to scope/anchor rather than terminology; `@codex` review on 2026-07-15 found fallback expanded queries still received the initial query's term matches.
- Disposition: change
- Disposition target: openspec/changes/rag-intent-routing/
- Resolution evidence: Proposal, design decision 5, capability requirements, M3A tasks, terminology delta spec, and fallback Level 0 wording define the corrected ordering; regression coverage proves every comprehensive branch and fallback-expanded query performs terminology preflight from its own retrieval text, while the candidate-only final rerank intentionally uses initial terms with the initial query.

## RAG-INTENT-F005

- Kind: design_ambiguity
- Primary scope: rag.postprocess.comprehensive
- Evidence status: confirmed
- Observation: The change required parallel sub-query retrieval and named union/weighted/hierarchical merge strategies, but did not place merge relative to rerank, auto_merge, step-chain, structure rerank, final top-k, or confidence. The production postprocess accepts a single query and runs the complete fixed sequence once, while the candidate-only API exposes a natural pre-postprocess boundary. Running the complete sequence independently per branch would duplicate expensive stages, truncate candidates before cross-query comparison, and produce scores/confidence that are not globally meaningful.
- Inference: A literal implementation could multiply CrossEncoder and structural work by sub-query count, compare non-comparable raw scores across queries, duplicate parent/step repair, and still collapse final evidence onto one branch. Scattered per-node strategy switches would make later cost/quality tuning unsafe and create untested combinations.
- Decision: Use branch-local hybrid retrieval and query-local rerank, then priority-weighted RRF over local ranks, chunk/provenance dedupe, and one shared global auto_merge → step-chain → structure rerank → branch-aware top-k → comprehensive confidence sequence. Treat RERANK_CANDIDATE_POOL_SIZE as the shared global output budget and the device-tier RERANK_INPUT_K cap as the independent shared CrossEncoder pair budget. Resolve the full behavior through a typed, versioned ComprehensivePostprocessPolicy registry; v1 production profile is quality_first_v1, and LLM output does not select algorithms. Final selection statically reserves branch representation when capacity permits; this is not an evidence ledger or multi-turn loop.
- Residual risk: The accepted quality-first profile still performs one dense/BM25 hybrid search per sub-query and query-local relevance work, so latency and resource cost may be unacceptable at larger sub-query counts. Default enablement is blocked on a reproducible quality/cost comparison against a no-CrossEncoder ablation profile; thresholds must be derived from evidence rather than asserted in design.
- Evidence: `backend/rag/utils.py:284-458` implements the single-query fixed postprocess and single-query rerank input; `backend/rag/utils.py:1778-1826` exposes candidate-only retrieval; `openspec/specs/rag-postprocess-pipeline/spec.md` fixes the existing order and global top-k semantics; the former intent-routing artifacts only said merge by merge_strategy without executable stage ownership; user decision on 2026-07-14 accepts the quality-first split provisionally, requires explicit cost evaluation, and requires maintainable strategy composition; `@codex` reviews on 2026-07-15 found the global reranker could exceed a branch's allocated output budget and comprehensive treated an unset/small pool differently from precise, potentially emptying all branches.
- Disposition: change
- Disposition target: openspec/changes/rag-intent-routing/
- Resolution evidence: Design decisions 8-10, comprehensive and postprocess capability deltas, M4/M5B tasks, profile trace/monitoring requirements, and fallback profile preservation define the boundary; precise and comprehensive share one effective pool normalizer, successful/zero/no-pair/rerank-exception/no-CrossEncoder results are capped by allocated output quota before merge, and trace used budget equals the actual forwarded pool.

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

## RAG-INTENT-F017

- Kind: behavior_defect
- Primary scope: rag.retrieval.precise_fallback_scope
- Evidence status: confirmed
- Observation: Initial precise retrieval consumed an intent-built scoped `PreciseQueryPlan`, but existing HyDE/step-back full and candidate-only fallback jobs passed only the expanded text and context_files. With no context_files and legacy QueryPlan disabled, candidate preparation rebuilt an unscoped global plan because the expanded text no longer contained the original document hint.
- Inference: Level 1 query expansion could replace correctly scoped initial evidence with unrelated global chunks, implicitly performing the scope relaxation reserved for fallback Level 2.
- Decision: Derive every expanded retrieval plan from the original PreciseQueryPlan, replacing only semantic_query while preserving raw_query, matched_files, scope_mode, anchors, heading_hint, route, and other deterministic constraints. Each expanded semantic query still runs its own terminology preflight.
- Residual risk: none
- Evidence: `@codex` review on 2026-07-15; `tests/unit/backend/rag/pipeline/test_rag_pipeline.py` covers parallel full second-pass and candidate-only HyDE/step-back jobs and asserts preserved scope with branch-specific semantic queries.
- Disposition: closed_in_place
- Disposition target: null
- Resolution evidence: `backend/rag/pipeline.py` carries a derived scoped plan into every expanded retrieval job; targeted fallback tests pass after reproducing three failures before the fix.

## RAG-INTENT-F018

- Kind: design_ambiguity
- Primary scope: rag.chat_session_routing
- Evidence status: confirmed
- Observation: Proposal and delta spec said `plan_rag_turn()` must not analyze query content, while design and task 3.6 required it to remain unchanged. The existing contract uses generic document-retrieval markers to choose session-level forced preload, without classifying precise/comprehensive intent.
- Inference: Removing the marker gate would either force every unified turn through RAG or return document questions to Agent-controlled optional tool selection, changing behavior and cost outside this change. Keeping the implementation without correcting the artifacts would falsely describe the same session gate as an intent-routing violation.
- Decision: Preserve the existing context_files/document-marker session gate. Prohibit only precise/comprehensive classification, QueryPlan construction, sub-query orchestration, and postprocess selection outside the graph. The user accepted this boundary on 2026-07-15.
- Residual risk: Generic document markers remain a coarse RAG invocation heuristic; changing that invocation policy requires a separately scoped change and cost/behavior evidence.
- Evidence: Independent final review on 2026-07-15 identified the artifact conflict; user decision retained the existing session contract; `tests/unit/backend/rag/output/test_rag_execution.py` covers the trigger behavior.
- Disposition: change
- Disposition target: openspec/changes/rag-intent-routing/
- Resolution evidence: Proposal, design, task 3.6, delta spec, and architecture now distinguish session-level RAG invocation from graph-owned retrieval intent routing.

## RAG-INTENT-F019

- Kind: behavior_defect
- Primary scope: rag.api.terminology_trace
- Evidence status: confirmed
- Observation: Internal trace retained semantic_query and terminology term_matches, but the public RagTrace response schema declared only term_matches. FastAPI serialization therefore exposed start/end offsets while dropping the actual preflight input that defines their coordinate space.
- Inference: ChatResponse and historical-message consumers could not reliably interpret terminology offsets after structural query cleaning.
- Decision: Add semantic_query to the typed internal and public trace contracts and round-trip it with term_matches through ChatResponse.
- Residual risk: none
- Evidence: Independent final review on 2026-07-15; `tests/unit/backend/contracts/test_rag_trace_schema.py` reproduced the dropped field before the fix and now verifies semantic_query plus offsets after API serialization.
- Disposition: closed_in_place
- Disposition target: null
- Resolution evidence: Public RagTrace retains semantic_query and the routing source fingerprint binds the response schema.

## RAG-INTENT-F020

- Kind: behavior_defect
- Primary scope: rag.postprocess.multi_query_merge
- Evidence status: confirmed
- Observation: When the comprehensive merger raised, graph code preserved branch candidates but emitted only merge_error and a stage error. It omitted the required `multi_query_merge_skipped` state and branch/merged/unique/deduplicated counts that remained directly knowable.
- Inference: Failure traces could not distinguish a completed merge from a branch-union degradation or account for candidate-pool cost, despite continuing to answer with preserved evidence.
- Decision: Centralize success and failure merge telemetry. Failure retains the branch union, marks the stage skipped, records the error, and reports every knowable candidate count; success explicitly marks the stage not skipped.
- Residual risk: A skipped merger intentionally preserves the undeduplicated branch union; consumers must use the explicit skipped/error state and candidate counts to interpret this degraded evidence state.
- Evidence: Independent final review on 2026-07-15; `tests/unit/backend/rag/pipeline/test_comprehensive_graph.py` covers duplicate candidates, branch failure, public serialization, and complete merge-degradation telemetry.
- Disposition: change
- Disposition target: openspec/changes/rag-intent-routing/
- Resolution evidence: `backend/rag/comprehensive_postprocess.py` supplies shared merge trace helpers used by both graph and direct policy paths; targeted contract and postprocess tests pass.

## RAG-INTENT-F021

- Kind: behavior_defect
- Primary scope: rag.postprocess.branch_rerank_budget
- Evidence status: confirmed
- Observation: When a branch received more output-candidate quota than CrossEncoder pair quota, the successful rerank path returned only paired candidates and discarded the unpaired Milvus-ranked tail despite available output quota.
- Inference: A lower device-tier pair cap could silently underfill the shared merge pool, reduce branch evidence coverage, and make used output telemetry diverge from the allocated quality/cost strategy.
- Decision: Keep reranked pairs first, then fill the remaining branch output quota from the unpaired local-rank tail. Pair and output usage remain independently observable.
- Residual risk: none
- Evidence: `@codex` review on 2026-07-15; `tests/unit/backend/rag/postprocess/test_comprehensive_shared_pipeline.py` reproduced the truncated branch and now asserts reranked-pair order plus Milvus-tail retention.
- Disposition: closed_in_place
- Disposition target: null
- Resolution evidence: `CrossEncoderLocalReranker` now honors the allocated output quota when pair quota is smaller; the focused red/green test passes.

## RAG-INTENT-F022

- Kind: behavior_defect
- Primary scope: rag.postprocess.merge_failure_provenance
- Evidence status: confirmed
- Observation: The multi-query merge failure fallback initially preserved raw branch candidates but omitted provenance. Its first repair annotated only each physical copy's immediate source; when duplicate identities came from multiple branches, selector identity dedupe could still discard the other copies' branch coverage.
- Inference: Branch-aware selection and comprehensive confidence could falsely report successful generated branches as unrepresented after a recoverable merger failure, even when the selected evidence identity was returned by those branches.
- Decision: Aggregate branch ids, best per-branch ranks/scores, baseline state, and generated coverage by candidate identity, then annotate every retained branch-union copy with that complete known provenance before shared postprocess continues.
- Residual risk: none
- Evidence: `@codex` reviews on 2026-07-15; `tests/unit/backend/rag/pipeline/test_comprehensive_graph.py` covers the initial missing fields and duplicate identities shared across baseline plus two generated branches, then runs the degraded union through branch-aware shared postprocess without a false missing-branch signal.
- Disposition: closed_in_place
- Disposition target: null
- Resolution evidence: `merge_failure_fallback` now preserves identity-unioned branch provenance on every retained copy while keeping the undeduplicated branch union and complete degradation telemetry.

## RAG-INTENT-F023

- Kind: behavior_defect
- Primary scope: rag.api.terminology_trace
- Evidence status: confirmed
- Observation: Public RagTrace retained `semantic_query` and `term_matches` but still omitted the companion terminology preflight outputs `normalized_query`, `sparse_expansion`, and `protected_tokens` that retrieval had already placed in the internal trace.
- Inference: API and history consumers could identify the match-offset coordinate query but could not inspect the actual dense/BM25 query composition or protected-token context used by retrieval and evaluation.
- Decision: Type and serialize the complete terminology preflight trace context in both internal RagTrace and the public response schema.
- Residual risk: none
- Evidence: `@codex` review on 2026-07-15; `tests/unit/backend/contracts/test_rag_trace_schema.py` reproduced the three dropped fields and now round-trips all preflight inputs through `ChatResponse`.
- Disposition: closed_in_place
- Disposition target: null
- Resolution evidence: `backend/contracts/schemas.py` and `backend/rag/types.py` declare the full preflight trace contract; the focused red/green API test passes.

## RAG-INTENT-F024

- Kind: behavior_defect
- Primary scope: rag.postprocess.branch_rerank_diagnostics
- Evidence status: confirmed
- Observation: `_rerank_documents` may return usable Milvus-ranked candidates plus `rerank_meta["rerank_error"]` when CrossEncoder loading or prediction fails. The comprehensive reranker copied the meta but left `BranchRetrievalResult.error` empty because no exception was raised.
- Inference: Branch diagnostics, rollout error metrics, and fallback inputs reported a clean local rerank despite an actual quality degradation.
- Decision: Promote a non-empty soft rerank error into the branch error path while retaining the returned candidates and all usage telemetry.
- Residual risk: none
- Evidence: `@codex` review on 2026-07-15; `tests/unit/backend/rag/postprocess/test_comprehensive_shared_pipeline.py` reproduces the metadata-only failure and now verifies retained evidence plus branch error/diagnostic propagation.
- Disposition: closed_in_place
- Disposition target: null
- Resolution evidence: `CrossEncoderLocalReranker` sets the branch error from rerank metadata when no earlier branch error exists; the focused red/green test passes.

## RAG-INTENT-F025

- Kind: behavior_defect
- Primary scope: rag.api.candidate_provenance
- Evidence status: confirmed
- Observation: Internal comprehensive candidates carried branch provenance, but `RagTrace.retrieved_chunks` validated them through a `RetrievedChunk` schema that omitted all branch fields, so Pydantic removed the provenance from chat and history responses.
- Inference: API consumers could see aggregate merge degradation yet could not inspect which final evidence represented the baseline or each generated branch.
- Decision: Add the complete comprehensive branch provenance set to the public retrieved-chunk contract instead of weakening the schema to arbitrary dictionaries.
- Residual risk: none
- Evidence: `@codex` review on 2026-07-15; `tests/unit/backend/contracts/test_rag_trace_schema.py` reproduces the dropped fields and now round-trips branch ids, ranks/scores, baseline state, coverage, and RRF score through `ChatResponse`.
- Disposition: closed_in_place
- Disposition target: null
- Resolution evidence: `backend/contracts/schemas.py::RetrievedChunk` now explicitly retains the comprehensive candidate provenance fields; the focused red/green API test passes.

## RAG-INTENT-F026

- Kind: behavior_defect
- Primary scope: rag.retrieval.branch_failure_diagnostics
- Evidence status: confirmed
- Observation: Candidate retrieval reports total embedding/Milvus failure as a normal payload with `retrieval_mode="failed"` and stage errors. Comprehensive fan-out treated any returned payload as a successful `BranchRetrievalResult`, leaving its error empty.
- Inference: An empty generated branch could be absent from `failed_generated_branch_ids`, so comprehensive confidence would not add `generated_branch_failure` or request fallback despite a real retrieval failure.
- Decision: Convert a returned failed retrieval mode into a branch error using the most specific stage or retrieval error while retaining its meta, timings, and any candidates.
- Residual risk: none
- Evidence: `@codex` review on 2026-07-15; `tests/unit/backend/rag/pipeline/test_comprehensive_graph.py` reproduces a non-throwing failed branch and now verifies diagnostics plus comprehensive confidence/fallback propagation.
- Disposition: closed_in_place
- Disposition target: null
- Resolution evidence: `decompose_and_fanout` recognizes `retrieval_mode="failed"` and populates `BranchRetrievalResult.error`; the focused red/green graph test passes.

## RAG-INTENT-F027

- Kind: behavior_defect
- Primary scope: rag.retrieval.precise_scope_filter
- Evidence status: confirmed
- Observation: Precise retrieval passed a `scope_mode="filter"` QueryPlan into candidate preparation without setting `strict_scope_filter`. Candidate preparation therefore used the scoped-plus-global-reserve path intended for boosts and could admit out-of-scope chunks.
- Inference: Explicit single-document/context-file lookups and their Level 1 expansions could violate the accepted closed-scope contract; preserving the plan object alone did not enforce the filter.
- Decision: Derive `strict_scope_filter` from the typed PreciseQueryPlan at every initial, full expanded, and candidate-only expanded retrieval call. Boost and none plans continue to pass false.
- Residual risk: none
- Evidence: `@codex` review on 2026-07-15; `tests/unit/backend/rag/pipeline/test_intent_state.py` and `test_rag_pipeline.py` reproduce the missing flag and now cover initial plus full/candidate-only HyDE/step-back paths.
- Disposition: closed_in_place
- Disposition target: null
- Resolution evidence: `backend/rag/pipeline.py` propagates hard-filter semantics consistently across the precise path; four focused red/green tests pass.

## RAG-INTENT-F028

- Kind: evidence_gap
- Primary scope: evaluation.rag.source_binding
- Evidence status: confirmed
- Observation: The comprehensive paired-evaluation fingerprint listed selected direct routing files but omitted transitive runtime dependencies including `backend/rag/trace.py` (`candidate_identity`) and terminology preflight modules. Those dependencies can change merge/selection or dense/BM25 inputs without changing the fingerprint.
- Inference: A release report could claim paired runs used identical source even though effective retrieval behavior differed, weakening the A/B activation gate.
- Decision: Introduce source fingerprint version 2 with a deterministic sorted manifest that includes all Python files under `backend/rag`, `backend/infra`, and `backend/shared`, plus config, public schema, evaluation implementation/runner/tests, OpenSpec design/spec, and datasets.
- Residual risk: none
- Evidence: `@codex` review on 2026-07-15; evaluation and unit fingerprint tests now require version 2 and explicitly cover trace, terminology table, embedding, Milvus client, public schema, spec, and dataset paths.
- Disposition: validation
- Disposition target: docs/validation/rag-intent-routing-evaluation.md
- Resolution evidence: `routing_source_fingerprint()` expands and sorts the governed runtime globs before hashing; the validation report records the version 2 coverage boundary and bound digest.

## RAG-INTENT-F029

- Kind: evidence_gap
- Primary scope: rag.trace.retrieval_scope
- Evidence status: confirmed
- Observation: Comprehensive boost scope was represented only by false hard-filter flags, while branch diagnostics omitted the resolved scope source and matched files.
- Inference: API/history traces could not distinguish an ordinary document-hint boost from an unscoped global query, so rollout evidence could not verify the accepted shared-scope behavior.
- Decision: Serialize the resolved shared retrieval scope as mode/source/matched_files in the top-level comprehensive trace and every branch retrieval diagnostic, and preserve it through the public RagTrace schema.
- Residual risk: none
- Evidence: `@codex` review on 2026-07-15; focused pipeline and schema red/green tests cover boost/filter scope and public serialization.
- Disposition: closed_in_place
- Disposition target: null
- Resolution evidence: `backend/rag/pipeline.py`, `backend/contracts/schemas.py`, and the focused comprehensive/schema tests preserve identical scope telemetry without changing retrieval semantics.

## RAG-INTENT-F030

- Kind: evidence_gap
- Primary scope: evaluation.rag.degradation_rate
- Evidence status: confirmed
- Observation: Comprehensive summary counted only top-level stage_errors, while branch-local rerank failures can preserve candidates and be recorded solely in branch_errors or branch diagnostic error.
- Inference: The quality/cost activation gate could underreport branch error and degradation rates as zero.
- Decision: Count a case as error/degraded when stage_errors, branch_errors, or branch retrieval/rerank diagnostic errors are present.
- Residual risk: none
- Evidence: `@codex` review on 2026-07-15; parameterized evaluation red/green tests cover branch_errors and branch_diagnostics.
- Disposition: validation
- Disposition target: docs/validation/rag-intent-routing-evaluation.md
- Resolution evidence: `summarize_comprehensive_runs()` uses a shared error predicate for both error_rate and degradation_rate.

## RAG-INTENT-F031

- Kind: behavior_defect
- Primary scope: rag.comprehensive.auto_merge_provenance
- Evidence status: confirmed
- Observation: When comprehensive auto-merge replaced leaf candidates with a parent, branch ids/ranks were repaired but the public `multi_query_rrf_score` was not inherited.
- Inference: Parent chunks lost the cross-query ranking signal whenever auto-merge fired, making trace/API evaluation inconsistent with non-merged candidates.
- Decision: Inherit the maximum `multi_query_rrf_score` among contributing leaves while unioning parent provenance. Maximum preserves the strongest existing rank signal without inflating it by summing multiple child representations.
- Residual risk: none
- Evidence: `@codex` review on 2026-07-15; the shared structural pipeline red/green test reproduces a two-leaf parent replacement and verifies the inherited score.
- Disposition: closed_in_place
- Disposition target: null
- Resolution evidence: `_inherit_parent_provenance()` now restores the multi-query score together with branch ids, ranks, baseline state, and coverage.

## RAG-INTENT-F032

- Kind: behavior_defect
- Primary scope: rag.comprehensive.fanout_budget
- Evidence status: confirmed
- Observation: A schema-valid classifier response could contain an arbitrarily large sub_queries list, and every item was submitted for embedding plus Milvus retrieval before shared rerank budgets applied.
- Inference: One overlong LLM response could trigger dozens or hundreds of retrieval branches despite bounded postprocess cost.
- Decision: Bound generated fanout inside the RAG graph before retrieval. Default to 4 generated sub-queries, allow operator configuration from 1 through a hard maximum of 8, retain lower numeric priority first with stable original order for ties, and write the effective truncated plan back to graph state. Baseline remains additional.
- Residual risk: none
- Evidence: `@codex` review on 2026-07-15; user accepted default 4 plus priority-first truncation; runtime config, graph fanout, and public schema red/green tests cover bounds, selected order, retrieval call count, effective plan, and dropped-item telemetry.
- Disposition: validation
- Disposition target: docs/validation/rag-intent-routing-evaluation.md
- Resolution evidence: `backend/rag/runtime_config.py` bounds the setting; `decompose_and_fanout()` truncates before executor submission and reports requested/executed/truncated fields.

## RAG-INTENT-F033

- Kind: behavior_defect
- Primary scope: rag.retrieval.query_plan_activation
- Evidence status: confirmed
- Observation: Precise HyDE/step-back fallback derives a new plan by replacing `semantic_query`. Candidate preparation inferred plan activation from that difference, so a default-off compatibility plan could report `query_plan_enabled=true` and query-plan layers during expanded retrieval even though the initial retrieval correctly reported false.
- Inference: Default-off requests could change telemetry semantics during fallback and make rollout evidence falsely attribute legacy-compatible retrieval to QueryPlan behavior.
- Decision: Treat the initial retrieval's boolean `query_plan_enabled` trace as authoritative for all full and candidate-only expanded retrieval calls. Preserve legacy inference only when that trace field is absent.
- Residual risk: none
- Evidence: `@codex` review 4701746410 on 2026-07-15; `tests/unit/backend/rag/pipeline/test_rag_pipeline.py` reproduces both full and candidate-only drift before the fix and verifies explicit inactive propagation afterward.
- Disposition: closed_in_place
- Disposition target: null
- Resolution evidence: `backend/rag/pipeline.py::_expanded_query_plan_active()` forwards the initial activation state independently of rewritten query text; the focused fallback regression suite passes.
