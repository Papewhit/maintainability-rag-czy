import time
import logging
from contextlib import ExitStack
from unittest.mock import patch

import pytest

import backend.rag.utils as rag_utils
import backend.rag.pipeline as rag_pipeline
from backend.rag.runtime_config import load_runtime_config


pytestmark = pytest.mark.unit


def _docs(count: int) -> list[dict]:
    return [
        {
            "chunk_id": f"leaf-{index}",
            "root_chunk_id": f"root-{index}",
            "filename": "manual.pdf",
            "chunk_level": 1,
            "chunk_role": "root",
            "index_profile": "v4",
            "text": f"evidence {index}",
            "score": 1.0 - index / 100,
        }
        for index in range(count)
    ]


def test_runtime_config_defaults_rerank_candidate_pool_to_twenty():
    config = load_runtime_config({})

    assert config.rerank_candidate_pool_size == 20
    assert config.step_chain_check_enabled is False
    assert config.step_chain_adjacent_lookback == 2


def test_effective_rerank_output_size_uses_pool_and_legacy_override():
    with (
        patch.object(rag_utils, "RERANK_CANDIDATE_POOL_SIZE", 20),
        patch.object(rag_utils, "RERANK_TOP_N", 0),
    ):
        assert rag_utils._effective_rerank_output_size(top_k=5, candidate_count=50) == 20
        assert rag_utils._effective_rerank_output_size(top_k=5, candidate_count=10) == 10

    with (
        patch.object(rag_utils, "RERANK_CANDIDATE_POOL_SIZE", 20),
        patch.object(rag_utils, "RERANK_TOP_N", 15),
    ):
        assert rag_utils._effective_rerank_output_size(top_k=5, candidate_count=50) == 15


def test_finish_pipeline_runs_candidate_pool_then_truncates_before_confidence():
    retrieved = _docs(30)
    calls: list[tuple[str, int]] = []

    def rerank(*, query, docs, top_k):
        calls.append(("rerank", top_k))
        return docs[:top_k], {"rerank_enabled": True, "rerank_applied": True, "rerank_output_count": top_k}

    def merge(docs, top_k):
        calls.append(("auto_merge", top_k))
        return docs, {
            "auto_merge_enabled": True,
            "auto_merge_applied": False,
            "auto_merge_replaced_chunks": 0,
        }

    def structure(docs, top_k):
        calls.append(("structure_rerank", top_k))
        return docs, {"structure_rerank_enabled": True, "structure_rerank_applied": True}

    def step_chain(docs, top_k):
        calls.append(("step_chain_check", top_k))
        return docs, {
            "step_chain_check_enabled": False,
            "step_chain_repaired_groups": [],
            "step_chain_completion_count": 0,
        }

    def confidence(*, query, docs):
        calls.append(("confidence_gate", len(docs)))
        return {"confidence_gate_enabled": True, "fallback_required": False, "confidence_reasons": []}

    with (
        patch.object(rag_utils, "RERANK_CANDIDATE_POOL_SIZE", 20),
        patch.object(rag_utils, "RERANK_TOP_N", 0),
        patch.object(rag_utils, "_rerank_documents", side_effect=rerank),
        patch.object(rag_utils, "_auto_merge_documents", side_effect=merge),
        patch.object(rag_utils, "_step_chain_check", side_effect=step_chain),
        patch.object(rag_utils, "_apply_structure_rerank", side_effect=structure),
        patch.object(rag_utils, "_evaluate_retrieval_confidence", side_effect=confidence),
    ):
        result = rag_utils._finish_retrieval_pipeline(
            query="query",
            search_query="query",
            retrieved=retrieved,
            top_k=5,
            candidate_k=30,
            timings={},
            stage_errors=[],
            total_start=time.perf_counter(),
        )

    assert calls == [
        ("rerank", 20),
        ("auto_merge", 20),
        ("step_chain_check", 20),
        ("structure_rerank", 20),
        ("confidence_gate", 5),
    ]
    assert len(result["docs"]) == 5
    assert result["meta"]["rerank_candidate_pool_size"] == 20
    assert result["meta"]["rerank_output_count"] == 20
    assert result["meta"]["candidate_count_after_structure_rerank"] == 20
    assert len(result["meta"]["candidates_after_structure_rerank"]) == 20
    assert result["meta"]["step_chain_check_enabled"] is False
    assert result["meta"]["step_chain_repaired_groups"] == []
    assert result["meta"]["timings"]["step_chain_ms"] >= 0
    for timing_key in (
        "rerank_ms",
        "auto_merge_ms",
        "step_chain_ms",
        "structure_rerank_ms",
        "confidence_ms",
    ):
        assert result["meta"][timing_key] == result["meta"]["timings"][timing_key]


