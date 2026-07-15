from dataclasses import replace
from unittest.mock import patch

import pytest

import backend.rag.pipeline as rag_pipeline
import backend.rag.utils as rag_utils
from backend.rag.comprehensive_postprocess import (
    BranchRetrievalResult,
    build_retrieval_branches,
    resolve_comprehensive_postprocess_policy,
    run_shared_postprocess,
)
from backend.rag.intent import IntentParseResult
from backend.rag.query_plan import ComprehensiveQueryPlan, RetrievalScope, SubQuery
from backend.rag.runtime_config import load_runtime_config
from backend.contracts.schemas import ChatResponse, MessageInfo


pytestmark = pytest.mark.unit


def _plan() -> ComprehensiveQueryPlan:
    return ComprehensiveQueryPlan(
        raw_query="《记录汇编》中，综合风险",
        clean_query="综合风险",
        analysis_type="general",
        sub_queries=(
            SubQuery(query="机械风险", domain="mechanical", priority=1),
            SubQuery(query="电气风险", domain="electrical", priority=2),
        ),
        coverage_domains=("mechanical", "electrical"),
    )


def test_fanout_uses_clean_query_baseline_and_each_branch_runs_independent_preflight():
    config = replace(load_runtime_config({}), rerank_candidate_pool_size=6)
    calls = []

    def retrieve(query, **kwargs):
        calls.append(query)
        if query == "电气风险":
            raise RuntimeError("electrical unavailable")
        return {
            "candidates": [{"chunk_id": query, "rrf_rank": 1}],
            "meta": {
                "semantic_query": query,
                "normalized_query": f"norm:{query}",
                "sparse_expansion": f"sparse:{query}",
                "term_matches": [{"surface": query}],
                "stage_errors": [],
                "timings": {},
                "dense_embedding_call_count": 1,
                "sparse_embedding_call_count": 1,
                "hybrid_search_call_count": 1,
                "split_search_call_count": 1,
            },
        }

    with (
        patch("backend.rag.pipeline.load_runtime_config", return_value=config),
        patch("backend.rag.pipeline.retrieve_candidate_pool", side_effect=retrieve),
    ):
        result = rag_pipeline.decompose_and_fanout(
            {
                "question": _plan().raw_query,
                "context_files": [],
                "query_plan": _plan(),
                "query_plan_type": "comprehensive",
                "rag_trace": {"intent": "comprehensive_analysis"},
            }
        )

    assert set(calls) == {"综合风险", "机械风险", "电气风险"}
    assert len(result["branch_retrieval_results"]) == 3
    baseline = next(item for item in result["branch_retrieval_results"] if item.branch.branch_id == "baseline")
    failed = next(item for item in result["branch_retrieval_results"] if item.branch.branch_id == "sub_query_1")
    assert baseline.meta["normalized_query"] == "norm:综合风险"
    assert failed.error == "electrical unavailable"
    assert result["rag_trace"]["retrieval_branch_count"] == 3
    assert result["rag_trace"]["sub_query_count"] == 2
    assert result["rag_trace"]["dense_embedding_call_count"] == 2
    assert result["rag_trace"]["sparse_embedding_call_count"] == 2
    assert result["rag_trace"]["embedding_call_count"] == 4
    assert result["rag_trace"]["hybrid_search_call_count"] == 2
    assert result["rag_trace"]["split_search_call_count"] == 2


