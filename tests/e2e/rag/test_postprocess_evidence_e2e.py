import time
from unittest.mock import patch

import pytest

import backend.rag.utils as rag_utils


pytestmark = pytest.mark.e2e


class _FakeCrossEncoder:
    def predict(self, pairs):
        scores = []
        for _, text in pairs:
            if "拆卸" in text:
                scores.append(0.95)
            elif "检查" in text:
                scores.append(0.90)
            else:
                scores.append(0.40)
        return scores


def test_complete_postprocess_evidence_chain_e2e():
    retrieved = [
        {
            "chunk_id": "leaf-mid-1",
            "parent_chunk_id": "parent-mid",
            "root_chunk_id": "parent-mid",
            "chunk_level": 3,
            "chunk_role": "leaf",
            "filename": "manual.pdf",
            "index_profile": "v4",
            "text": "2. 拆卸泵体",
            "retrieval_text": "2. 拆卸泵体",
            "entity_types": ["component", "maintenance_action"],
            "term_match_count": 2,
            "score": 0.90,
        },
        {
            "chunk_id": "leaf-mid-2",
            "parent_chunk_id": "parent-mid",
            "root_chunk_id": "parent-mid",
            "chunk_level": 3,
            "chunk_role": "leaf",
            "filename": "manual.pdf",
            "index_profile": "v4",
            "text": "检查密封面",
            "retrieval_text": "检查密封面",
            "entity_types": ["component"],
            "term_match_count": 1,
            "score": 0.85,
        },
        {
            "chunk_id": "unrelated",
            "parent_chunk_id": "other-parent",
            "root_chunk_id": "other-parent",
            "chunk_level": 3,
            "chunk_role": "leaf",
            "filename": "other.pdf",
            "index_profile": "v4",
            "text": "一般说明",
            "retrieval_text": "一般说明",
            "entity_types": [],
            "term_match_count": 0,
            "score": 0.30,
        },
    ]
    parent_mid = {
        "chunk_id": "parent-mid",
        "parent_chunk_id": "parent-mid",
        "root_chunk_id": "parent-mid",
        "chunk_level": 1,
        "chunk_role": "root",
        "filename": "manual.pdf",
        "index_profile": "v4",
        "text": "2. 拆卸泵体\n检查密封面",
        "retrieval_text": "",
        "list_group_id": "lg_p1_l1_s0",
        "list_order": 2,
        "list_complete": False,
        "entity_types": ["component", "maintenance_action"],
        "term_match_count": 3,
        "score": 0.0,
    }
    adjacent = [
        {
            **parent_mid,
            "chunk_id": "parent-first",
            "root_chunk_id": "parent-first",
            "text": "1. 准备工具",
            "list_order": 1,
            "score": 0.70,
        },
        {
            **parent_mid,
            "chunk_id": "parent-last",
            "root_chunk_id": "parent-last",
            "text": "3. 安装并复验",
            "list_order": 3,
            "score": 0.65,
        },
    ]
    adjacent_leaf_refs = [
        {"parent_chunk_id": "parent-first", "parent_list_order": 1},
        {"parent_chunk_id": "parent-last", "parent_list_order": 3},
    ]

    def load_parents(chunk_ids):
        if chunk_ids == ["parent-mid"]:
            return [parent_mid]
        assert chunk_ids == ["parent-first", "parent-last"]
        return adjacent

    with (
        patch.object(rag_utils, "RERANK_PROVIDER", "local"),
        patch.object(rag_utils, "RERANK_MODEL", "fake-cross-encoder"),
        patch.object(rag_utils, "RERANK_DEVICE", "cpu"),
        patch.object(rag_utils, "RERANK_INPUT_K_CPU", 0),
        patch.object(rag_utils, "RERANK_TOP_N", 0),
        patch.object(rag_utils, "RERANK_CANDIDATE_POOL_SIZE", 20),
        patch.object(rag_utils, "RERANK_CACHE_ENABLED", False),
        patch.object(rag_utils, "RERANK_SCORE_FUSION_ENABLED", True),
        patch.object(rag_utils, "AUTO_MERGE_ENABLED", True),
        patch.object(rag_utils, "AUTO_MERGE_THRESHOLD", 2),
        patch.object(rag_utils, "STEP_CHAIN_CHECK_ENABLED", True),
        patch.object(rag_utils, "STEP_CHAIN_ADJACENT_LOOKBACK", 1),
        patch.object(rag_utils, "STRUCTURE_RERANK_ENABLED", True),
        patch.object(rag_utils, "CONFIDENCE_GATE_ENABLED", True),
        patch.object(rag_utils, "LOW_CONF_TOP_SCORE", 0.0),
        patch.object(rag_utils, "LOW_CONF_TOP_MARGIN", 0.0),
        patch.object(rag_utils, "LOW_CONF_ROOT_SHARE", 0.0),
        patch.object(rag_utils, "ENABLE_ANCHOR_GATE", False),
        patch.object(rag_utils, "_get_local_reranker", return_value=_FakeCrossEncoder()),
        patch.object(rag_utils, "_get_parent_chunk_store") as parent_store,
        patch.object(rag_utils._milvus_manager, "query_all", return_value=adjacent_leaf_refs) as milvus_query,
    ):
        parent_store.return_value.get_documents_by_ids.side_effect = load_parents
        result = rag_utils._finish_retrieval_pipeline(
            query="泵体拆卸和检查步骤",
            search_query="泵体拆卸和检查步骤",
            retrieved=retrieved,
            top_k=3,
            candidate_k=3,
            timings={},
            stage_errors=[],
            total_start=time.perf_counter(),
            extra_trace={
                "term_matches": [
                    {"entity_type": "component", "canonical": "泵体"},
                    {"entity_type": "maintenance_action", "canonical": "拆卸"},
                ],
            },
        )

    final_ids = {doc["chunk_id"] for doc in result["docs"]}
    assert final_ids == {"parent-mid", "parent-first", "parent-last"}
    assert result["meta"]["auto_merge_applied"] is True
    assert result["meta"]["auto_merge_replaced_chunks"] == 2
    assert result["meta"]["step_chain_repaired_groups"] == ["lg_p1_l1_s0"]
    assert result["meta"]["step_chain_completion_count"] == 1
    assert result["meta"]["structure_rerank_applied"] is True
    assert result["meta"]["entity_metadata_score_applied"] is True
    assert result["meta"]["entity_type_coverage"] == 1.0
    assert result["meta"]["fallback_required"] is False
    assert result["meta"]["stage_errors"] == []
    assert set(result["meta"]["timings"]) >= {
        "rerank_ms",
        "auto_merge_ms",
        "step_chain_ms",
        "structure_rerank_ms",
        "confidence_ms",
    }
    filter_expr = milvus_query.call_args.kwargs["filter_expr"]
    assert 'filename == "manual.pdf"' in filter_expr
    assert 'index_profile == "v4"' in filter_expr
    assert "parent_list_order in [1, 3]" in filter_expr
    assert "chunk_level == 3" in filter_expr
