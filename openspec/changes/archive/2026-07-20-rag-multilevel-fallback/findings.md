---
document_type: finding_ledger
change: rag-multilevel-fallback
last_verified_commit: 230c3f3889eebea6210466e7be3fdbe9b0ea1d2f
last_verified_date: 2026-07-19
---

# Change Findings

## RAG-MF-F001

- Kind: design_ambiguity
- Primary scope: rag.retrieval
- Evidence status: confirmed
- Observation: `retrieve_initial()` already sends `context_files` into the main filtered retrieval and then separately calls `retrieve_context_documents()` once per file, appending those directly queried leaf chunks after the main postprocess/confidence result. The change spec also proposed relaxing every filter to boost/none and described disabled fallback as Level 3, conflicting with the explicit attachment boundary and current disabled-path behavior.
- Inference: Without a single evidence lifecycle, the router evaluates a different document set from the answer generator; relaxing an explicit attachment filter can also escape the user-selected evidence domain.
- Decision: Treat `context_files` as an immutable hard retrieval domain, remove the direct attachment supplement, run all candidates through one postprocess/confidence lifecycle per retrieval round, and preserve direct Level 0 answer generation when fallback is disabled.
- Residual risk: Requests with many attachments can enlarge the filtered candidate domain and may require candidate budget tuning; comprehensive intent still incurs its planned fan-out cost, but attachments must not introduce additional branches or per-file supplement queries.
- Evidence: `backend/rag/pipeline.py::retrieve_initial`; `backend/rag/utils.py::retrieve_context_documents`; `backend/rag/query_plan.py` context-files scope construction; `tests/unit/backend/rag/query_plan/test_document_scope_matching.py`; updated change design and delta spec.
- Disposition: change
- Disposition target: openspec/changes/rag-multilevel-fallback/
- Resolution evidence: The design, delta spec, and tasks now state the immutable attachment boundary, unified per-round evidence lifecycle, and disabled-path compatibility behavior.

## RAG-MF-F002

- Kind: design_ambiguity
- Primary scope: rag.query_plan
- Evidence status: confirmed
- Observation: `parse_query_plan()` currently emits filter when filename similarity reaches `DOC_SCOPE_MATCH_FILTER` (default 0.85), and applies `preferred_scope_mode` before score-based classification. `_precise_plan_from_decision()` passes classifier `scope_hint` as that preferred mode, while the classifier prompt does not define filter/boost/none semantics. `PreciseQueryPlan` has no source field; comprehensive `RetrievalScope.source` exists for provenance.
- Inference: If Level 2 preserves every filter without first hardening filter production, an incorrect classifier hint or high lexical filename match can lock all fallback attempts inside a file the user did not hard-select, and Level 3 can falsely attribute that boundary to the user.
- Decision: Define filter as the authoritative hard-scope behavior contract; allow only deterministic hard-range signals to produce it; prevent classifier hints and filename score alone from creating it. Fallback consumes only scope_mode. Keep comprehensive source as non-authoritative trace/provenance and do not add precise scope_source.
- Residual risk: Deterministic recognition of forms such as “《A》中……” needs negative and ambiguity coverage so ordinary document mentions are not overclassified as hard scope.
- Evidence: `backend/rag/query_plan.py::parse_query_plan` score/preferred-mode ordering; `backend/rag/intent.py::_precise_plan_from_decision`; `backend/rag/intent.py::INTENT_SYSTEM_PROMPT`; `backend/rag/query_plan.py::PreciseQueryPlan`; `backend/rag/query_plan.py::RetrievalScope`; updated change design, delta spec, and prerequisite tasks.
- Disposition: change
- Disposition target: openspec/changes/rag-multilevel-fallback/
- Resolution evidence: The change now makes trustworthy filter production an explicit prerequisite and specifies mode-only Level 2 behavior and scope-correct Level 3 disclosure.

## RAG-MF-F003

- Kind: design_ambiguity
- Primary scope: rag.query_plan
- Evidence status: confirmed
- Observation: Stage 1 review showed that a hard-scope document hint can resolve to multiple routable files, and that the lexical prefix `中` is ambiguous between a range marker (`《A》中说明步骤`) and common compounds (`《A》中心思想`). The prior artifacts did not define either boundary.
- Inference: Treating either case as an unconditional filter can lock fallback inside a domain the user did not uniquely select; treating every `中...` form as a compound would miss supported precise range syntax.
- Decision: Require unique resolution per hard-scope document hint. A hint matching multiple files produces at most boost, while multiple independent hard hints that each resolve uniquely may form a combined filter. Treat common `中` compounds such as 中心、中文、中英文、中外、中长期、中短期、中间 and 中部 as non-range text; keep `《A》中说明步骤` as a precise range.
- Residual risk: Natural-language compounds outside the governed examples may require later evidence and an artifact update; they are not grounds for adding open-ended compatibility heuristics in this change.
- Evidence: Stage 1 dual-subagent review reproducer; user confirmation on 2026-07-17; updated design and delta specs; targeted query-plan regression tests.
- Disposition: change
- Disposition target: openspec/changes/rag-multilevel-fallback/
- Resolution evidence: The confirmed boundaries are now explicit scenarios and task 0.5 requires unique/multi-match and lexical-confusion coverage.