def test_finish_pipeline_exposes_real_auto_merge_result():
    retrieved = [
        {
            "chunk_id": "leaf-a1",
            "parent_chunk_id": "parent-a",
            "root_chunk_id": "parent-a",
            "filename": "manual.pdf",
            "text": "step one",
            "score": 0.9,
            "rerank_score": 0.99,
            "raw_rerank_score": 2.5,
            "fusion_score": 0.95,
        },
        {
            "chunk_id": "leaf-a2",
            "parent_chunk_id": "parent-a",
            "root_chunk_id": "parent-a",
            "filename": "manual.pdf",
            "text": "step two",
            "score": 0.8,
        },
        {
            "chunk_id": "leaf-b1",
            "parent_chunk_id": "parent-b",
            "root_chunk_id": "parent-b",
            "filename": "manual.pdf",
            "text": "other evidence",
            "score": 0.7,
        },
    ]
    parent = {
        "chunk_id": "parent-a",
        "root_chunk_id": "parent-a",
        "filename": "manual.pdf",
        "text": "complete procedure",
        "score": 0.0,
    }

    with (
        patch.object(rag_utils, "RERANK_CANDIDATE_POOL_SIZE", 20),
        patch.object(rag_utils, "RERANK_TOP_N", 0),
        patch.object(rag_utils, "AUTO_MERGE_ENABLED", True),
        patch.object(rag_utils, "AUTO_MERGE_THRESHOLD", 2),
        patch.object(rag_utils, "_rerank_documents", return_value=(retrieved, {
            "rerank_enabled": True,
            "rerank_applied": True,
            "rerank_output_count": 3,
        })),
        patch.object(rag_utils, "_get_parent_chunk_store") as get_store,
        patch.object(rag_utils, "_step_chain_check", side_effect=lambda docs, top_k: (
            docs,
            {
                "step_chain_check_enabled": False,
                "step_chain_repaired_groups": [],
                "step_chain_completion_count": 0,
            },
        )),
        patch.object(rag_utils, "_apply_structure_rerank", side_effect=lambda docs, top_k: (
            docs,
            {"structure_rerank_enabled": False, "structure_rerank_applied": False},
        )),
        patch.object(rag_utils, "_evaluate_retrieval_confidence", return_value={
            "confidence_gate_enabled": False,
            "fallback_required": False,
            "confidence_reasons": [],
        }),
    ):
        get_store.return_value.get_documents_by_ids.return_value = [parent]
        result = rag_utils._finish_retrieval_pipeline(
            query="procedure",
            search_query="procedure",
            retrieved=retrieved,
            top_k=5,
            candidate_k=20,
            timings={},
            stage_errors=[],
            total_start=time.perf_counter(),
        )

    assert [doc["chunk_id"] for doc in result["docs"]] == ["parent-a", "leaf-b1"]
    assert result["docs"][0]["rerank_score"] == pytest.approx(0.99)
    assert result["docs"][0]["raw_rerank_score"] == pytest.approx(2.5)
    assert result["docs"][0]["fusion_score"] == pytest.approx(0.95)
    assert result["meta"]["auto_merge_applied"] is True
    assert result["meta"]["auto_merge_replaced_chunks"] == 2
    assert result["meta"]["timings"]["auto_merge_ms"] >= 0


