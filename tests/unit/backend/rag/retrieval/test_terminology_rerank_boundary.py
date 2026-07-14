from __future__ import annotations

import inspect
import time
from unittest.mock import patch

import pytest

import backend.rag.utils as rag_utils


pytestmark = pytest.mark.unit


def test_rerank_query_contract_names_terminology_matches_not_semantic_entities():
    parameters = inspect.signature(rag_utils._rerank_documents).parameters

    assert "query_term_matches" in parameters
    assert "query_entities" not in parameters


def test_finish_pipeline_only_consumes_term_matches_and_never_emits_query_entities():
    captured = []

    def rerank(*, query, docs, top_k, query_term_matches):
        captured.extend(query_term_matches)
        return docs, {
            "rerank_enabled": True,
            "rerank_applied": True,
            "rerank_output_count": len(docs),
            "terminology_metadata_score_applied": True,
        }

    pass_stage = lambda docs, top_k: (docs, {})
    docs = [{"chunk_id": "c1", "text": "pump", "entity_types": ["component"], "term_match_count": 2}]
    with (
        patch.object(rag_utils, "_rerank_documents", side_effect=rerank),
        patch.object(rag_utils, "_auto_merge_documents", side_effect=pass_stage),
        patch.object(rag_utils, "_step_chain_check", side_effect=pass_stage),
        patch.object(rag_utils, "_apply_structure_rerank", side_effect=pass_stage),
        patch.object(rag_utils, "_evaluate_retrieval_confidence", return_value={}),
    ):
        result = rag_utils._finish_retrieval_pipeline(
            query="pump",
            search_query="pump",
            retrieved=docs,
            top_k=1,
            candidate_k=1,
            timings={},
            stage_errors=[],
            total_start=time.perf_counter(),
            extra_trace={
                "term_matches": [{"entity_type": "component", "canonical": "pump"}],
                "query_entities": [{"entity_type": "product", "canonical": "must-be-ignored"}],
            },
        )

    assert captured == [{"entity_type": "component", "canonical": "pump"}]
    assert result["meta"]["term_matches"] == captured
    assert "query_entities" not in result["meta"]


def test_term_match_count_remains_all_chunk_term_density_not_query_specific_count():
    query_term_matches = [{"entity_type": "component", "canonical": "pump"}]
    doc = {
        "entity_types": ["component", "maintenance_action", "failure_mode"],
        "term_match_count": 5,
    }

    score = rag_utils._metadata_score(doc, query_term_matches)

    assert score == pytest.approx(1.0)