## RAG-MF-F004

- Kind: design_ambiguity
- Primary scope: rag.configuration
- Evidence status: confirmed
- Observation: Stage 1 implementation briefly introduced silent clamping for non-positive fallback budgets even though no requirement or failing regression defined that behavior.
- Inference: Rejecting, clamping, disabling, or immediately routing to Level 3 are distinct compatibility contracts and must not be chosen implicitly.
- Decision: The supported budget configuration domain is positive integer milliseconds. Non-positive values are unsupported; this change adds no validation or compatibility interpretation for them.
- Residual risk: A future configuration-hardening change may define validation if production evidence establishes a need.
- Evidence: Stage 1 dual-subagent review; removal of the unmapped clamp; user confirmation on 2026-07-17; updated budget requirement and design.
- Disposition: change
- Disposition target: openspec/changes/rag-multilevel-fallback/
- Resolution evidence: The supported-domain boundary is explicit and the implementation contains no new non-positive-budget validation branch.

## RAG-MF-F005

- Kind: design_ambiguity
- Primary scope: rag.fallback.execution
- Evidence status: confirmed
- Observation: Stage 2 artifacts required a `max_candidate_k`, a concrete same-root relaxation, and behavior for multiple failed comprehensive branches, but did not define their runtime values or selection rule.
- Inference: Choosing new limits or processing every failed branch implicitly would alter latency, recall, and LLM-call contracts without an approved boundary.
- Decision: Reuse `RAG_FALLBACK_EXPANDED_CANDIDATE_K` as the Level 2 candidate ceiling; increase `same_root_cap` by 1 for the Level 2 round; sort failed generated branches by priority then stable branch_id and rewrite at most `RAG_FALLBACK_COMPREHENSIVE_REWRITE_WINDOW` branches per round, default 2.
- Residual risk: The chosen limits require later evaluation data; this change does not retune them without evidence.
- Evidence: Stage 2 artifact/code audit and user confirmation on 2026-07-17; updated proposal, design, delta spec, and tasks.
- Disposition: change
- Disposition target: openspec/changes/rag-multilevel-fallback/
- Resolution evidence: The formerly undefined boundaries are explicit scenarios and configuration tasks before implementation.

## RAG-MF-F006

- Kind: evidence_gap
- Primary scope: rag.fallback.routing_order
- Evidence status: confirmed
- Observation: The user requested that future work weigh whether scope relax should precede query rewrite for some confidence patterns instead of always using the current Level 1 → Level 2 order.
- Inference: A different order could improve some weak-scope cases but could also widen retrieval prematurely; this requires evaluation rather than a compatibility branch in the current implementation.
- Decision: Keep the confirmed Level 1 → Level 2 order for this change. Before any future ordering change, create or amend an OpenSpec change with signal-specific scenarios and comparative quality/latency evidence.
- Residual risk: The current fixed ordering may spend Level 1 budget on queries whose dominant problem is scope rather than formulation.
- Evidence: User request on 2026-07-17; no comparative evaluation evidence yet.
- Disposition: enhancement
- Disposition target: docs/enhancements/rag-fallback-routing-order-evaluation.md
- Resolution evidence: The candidate enhancement records the evaluation question, non-goals, evidence dependencies, and requirement for a separately authorized OpenSpec change. RAG-MF-F026 later adds real signal-directed `[2, 3]` path evidence and refines the question from a nominal fixed order to direct-Level-2 backfill.

## RAG-MF-F007

- Kind: behavior_defect
- Primary scope: rag.fallback.budget
- Evidence status: confirmed
- Observation: Stage 2 review showed that Level 2 did not create its own deadline and that precise/comprehensive full postprocess rounds executed synchronously outside the Level 1/2 deadlines.
- Inference: Supported slow retrieval or rerank paths could exceed both per-level and total hard budgets even though entry checks passed.
- Decision: Bound every precise and comprehensive retrieval-plus-postprocess round with `min(total_deadline, level_started + level_budget)` and return to the router on timeout while preserving the previous round evidence.
- Residual risk: None within the thread-based timeout contract; already-running Python threads may finish in the background, as they cannot be force-terminated safely.
- Evidence: Stage 2 code review execution-path analysis; four deterministic slow-round regression tests for precise/comprehensive Level 1/2.
- Disposition: change
- Disposition target: openspec/changes/rag-multilevel-fallback/
- Resolution evidence: Level-specific round wrappers and timeout regressions close the reachable budget violation.

## RAG-MF-F008