def test_fanout_marks_non_throwing_failed_retrieval_for_comprehensive_confidence():
    plan = _plan()

    def retrieve(query, **kwargs):
        if query == "机械风险":
            return {
                "candidates": [],
                "meta": {
                    "retrieval_mode": "failed",
                    "stage_errors": [{"stage": "dense_retrieve", "error": "dense down"}],
                    "timings": {},
                },
            }
        return {
            "candidates": [{"chunk_id": query, "filename": "manual.pdf", "text": query}],
            "meta": {"retrieval_mode": "hybrid", "stage_errors": [], "timings": {}},
        }

    with patch("backend.rag.pipeline.retrieve_candidate_pool", side_effect=retrieve):
        fanout = rag_pipeline.decompose_and_fanout(
            {
                "question": plan.raw_query,
                "context_files": [],
                "query_plan": plan,
                "query_plan_type": "comprehensive",
                "rag_trace": {},
            }
        )

    failed = next(
        item
        for item in fanout["branch_retrieval_results"]
        if item.branch.branch_id == "sub_query_0"
    )
    assert failed.error == "dense down"
    diagnostics = {
        item["branch_id"]: item
        for item in fanout["rag_trace"]["branch_retrieval_diagnostics"]
    }
    assert diagnostics["sub_query_0"]["error"] == "dense down"

    pass_stage = lambda docs, top_k: (docs, {})
    _, trace = run_shared_postprocess(
        fanout["comprehensive_policy_resolution"].policy,
        plan,
        fanout["branch_retrieval_results"],
        top_k=5,
        auto_merge_fn=pass_stage,
        step_chain_fn=pass_stage,
        structure_rerank_fn=pass_stage,
        confidence_fn=lambda query, docs: {
            "confidence_gate_enabled": True,
            "fallback_required": False,
        },
    )

    assert trace["comprehensive_confidence_inputs"]["failed_generated_branch_ids"] == [
        "sub_query_0"
    ]
    assert trace["fallback_required"] is True
    assert "generated_branch_failure" in trace["confidence_reasons"]


@pytest.mark.parametrize(
    ("scope_mode", "source"),
    [("boost", "document_hints"), ("filter", "explicit_closed_scope")],
)
def test_fanout_applies_one_shared_scope_plan_to_every_branch(scope_mode, source):
    plan = replace(
        _plan(),
        retrieval_scope=RetrievalScope(
            scope_mode=scope_mode,
            matched_files=(("记录汇编.pdf", 1.0),),
            doc_hints=("记录汇编",),
            source=source,
        ),
    )
    calls = []

    def retrieve(query, **kwargs):
        calls.append((query, kwargs))
        return {"candidates": [], "meta": {"timings": {}, "stage_errors": []}}

    with patch("backend.rag.pipeline.retrieve_candidate_pool", side_effect=retrieve):
        result = rag_pipeline.decompose_and_fanout(
            {
                "question": plan.raw_query,
                "context_files": [],
                "query_plan": plan,
                "query_plan_type": "comprehensive",
                "rag_trace": {},
            }
        )

    assert {query for query, _ in calls} == {"综合风险", "机械风险", "电气风险"}
    assert all(kwargs["query_plan"].scope_mode == scope_mode for _, kwargs in calls)
    assert all(kwargs["query_plan"].matched_files == (("记录汇编.pdf", 1.0),) for _, kwargs in calls)
    assert all(kwargs["query_plan_active"] is True for _, kwargs in calls)
    assert all(
        kwargs["strict_scope_filter"] is (scope_mode == "filter")
        for _, kwargs in calls
    )
    assert result["rag_trace"]["query_plan_enabled"] is True
    assert result["rag_trace"]["scope_filter_applied"] is (scope_mode == "filter")
    assert result["rag_trace"]["strict_scope_filter"] is (scope_mode == "filter")
    assert all(
        diagnostic["strict_scope_filter"] is (scope_mode == "filter")
        for diagnostic in result["rag_trace"]["branch_retrieval_diagnostics"]
    )


