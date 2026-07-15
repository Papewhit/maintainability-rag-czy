import pytest

from backend.contracts.schemas import ChatResponse, RagTrace


pytestmark = pytest.mark.unit


def test_rag_trace_schema_preserves_postprocess_fields():
    trace = RagTrace(
        tool_used=True,
        tool_name="search_knowledge_base",
        rerank_candidate_pool_size=20,
        candidate_count_before_rerank=30,
        candidate_count_after_rerank=20,
        candidate_count_after_structure_rerank=18,
        final_top_k_count=5,
        semantic_query="MRG 拆卸怎么做",
        normalized_query="主减速齿轮箱 拆卸怎么做",
        sparse_expansion="MRG 主减速齿轮箱 拆卸 分解 怎么做",
        protected_tokens=["MRG"],
        retrieved_chunks=[{
            "filename": "manual.pdf",
            "text": "evidence",
            "matched_branch_ids": ["baseline", "sub_query_0"],
            "per_branch_local_rank": {"baseline": 2, "sub_query_0": 1},
            "per_branch_rerank_score": {"sub_query_0": 0.9},
            "best_local_rank": 1,
            "baseline_matched": True,
            "coverage_count": 1,
            "multi_query_rrf_score": 0.42,
        }],
        term_matches=[{
            "entity_type": "component",
            "canonical": "主减速齿轮箱",
            "surface": "MRG",
            "start": 0,
            "end": 3,
        }],
        rerank_output_count=18,
        rerank_skipped=False,
        auto_merge_enabled=True,
        auto_merge_applied=True,
        auto_merge_replaced_chunks=2,
        auto_merge_skipped=True,
        auto_merge_error="recovered",
        step_chain_check_enabled=True,
        step_chain_repaired_groups=["g1"],
        step_chain_completion_count=1,
        structure_rerank_applied=True,
        entity_metadata_score_applied=True,
        entity_type_coverage=1.0,
        entity_match_density=0.6,
        confidence_gate_enabled=True,
        fallback_required=False,
        confidence_reasons=[],
        rerank_ms=1.0,
        auto_merge_ms=2.0,
        step_chain_ms=3.0,
        structure_rerank_ms=4.0,
        confidence_ms=5.0,
        timings={
            "rerank_ms": 1.0,
            "auto_merge_ms": 2.0,
            "step_chain_ms": 3.0,
            "structure_rerank_ms": 4.0,
            "confidence_ms": 5.0,
        },
        stage_errors=[{"stage": "auto_merge", "error": "recovered", "severity": "warning"}],
        intent="comprehensive_analysis",
        intent_confidence=0.91,
        query_plan_type="comprehensive",
        intent_llm_model="fast-model",
        intent_llm_ms=12.5,
        intent_fallback_to_rules=False,
        analysis_type="comparison",
        sub_query_count=2,
        retrieval_branch_count=3,
        requested_comprehensive_postprocess_profile="quality_first_v1",
        effective_comprehensive_postprocess_profile="quality_first_v1",
        budget_strategy_id="priority_weighted_v1",
        branch_retrieval_diagnostics=[{"branch_id": "baseline", "candidate_count": 4}],
        branch_diagnostics=[{"branch_id": "baseline", "used_pair_budget": 3}],
        allocated_pair_budget=8,
        used_pair_budget=6,
        rerank_pair_count=6,
        baseline_hit=True,
        baseline_selected=True,
        query_plan_enabled=True,
        scope_filter_applied=True,
        strict_scope_filter=True,
        retrieval_scope={
            "scope_mode": "boost",
            "source": "document_hints",
            "matched_files": [{"filename": "manual.pdf", "score": 0.9}],
        },
    )

    payload = trace.model_dump()
    assert payload["rerank_candidate_pool_size"] == 20
    assert payload["candidate_count_before_rerank"] == 30
    assert payload["final_top_k_count"] == 5
    assert payload["semantic_query"] == "MRG 拆卸怎么做"
    assert payload["normalized_query"] == "主减速齿轮箱 拆卸怎么做"
    assert payload["sparse_expansion"] == "MRG 主减速齿轮箱 拆卸 分解 怎么做"
    assert payload["protected_tokens"] == ["MRG"]
    assert payload["retrieved_chunks"][0]["matched_branch_ids"] == ["baseline", "sub_query_0"]
    assert payload["retrieved_chunks"][0]["per_branch_local_rank"] == {
        "baseline": 2,
        "sub_query_0": 1,
    }
    assert payload["retrieved_chunks"][0]["baseline_matched"] is True
    assert payload["term_matches"][0]["canonical"] == "主减速齿轮箱"
    assert payload["step_chain_repaired_groups"] == ["g1"]
    assert payload["entity_type_coverage"] == 1.0
    assert payload["timings"]["confidence_ms"] == 5.0
    assert payload["rerank_ms"] == 1.0
    assert payload["auto_merge_skipped"] is True
    assert payload["auto_merge_error"] == "recovered"
    assert payload["stage_errors"][0]["stage"] == "auto_merge"
    assert payload["intent"] == "comprehensive_analysis"
    assert payload["retrieval_branch_count"] == 3
    assert payload["branch_retrieval_diagnostics"][0]["branch_id"] == "baseline"
    assert payload["rerank_pair_count"] == 6
    assert payload["strict_scope_filter"] is True
    assert payload["retrieval_scope"]["source"] == "document_hints"

    response = ChatResponse.model_validate({"response": "ok", "rag_trace": payload})
    response_trace = response.model_dump()["rag_trace"]
    assert response_trace["intent"] == "comprehensive_analysis"
    assert response_trace["semantic_query"] == "MRG 拆卸怎么做"
    assert response_trace["normalized_query"] == "主减速齿轮箱 拆卸怎么做"
    assert response_trace["sparse_expansion"] == "MRG 主减速齿轮箱 拆卸 分解 怎么做"
    assert response_trace["protected_tokens"] == ["MRG"]
    assert response_trace["retrieved_chunks"][0]["matched_branch_ids"] == [
        "baseline",
        "sub_query_0",
    ]
    assert response_trace["retrieved_chunks"][0]["coverage_count"] == 1
    assert response_trace["term_matches"][0]["start"] == 0
    assert response_trace["budget_strategy_id"] == "priority_weighted_v1"
    assert response_trace["branch_diagnostics"][0]["used_pair_budget"] == 3
    assert response_trace["retrieval_scope"]["matched_files"] == [
        {"filename": "manual.pdf", "score": 0.9}
    ]