def test_auto_merge_no_eligible_parent_is_noop():
    docs = [
        {"chunk_id": "b", "parent_chunk_id": "parent-b", "score": 0.1, "rerank_score": 0.9},
        {"chunk_id": "a", "parent_chunk_id": "parent-a", "score": 0.9, "rerank_score": 0.8},
    ]

    with (
        patch.object(rag_utils, "AUTO_MERGE_ENABLED", True),
        patch.object(rag_utils, "AUTO_MERGE_THRESHOLD", 2),
        patch.object(rag_utils, "_get_parent_chunk_store", side_effect=AssertionError("must not load")),
    ):
        result, meta = rag_utils._auto_merge_documents(docs, top_k=5)

    assert [doc["chunk_id"] for doc in result] == ["b", "a"]
    assert meta["auto_merge_applied"] is False
    assert meta["auto_merge_replaced_chunks"] == 0


def test_auto_merge_disabled_is_noop():
    docs = [
        {"chunk_id": "a", "parent_chunk_id": "parent-a", "score": 0.9},
        {"chunk_id": "b", "parent_chunk_id": "parent-a", "score": 0.8},
    ]

    with (
        patch.object(rag_utils, "AUTO_MERGE_ENABLED", False),
        patch.object(rag_utils, "_get_parent_chunk_store", side_effect=AssertionError("must not load")),
    ):
        result, meta = rag_utils._auto_merge_documents(docs, top_k=5)

    assert result == docs
    assert meta["auto_merge_enabled"] is False
    assert meta["auto_merge_applied"] is False


def test_legacy_rerank_top_n_logs_deprecation(caplog):
    with (
        patch.object(rag_utils, "RERANK_CANDIDATE_POOL_SIZE", 20),
        patch.object(rag_utils, "RERANK_TOP_N", 15),
        caplog.at_level(logging.WARNING, logger="backend.rag.utils"),
    ):
        assert rag_utils._effective_rerank_output_size(top_k=5, candidate_count=50) == 15

    assert "RERANK_TOP_N is deprecated" in caplog.text


def test_retrieve_initial_emits_real_auto_merge_status():
    retrieve_result = {
        "docs": [{"chunk_id": "parent-a", "filename": "manual.pdf", "text": "complete procedure"}],
        "meta": {
            "leaf_retrieve_level": 3,
            "candidate_k": 20,
            "retrieval_mode": "hybrid",
            "auto_merge_enabled": True,
            "auto_merge_applied": True,
            "auto_merge_replaced_chunks": 2,
            "timings": {},
            "stage_errors": [],
        },
    }

    with (
        patch.object(rag_pipeline, "retrieve_documents", return_value=retrieve_result),
        patch.object(rag_pipeline, "emit_rag_step") as emit,
    ):
        result = rag_pipeline.retrieve_initial({"question": "procedure", "context_files": []})

    auto_merge_calls = [call for call in emit.call_args_list if call.args[1] == "Auto-merging 合并"]
    assert len(auto_merge_calls) == 1
    assert "应用: True" in auto_merge_calls[0].args[2]
    assert "替换片段: 2" in auto_merge_calls[0].args[2]
    assert result["rag_trace"]["auto_merge_applied"] is True


def test_retrieve_initial_passes_intent_entities_to_retrieval():
    entities = [{"type": "component", "value": "pump"}]
    retrieve_result = {"docs": [], "meta": {"timings": {}, "stage_errors": []}}

    with (
        patch.object(rag_pipeline, "retrieve_documents", return_value=retrieve_result) as retrieve,
        patch.object(rag_pipeline, "emit_rag_step"),
    ):
        rag_pipeline.retrieve_initial({
            "question": "pump",
            "context_files": [],
            "intent_result": {"entities": entities},
        })

    assert retrieve.call_args.kwargs["query_entities"] == entities


def test_step_chain_check_repairs_incomplete_middle_chunk():
    docs = [
        {
            "chunk_id": "g1-2",
            "list_group_id": "g1",
            "list_order": 2,
            "list_complete": False,
            "filename": "manual.pdf",
            "chunk_level": 1,
            "chunk_role": "root",
            "index_profile": "v4",
            "score": 0.9,
        }
    ]
    adjacent = [
        {"chunk_id": "g1-1", "list_group_id": "g1", "list_order": 1, "score": 0.8},
        {"chunk_id": "g1-3", "list_group_id": "g1", "list_order": 3, "score": 0.7},
    ]

    with (
        patch.object(rag_utils, "STEP_CHAIN_CHECK_ENABLED", True),
        patch.object(rag_utils, "STEP_CHAIN_ADJACENT_LOOKBACK", 2),
        patch.object(rag_utils, "_fetch_adjacent_chunks", return_value=adjacent) as fetch,
    ):
        repaired, meta = rag_utils._step_chain_check(docs, top_k=3)

    fetch.assert_called_once_with("g1", [1, 3, 4], filename="manual.pdf", index_profile="v4")
    assert [doc["chunk_id"] for doc in repaired] == ["g1-2", "g1-1", "g1-3"]
    assert meta["step_chain_repaired_groups"] == ["g1"]
    assert meta["step_chain_completion_count"] == 1
    assert meta["step_chain_ms"] >= 0