def test_each_branch_independently_composes_dense_and_bm25_from_its_own_query():
    preflight_inputs = []
    embedding_inputs = []

    def preflight(query):
        preflight_inputs.append(query)
        return {
            "term_matches": [{"surface": query}],
            "normalized_query": f"dense:{query}",
            "sparse_expansion": f"bm25:{query}",
            "protected_tokens": [query],
        }

    def embed(dense_query, timings, stage_errors, *, sparse_query):
        embedding_inputs.append((dense_query, sparse_query))
        return rag_utils.QueryEmbeddings([0.1], {1: 1.0})

    def retrieve(embeddings, **kwargs):
        return rag_utils.CandidateRetrievalResult(
            candidates=[{"chunk_id": str(len(embedding_inputs)), "rrf_rank": 1}],
            retrieval_mode="hybrid",
        )

    with (
        patch("backend.rag.pipeline.retrieve_candidate_pool", side_effect=rag_utils.retrieve_candidate_pool),
        patch("backend.rag.utils.terminology_preflight", side_effect=preflight),
        patch("backend.rag.utils.embed_search_query", side_effect=embed),
        patch("backend.rag.utils.retrieve_global_candidates", side_effect=retrieve),
    ):
        result = rag_pipeline.decompose_and_fanout(
            {
                "question": _plan().raw_query,
                "context_files": [],
                "query_plan": _plan(),
                "query_plan_type": "comprehensive",
                "rag_trace": {},
            }
        )

    expected = {"综合风险", "机械风险", "电气风险"}
    assert set(preflight_inputs) == expected
    assert set(embedding_inputs) == {(f"dense:{query}", f"bm25:{query}") for query in expected}
    assert all(result.meta["term_matches"] for result in result["branch_retrieval_results"])


@pytest.mark.parametrize(
    ("configured_pool", "expected_budget"),
    [(0, 6), (2, 5)],
)
def test_comprehensive_branch_budget_reuses_effective_rerank_pool_rules(
    configured_pool,
    expected_budget,
):
    plan = _plan()
    branches = build_retrieval_branches(plan)
    branch_results = [
        BranchRetrievalResult(
            branch=branch,
            candidates=tuple(
                {"chunk_id": f"{branch.branch_id}-{index}"}
                for index in range(2)
            ),
        )
        for branch in branches
    ]
    config = replace(
        load_runtime_config({}),
        rerank_candidate_pool_size=configured_pool,
        rerank_top_n=0,
        rerank_input_k_cpu=20,
    )

    with (
        patch("backend.rag.pipeline._runtime_config", return_value=config),
        patch(
            "backend.rag.pipeline.run_branch_rerank",
            return_value=(branch_results, {}),
        ) as rerank,
    ):
        rag_pipeline.branch_rerank_node(
            {
                "comprehensive_policy_resolution": resolve_comprehensive_postprocess_policy(
                    "quality_first_v1"
                ),
                "branch_retrieval_results": branch_results,
                "rag_trace": {},
            }
        )

    assert rerank.call_args.kwargs["output_candidate_budget"] == expected_budget


def test_graph_routes_by_plan_type_without_profile_specific_conditionals():
    graph = rag_pipeline.build_rag_graph()
    nodes = set(graph.get_graph().nodes)

    assert {
        "intent_parse",
        "decompose_and_fanout",
        "branch_rerank",
        "merge_sub_query_results",
        "shared_postprocess",
    }.issubset(nodes)


def test_shared_postprocess_preserves_actual_upstream_merge_timing():
    plan = _plan()
    branches = build_retrieval_branches(plan)
    branch_results = [
        BranchRetrievalResult(
            branch=branches[0],
            candidates=({"chunk_id": "baseline", "matched_branch_ids": ["baseline"]},),
        )
    ]
    pass_stage = lambda docs, top_k: (docs, {})

    with (
        patch("backend.rag.pipeline._auto_merge_documents", side_effect=pass_stage),
        patch("backend.rag.pipeline._step_chain_check", side_effect=pass_stage),
        patch("backend.rag.pipeline._apply_structure_rerank", side_effect=pass_stage),
        patch(
            "backend.rag.pipeline._evaluate_retrieval_confidence",
            return_value={"fallback_required": False},
        ),
    ):
        result = rag_pipeline.shared_postprocess_node(
            {
                "query_plan": plan,
                "comprehensive_policy_resolution": resolve_comprehensive_postprocess_policy(
                    "quality_first_v1"
                ),
                "branch_rerank_results": branch_results,
                "merged_candidates": list(branch_results[0].candidates),
                "merge_meta": {"merged_unique_candidate_count": 1},
                "rag_trace": {"timings": {"multi_query_merge_ms": 123.456}},
            }
        )

    assert result["rag_trace"]["timings"]["multi_query_merge_ms"] == 123.456


