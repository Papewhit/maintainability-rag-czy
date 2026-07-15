from dataclasses import replace

import pytest

from backend.rag.comprehensive_postprocess import (
    BranchRetrievalResult,
    build_retrieval_branches,
    resolve_comprehensive_postprocess_policy,
    run_branch_rerank,
    run_shared_postprocess,
)
from backend.rag.query_plan import ComprehensiveQueryPlan, SubQuery
from backend.rag.context import apply_structure_rerank


pytestmark = pytest.mark.unit


def _plan() -> ComprehensiveQueryPlan:
    return ComprehensiveQueryPlan(
        raw_query="综合记录",
        clean_query="综合记录",
        analysis_type="general",
        sub_queries=(SubQuery(query="机械风险", domain="mechanical", priority=1),),
        coverage_domains=("mechanical",),
    )


def test_branch_rerank_uses_branch_query_terms_and_partial_failure_keeps_local_candidates():
    branches = build_retrieval_branches(_plan())
    inputs = [
        BranchRetrievalResult(
            branch=branches[0],
            candidates=({"chunk_id": "base"},),
            meta={"term_matches": [{"surface": "综合"}]},
        ),
        BranchRetrievalResult(
            branch=branches[1],
            candidates=({"chunk_id": "generated"},),
            meta={"term_matches": [{"surface": "机械"}]},
        ),
    ]
    calls = []

    def rerank_fn(*, query, docs, top_k, query_term_matches):
        calls.append((query, query_term_matches))
        if query == "机械风险":
            raise RuntimeError("branch failure")
        return list(docs[:top_k]), {"rerank_applied": True, "rerank_input_count": len(docs)}

    policy = resolve_comprehensive_postprocess_policy("quality_first_v1").policy
    results, trace = run_branch_rerank(
        policy,
        inputs,
        output_candidate_budget=4,
        pair_budget=4,
        rerank_fn=rerank_fn,
    )

    assert calls == [("综合记录", [{"surface": "综合"}]), ("机械风险", [{"surface": "机械"}])]
    failed = next(item for item in results if item.branch.branch_id == "sub_query_0")
    assert failed.candidates[0]["chunk_id"] == "generated"
    assert failed.error == "branch failure"
    assert trace["branch_errors"][0]["branch_kind"] == "sub_query"


def test_branch_rerank_caps_output_when_reranker_expands_requested_top_k():
    branch = build_retrieval_branches(_plan())[0]
    inputs = [
        BranchRetrievalResult(
            branch=branch,
            candidates=tuple({"chunk_id": f"candidate-{index}"} for index in range(5)),
        )
    ]

    def expanding_rerank(**kwargs):
        return list(kwargs["docs"]), {"rerank_input_count": len(kwargs["docs"])}

    results, trace = run_branch_rerank(
        resolve_comprehensive_postprocess_policy("quality_first_v1").policy,
        inputs,
        output_candidate_budget=2,
        pair_budget=5,
        rerank_fn=expanding_rerank,
    )

    assert len(results[0].candidates) == 2
    assert results[0].meta["used_output_budget"] == 2
    assert trace["used_output_budget"] == 2


def test_branch_rerank_fills_output_quota_with_unpaired_local_rank_tail():
    branch = build_retrieval_branches(_plan())[0]
    inputs = [
        BranchRetrievalResult(
            branch=branch,
            candidates=tuple(
                {"chunk_id": f"candidate-{index}"}
                for index in range(4)
            ),
        )
    ]

    def rerank_pairs(**kwargs):
        reranked = [dict(doc, rerank_score=1.0 - index) for index, doc in enumerate(reversed(kwargs["docs"]))]
        return reranked, {"rerank_input_count": len(kwargs["docs"])}

    results, trace = run_branch_rerank(
        resolve_comprehensive_postprocess_policy("quality_first_v1").policy,
        inputs,
        output_candidate_budget=4,
        pair_budget=2,
        rerank_fn=rerank_pairs,
    )

    assert [doc["chunk_id"] for doc in results[0].candidates] == [
        "candidate-1",
        "candidate-0",
        "candidate-2",
        "candidate-3",
    ]
    assert results[0].meta["used_pair_budget"] == 2
    assert results[0].meta["used_output_budget"] == 4
    assert trace["used_output_budget"] == 4