- Kind: behavior_defect
- Primary scope: rag.comprehensive.confidence
- Evidence status: confirmed
- Observation: Comprehensive confidence classified a generated branch as failed only when both `error` and empty candidates were present; a normal zero-candidate result with `error=None` was omitted.
- Inference: A supported empty generated sub-query could fail silently, leaving Level 1 rewrite unreachable even while a planned coverage dimension had no evidence.
- Decision: Treat every empty generated branch as failed for comprehensive confidence while continuing to exclude the clean-query baseline from rewrite targets.
- Residual risk: None.
- Evidence: Stage 2 spec review reproducer and `test_comprehensive_confidence_treats_normal_empty_generated_recall_as_failure`.
- Disposition: change
- Disposition target: openspec/changes/rag-multilevel-fallback/
- Resolution evidence: Comprehensive confidence now emits `generated_branch_failure` for normal empty generated recall.

## RAG-MF-F009

- Kind: behavior_defect
- Primary scope: rag.fallback.rewrite_continuity
- Evidence status: confirmed
- Observation: Precise strategy selection saw raw query, anchors, document hints, and scope, but the actual step-back/HyDE generation prompts received only semantic text. Level 2 also used a generic strategy token and could replace HyDE/complex retrieval input with `expanded_query`.
- Inference: Level 1 generation lacked required plan context, and Level 2 could unintentionally undo the Level 1 query rewrite instead of changing only scope/candidate parameters.
- Decision: Pass plan context separately into the existing generation prompts, keep semantic text as the query, and reuse the active Level 1 expansion strategy when Level 2 reruns retrieval.
- Residual risk: None.
- Evidence: Independent OpenSpec verification, Stage 2 spec review reproducer, prompt-context regression, and HyDE/complex Level 2 query-form regressions.
- Disposition: change
- Disposition target: openspec/changes/rag-multilevel-fallback/
- Resolution evidence: Generation prompts and Level 2 round selection now preserve the typed plan and prior rewrite form without restoring raw retrieval input.

## RAG-MF-F010

- Kind: design_ambiguity
- Primary scope: rag.fallback.level3
- Evidence status: confirmed
- Observation: The comprehensive Level 3 requirement asked for each successful sub-query's “corresponding answer”, but the graph has only branch candidates at that point and Level 3 is explicitly template-only without an LLM. The baseline-only scenario also made background evidence optional.
- Inference: Treating a candidate chunk as a generated answer, omitting all successful evidence, or adding an LLM call would create materially different answer and latency contracts.
- Decision: For each successful generated dimension, output the dimension name and a clearly labelled evidence excerpt, never call it a generated answer. When only the clean-query baseline has candidates, output exactly one excerpt labelled as general background evidence that does not count toward analysis coverage.
- Residual risk: Evidence excerpts are not synthesized prose; users may still need to reformulate the query or provide more source material.
- Evidence: Stage 3 artifact audit and user confirmation on 2026-07-17; updated design, delta spec, and task 6.3.
- Disposition: change
- Disposition target: openspec/changes/rag-multilevel-fallback/
- Resolution evidence: The evidence-only partial-answer choice was implemented, then explicitly reopened by the user on 2026-07-17 and later resolved by RAG-MF-F018; the baseline-only decision remained confirmed throughout.

## RAG-MF-F011

- Kind: evidence_gap
- Primary scope: rag.testing
- Evidence status: confirmed
- Observation: M10.1 and M10.2 referenced new or existing test files directly under `tests/`, while repository governance requires all tests to be routed by execution cost and product area and explicitly forbids new root-level test files.
- Inference: Copying equivalent tests to the obsolete paths would duplicate evidence and violate the authoritative test taxonomy without improving behavioral coverage.
- Decision: Route disabled-path regressions to `tests/unit/backend/rag/pipeline/` and pure signal/graph coverage to `tests/unit/backend/rag/fallback/` plus `tests/unit/backend/rag/pipeline/`; update the task ledger to name those authoritative files.
- Residual risk: None.
- Evidence: Repository `AGENTS.md` test taxonomy; 31 passing disabled-path, pipeline, pure-router, and graph-routing tests on 2026-07-17.
- Disposition: change
- Disposition target: openspec/changes/rag-multilevel-fallback/
- Resolution evidence: M10.1 and M10.2 now point to the governed test locations and are backed by passing targeted evidence.

## RAG-MF-F012

- Kind: design_ambiguity
- Primary scope: rag.answer_delivery
- Evidence status: confirmed
- Observation: The Level 3 design said the template used no LLM and named chat prompt injection, but the supported optional-tool path performs retrieval only after answer-message preparation, inside the existing agent execution.
- Inference: Restricting delivery to forced-preload, refactoring optional-tool into eager retrieval, or placing the template in tool output are materially different execution contracts.
- Decision: Keep the existing execution policies. forced-preload delivers the template constraint in a system message; optional-tool delivers the same constraint in the tool response before retrieval content, after which the existing agent LLM completes the answer. Only template generation is prohibited from calling an LLM.
- Residual risk: optional-tool final wording is mediated by the existing agent model rather than byte-identical direct return.
- Evidence: Stage 3 execution-path audit and user confirmation on 2026-07-17; updated design, delta spec, and delivery task.
- Disposition: change
- Disposition target: openspec/changes/rag-multilevel-fallback/
- Resolution evidence: Both supported delivery modes now have one explicit, shared instruction contract without an execution-policy refactor.