def test_comprehensive_graph_runs_once_and_returns_merged_context_with_full_trace():
    plan = _plan()
    intent_result = IntentParseResult(
        intent="comprehensive_analysis",
        confidence=0.9,
        query_plan=plan,
        trace={
            "intent": "comprehensive_analysis",
            "intent_confidence": 0.9,
            "query_plan_type": "comprehensive",
            "intent_fallback_to_rules": False,
        },
    )

    def retrieve(query, **kwargs):
        return {
            "candidates": [{
                "chunk_id": query,
                "filename": "manual.pdf",
                "text": f"evidence:{query}",
                "rrf_rank": 1,
            }],
            "meta": {"term_matches": [{"surface": query}], "timings": {}, "stage_errors": []},
        }

    def rerank(**kwargs):
        return kwargs["docs"][: kwargs["top_k"]], {
            "rerank_applied": True,
            "rerank_input_count": len(kwargs["docs"]),
        }

    pass_stage = lambda docs, top_k: (docs, {})
    config = replace(
        load_runtime_config({}),
        rerank_candidate_pool_size=6,
        rerank_input_k_cpu=6,
    )

    with (
        patch("backend.rag.pipeline.build_intent_parse_result", return_value=intent_result),
        patch("backend.rag.pipeline.retrieve_candidate_pool", side_effect=retrieve),
        patch("backend.rag.pipeline._rerank_documents", side_effect=rerank),
        patch("backend.rag.pipeline._rerank_device_tier", return_value="cpu"),
        patch("backend.rag.pipeline._runtime_config", return_value=config),
        patch("backend.rag.pipeline._auto_merge_documents", side_effect=pass_stage),
        patch("backend.rag.pipeline._step_chain_check", side_effect=pass_stage),
        patch("backend.rag.pipeline._apply_structure_rerank", side_effect=pass_stage),
        patch("backend.rag.pipeline._evaluate_retrieval_confidence", return_value={"fallback_required": False}),
    ):
        graph = rag_pipeline.build_rag_graph()
        result = graph.invoke(
            {
                "question": plan.raw_query,
                "query": plan.raw_query,
                "context": "",
                "docs": [],
                "context_files": [],
                "rag_trace": None,
            }
        )

    assert len(result["docs"]) == 3
    assert "evidence:综合风险" in result["context"]
    assert result["rag_trace"]["intent_confidence"] == 0.9
    assert result["rag_trace"]["sub_query_count"] == 2
    assert result["rag_trace"]["retrieval_branch_count"] == 3
    assert result["rag_trace"]["rerank_pair_count"] == 3
    assert result["rag_trace"]["shared_postprocess_count"] == 1
    assert result["rag_trace"]["tool_used"] is True
    assert result["rag_trace"]["tool_name"] == "search_knowledge_base"
    assert result["rag_trace"]["branch_candidate_count"] == 3
    assert result["rag_trace"]["deduplicated_candidate_count"] == 0

    chat_payload = ChatResponse(
        response="ok",
        rag_trace=result["rag_trace"],
    ).model_dump()["rag_trace"]
    message_payload = MessageInfo(
        type="assistant",
        content="ok",
        timestamp="2026-07-15T00:00:00Z",
        rag_trace=result["rag_trace"],
    ).model_dump()["rag_trace"]
    assert chat_payload["branch_candidate_count"] == 3
    assert message_payload["deduplicated_candidate_count"] == 0


