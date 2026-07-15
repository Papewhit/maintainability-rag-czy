from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

import pytest
from dotenv import dotenv_values

import backend.rag.pipeline as rag_pipeline
import backend.rag.utils as rag_utils
from backend.contracts.schemas import ChatResponse
from backend.rag.intent import IntentClassifier
from backend.rag.query_plan import ComprehensiveQueryPlan
from backend.rag.runtime_config import load_runtime_config


pytestmark = pytest.mark.e2e


WORKSPACE_ROOT = Path(__file__).resolve().parents[3]
WORKFLOW_CONFIG = WORKSPACE_ROOT / ".env.rag-intent-routing-workflow.example"


class _FakeStructuredIntentModel:
    def __init__(self, payload):
        self.payload = payload
        self.invoke_count = 0
        self.messages = None
        self.schema = None

    def with_structured_output(self, schema):
        self.schema = schema
        return self

    def invoke(self, messages):
        self.invoke_count += 1
        self.messages = messages
        return self.schema.model_validate(self.payload)


def test_comprehensive_intent_routing_runs_through_the_compiled_graph():
    question = "综合分析回滚与恢复策略"
    branch_queries = (question, "回滚策略", "恢复策略")
    query_ids = {f"dense::{query}": index for index, query in enumerate(branch_queries, 1)}
    evidence_by_id = {
        1: "整体回滚与恢复背景",
        2: "回滚前应保存配置并验证检查点",
        3: "恢复后应执行健康检查并确认数据一致性",
    }
    runtime = replace(
        load_runtime_config(dotenv_values(WORKFLOW_CONFIG)),
        intent_classifier_model="fake-intent-model",
        intent_classifier_timeout_seconds=1.0,
        rerank_candidate_pool_size=6,
        rerank_input_k_cpu=6,
    )
    model = _FakeStructuredIntentModel(
        {
            "intent": "comprehensive_analysis",
            "confidence": 0.93,
            "analysis_type": "comparison",
            "sub_queries": [
                {"query": "回滚策略", "domain": "rollback", "priority": 1},
                {"query": "恢复策略", "domain": "recovery", "priority": 2},
            ],
        }
    )
    classifier = IntentClassifier(
        model=model,
        model_name=runtime.intent_classifier_model,
        timeout_seconds=runtime.intent_classifier_timeout_seconds,
    )
    preflight_inputs = []
    embedding_inputs = []
    retrieval_filters = []

    def terminology_preflight(query):
        preflight_inputs.append(query)
        return {
            "term_matches": [
                {
                    "entity_type": "maintenance_action",
                    "canonical": query,
                    "surface": query,
                    "start": 0,
                    "end": len(query),
                }
            ],
            "normalized_query": f"dense::{query}",
            "sparse_expansion": f"bm25::{query}",
            "protected_tokens": [query],
        }

    def embed_search_query(search_query, timings, stage_errors, *, sparse_query):
        del timings, stage_errors
        embedding_inputs.append((search_query, sparse_query))
        query_id = query_ids[search_query]
        return rag_utils.QueryEmbeddings(
            dense=[float(query_id)],
            sparse={query_id: 1.0},
        )

    def retrieve_candidates(
        embeddings,
        *,
        candidate_k,
        filter_expr,
        timings,
        trace_patch,
        **kwargs,
    ):
        del candidate_k, timings, kwargs
        query_id = int(embeddings.dense[0])
        retrieval_filters.append(filter_expr)
        return rag_utils.CandidateRetrievalResult(
            candidates=[
                {
                    "chunk_id": f"chunk-{query_id}",
                    "root_chunk_id": f"root-{query_id}",
                    "parent_chunk_id": f"parent-{query_id}",
                    "chunk_level": 3,
                    "chunk_role": "leaf",
                    "filename": "maintenance.pdf",
                    "page_number": query_id,
                    "text": evidence_by_id[query_id],
                    "retrieval_text": evidence_by_id[query_id],
                    "rrf_rank": 1,
                    "rrf_score": 1.0 - query_id * 0.1,
                    "score": 1.0 - query_id * 0.1,
                }
            ],
            retrieval_mode="hybrid",
            trace_patch={**trace_patch, "hybrid_search_call_count": 1},
        )

    def rerank(query, docs, top_k, query_term_matches=None):
        assert query_term_matches
        reranked = [
            {
                **doc,
                "raw_rerank_score": 0.95,
                "rerank_score": 0.95,
            }
            for doc in docs[:top_k]
        ]
        return reranked, {
            "rerank_applied": True,
            "rerank_input_count": len(docs),
            "rerank_output_count": len(reranked),
        }

    with (
        patch("backend.rag.pipeline._runtime_config", return_value=runtime),
        patch("backend.rag.pipeline.IntentClassifier", return_value=classifier) as classifier_factory,
        patch("backend.rag.pipeline.load_query_filename_registry", return_value=[]),
        patch("backend.rag.pipeline._rerank_documents", side_effect=rerank),
        patch("backend.rag.utils.terminology_preflight", side_effect=terminology_preflight),
        patch("backend.rag.utils.embed_search_query", side_effect=embed_search_query),
        patch("backend.rag.utils.retrieve_global_candidates", side_effect=retrieve_candidates),
        patch.object(rag_utils, "HEADING_LEXICAL_ENABLED", runtime.heading_lexical_enabled),
        patch.object(rag_utils, "AUTO_MERGE_ENABLED", False),
        patch.object(rag_utils, "STEP_CHAIN_CHECK_ENABLED", False),
        patch.object(rag_utils, "STRUCTURE_RERANK_ENABLED", True),
        patch.object(rag_utils, "CONFIDENCE_GATE_ENABLED", runtime.confidence_gate_enabled),
        patch.object(rag_utils, "ENABLE_ANCHOR_GATE", runtime.enable_anchor_gate),
        patch.object(rag_utils, "LOW_CONF_TOP_MARGIN", 0.0),
        patch.object(rag_utils, "LOW_CONF_ROOT_SHARE", 0.0),
        patch.object(rag_utils, "LOW_CONF_TOP_SCORE", 0.0),
    ):
        result = rag_pipeline.run_rag_graph(
            question,
            context_files=["maintenance.pdf"],
        )

    assert classifier_factory.call_count == 1
    assert model.invoke_count == 1
    assert model.messages[-1]["content"] == question
    assert isinstance(result["query_plan"], ComprehensiveQueryPlan)
    assert result["query_plan"].retrieval_scope.scope_mode == "filter"
    assert result["query_plan"].retrieval_scope.matched_files == (
        ("maintenance.pdf", 1.0),
    )
    assert set(preflight_inputs) == set(branch_queries)
    assert set(embedding_inputs) == {
        (f"dense::{query}", f"bm25::{query}") for query in branch_queries
    }
    assert len(retrieval_filters) == 3
    assert all('filename in ["maintenance.pdf"]' in value for value in retrieval_filters)

    assert {doc["chunk_id"] for doc in result["docs"]} == {
        "chunk-1",
        "chunk-2",
        "chunk-3",
    }
    assert all(text in result["context"] for text in evidence_by_id.values())
    assert all(doc["matched_branch_ids"] for doc in result["docs"])

    trace = result["rag_trace"]
    assert trace["intent"] == "comprehensive_analysis"
    assert trace["query_plan_type"] == "comprehensive"
    assert trace["intent_fallback_to_rules"] is False
    assert trace["sub_query_count"] == 2
    assert trace["retrieval_branch_count"] == 3
    assert trace["dense_embedding_call_count"] == 3
    assert trace["sparse_embedding_call_count"] == 3
    assert trace["hybrid_search_call_count"] == 3
    assert trace["rerank_pair_count"] == 3
    assert trace["shared_postprocess_count"] == 1
    assert trace["retrieval_stage"] == "comprehensive"
    assert trace["retrieval_mode"] == "comprehensive_parallel_hybrid"
    assert trace["retrieval_scope"] == {
        "scope_mode": "filter",
        "source": "context_files",
        "matched_files": [{"filename": "maintenance.pdf", "score": 1.0}],
    }
    assert trace["fallback_required"] is False
    assert trace["stage_errors"] == []
    assert "total_rag_graph_ms" in trace["timings"]

    public_trace = ChatResponse(response="ok", rag_trace=trace).model_dump()["rag_trace"]
    assert public_trace["intent"] == "comprehensive_analysis"
    assert public_trace["retrieval_branch_count"] == 3
    assert len(public_trace["retrieved_chunks"]) == 3