def test_pair_budget_exhaustion_never_clears_unreranked_branch_candidates():
    branches = build_retrieval_branches(
        ComprehensiveQueryPlan(
            raw_query="综合",
            clean_query="综合",
            analysis_type="general",
            sub_queries=(
                SubQuery(query="high", domain="high", priority=1),
                SubQuery(query="low", domain="low", priority=3),
            ),
            coverage_domains=("high", "low"),
        )
    )
    inputs = [
        BranchRetrievalResult(branch=branch, candidates=({"chunk_id": branch.branch_id},))
        for branch in branches
    ]
    calls = []

    def rerank_fn(**kwargs):
        calls.append(kwargs["query"])
        return kwargs["docs"], {"rerank_input_count": len(kwargs["docs"])}

    results, trace = run_branch_rerank(
        resolve_comprehensive_postprocess_policy("quality_first_v1").policy,
        inputs,
        output_candidate_budget=3,
        pair_budget=1,
        rerank_fn=rerank_fn,
    )

    assert calls == ["high"]
    assert all(result.candidates for result in results)
    exhausted = [item for item in trace["branch_diagnostics"] if item["branch_rerank_budget_exhausted"]]
    assert {item["branch_id"] for item in exhausted} == {"baseline", "sub_query_1"}
    assert trace["rerank_pair_count"] == 1


def test_zero_and_missing_pair_quotas_never_exceed_global_output_budget():
    branches = build_retrieval_branches(
        ComprehensiveQueryPlan(
            raw_query="综合",
            clean_query="综合",
            analysis_type="general",
            sub_queries=(
                SubQuery(query="high", domain="high", priority=1),
                SubQuery(query="low", domain="low", priority=3),
            ),
            coverage_domains=("high", "low"),
        )
    )
    inputs = [
        BranchRetrievalResult(
            branch=branch,
            candidates=tuple(
                {"chunk_id": f"{branch.branch_id}-{index}"}
                for index in range(5)
            ),
        )
        for branch in branches
    ]

    results, trace = run_branch_rerank(
        resolve_comprehensive_postprocess_policy("quality_first_v1").policy,
        inputs,
        output_candidate_budget=2,
        pair_budget=1,
        rerank_fn=lambda **kwargs: (
            kwargs["docs"],
            {"rerank_input_count": len(kwargs["docs"])},
        ),
    )

    assert sum(len(result.candidates) for result in results) == 2
    assert trace["used_output_budget"] == 2
    assert trace["rerank_pair_count"] == 1


def test_rerank_exception_preserves_local_rank_only_within_output_quota():
    branch = build_retrieval_branches(_plan())[0]
    inputs = [
        BranchRetrievalResult(
            branch=branch,
            candidates=tuple({"chunk_id": f"candidate-{index}"} for index in range(5)),
        )
    ]

    def failing_rerank(**kwargs):
        raise RuntimeError("rerank unavailable")

    results, trace = run_branch_rerank(
        resolve_comprehensive_postprocess_policy("quality_first_v1").policy,
        inputs,
        output_candidate_budget=2,
        pair_budget=5,
        rerank_fn=failing_rerank,
    )

    assert len(results[0].candidates) == 2
    assert results[0].meta["used_output_budget"] == 2
    assert results[0].meta["used_pair_budget"] == 5
    assert trace["used_output_budget"] == 2


def test_eval_ablation_never_allocates_or_executes_crossencoder_pairs():
    branches = build_retrieval_branches(_plan())
    inputs = [
        BranchRetrievalResult(branch=branch, candidates=({"chunk_id": branch.branch_id},))
        for branch in branches
    ]

    def forbidden_rerank(**kwargs):
        raise AssertionError(f"unexpected rerank call: {kwargs}")

    results, trace = run_branch_rerank(
        resolve_comprehensive_postprocess_policy("eval_no_crossencoder_v1").policy,
        inputs,
        output_candidate_budget=4,
        pair_budget=99,
        rerank_fn=forbidden_rerank,
    )

    assert all(result.candidates for result in results)
    assert trace["allocated_pair_budget"] == 0
    assert trace["used_pair_budget"] == 0
    assert trace["rerank_pair_count"] == 0