def test_multi_query_merge_failure_preserves_candidates_and_complete_trace():
    class FailingMerger:
        strategy_id = "failing_merge_v1"

        def merge(self, branch_results, *, rrf_k):
            del branch_results, rrf_k
            raise RuntimeError("merge exploded")

    plan = _plan()
    branches = build_retrieval_branches(plan)
    resolution = resolve_comprehensive_postprocess_policy("quality_first_v1")
    failing_merger = FailingMerger()
    policy = replace(
        resolution.policy,
        merger=failing_merger,
        merge_strategy_id=failing_merger.strategy_id,
    )
    resolution = replace(resolution, policy=policy)
    branch_results = [
        BranchRetrievalResult(
            branches[0],
            (
                {"chunk_id": "shared", "text": "baseline shared"},
                {"chunk_id": "baseline-only", "text": "baseline only"},
            ),
            {},
        ),
        BranchRetrievalResult(
            branches[1],
            (
                {"chunk_id": "shared", "text": "generated shared"},
                {"chunk_id": "generated-only", "text": "generated only"},
            ),
            {},
        ),
        BranchRetrievalResult(branches[2], (), {}, "branch unavailable"),
    ]

    result = rag_pipeline.merge_sub_query_results(
        {
            "comprehensive_policy_resolution": resolution,
            "branch_rerank_results": branch_results,
            "rag_trace": {
                "tool_used": True,
                "tool_name": "search_knowledge_base",
                "stage_errors": [],
            },
        }
    )

    assert len(result["merged_candidates"]) == 4
    trace = result["rag_trace"]
    assert trace["multi_query_merge_skipped"] is True
    assert trace["multi_query_merge_error"] == "merge exploded"
    assert trace["branch_candidate_count"] == 4
    assert trace["merged_candidate_count"] == 4
    assert trace["merged_unique_candidate_count"] == 3
    assert trace["deduplicated_candidate_count"] == 0
    assert trace["stage_errors"][-1] == {
        "stage": "multi_query_merge",
        "error": "merge exploded",
        "fallback_to": "branch_union",
    }
    by_text = {doc["text"]: doc for doc in result["merged_candidates"]}
    assert by_text["baseline shared"]["matched_branch_ids"] == ["baseline"]
    assert by_text["baseline shared"]["per_branch_local_rank"] == {"baseline": 1}
    assert by_text["baseline shared"]["baseline_matched"] is True
    assert by_text["generated shared"]["matched_branch_ids"] == ["sub_query_0"]
    assert by_text["generated shared"]["per_branch_local_rank"] == {"sub_query_0": 1}
    assert by_text["generated shared"]["baseline_matched"] is False

    pass_stage = lambda docs, top_k: (docs, {})
    with (
        patch("backend.rag.pipeline._auto_merge_documents", side_effect=pass_stage),
        patch("backend.rag.pipeline._step_chain_check", side_effect=pass_stage),
        patch("backend.rag.pipeline._apply_structure_rerank", side_effect=pass_stage),
        patch(
            "backend.rag.pipeline._evaluate_retrieval_confidence",
            return_value={"fallback_required": False, "confidence_gate_enabled": True},
        ),
    ):
        postprocessed = rag_pipeline.shared_postprocess_node(
            {
                "query_plan": plan,
                "comprehensive_policy_resolution": resolution,
                "branch_rerank_results": branch_results,
                "merged_candidates": result["merged_candidates"],
                "merge_meta": result["merge_meta"],
                "rag_trace": trace,
            }
        )

    assert postprocessed["docs"]
    assert postprocessed["rag_trace"]["represented_generated_branch_ids"] == ["sub_query_0"]
    assert postprocessed["rag_trace"]["comprehensive_confidence_inputs"]["missing_generated_branch_ids"] == []
    assert postprocessed["rag_trace"]["stage_errors"][-1]["fallback_to"] == "branch_union"

    payload = ChatResponse(response="ok", rag_trace=trace).model_dump()["rag_trace"]
    assert payload["multi_query_merge_skipped"] is True
    assert payload["multi_query_merge_error"] == "merge exploded"
    assert payload["merged_candidate_count"] == 4