def test_step_chain_check_skips_complete_first_and_legacy_chunks():
    docs = [
        {"chunk_id": "complete", "list_group_id": "g1", "list_order": 3, "list_complete": True},
        {"chunk_id": "first", "list_group_id": "g2", "list_order": 1, "list_complete": False},
        {"chunk_id": "legacy", "list_complete": False},
        {
            "chunk_id": "leaf",
            "filename": "manual.pdf",
            "chunk_level": 3,
            "list_group_id": "g3",
            "list_order": 2,
            "list_complete": False,
        },
    ]

    with (
        patch.object(rag_utils, "STEP_CHAIN_CHECK_ENABLED", True),
        patch.object(rag_utils, "_fetch_adjacent_chunks", side_effect=AssertionError("must not query")),
    ):
        repaired, meta = rag_utils._step_chain_check(docs, top_k=4)

    assert repaired == docs
    assert meta["step_chain_repaired_groups"] == []
    assert meta["step_chain_completion_count"] == 0


def test_step_chain_check_limits_window_dedupes_and_handles_groups_independently():
    docs = [
        {"chunk_id": "g1-5", "filename": "a.pdf", "index_profile": "v4", "chunk_level": 1, "list_group_id": "g1", "list_order": 5, "list_complete": False},
        {"chunk_id": "g2-2", "filename": "b.pdf", "index_profile": "v4", "chunk_level": 1, "list_group_id": "g2", "list_order": 2, "list_complete": False},
        {"chunk_id": "g1-4", "filename": "a.pdf", "index_profile": "v4", "chunk_level": 1, "list_group_id": "g1", "list_order": 4, "list_complete": False},
    ]

    def fetch(group_id, orders, *, filename, index_profile):
        if group_id == "g1":
            assert filename == "a.pdf"
            assert index_profile == "v4"
            assert orders == [3, 4, 6, 7]
            return [
                {"chunk_id": "g1-4", "list_group_id": "g1", "list_order": 4},
                {"chunk_id": "g1-6", "list_group_id": "g1", "list_order": 6},
            ]
        assert group_id == "g2"
        assert filename == "b.pdf"
        assert index_profile == "v4"
        assert orders == [1, 3, 4]
        return [{"chunk_id": "g2-1", "list_group_id": "g2", "list_order": 1}]

    with (
        patch.object(rag_utils, "STEP_CHAIN_CHECK_ENABLED", True),
        patch.object(rag_utils, "STEP_CHAIN_ADJACENT_LOOKBACK", 2),
        patch.object(rag_utils, "_fetch_adjacent_chunks", side_effect=fetch) as fetch_mock,
    ):
        repaired, meta = rag_utils._step_chain_check(docs, top_k=3)

    assert fetch_mock.call_count == 2
    assert [doc["chunk_id"] for doc in repaired] == ["g1-5", "g2-2", "g1-4", "g1-6", "g2-1"]
    assert meta["step_chain_repaired_groups"] == ["g1", "g2"]
    assert meta["step_chain_completion_count"] == 2