def test_eval_ablation_enforces_zero_output_quota():
    branches = build_retrieval_branches(_plan())
    inputs = [
        BranchRetrievalResult(
            branch=branch,
            candidates=tuple(
                {"chunk_id": f"{branch.branch_id}-{index}"}
                for index in range(5)
            ),
        )
        for branch in branches
    ]

    results, trace = run_branch_rerank(
        resolve_comprehensive_postprocess_policy("eval_no_crossencoder_v1").policy,
        inputs,
        output_candidate_budget=1,
        pair_budget=99,
        rerank_fn=lambda **kwargs: (_ for _ in ()).throw(AssertionError("unused")),
    )

    assert sum(len(result.candidates) for result in results) == 1
    assert trace["used_output_budget"] == 1


def test_shared_structural_stages_execute_once_and_parent_inherits_provenance():
    branches = build_retrieval_branches(_plan())
    reranked = [
        BranchRetrievalResult(
            branch=branches[0],
            candidates=({"chunk_id": "leaf-a", "parent_chunk_id": "parent", "rrf_rank": 1},),
        ),
        BranchRetrievalResult(
            branch=branches[1],
            candidates=({"chunk_id": "leaf-b", "parent_chunk_id": "parent", "rrf_rank": 1},),
        ),
    ]
    calls = {"auto": 0, "step": 0, "structure": 0, "confidence": 0}

    def auto_merge(docs, top_k):
        calls["auto"] += 1
        return [{"chunk_id": "parent", "merged_from_children": True}], {"auto_merge_applied": True}

    def step_chain(docs, top_k):
        calls["step"] += 1
        return docs, {"step_chain_check_enabled": True}

    def structure(docs, top_k):
        calls["structure"] += 1
        return docs, {"structure_rerank_applied": True}

    def confidence(query, docs):
        calls["confidence"] += 1
        return {"fallback_required": False}

    docs, trace = run_shared_postprocess(
        resolve_comprehensive_postprocess_policy("quality_first_v1").policy,
        _plan(),
        reranked,
        top_k=5,
        auto_merge_fn=auto_merge,
        step_chain_fn=step_chain,
        structure_rerank_fn=structure,
        confidence_fn=confidence,
    )

    assert calls == {"auto": 1, "step": 1, "structure": 1, "confidence": 1}
    assert docs[0]["matched_branch_ids"] == ["baseline", "sub_query_0"]
    assert docs[0]["baseline_matched"] is True
    assert docs[0]["coverage_count"] == 1
    assert trace["shared_postprocess_count"] == 1
    assert trace["shared_postprocess_version"] == "shared-postprocess-v1"
    assert trace["timings"]["auto_merge_ms"] >= 0
    assert trace["timings"]["structure_rerank_ms"] >= 0
    assert trace["timings"]["confidence_ms"] >= 0


def test_structure_root_cap_cannot_remove_required_generated_branch_reservation():
    plan = ComprehensiveQueryPlan(
        raw_query="比较",
        clean_query="比较",
        analysis_type="comparison",
        sub_queries=(
            SubQuery(query="A", domain="A", priority=1),
            SubQuery(query="B", domain="B", priority=2),
        ),
        coverage_domains=("A", "B"),
    )
    branches = build_retrieval_branches(plan)
    results = [
        BranchRetrievalResult(
            branch=branches[1],
            candidates=({"chunk_id": "a", "root_chunk_id": "same-root", "rerank_score": 0.9},),
        ),
        BranchRetrievalResult(
            branch=branches[2],
            candidates=({"chunk_id": "b", "root_chunk_id": "same-root", "rerank_score": 0.8},),
        ),
    ]
    pass_stage = lambda docs, top_k: (docs, {})

    docs, trace = run_shared_postprocess(
        resolve_comprehensive_postprocess_policy("quality_first_v1").policy,
        plan,
        results,
        top_k=2,
        auto_merge_fn=pass_stage,
        step_chain_fn=pass_stage,
        structure_rerank_fn=lambda docs, top_k: apply_structure_rerank(
            docs,
            top_k,
            enabled=True,
            root_weight=0.3,
            same_root_cap=1,
        ),
        confidence_fn=lambda query, docs: {"fallback_required": False},
    )

    assert {doc["chunk_id"] for doc in docs} == {"a", "b"}
    assert trace["represented_generated_branch_ids"] == ["sub_query_0", "sub_query_1"]
    assert trace["structure_reservation_restored_branch_ids"] == ["sub_query_1"]