## RAG-MF-F013

- Kind: design_ambiguity
- Primary scope: rag.fallback.level2_disclosure
- Evidence status: confirmed
- Observation: Level 2 supports `scope_mode=none` remaining none, but the disclosure scenarios defined only boost-to-none and filter-preserved paths.
- Inference: Reusing the boost wording would falsely claim a preferred file and outside-scope retrieval; omitting disclosure would violate the Level 2 prompt requirement.
- Decision: For none-to-none, state that no exact match was found, candidate-pool and structural constraints were relaxed, and the document retrieval range did not change.
- Residual risk: None.
- Evidence: Stage 3 artifact/code audit and user confirmation on 2026-07-17; updated design and delta spec.
- Disposition: change
- Disposition target: openspec/changes/rag-multilevel-fallback/
- Resolution evidence: The supported none-to-none path now has an explicit scenario and exact disclosure text.

## RAG-MF-F014

- Kind: behavior_defect
- Primary scope: rag.fallback.level3
- Evidence status: confirmed
- Observation: Comprehensive Level 3 derives coverage and excerpts from raw `branch_retrieval_results`, so a branch candidate rejected by shared final top-k can re-enter the answer and `level3_uncovered_sub_queries` trace.
- Inference: The answer and router would describe different evidence sets, violating the current change's unified evidence lifecycle and making an unavailable dimension appear covered.
- Decision: Derive comprehensive coverage, excerpts, baseline use, and Level 3 trace only from branch identities actually represented by the current round final top-k.
- Residual risk: None after the final-top-k identity regression is covered.
- Evidence: Stage 3 code review reproducer produced `RAW_COST_REJECTED` in a 2/2 Level 3 answer although final docs represented only the risk branch.
- Disposition: change
- Disposition target: openspec/changes/rag-multilevel-fallback/
- Resolution evidence: `level3_insufficient_evidence_node` and `generate_level3_answer` now consume only final documents; the raw-candidate rejection regression passes under tasks 6.3c and 6.7.

## RAG-MF-F015

- Kind: design_ambiguity
- Primary scope: rag.fallback.budget
- Evidence status: confirmed
- Observation: Design and delta spec promised an independent Level 3 budget while proposal, tasks, runtime configuration, migration guidance, and implementation exposed only total, Level 1, and Level 2 budgets.
- Inference: Applying “insufficient remaining budget enters Level 3” to Level 3 itself has no defined terminal behavior and would require a new configuration and exception path.
- Decision: Level 3 is a deterministic terminal step governed only by the total fallback budget; it has no independent budget configuration or entry threshold.
- Residual risk: Level 3 delivery still uses the existing answer model after deterministic template generation, so end-to-end response time remains observable through the total timing rather than a new Level 3 setting.
- Evidence: Stage 3 spec review and user decision `1A` on 2026-07-17.
- Disposition: change
- Disposition target: openspec/changes/rag-multilevel-fallback/
- Resolution evidence: Proposal, design, delta spec, and task 1.6 now state the same total/L1/L2 budget contract.

## RAG-MF-F016

- Kind: design_ambiguity
- Primary scope: rag.fallback.trace
- Evidence status: confirmed
- Observation: The generic trace scenario required `level1_strategy` and `level1_rewritten_query` for every Level 1 execution, while comprehensive rewrite recorded only dedicated ordered-list fields and emitted `strategy="comprehensive"` only in a step event.
- Inference: A comprehensive multi-branch rewrite cannot be represented faithfully by the precise path's scalar rewritten-query convention without a type decision.
- Decision: Comprehensive Level 1 records `level1_strategy="comprehensive"` and a `level1_rewritten_query: list[str]` flattened in stable selected-branch/output order; precise Level 1 retains a scalar string.
- Residual risk: Trace consumers must branch on `level1_strategy` before interpreting the union-typed rewritten-query field.
- Evidence: Stage 3 code/spec audit and user decision `2B` on 2026-07-17.
- Disposition: change
- Disposition target: openspec/changes/rag-multilevel-fallback/
- Resolution evidence: Artifact contract and comprehensive trace implementation now agree; stable ordered-list regression passes under tasks 4.8 and 6.7.

## RAG-MF-F017

- Kind: design_ambiguity
- Primary scope: rag.fallback.level3
- Evidence status: confirmed
- Observation: Final top-k can represent all generated dimensions while the aggregate confidence gate still routes to Level 3; the partial-coverage template then reports Y/Y but incorrectly recommends filling missing dimensions.
- Inference: Coverage and aggregate confidence are distinct signals and need a deterministic full-coverage/low-confidence terminal state.
- Decision: Coverage means final evidence availability. For Y/Y with insufficient aggregate confidence, state that every dimension has related evidence but overall confidence is insufficient, show labelled evidence excerpts, and recommend source verification or more discriminative query conditions without mentioning missing dimensions.
- Residual risk: The excerpts remain evidence, not a synthesized answer.
- Evidence: Stage 3 code review execution-path analysis and user confirmation `3认可` on 2026-07-17.
- Disposition: change
- Disposition target: openspec/changes/rag-multilevel-fallback/
- Resolution evidence: Artifact contract and deterministic Y/Y template now agree; full-coverage/low-confidence regression passes under tasks 6.3b and 6.7.

