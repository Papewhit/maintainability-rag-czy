import pytest

from backend.contracts.schemas import RagTrace


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
        term_matches=[{"entity_type": "component", "canonical": "pump"}],
        query_entities=[{"type": "component", "value": "pump"}],
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
    )

    payload = trace.model_dump()
    assert payload["rerank_candidate_pool_size"] == 20
    assert payload["candidate_count_before_rerank"] == 30
    assert payload["final_top_k_count"] == 5
    assert payload["term_matches"][0]["canonical"] == "pump"
    assert payload["query_entities"][0]["type"] == "component"
    assert payload["step_chain_repaired_groups"] == ["g1"]
    assert payload["entity_type_coverage"] == 1.0
    assert payload["timings"]["confidence_ms"] == 5.0
    assert payload["rerank_ms"] == 1.0
    assert payload["auto_merge_skipped"] is True
    assert payload["auto_merge_error"] == "recovered"
    assert payload["stage_errors"][0]["stage"] == "auto_merge"