def test_selector_failure_degrades_to_structured_top_k_with_stage_error():
    class BrokenSelector:
        strategy_id = "broken_selector_v1"

        def select(self, *args, **kwargs):
            raise RuntimeError("selector failed")

    plan = _plan()
    branches = build_retrieval_branches(plan)
    results = [
        BranchRetrievalResult(branch=branches[1], candidates=({"chunk_id": "candidate"},)),
    ]
    base_policy = resolve_comprehensive_postprocess_policy("quality_first_v1").policy
    policy = replace(
        base_policy,
        final_selector=BrokenSelector(),
        final_selection_strategy_id="broken_selector_v1",
    )
    pass_stage = lambda docs, top_k: (docs, {})

    docs, trace = run_shared_postprocess(
        policy,
        plan,
        results,
        top_k=1,
        auto_merge_fn=pass_stage,
        step_chain_fn=pass_stage,
        structure_rerank_fn=pass_stage,
        confidence_fn=lambda query, docs: {"fallback_required": False},
    )

    assert [doc["chunk_id"] for doc in docs] == ["candidate"]
    assert trace["final_selection_skipped"] is True
    assert trace["final_selection_error"] == "selector failed"
    assert any(error["stage"] == "final_selection" for error in trace["stage_errors"])


def test_shared_stage_failures_record_skipped_flags_and_individual_timings():
    branches = build_retrieval_branches(_plan())
    results = [
        BranchRetrievalResult(branch=branches[1], candidates=({"chunk_id": "candidate"},)),
    ]

    def fail(stage):
        def invoke(*args, **kwargs):
            raise RuntimeError(f"{stage} failed")

        return invoke

    docs, trace = run_shared_postprocess(
        resolve_comprehensive_postprocess_policy("quality_first_v1").policy,
        _plan(),
        results,
        top_k=1,
        auto_merge_fn=fail("auto"),
        step_chain_fn=fail("step"),
        structure_rerank_fn=fail("structure"),
        confidence_fn=fail("confidence"),
    )

    assert docs
    assert trace["auto_merge_skipped"] is True
    assert trace["step_chain_skipped"] is True
    assert trace["structure_rerank_skipped"] is True
    assert trace["confidence_gate_skipped"] is True
    assert {
        "auto_merge_ms",
        "step_chain_ms",
        "structure_rerank_ms",
        "final_selection_ms",
        "confidence_ms",
    }.issubset(trace["timings"])


def test_comprehensive_confidence_uses_generated_failures_but_never_targets_baseline_failure():
    branches = build_retrieval_branches(_plan())
    failed_results = [
        BranchRetrievalResult(branch=branches[0], error="baseline unavailable"),
        BranchRetrievalResult(branch=branches[1], error="generated unavailable"),
    ]
    pass_stage = lambda docs, top_k: (docs, {})

    _, trace = run_shared_postprocess(
        resolve_comprehensive_postprocess_policy("quality_first_v1").policy,
        _plan(),
        failed_results,
        top_k=5,
        auto_merge_fn=pass_stage,
        step_chain_fn=pass_stage,
        structure_rerank_fn=pass_stage,
        confidence_fn=lambda query, docs: {
            "confidence_gate_enabled": True,
            "fallback_required": False,
            "confidence_reasons": [],
        },
    )

    inputs = trace["comprehensive_confidence_inputs"]
    assert inputs["failed_generated_branch_ids"] == ["sub_query_0"]
    assert inputs["baseline_hit"] is False
    assert trace["fallback_required"] is True
    assert trace["confidence_reasons"] == ["generated_branch_failure"]
    assert "baseline" not in trace["confidence_reasons"]