## RAG-MF-F018

- Kind: design_ambiguity
- Primary scope: rag.fallback.level3
- Evidence status: confirmed
- Observation: The previously confirmed evidence-only template for comprehensive Level 3 partial coverage may be less useful than allowing the existing answer model to synthesize an answer from successful sub-query evidence while explicitly leaving uncovered dimensions unresolved.
- Inference: Evidence-only delivery and partial synthesis have different answer, hallucination, citation, prompt, and acceptance contracts; implementing both or silently retaining either as final would violate the user's SPEC DECISION rule.
- Decision: For `0 < X < Y`, use the existing answer model to generate separate partial answers only for covered dimensions from final-top-k excerpts with existing filename/page provenance; state overall insufficiency, list uncovered dimensions, and prohibit answering them or producing cross-dimension comparison, summary, or overall recommendations. Keep Y/Y low-confidence, baseline-only, and no-evidence modes evidence-only. Add no new retrieval or LLM call.
- Residual risk: Final prose remains model-mediated, so prompt regressions could overstate completeness; both delivery modes therefore share one explicit constraint and require regression coverage.
- Evidence: User selected option B on 2026-07-17 after reviewing the evidence-only, partial-only synthesis, and all-coverage synthesis alternatives.
- Disposition: change
- Disposition target: openspec/changes/rag-multilevel-fallback/
- Resolution evidence: The deterministic partial template now carries source provenance and synthesis prohibitions through both shared delivery modes; focused Level 3 and output delivery tests pass under task 6.3.

## RAG-MF-F019

- Kind: technical_debt
- Primary scope: rag.fallback.configuration
- Evidence status: confirmed
- Observation: Explicit `RAG_FALLBACK_ENABLED` deprecation logging occurs in `load_runtime_config()`, which can be called by multiple graph nodes, so a request may emit the same advisory more than once.
- Inference: The current contract requires a deprecation warning but does not require once-only emission; no failing regression or runtime log evidence shows user-visible harm, and adding process-global guard state would introduce an unmapped abstraction.
- Decision: Classify as a non-blocking suggestion and do not remediate in this change. Reopen only with operational evidence or an explicit once-only logging requirement.
- Residual risk: Duplicate advisory log lines may occur when the master switch is explicitly set.
- Evidence: Stage 3 code review call-path inspection; no failing test or reproducer satisfying the user-defined blocking P2 threshold.
- Disposition: enhancement
- Disposition target: docs/enhancements/rag-fallback-deprecation-warning-deduplication.md
- Resolution evidence: ENH-RAG-0005 records the evidence threshold and explicitly does not authorize a guard in this change.

## RAG-MF-F020

- Kind: documentation_drift
- Primary scope: documentation.rag.fallback
- Evidence status: confirmed
- Observation: The design called P95 5-7s an observed result while real-environment evaluation and metric tasks 10.3-10.5 remain incomplete.
- Inference: Keeping the wording would overstate evidence confidence even though it does not alter runtime behavior.
- Decision: Label 5-7s only as a target pending real evaluation, and align the no-evidence scenario wording with the already confirmed final-top-k authority boundary.
- Residual risk: Actual P95 remains unknown until `rag-multilevel-fallback-activation` can run against a representative real corpus and release index.
- Evidence: Stage 3 remediation spec review; unchecked tasks 10.3-10.5 and absence of a validation report.
- Disposition: change
- Disposition target: openspec/changes/rag-multilevel-fallback-activation/
- Resolution evidence: Design no longer claims measured latency, the delta spec uses final-top-k semantics without changing the F014 contract, and the remaining real P95 evidence now has an independent activation owner.

## RAG-MF-F021

- Kind: behavior_defect
- Primary scope: rag.fallback.evidence_lifecycle
- Evidence status: confirmed
- Observation: If comprehensive Level 1 decompose changes sub-query indices and the complete rerun times out, the timeout fallback retains the new plan beside the previous round final documents; Level 3 then assigns an old branch identity to the wrong new dimension.
- Inference: Plan and evidence cease to describe one completed round, so even final-top-k-only consumption cannot prevent false attribution.
- Decision: Complete fallback rounds commit plan and evidence atomically; timeout or failure returns the previous completed plan, final documents, and branch identities while retaining timeout diagnostics and rewrite trace.
- Residual risk: None after decompose-timeout and scope-relax-timeout states share this atomic rollback rule.
- Evidence: Stage 3 remediation code-review reproducer and failing regression `test_comprehensive_decompose_timeout_keeps_previous_completed_plan_and_evidence`.
- Disposition: change
- Disposition target: openspec/changes/rag-multilevel-fallback/
- Resolution evidence: Complete comprehensive rounds now accept an explicit previous completed state for atomic timeout/failure rollback; the decompose-timeout attribution regression passes under task 2.10.

