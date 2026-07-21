from dataclasses import replace
from typing import get_args
from unittest.mock import patch

import pytest

import backend.rag.pipeline as rag_pipeline
from backend.rag.intent import IntentParseResult
from backend.rag.query_plan import IntentQueryPlan, PreciseQueryPlan
from backend.rag.runtime_config import load_runtime_config


pytestmark = pytest.mark.unit


def test_rag_state_carries_typed_intent_plan_without_semantic_entities():
    annotations = rag_pipeline.RAGState.__annotations__

    assert "query_plan" in annotations
    assert "query_plan_type" in annotations
    assert "raw_query" in annotations
    assert "clean_query" in annotations
    assert "semantic_query" in annotations
    assert "term_matches" in annotations
    assert "fallback_decisions" in annotations
    assert "attempted_levels" in annotations
    assert "query_entities" not in annotations
    assert IntentParseResult.__name__ in str(annotations["intent_result"])
    assert IntentQueryPlan is not None


def test_intent_parse_disabled_builds_compatibility_plan_without_registry_or_llm():
    config = replace(
        load_runtime_config({}),
        intent_classifier_enabled=False,
        query_plan_enabled=False,
    )

    with (
        patch("backend.rag.pipeline.load_runtime_config", return_value=config),
        patch("backend.rag.pipeline.load_query_filename_registry", side_effect=AssertionError("registry")),
        patch("backend.rag.pipeline.IntentClassifier", side_effect=AssertionError("classifier")),
        patch("backend.rag.pipeline.emit_rag_step") as emit,
    ):
        result = rag_pipeline.intent_parse_node(
            {"question": "《部署手册》中，如何回滚？", "context_files": []}
        )

    assert isinstance(result["query_plan"], PreciseQueryPlan)
    assert result["query_plan_type"] == "precise"
    assert result["semantic_query"] == "《部署手册》中，如何回滚？"
    assert result["rag_trace"]["intent_classifier_enabled"] is False
    emit.assert_called_once_with(
        "🧭",
        "意图解析：精确路线",
        "已选择单路径精确检索",
    )


def test_retrieve_initial_consumes_precise_plan_and_preserves_intent_trace():
    plan = PreciseQueryPlan(
        raw_query="raw query",
        clean_query="clean query",
        semantic_query="semantic query",
        scope_mode="filter",
        matched_files=(("manual.pdf", 1.0),),
    )
    intent_result = IntentParseResult(
        intent="precise_lookup",
        confidence=0.9,
        query_plan=plan,
        trace={
            "intent": "precise_lookup",
            "intent_confidence": 0.9,
            "query_plan_type": "precise",
            "intent_fallback_to_rules": False,
        },
    )
    retrieve_result = {
        "docs": [],
        "meta": {
            "timings": {},
            "stage_errors": [],
            "semantic_query": "semantic query",
            "term_matches": [{"surface": "query"}],
            "normalized_query": "normalized query",
            "sparse_expansion": "expanded query",
            "protected_tokens": ["query"],
        },
    }

    with (
        patch("backend.rag.pipeline.retrieve_documents", return_value=retrieve_result) as retrieve,
        patch("backend.rag.pipeline.emit_rag_step"),
    ):
        result = rag_pipeline.retrieve_initial(
            {
                "question": "raw query",
                "context_files": [],
                "query_plan": plan,
                "query_plan_type": "precise",
                "intent_result": intent_result,
            }
        )

    assert retrieve.call_args.args[0] == "raw query"
    assert retrieve.call_args.kwargs["query_plan"] is plan
    assert retrieve.call_args.kwargs["strict_scope_filter"] is True
    assert "query_entities" not in retrieve.call_args.kwargs
    assert result["rag_trace"]["intent_confidence"] == 0.9
    assert result["term_matches"] == [{"surface": "query"}]
    assert result["normalized_query"] == "normalized query"
    assert result["sparse_expansion"] == "expanded query"
    assert result["protected_tokens"] == ["query"]
    assert result["rag_trace"]["semantic_query"] == "semantic query"


def test_context_files_use_one_main_retrieval_without_attachment_supplement():
    context_files = ["manual-a.pdf", "manual-b.pdf"]
    plan = PreciseQueryPlan(
        raw_query="安装步骤",
        clean_query="安装步骤",
        semantic_query="安装步骤",
        scope_mode="filter",
        matched_files=(("manual-a.pdf", 1.0), ("manual-b.pdf", 1.0)),
        route="scoped_hybrid",
    )
    retrieve_result = {
        "docs": [{"chunk_id": "main", "text": "main retrieval"}],
        "meta": {
            "timings": {},
            "stage_errors": [],
            "fallback_required": False,
            "confidence_reasons": [],
        },
    }

    with (
        patch("backend.rag.pipeline.retrieve_documents", return_value=retrieve_result) as retrieve,
        patch(
            "backend.rag.pipeline.retrieve_context_documents",
            side_effect=AssertionError("attachment supplement must not run"),
            create=True,
        ),
        patch("backend.rag.pipeline.emit_rag_step"),
    ):
        result = rag_pipeline.retrieve_initial(
            {
                "question": "安装步骤",
                "context_files": context_files,
                "query_plan": plan,
                "query_plan_type": "precise",
            }
        )

    retrieve.assert_called_once()
    assert retrieve.call_args.kwargs["context_files"] == context_files
    assert retrieve.call_args.kwargs["query_plan"] is plan
    assert retrieve.call_args.kwargs["strict_scope_filter"] is True
    assert result["docs"] == retrieve_result["docs"]
    assert result["rag_trace"].get("attached_context_chunks") in (None, [])
