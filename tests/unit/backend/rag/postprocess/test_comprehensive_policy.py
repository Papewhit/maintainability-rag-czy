from dataclasses import replace

import pytest

from backend.rag.comprehensive_postprocess import (
    BranchRetrievalResult,
    ComprehensivePostprocessPolicy,
    PriorityBudgetAllocator,
    build_retrieval_branches,
    merge_branch_results,
    resolve_comprehensive_postprocess_policy,
    select_branch_aware_top_k,
)
from backend.rag.query_plan import ComprehensiveQueryPlan, SubQuery


pytestmark = pytest.mark.unit


def _plan() -> ComprehensiveQueryPlan:
    return ComprehensiveQueryPlan(
        raw_query="对比方案",
        clean_query="对比方案",
        analysis_type="comparison",
        sub_queries=(
            SubQuery(query="方案 A", domain="A", priority=1),
            SubQuery(query="方案 B", domain="B", priority=3),
        ),
        coverage_domains=("A", "B"),
    )


def test_profile_registry_resolves_unknown_atomically_and_exposes_eval_ablation():
    quality = resolve_comprehensive_postprocess_policy("unknown-profile")
    ablation = resolve_comprehensive_postprocess_policy("eval_no_crossencoder_v1")

    assert quality.requested_profile == "unknown-profile"
    assert quality.effective_profile == "quality_first_v1"
    assert quality.warning
    assert quality.policy.branch_rerank_strategy_id == "crossencoder_local_v1"
    assert ablation.effective_profile == "eval_no_crossencoder_v1"
    assert ablation.policy.branch_rerank_strategy_id == "milvus_rank_only_v1"
    assert ablation.policy.merge_strategy_id == quality.policy.merge_strategy_id


def test_baseline_is_stable_and_not_a_coverage_domain():
    branches = build_retrieval_branches(_plan())

    assert [branch.branch_id for branch in branches] == ["baseline", "sub_query_0", "sub_query_1"]
    assert branches[0].branch_kind == "baseline"
    assert branches[0].query == "对比方案"
    assert branches[0].priority == 2
    assert branches[0].domain is None


def test_global_budget_is_shared_and_priority_weighted_not_copied_per_branch():
    branches = build_retrieval_branches(_plan())
    results = [
        BranchRetrievalResult(branch=branch, candidates=tuple({"chunk_id": f"{branch.branch_id}-{i}"} for i in range(10)))
        for branch in branches
    ]

    allocations = PriorityBudgetAllocator().allocate(
        results,
        output_candidate_budget=7,
        pair_budget=5,
    )

    assert sum(item.output_candidates for item in allocations.values()) == 7
    assert sum(item.pairs for item in allocations.values()) == 5
    assert allocations["sub_query_0"].output_candidates > allocations["sub_query_1"].output_candidates
    assert allocations["sub_query_0"].pairs >= allocations["sub_query_1"].pairs


def test_priority_weighting_remains_visible_after_a_complete_allocation_round():
    branches = build_retrieval_branches(_plan())
    results = [
        BranchRetrievalResult(
            branch=branch,
            candidates=tuple({"chunk_id": f"{branch.branch_id}-{index}"} for index in range(20)),
        )
        for branch in branches
    ]

    allocations = PriorityBudgetAllocator().allocate(
        results,
        output_candidate_budget=12,
        pair_budget=12,
    )

    assert allocations["sub_query_0"].output_candidates > allocations["baseline"].output_candidates
    assert allocations["baseline"].output_candidates > allocations["sub_query_1"].output_candidates


def test_policy_rejects_declared_strategy_that_does_not_match_implementation():
    policy = resolve_comprehensive_postprocess_policy("quality_first_v1").policy

    with pytest.raises(ValueError, match="strategy id"):
        replace(policy, merge_strategy_id="incompatible")


def test_weighted_rrf_deduplicates_and_unions_branch_provenance_without_raw_score_comparison():
    branches = build_retrieval_branches(_plan())
    results = [
        BranchRetrievalResult(
            branch=branches[0],
            candidates=(
                {"chunk_id": "shared", "rerank_score": 0.01},
                {"chunk_id": "baseline-only", "rerank_score": 99.0},
            ),
        ),
        BranchRetrievalResult(
            branch=branches[1],
            candidates=(
                {"chunk_id": "shared", "rerank_score": 0.02},
                {"chunk_id": "a-only", "rerank_score": 0.03},
            ),
        ),
        BranchRetrievalResult(
            branch=branches[2],
            candidates=({"chunk_id": "shared", "rerank_score": 1000.0},),
        ),
    ]

    merged, meta = merge_branch_results(results, rrf_k=60)

    shared = next(doc for doc in merged if doc["chunk_id"] == "shared")
    assert shared["matched_branch_ids"] == ["baseline", "sub_query_0", "sub_query_1"]
    assert shared["baseline_matched"] is True
    assert shared["coverage_count"] == 2
    assert shared["per_branch_local_rank"] == {"baseline": 1, "sub_query_0": 1, "sub_query_1": 1}
    assert "per_branch_rerank_score" in shared
    assert meta["merged_unique_candidate_count"] == 3


def test_final_selection_reserves_generated_branches_but_not_baseline_and_never_expands_top_k():
    branches = build_retrieval_branches(_plan())
    docs = [
        {"chunk_id": "baseline", "matched_branch_ids": ["baseline"], "baseline_matched": True},
        {"chunk_id": "a", "matched_branch_ids": ["sub_query_0"], "baseline_matched": False},
        {"chunk_id": "b", "matched_branch_ids": ["sub_query_1"], "baseline_matched": False},
        {"chunk_id": "extra", "matched_branch_ids": ["sub_query_0"], "baseline_matched": False},
    ]

    selected, meta = select_branch_aware_top_k(
        docs,
        branches=branches,
        successful_generated_branch_ids={"sub_query_0", "sub_query_1"},
        top_k=3,
    )

    assert len(selected) == 3
    assert {"a", "b"}.issubset({doc["chunk_id"] for doc in selected})
    assert meta["baseline_selected"] is True
    assert meta["represented_generated_branch_ids"] == ["sub_query_0", "sub_query_1"]


def test_when_generated_branches_exceed_top_k_priority_and_stable_id_choose_reservations():
    plan = ComprehensiveQueryPlan(
        raw_query="综合",
        clean_query="综合",
        analysis_type="general",
        sub_queries=(
            SubQuery(query="low", domain="low", priority=3),
            SubQuery(query="high-b", domain="high-b", priority=1),
            SubQuery(query="high-a", domain="high-a", priority=1),
        ),
        coverage_domains=("low", "high-b", "high-a"),
    )
    branches = build_retrieval_branches(plan)
    docs = [
        {"chunk_id": "low", "matched_branch_ids": ["sub_query_0"]},
        {"chunk_id": "high-b", "matched_branch_ids": ["sub_query_1"]},
        {"chunk_id": "high-a", "matched_branch_ids": ["sub_query_2"]},
    ]

    selected, meta = select_branch_aware_top_k(
        docs,
        branches=branches,
        successful_generated_branch_ids={"sub_query_0", "sub_query_1", "sub_query_2"},
        top_k=2,
    )

    assert {doc["chunk_id"] for doc in selected} == {"high-a", "high-b"}
    assert len(selected) == 2