## RAG-MF-F022

- Kind: technical_debt
- Primary scope: rag.fallback.level3
- Evidence status: confirmed
- Observation: Level 3 template coverage requires non-empty final document text, while trace coverage currently keys only on final document branch provenance; a hypothetical final document with provenance but empty text could make template and trace disagree.
- Inference: No reviewed evidence shows empty-body final documents are supported input, so adding validation or fallback behavior in this change would expand the contract without a failing supported-path regression.
- Decision: Do not add a validation branch in this change. First establish the final-document content invariant or a supported empty-body reproducer, then define one template/trace rule.
- Residual risk: If empty-body final documents can reach the supported postprocess output, Level 3 trace may overstate usable coverage.
- Evidence: Stage 3 remediation code review; no supported data-contract evidence or failing regression was identified.
- Disposition: enhancement
- Disposition target: docs/enhancements/rag-level3-empty-final-evidence-consistency.md
- Resolution evidence: ENH-RAG-0006 records the evidence prerequisite and does not authorize protective compatibility behavior.

## RAG-MF-F023

- Kind: behavior_defect
- Primary scope: rag.fallback.level3
- Evidence status: confirmed
- Observation: F018(B) keeps baseline-only evidence-only, but the baseline template labels background evidence without explicitly prohibiting the existing answer model from turning it into an analysis answer.
- Inference: The shared delivery wrapper prohibits unsupported facts but still permits synthesis from the baseline excerpt, so 0/Y could be presented as an analysis despite baseline not counting toward coverage.
- Decision: Add an explicit baseline-only delivery constraint that permits displaying the general background excerpt but forbids generating an analysis answer from it.
- Residual risk: None after both delivery modes receive the same deterministic prohibition.
- Evidence: Task 6.3 code review of the reachable baseline-only template and shared delivery instruction.
- Disposition: change
- Disposition target: openspec/changes/rag-multilevel-fallback/
- Resolution evidence: The baseline-only template now explicitly permits evidence display but prohibits analysis generation; the focused negative regression passes under task 6.3d.

## RAG-MF-F024

- Kind: behavior_defect
- Primary scope: rag.evaluation
- Evidence status: confirmed
- Observation: The single full regression run reported two source-fingerprint failures because `routing_source_fingerprint()` unconditionally reads historical `rag-intent-routing` OpenSpec files that are absent from the clean `rag-fusion-design` merge-base.
- Inference: The implementation and failing tests have zero diff from the merge-base, so this is not caused by `rag-multilevel-fallback` and does not satisfy the user-defined blocking P2 rule's current-change-contract condition. Adding a missing-file compatibility path here would also introduce an unmapped validation branch.
- Decision: Do not remediate in this change. Preserve the full-run result as `830 passed, 2 failed, 2 skipped, 7 deselected`; validate the fallback implementation through its green targeted suites.
- Residual risk: Clean-worktree full regressions continue to report the two unrelated failures until the fingerprint authority set is repaired.
- Evidence: Full regression `uv run pytest tests -m "not slow and not e2e" -q` on 2026-07-17; both failures are `FileNotFoundError` for `openspec/changes/rag-intent-routing/design.md`; merge-base `cbcd3de07c3b0544701d778e6315b0216a857027` contains neither path and has no relevant implementation/test diff.
- Disposition: known_issue
- Disposition target: docs/known-issues/intent-routing-fingerprint-archived-openspec-paths.md
- Resolution evidence: KI-RAG-0007 records the clean-worktree reproducer and requires a durable-authority correction outside this change; no protective compatibility behavior was added.

## RAG-MF-F025

- Kind: behavior_defect
- Primary scope: rag.fallback.evidence_lifecycle
- Evidence status: confirmed
- Observation: A precise Level 2 `boost → none` attempt that times out during complete postprocess retained the previous round documents but returned the relaxed `none` plan and `level2_new_scope_mode`, so Level 3 could describe an unscoped search that never completed.
- Inference: This reachable supported path violates the existing complete-round atomic state scenario and combines a new plan with old final evidence.
- Decision: When the precise Level 2 round returns no completed result, retain its timeout/failure diagnostics but restore the previous completed state and report the previous scope mode as the effective `level2_new_scope_mode`.
- Residual risk: None after precise and comprehensive incomplete rounds share the same plan/evidence rollback outcome.
- Evidence: First GitHub Codex review on PR #5; failing regression `test_precise_level_two_uses_own_deadline_for_complete_postprocess_round` reproduced `scope_mode=none` beside the previous Level 0 documents.
- Disposition: change
- Disposition target: openspec/changes/rag-multilevel-fallback/
- Resolution evidence: The precise Level 2 incomplete-round branch now restores the prior state while preserving diagnostics; the regression asserts both plan equality and effective scope trace rollback.