def test_fetch_adjacent_chunks_locates_parent_ids_via_leaf_metadata_then_hydrates_parents():
    leaf_refs = [
        {"parent_chunk_id": "g1-parent-3", "parent_list_order": 3},
        {"parent_chunk_id": "g1-parent-1", "parent_list_order": 1},
        {"parent_chunk_id": "g1-parent-3", "parent_list_order": 3},
    ]
    parents = [
        {"chunk_id": "g1-parent-1", "list_group_id": 'group "one"', "list_order": 1},
        {"chunk_id": "g1-parent-3", "list_group_id": 'group "one"', "list_order": 3},
    ]

    with (
        patch.object(rag_utils._milvus_manager, "query_all", return_value=leaf_refs) as query,
        patch.object(rag_utils, "_get_parent_chunk_store") as get_store,
    ):
        get_store.return_value.get_documents_by_ids.return_value = parents
        rows = rag_utils._fetch_adjacent_chunks(
            'group "one"', [1, 3], filename="manual.pdf", index_profile="v4"
        )

    assert rows == parents
    kwargs = query.call_args.kwargs
    assert 'list_group_id == "group \\u0022one\\u0022"' not in kwargs["filter_expr"]
    assert "list_group_id ==" in kwargs["filter_expr"]
    assert "parent_list_order in [1, 3]" in kwargs["filter_expr"]
    assert "chunk_level == 3" in kwargs["filter_expr"]
    assert 'filename == "manual.pdf"' in kwargs["filter_expr"]
    assert 'index_profile == "v4"' in kwargs["filter_expr"]
    assert "parent_chunk_id" in kwargs["output_fields"]
    assert "parent_list_order" in kwargs["output_fields"]
    get_store.return_value.get_documents_by_ids.assert_called_once_with(["g1-parent-1", "g1-parent-3"])


def test_step_chain_check_disabled_is_noop():
    docs = [{"chunk_id": "g1-2", "list_group_id": "g1", "list_order": 2, "list_complete": False}]

    with (
        patch.object(rag_utils, "STEP_CHAIN_CHECK_ENABLED", False),
        patch.object(rag_utils, "_fetch_adjacent_chunks", side_effect=AssertionError("must not query")),
    ):
        result, meta = rag_utils._step_chain_check(docs, top_k=3)

    assert result == docs
    assert meta["step_chain_check_enabled"] is False


def test_finish_pipeline_keeps_auto_merge_output_when_step_chain_fails():
    retrieved = _docs(3)
    merged = retrieved[:2]
    stage_errors: list[dict] = []

    with (
        patch.object(rag_utils, "RERANK_CANDIDATE_POOL_SIZE", 20),
        patch.object(rag_utils, "RERANK_TOP_N", 0),
        patch.object(rag_utils, "_rerank_documents", return_value=(retrieved, {
            "rerank_enabled": True,
            "rerank_applied": True,
            "rerank_output_count": 3,
        })),
        patch.object(rag_utils, "_auto_merge_documents", return_value=(merged, {
            "auto_merge_enabled": True,
            "auto_merge_applied": True,
            "auto_merge_replaced_chunks": 1,
        })),
        patch.object(rag_utils, "_step_chain_check", side_effect=RuntimeError("milvus unavailable")),
        patch.object(rag_utils, "_apply_structure_rerank", side_effect=lambda docs, top_k: (
            docs,
            {"structure_rerank_enabled": False, "structure_rerank_applied": False},
        )),
        patch.object(rag_utils, "_evaluate_retrieval_confidence", return_value={
            "confidence_gate_enabled": False,
            "fallback_required": False,
            "confidence_reasons": [],
        }),
    ):
        result = rag_utils._finish_retrieval_pipeline(
            query="procedure",
            search_query="procedure",
            retrieved=retrieved,
            top_k=5,
            candidate_k=20,
            timings={},
            stage_errors=stage_errors,
            total_start=time.perf_counter(),
        )

    assert result["docs"] == merged
    assert result["meta"]["step_chain_skipped"] is True
    assert result["meta"]["stage_errors"][-1]["stage"] == "step_chain_check"
    assert result["meta"]["stage_errors"][-1]["fallback_to"] == "auto_merge_output"


def test_metadata_score_uses_entity_type_coverage_and_match_density():
    query_entities = [
        {"type": "product_model", "value": "A"},
        {"entity_type": "component", "canonical": "pump"},
    ]
    doc = {
        "entity_types": ["product_model", "component", "maintenance_action"],
        "term_match_count": 2,
    }

    assert rag_utils._metadata_score(doc, query_entities) == pytest.approx(0.82)
    assert rag_utils._metadata_score(doc, []) == 0.0
    assert rag_utils._metadata_score({}, query_entities) == 0.0


