from dataclasses import replace
from unittest.mock import patch

import pytest

import backend.rag.pipeline as rag_pipeline
import backend.rag.utils as rag_utils
from backend.rag.comprehensive_postprocess import (
    BranchRetrievalResult,
    build_retrieval_branches,
    resolve_comprehensive_postprocess_policy,
)
from backend.rag.intent import IntentParseResult
from backend.rag.query_plan import ComprehensiveQueryPlan, SubQuery
from backend.rag.runtime_config import load_runtime_config


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

    def intent_node(state):
        return {
            "intent_result": intent_result,
            "query_plan": plan,
            "query_plan_type": "comprehensive",
            "raw_query": plan.raw_query,
            "clean_query": plan.clean_query,
            "semantic_query": plan.clean_query,
            "rag_trace": dict(intent_result.trace),
        }

    def retrieve(query, **kwargs):
        return {
            "candidates": [{"chunk_id": query, "text": f"evidence:{query}", "rrf_rank": 1}],
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
        patch("backend.rag.pipeline.intent_parse_node", side_effect=intent_node),
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