## RAG-MF-F026

- Kind: evaluation_result
- Primary scope: rag.fallback.routing_order
- Evidence status: confirmed
- Observation: A real precise query with only `weak_margin_and_root` entered Level 2 directly and, after Level 2 retained the same signal, terminated at Level 3 without attempting Level 1; the persisted path was `[2, 3]`.
- Inference: The current implementation is signal-directed rather than an unconditional Level 1 → Level 2 chain. The existing future-ordering question must include whether a failed direct-Level-2 path should evaluate query rewrite before Level 3, while separating ordering effects from confidence and candidate-cap defects.
- Decision: Do not change routing in this change. Add the runtime evidence and refined comparison matrix to the existing routing-order enhancement.
- Residual risk: A query whose signal selects Level 2 can reach Level 3 without testing whether rewrite would recover evidence, even when scope relaxation does not address the actual failure.
- Evidence: Session `session_1784383996604`, assistant message `13`, on 2026-07-18: `top_score=0.87475`, `confidence_reasons=[weak_margin_and_root]`, decisions `Level 2 weak_margin_and_root` then `Level 3 levels_exhausted`, and `fallback_path=[2, 3]`; an earlier same-query run reached Level 3 before Level 2 because reranking exhausted the remaining budget.
- Disposition: enhancement
- Disposition target: docs/enhancements/rag-fallback-routing-order-evaluation.md
- Resolution evidence: ENH-RAG-0004 now records the direct-Level-2 behavior, backfill evaluation question, latency-state comparison, and confounders without authorizing an order change.

## RAG-MF-F027

- Kind: behavior_defect
- Primary scope: rag.fallback.level2
- Evidence status: confirmed
- Observation: In the same real Level 2 run, the trace recorded `candidate_k: 120 -> 50` because the prior-round candidate count exceeded the reused `RAG_FALLBACK_EXPANDED_CANDIDATE_K=50` ceiling.
- Inference: `min(max_candidate_k, ceil(current_candidate_k * 1.5))` can narrow the candidate pool, contradicting the existing Level 2 enlargement contract and M5 acceptance boundary on a reachable positive configuration.
- Decision: Treat the reused setting as an expansion ceiling rather than permission to shrink a completed prior pool. Compute the effective value as the larger of the prior completed candidate_k and the capped 1.5x growth target; preserve the prior value when the configured ceiling is lower.
- Residual risk: A ceiling below the prior value prevents candidate-count growth, so Level 2 may rely only on its other relaxations; it no longer makes the retry strictly narrower.
- Evidence: Session `session_1784383996604`, assistant message `13`, on 2026-07-18; `backend/rag/fallback_scope.py`; existing `test_level2_candidate_k_grows_by_one_point_five_and_respects_existing_cap` cases cover only current values at or below the cap.
- Disposition: change
- Disposition target: openspec/changes/rag-multilevel-fallback/
- Resolution evidence: The updated Level 2 contract prohibits candidate shrink; task 5.11 passes both the pure rule and graph-node `120 → 120` regressions. KI-RAG-0009 retains the runtime history as mitigated pending a live rerun.

## RAG-MF-F028

- Kind: evidence_gap
- Primary scope: evaluation.rag.fallback.activation
- Evidence status: confirmed
- Observation: The current environment cannot prepare a representative real corpus, release Milvus/BM25 index, stable answer/judge models and reviewed query set, so tasks 10.3-10.5 cannot produce valid quality, routing, P95 or budget evidence inside the implementation PR.
- Inference: This is the same implementation-versus-activation boundary already established for intent routing; leaving the tasks in the implementation change would either block default-disabled code indefinitely or invite non-representative evidence.
- Decision: Migrate real query-set evaluation, metric thresholds and data-driven budget tuning to the independent `rag-multilevel-fallback-activation` change. Treat the current change as complete default-disabled implementation only; its merge is not activation evidence.
- Residual risk: Production quality, routing proportions, P95 and tuned budgets remain unknown until the activation change obtains the required external environment and passes its gate.
- Evidence: User decision on 2026-07-19; current tasks 10.3-10.5; absence of usable release corpus/index and activation-grade model/query-set identities; established `rag-intent-routing-activation` precedent.
- Disposition: change
- Disposition target: openspec/changes/rag-multilevel-fallback-activation/
- Resolution evidence: The new change contains proposal, design, normative activation spec and tasks for real identity binding, evaluation, thresholds, budget tuning, coordinated canary and rollback.

## RAG-MF-F029