def test_metadata_score_treats_json_and_list_entity_types_equally():
    query_entities = [{"type": "component"}]
    list_doc = {"entity_types": ["component"], "term_match_count": 2}
    json_doc = {"entity_types": '["component"]', "term_match_count": 2}

    assert rag_utils._metadata_score(json_doc, query_entities) == rag_utils._metadata_score(
        list_doc, query_entities
    )


def test_entity_metadata_score_can_change_fusion_order():
    docs = [
        {"chunk_id": "plain", "entity_types": [], "term_match_count": 0},
        {"chunk_id": "matched", "entity_types": ["component"], "term_match_count": 3},
    ]

    with (
        patch.object(rag_utils, "RERANK_SCORE_FUSION_ENABLED", True),
        patch.object(rag_utils, "RERANK_FUSION_RERANK_WEIGHT", 0.0),
        patch.object(rag_utils, "RERANK_FUSION_RRF_WEIGHT", 0.0),
        patch.object(rag_utils, "RERANK_FUSION_SCOPE_WEIGHT", 0.0),
        patch.object(rag_utils, "RERANK_FUSION_METADATA_WEIGHT", 1.0),
    ):
        fused = rag_utils._apply_rerank_score_fusion(
            [(0, 0.9), (1, 0.1)],
            docs,
            query_entities=[{"type": "component"}],
        )

    assert fused[0][0] == 1


def test_entity_fusion_preserves_generic_metadata_for_legacy_chunks():
    docs = [
        {"chunk_id": "legacy", "anchor_id": "第一章", "entity_types": []},
        {"chunk_id": "plain", "entity_types": []},
    ]

    with (
        patch.object(rag_utils, "RERANK_SCORE_FUSION_ENABLED", True),
        patch.object(rag_utils, "RERANK_FUSION_RERANK_WEIGHT", 0.0),
        patch.object(rag_utils, "RERANK_FUSION_RRF_WEIGHT", 0.0),
        patch.object(rag_utils, "RERANK_FUSION_SCOPE_WEIGHT", 0.0),
        patch.object(rag_utils, "RERANK_FUSION_METADATA_WEIGHT", 1.0),
    ):
        fused = rag_utils._apply_rerank_score_fusion(
            [(0, 0.5), (1, 0.5)],
            docs,
            query_entities=[{"type": "component"}],
        )
    scores = dict(fused)

    assert scores[0] > scores[1]


def test_rerank_trace_reports_entity_metadata_components():
    class FakeReranker:
        def predict(self, pairs):
            return [0.5 for _ in pairs]

    docs = [
        {
            "chunk_id": "matched",
            "text": "pump procedure",
            "entity_types": ["component"],
            "term_match_count": 3,
        }
    ]

    with (
        patch.object(rag_utils, "RERANK_PROVIDER", "local"),
        patch.object(rag_utils, "RERANK_MODEL", "fake-reranker"),
        patch.object(rag_utils, "RERANK_TOP_N", 0),
        patch.object(rag_utils, "RERANK_INPUT_K_CPU", 0),
        patch.object(rag_utils, "RERANK_DEVICE", "cpu"),
        patch.object(rag_utils, "RERANK_CACHE_ENABLED", False),
        patch.object(rag_utils, "RERANK_SCORE_FUSION_ENABLED", True),
        patch.object(rag_utils, "_get_local_reranker", return_value=FakeReranker()),
    ):
        _, meta = rag_utils._rerank_documents(
            "pump",
            docs,
            top_k=1,
            query_entities=[{"entity_type": "component"}],
        )

    assert meta["entity_metadata_score_applied"] is True
    assert meta["entity_type_coverage"] == 1.0
    assert meta["entity_match_density"] == pytest.approx(0.6)


def test_entity_metadata_trace_is_not_applied_when_fusion_is_disabled():
    docs = [{
        "chunk_id": "matched",
        "text": "pump procedure",
        "entity_types": ["component"],
        "term_match_count": 3,
    }]

    with (
        patch.object(rag_utils, "RERANK_MODEL", ""),
        patch.object(rag_utils, "RERANK_SCORE_FUSION_ENABLED", False),
    ):
        _, meta = rag_utils._rerank_documents(
            "pump",
            docs,
            top_k=1,
            query_entities=[{"entity_type": "component"}],
        )

    assert meta["entity_metadata_score_applied"] is False
    assert meta["entity_type_coverage"] == 1.0


