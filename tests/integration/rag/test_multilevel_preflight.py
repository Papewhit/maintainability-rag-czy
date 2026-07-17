from __future__ import annotations

import time
from dataclasses import replace
from unittest.mock import patch

import pytest

import backend.rag.pipeline as rag_pipeline
import backend.rag.utils as rag_utils
from backend.rag.intent import build_intent_parse_result
from backend.rag.query_plan import PreciseQueryPlan
from backend.rag.runtime_config import load_runtime_config
from backend.rag.terminology.table import (
    EntityType,
    TerminologyEntry,
    TerminologyTable,
    set_terminology_table,
)


pytestmark = pytest.mark.integration


def test_level_zero_plan_cleanup_and_real_terminology_composition_feed_dense_and_bm25():
    raw_query = "仅在《设备手册》中说明 MRG 拆卸步骤"
    intent = build_intent_parse_result(
        raw_query,
        classifier_enabled=False,
        query_plan_enabled=True,
        filename_registry=[{"raw": "设备手册.pdf", "normalized": "设备手册"}],
        context_files=["设备手册.pdf"],
    )
    plan = intent.query_plan
    assert isinstance(plan, PreciseQueryPlan)
    assert plan.scope_mode == "filter"
    assert "《设备手册》" not in plan.semantic_query

    table = TerminologyTable()
    table.reload_from_db(
        [
            TerminologyEntry(
                canonical="主减速齿轮箱",
                entity_type=EntityType.COMPONENT,
                variants=("MRG",),
            ),
            TerminologyEntry(
                canonical="拆卸",
                entity_type=EntityType.MAINTENANCE_ACTION,
                variants=("拆解",),
            ),
        ]
    )
    dense_inputs = []
    sparse_inputs = []

    def dense(values):
        dense_inputs.extend(values)
        return [[0.1, 0.2] for _ in values]

    def sparse(value):
        sparse_inputs.append(value)
        return {1: 0.5}

    set_terminology_table(table)
    try:
        with (
            patch.object(rag_utils._embedding_service, "get_embeddings", side_effect=dense),
            patch.object(rag_utils._embedding_service, "get_sparse_embedding", side_effect=sparse),
            patch.object(rag_utils._milvus_manager, "hybrid_retrieve", return_value=[]) as hybrid,
        ):
            result = rag_utils.retrieve_candidate_pool(
                raw_query,
                top_k=5,
                context_files=["设备手册.pdf"],
                query_plan=plan,
                query_plan_active=True,
                strict_scope_filter=True,
            )
    finally:
        set_terminology_table(TerminologyTable())

    assert dense_inputs == [result["meta"]["normalized_query"]]
    assert sparse_inputs == [result["meta"]["sparse_expansion"]]
    assert "主减速齿轮箱" in dense_inputs[0]
    assert "MRG" in sparse_inputs[0]
    assert "拆卸" in sparse_inputs[0]
    assert raw_query not in dense_inputs
    assert raw_query not in sparse_inputs
    assert result["meta"]["semantic_query"] == plan.semantic_query
    assert result["meta"]["strict_scope_filter"] is True
    assert "设备手册.pdf" in hybrid.call_args.kwargs["filter_expr"]


def test_precise_level_one_and_two_reuse_processed_queries_through_real_preflight():
    raw_query = "仅在《设备手册》中说明 MRG 拆卸步骤"
    intent = build_intent_parse_result(
        raw_query,
        classifier_enabled=False,
        query_plan_enabled=True,
        filename_registry=[{"raw": "设备手册.pdf", "normalized": "设备手册"}],
        context_files=["设备手册.pdf"],
    )
    plan = intent.query_plan
    assert isinstance(plan, PreciseQueryPlan)

    table = TerminologyTable()
    table.reload_from_db(
        [
            TerminologyEntry(
                canonical="主减速齿轮箱",
                entity_type=EntityType.COMPONENT,
                variants=("MRG",),
            ),
            TerminologyEntry(
                canonical="拆卸",
                entity_type=EntityType.MAINTENANCE_ACTION,
                variants=("拆解",),
            ),
        ]
    )
    dense_inputs: list[str] = []
    sparse_inputs: list[str] = []

    def dense(values):
        dense_inputs.extend(values)
        return [[0.1, 0.2] for _ in values]

    def sparse(value):
        sparse_inputs.append(value)
        return {1: 0.5}

    rewritten_query = "MRG 拆卸的一般安全步骤"
    state = {
        "question": raw_query,
        "semantic_query": plan.semantic_query,
        "query_plan": plan,
        "query_plan_type": "precise",
        "context_files": ["设备手册.pdf"],
        "attempted_levels": [],
        "fallback_decisions": [],
        "fallback_started_at": time.perf_counter(),
        "rag_trace": {
            "fallback_required": True,
            "confidence_reasons": ["anchor_mismatch"],
            "query_plan_enabled": True,
        },
    }
    rewrite_patch = {
        "expansion_type": "step_back",
        "expanded_query": rewritten_query,
        "step_back_question": "通常如何安全拆卸主减速齿轮箱？",
        "step_back_answer": "",
        "hypothetical_doc": "",
        "rag_trace": dict(state["rag_trace"]),
    }
    config = replace(
        load_runtime_config({}),
        fallback_enabled=True,
        fallback_total_budget_ms=8000,
        fallback_level1_budget_ms=3000,
        fallback_level2_budget_ms=2500,
    )

    set_terminology_table(table)
    try:
        with (
            patch("backend.rag.pipeline.load_runtime_config", return_value=config),
            patch("backend.rag.pipeline.rewrite_question_node", return_value=rewrite_patch),
            patch.object(rag_utils._embedding_service, "get_embeddings", side_effect=dense),
            patch.object(rag_utils._embedding_service, "get_sparse_embedding", side_effect=sparse),
            patch.object(rag_utils._milvus_manager, "hybrid_retrieve", return_value=[]),
        ):
            level1 = rag_pipeline.level1_query_rewrite_node(state)
            level2 = rag_pipeline.level2_scope_relax_node(level1)
    finally:
        set_terminology_table(TerminologyTable())

    assert level2["attempted_levels"] == [1, 2]
    assert len(dense_inputs) == 2
    assert len(sparse_inputs) == 2
    assert all("《设备手册》" not in value for value in dense_inputs + sparse_inputs)
    assert all(raw_query != value for value in dense_inputs + sparse_inputs)
    assert all("主减速齿轮箱" in value for value in dense_inputs)
    assert all("MRG" in value for value in sparse_inputs)
    assert level1["rag_trace"]["fallback_round_queries"] == [rewritten_query]
    assert level2["rag_trace"]["fallback_round_queries"] == [rewritten_query]