- Kind: documentation_drift
- Primary scope: documentation.rag.anchor-routing
- Evidence status: confirmed
- Observation: KI-RAG-0006 still described multilevel fallback and the comprehensive fallback graph as planned or unimplemented after this change implemented both, which could make maintainers misjudge the remaining anchor-routing risk.
- Inference: The known issue remains open for atomic capability configuration and shared anchor grammar, but its fallback status and resolution criteria must distinguish implemented wiring from missing real activation evidence.
- Decision: Update KI-RAG-0006 to describe the current implemented default-disabled fallback boundary and point real behavior evaluation to the new activation change without claiming the broader anchor issue is resolved.
- Residual risk: Atomic configuration and shared anchor normalization remain unresolved; fallback activation evidence is also pending.
- Evidence: Current fallback graph and architecture in this PR; stale KI-RAG-0006 Observed Behavior, Evidence and Resolution Criteria text.
- Disposition: known_issue
- Disposition target: docs/known-issues/anchor-capability-configuration.md
- Resolution evidence: KI-RAG-0006 now separates implemented fallback wiring from the still-open anchor contract and activation gates.

## RAG-MF-F030

- Kind: behavior_defect
- Primary scope: rag.fallback.level1.comprehensive
- Evidence status: confirmed
- Observation: When only the clean-query baseline branch fails and no generated sub-query is eligible for rewrite, `_level1_comprehensive()` still initializes the rewrite model before observing the empty selected-branch set. Model initialization can fail before the node returns the required no-rewrite result.
- Inference: This is blocking under the current P2 rule: it violates the explicit baseline-no-rewrite scenario, is reachable with comprehensive fallback enabled, has a failing regression in the supported unit configuration, and the minimal fix does not expand the contract.
- Decision: Initialize the rewrite model only when `select_failed_generated_branches()` returns at least one eligible generated branch; keep baseline-only failure diagnostics and the existing empty rewrite trace unchanged.
- Residual risk: None; generated-branch rewrite continues to use the same model path, while an empty rewrite target set no longer creates an unrelated model dependency.
- Evidence: Failing `test_comprehensive_baseline_failure_does_not_call_rewriter` on reviewed commit `230c3f3`, where eager model construction raised before the baseline-only result; strengthened regression asserts that model lookup, rewrite, and rerun are all skipped.
- Disposition: change
- Disposition target: openspec/changes/rag-multilevel-fallback/
- Resolution evidence: `_level1_comprehensive()` now gates model initialization on a non-empty generated-branch selection; the focused test and 134-test fallback/OpenSpec scenario suite pass.

## RAG-MF-F031

- Kind: design_ambiguity
- Primary scope: rag.query-preparation.scope
- Evidence status: confirmed
- Observation: For a precise hard-scope query such as `只基于《A》说明步骤`, query preparation consumes the resolved `《A》` document span but retains `只基于` in `semantic_query`; the same occurs for a prefix before an exact `《A》中` range.
- Inference: This P2 is advisory rather than blocking under the current rule. The path is reachable, but no current MUST requires the prefix itself to be consumed and no failing regression establishes its ownership. Multi-document prefixes, conjunctions, punctuation, negation and unresolved hints require a specification decision before changing cleanup behavior.
- Decision: Do not implement the reviewer's single cleanup interpretation in this PR. Preserve the question in an enhancement and require explicit OpenSpec scenarios before code changes.
- Residual risk: Closed-scope control wording may add low-value terms to dense/sparse retrieval inside the already-correct hard document filter.
- Evidence: Codex review on commit `230c3f3`; direct `parse_query_plan()` reproductions for `只基于《A》说明步骤`, `仅在《A》中说明步骤`, and the multi-document form; current deterministic query-preparation and hard-filter requirements.
- Disposition: enhancement
- Disposition target: docs/enhancements/rag-closed-scope-prefix-consumption.md
- Resolution evidence: ENH-RAG-0008 records the ownership ambiguity, affected forms, non-goals and required future specification decisions without changing the current contract.

## RAG-MF-F032

- Kind: behavior_defect
- Primary scope: rag.trace.public-api
- Evidence status: confirmed
- Observation: `POST /chat` validates graph output through `ChatResponse` / `RagTrace`, but the schema did not declare the multilevel fallback fields, so Pydantic dropped `fallback_level`, `fallback_path`, `fallback_decisions`, Level 1/2 details and Level 3 delivery fields from the supported non-streaming response.
- Inference: This P3 is blocking under the current rule: public trace completeness is an explicit current-change requirement, the non-streaming chat path is supported, a failing serialization regression reproduces the loss, and declaring the already-existing fields in the existing schema does not expand the contract.
- Decision: Add only the existing documented multilevel trace fields to `RagTrace`, preserving the precise scalar versus comprehensive list type of `level1_rewritten_query`; do not add new runtime fields or compatibility behavior.
- Residual risk: Internal diagnostic-only fields not named by the current trace contract remain outside the public response schema.
- Evidence: Codex review on commit `230c3f3`; failing `test_rag_trace_schema_preserves_multilevel_fallback_fields` with `KeyError: fallback_level` before remediation.
- Disposition: change
- Disposition target: openspec/changes/rag-multilevel-fallback/
- Resolution evidence: The public schema now round-trips the documented Level 0/1/2/3 fields; the focused schema regression passes.