def test_entity_metadata_trace_is_not_applied_without_reranker_execution():
    docs = [{
        "chunk_id": "matched",
        "text": "pump procedure",
        "entity_types": ["component"],
        "term_match_count": 3,
    }]

    with (
        patch.object(rag_utils, "RERANK_MODEL", ""),
        patch.object(rag_utils, "RERANK_SCORE_FUSION_ENABLED", True),
        patch.object(rag_utils, "RERANK_FUSION_METADATA_WEIGHT", 1.0),
    ):
        _, meta = rag_utils._rerank_documents(
            "pump",
            docs,
            top_k=1,
            query_entities=[{"entity_type": "component"}],
        )

    assert meta["entity_metadata_score_applied"] is False


def test_real_reranker_failure_marks_skipped_and_preserves_candidates():
    class FailingReranker:
        def predict(self, pairs):
            raise RuntimeError("inference failed")

    docs = [{"chunk_id": "c1", "text": "evidence", "score": 0.8}]

    with (
        patch.object(rag_utils, "RERANK_MODEL", "fake-reranker"),
        patch.object(rag_utils, "RERANK_DEVICE", "cpu"),
        patch.object(rag_utils, "RERANK_CACHE_ENABLED", False),
        patch.object(rag_utils, "_get_local_reranker", return_value=FailingReranker()),
        patch.object(rag_utils, "_auto_merge_documents", side_effect=lambda docs, top_k: (docs, {})),
        patch.object(rag_utils, "_step_chain_check", side_effect=lambda docs, top_k: (docs, {})),
        patch.object(rag_utils, "_apply_structure_rerank", side_effect=lambda docs, top_k: (docs, {})),
        patch.object(rag_utils, "_evaluate_retrieval_confidence", return_value={}),
    ):
        result = rag_utils._finish_retrieval_pipeline(
            query="evidence",
            search_query="evidence",
            retrieved=docs,
            top_k=1,
            candidate_k=1,
            timings={},
            stage_errors=[],
            total_start=time.perf_counter(),
        )

    assert [doc["chunk_id"] for doc in result["docs"]] == ["c1"]
    assert result["meta"]["rerank_skipped"] is True
    assert result["meta"]["rerank_error"] == "inference failed"
    assert result["meta"]["stage_errors"][0]["stage"] == "rerank"


def test_finish_pipeline_passes_terminology_entities_to_rerank():
    retrieved = _docs(1)

    def rerank(*, query, docs, top_k, query_entities):
        assert query_entities == [{"entity_type": "component", "canonical": "pump"}]
        return docs, {
            "rerank_enabled": True,
            "rerank_applied": True,
            "rerank_output_count": 1,
            "entity_metadata_score_applied": False,
        }

    with (
        patch.object(rag_utils, "_rerank_documents", side_effect=rerank),
        patch.object(rag_utils, "_auto_merge_documents", side_effect=lambda docs, top_k: (docs, {})),
        patch.object(rag_utils, "_step_chain_check", side_effect=lambda docs, top_k: (docs, {})),
        patch.object(rag_utils, "_apply_structure_rerank", side_effect=lambda docs, top_k: (docs, {})),
        patch.object(rag_utils, "_evaluate_retrieval_confidence", return_value={}),
    ):
        result = rag_utils._finish_retrieval_pipeline(
            query="pump",
            search_query="pump",
            retrieved=retrieved,
            top_k=1,
            candidate_k=1,
            timings={},
            stage_errors=[],
            total_start=time.perf_counter(),
            extra_trace={
                "term_matches": [{"entity_type": "component", "canonical": "pump"}],
            },
        )

    assert result["docs"] == retrieved


