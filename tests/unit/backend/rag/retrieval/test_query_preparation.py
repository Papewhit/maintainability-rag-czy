from unittest.mock import patch

import pytest

import backend.rag.utils as rag_utils
from backend.rag.query_plan import PreciseQueryPlan


pytestmark = pytest.mark.unit


def _plan(*, raw_query: str, semantic_query: str) -> PreciseQueryPlan:
    return PreciseQueryPlan(
        raw_query=raw_query,
        clean_query=semantic_query,
        semantic_query=semantic_query,
        scope_mode="none",
        route="global_hybrid",
    )


def _retrieval_result() -> rag_utils.CandidateRetrievalResult:
    return rag_utils.CandidateRetrievalResult(
        candidates=[{"chunk_id": "c1", "text": "result", "rrf_rank": 1}],
        retrieval_mode="hybrid",
    )


def test_terminology_consumes_semantic_query_and_routes_dense_and_sparse_inputs():
    plan = _plan(
        raw_query="《维修手册》中，MRG 拆卸怎么做",
        semantic_query="MRG 拆卸怎么做",
    )
    term_result = {
        "term_matches": [{"surface": "MRG", "canonical": "主减速齿轮箱", "entity_type": "component"}],
        "normalized_query": "主减速齿轮箱 拆卸怎么做",
        "sparse_expansion": "MRG 主减速齿轮箱 拆卸 解体 怎么做",
        "protected_tokens": ["MRG"],
    }

    with (
        patch("backend.rag.utils.terminology_preflight", return_value=term_result) as preflight,
        patch("backend.rag.utils.embed_search_query", return_value=rag_utils.QueryEmbeddings([0.1], {1: 1.0})) as embed,
        patch("backend.rag.utils.retrieve_global_candidates", return_value=_retrieval_result()),
    ):
        prepared = rag_utils.prepare_candidate_retrieval(
            plan.raw_query,
            top_k=2,
            query_plan=plan,
        )

    preflight.assert_called_once_with(plan.semantic_query)
    embed.assert_called_once()
    assert embed.call_args.args[0] == term_result["normalized_query"]
    assert embed.call_args.kwargs["sparse_query"] == term_result["sparse_expansion"]
    assert prepared.trace_patch["term_matches"] == term_result["term_matches"]


def test_no_terminology_hit_keeps_semantic_query_in_both_embedding_paths():
    plan = _plan(raw_query="《手册》中，普通问题", semantic_query="普通问题")
    no_hit = {
        "term_matches": [],
        "normalized_query": plan.semantic_query,
        "sparse_expansion": plan.semantic_query,
        "protected_tokens": [],
    }

    with (
        patch("backend.rag.utils.terminology_preflight", return_value=no_hit),
        patch("backend.rag.utils.embed_search_query", return_value=rag_utils.QueryEmbeddings([0.1], {1: 1.0})) as embed,
        patch("backend.rag.utils.retrieve_global_candidates", return_value=_retrieval_result()),
    ):
        rag_utils.prepare_candidate_retrieval(plan.raw_query, query_plan=plan)

    assert embed.call_args.args[0] == plan.semantic_query
    assert embed.call_args.kwargs["sparse_query"] == plan.semantic_query
    assert plan.raw_query not in (embed.call_args.args[0], embed.call_args.kwargs["sparse_query"])


def test_terminology_failure_degrades_to_semantic_query_without_aborting_hybrid():
    plan = _plan(raw_query="《手册》中，普通问题", semantic_query="普通问题")

    with (
        patch("backend.rag.utils.terminology_preflight", side_effect=RuntimeError("term table broken")),
        patch("backend.rag.utils.embed_search_query", return_value=rag_utils.QueryEmbeddings([0.1], {1: 1.0})) as embed,
        patch("backend.rag.utils.retrieve_global_candidates", return_value=_retrieval_result()) as retrieve,
    ):
        prepared = rag_utils.prepare_candidate_retrieval(plan.raw_query, query_plan=plan)

    assert embed.call_args.args[0] == plan.semantic_query
    assert embed.call_args.kwargs["sparse_query"] == plan.semantic_query
    retrieve.assert_called_once()
    assert any(error["stage"] == "terminology_preflight" for error in prepared.stage_errors)


def test_terminology_unavailable_uses_semantic_query_for_dense_and_bm25():
    plan = _plan(raw_query="《手册》中，普通问题", semantic_query="普通问题")

    with (
        patch("backend.rag.utils.terminology_preflight", return_value=None),
        patch("backend.rag.utils.embed_search_query", return_value=rag_utils.QueryEmbeddings([0.1], {1: 1.0})) as embed,
        patch("backend.rag.utils.retrieve_global_candidates", return_value=_retrieval_result()),
    ):
        rag_utils.prepare_candidate_retrieval(plan.raw_query, query_plan=plan)

    assert embed.call_args.args[0] == plan.semantic_query
    assert embed.call_args.kwargs["sparse_query"] == plan.semantic_query


def test_prebuilt_boost_plan_applies_when_legacy_query_plan_flag_is_disabled():
    plan = PreciseQueryPlan(
        raw_query="部署故障",
        clean_query="部署故障",
        semantic_query="部署故障",
        scope_mode="boost",
        matched_files=(("部署手册.pdf", 0.85),),
        route="scoped_hybrid",
    )
    candidates = [
        {"chunk_id": "target", "filename": "部署手册.pdf", "rrf_score": 0.1},
        {"chunk_id": "other", "filename": "其他.pdf", "rrf_score": 0.2},
    ]

    with patch.object(rag_utils, "QUERY_PLAN_ENABLED", False):
        adjusted, trace = rag_utils.apply_candidate_adjustments(
            plan,
            candidates,
            {},
            plan_enabled=True,
        )

    assert trace["filename_boost_applied"] is True
    assert adjusted[0]["chunk_id"] == "target"