def test_rerank_cache_key_includes_query_entity_types():
    docs = [{"chunk_id": "c1", "text": "pump"}]

    plain = rag_utils._rerank_cache_key("pump", docs, 1, 1, False)
    entity = rag_utils._rerank_cache_key(
        "pump",
        docs,
        1,
        1,
        False,
        query_entities=[{"entity_type": "component"}],
    )

    assert plain != entity

    changed_metadata = rag_utils._rerank_cache_key(
        "pump",
        [{"chunk_id": "c1", "text": "pump", "entity_types": ["component"], "term_match_count": 2}],
        1,
        1,
        False,
        query_entities=[{"entity_type": "component"}],
    )
    assert changed_metadata != entity


def test_rerank_cache_key_normalizes_entity_types_wire_representation():
    kwargs = {
        "query": "pump",
        "rerank_top_n": 1,
        "rerank_input_k": 1,
        "enrichment_enabled": False,
        "query_entities": [{"entity_type": "component"}],
    }
    list_key = rag_utils._rerank_cache_key(
        docs_for_rerank=[{
            "chunk_id": "c1",
            "text": "pump",
            "entity_types": ["component"],
            "term_match_count": 2,
        }],
        **kwargs,
    )
    json_key = rag_utils._rerank_cache_key(
        docs_for_rerank=[{
            "chunk_id": "c1",
            "text": "pump",
            "entity_types": '["component"]',
            "term_match_count": 2,
        }],
        **kwargs,
    )

    assert json_key == list_key


@pytest.mark.parametrize(
    ("failed_stage", "skipped_key", "fallback_to"),
    [
        ("rerank", "rerank_skipped", "retrieved_candidates"),
        ("auto_merge", "auto_merge_skipped", "rerank_output"),
        ("structure_rerank", "structure_rerank_skipped", "step_chain_output"),
        ("confidence_gate", "confidence_gate_skipped", "final_top_k"),
    ],
)
def test_postprocess_stage_failure_keeps_previous_output(failed_stage, skipped_key, fallback_to):
    retrieved = _docs(3)

    def stage_result(name, docs):
        if name == failed_stage:
            raise RuntimeError(f"{name} failed")
        if name == "rerank":
            return docs, {"rerank_enabled": True, "rerank_applied": True, "rerank_output_count": len(docs)}
        if name == "auto_merge":
            return docs, {"auto_merge_enabled": True, "auto_merge_applied": False}
        if name == "step_chain_check":
            return docs, {"step_chain_check_enabled": False, "step_chain_repaired_groups": []}
        if name == "structure_rerank":
            return docs, {"structure_rerank_enabled": True, "structure_rerank_applied": True}
        return {"confidence_gate_enabled": True, "fallback_required": False, "confidence_reasons": []}

    with ExitStack() as stack:
        stack.enter_context(patch.object(
            rag_utils,
            "_rerank_documents",
            side_effect=lambda **kwargs: stage_result("rerank", kwargs["docs"]),
        ))
        stack.enter_context(patch.object(
            rag_utils,
            "_auto_merge_documents",
            side_effect=lambda docs, top_k: stage_result("auto_merge", docs),
        ))
        stack.enter_context(patch.object(
            rag_utils,
            "_step_chain_check",
            side_effect=lambda docs, top_k: stage_result("step_chain_check", docs),
        ))
        stack.enter_context(patch.object(
            rag_utils,
            "_apply_structure_rerank",
            side_effect=lambda docs, top_k: stage_result("structure_rerank", docs),
        ))
        stack.enter_context(patch.object(
            rag_utils,
            "_evaluate_retrieval_confidence",
            side_effect=lambda **kwargs: stage_result("confidence_gate", kwargs["docs"]),
        ))
        result = rag_utils._finish_retrieval_pipeline(
            query="procedure",
            search_query="procedure",
            retrieved=retrieved,
            top_k=3,
            candidate_k=3,
            timings={},
            stage_errors=[],
            total_start=time.perf_counter(),
        )

    assert result["docs"] == retrieved
    assert result["meta"][skipped_key] is True
    error = next(item for item in result["meta"]["stage_errors"] if item["stage"] == failed_stage)
    assert error["fallback_to"] == fallback_to
    timing_key = "confidence_ms" if failed_stage == "confidence_gate" else f"{failed_stage}_ms"
    assert result["meta"]["timings"][timing_key] >= 0
