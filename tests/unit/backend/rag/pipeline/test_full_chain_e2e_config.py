import math
from pathlib import Path

import pytest
from dotenv import dotenv_values

from backend.chat.rag_execution import RagExecutionPolicy, RagTurnRequest, plan_rag_turn
from backend.rag.candidate_strategy import CandidateStrategyId
from backend.rag.runtime_config import load_runtime_config


pytestmark = pytest.mark.unit


WORKSPACE_ROOT = Path(__file__).resolve().parents[5]
E2E_CONFIG = WORKSPACE_ROOT / ".env.rag-full-chain-e2e.example"


def _env() -> dict[str, str | None]:
    return dict(dotenv_values(E2E_CONFIG))


def test_full_chain_e2e_overlay_is_non_secret_and_validation_only():
    raw_config = E2E_CONFIG.read_text(encoding="utf-8")
    env = _env()

    assert "FULL-CHAIN RAG E2E VALIDATION ONLY" in raw_config
    assert "NOT a\n# production recommendation" in raw_config
    assert env["LANGSMITH_TRACING"] == "true"
    assert env["LANGCHAIN_TRACING_V2"] == "true"
    assert env["LANGSMITH_PROJECT"] == "superhermes-rag-full-chain-e2e"
    assert not {
        "ARK_API_KEY",
        "OPENAI_API_KEY",
        "LANGSMITH_API_KEY",
        "JWT_SECRET_KEY",
        "ADMIN_INVITE_CODE",
        "DATABASE_URL",
        "REDIS_URL",
    }.intersection(env)
    assert "RERANK_TOP_N" not in env
    assert "RAG_FALLBACK_TIMEOUT_SECONDS" not in env


def test_full_chain_e2e_overlay_enables_composable_standard_rag_path():
    env = _env()
    config = load_runtime_config(env)

    for field_name in (
        "auto_merge_enabled",
        "structure_rerank_enabled",
        "step_chain_check_enabled",
        "rerank_cache_enabled",
        "rerank_pair_enrichment_enabled",
        "heading_lexical_enabled",
        "rerank_score_fusion_enabled",
        "query_plan_enabled",
        "intent_classifier_enabled",
        "confidence_gate_enabled",
        "enable_anchor_gate",
        "unified_execution_enabled",
        "citation_verify_enabled",
        "fallback_enabled",
        "fallback_level1_enabled",
        "fallback_level2_enabled",
        "fallback_use_fast_model",
    ):
        assert getattr(config, field_name) is True, field_name

    assert config.candidate_strategy.strategy is CandidateStrategyId.LAYERED
    assert config.rag_index_profile == "v4_full"
    assert config.intent_classifier_model == "qwen3.6-plus"
    assert config.fallback_candidate_only_enabled is False
    assert config.deep_shadow_enabled is False
    assert config.deep_active_enabled is False
    assert config.fallback_total_budget_ms > 0
    assert config.fallback_level1_budget_ms > 0
    assert config.fallback_level2_budget_ms > 0
    assert config.fallback_expanded_candidate_k >= math.ceil(config.rag_candidate_k * 1.5)


def test_full_chain_e2e_overlay_isolates_index_authorities():
    env = _env()

    assert env["RAG_INDEX_PROFILE"] == "v4_full"
    assert env["MILVUS_COLLECTION"] == "embeddings_collection_v4_full_e2e"
    assert env["BM25_STATE_PATH"] == "data/bm25_state_v4_full_e2e.json"
    assert env["EVAL_RETRIEVAL_TEXT_MODE"] == "title_context_filename"


def test_full_chain_e2e_entry_queries_have_explicit_reachability_boundary():
    bare = plan_rag_turn(
        RagTurnRequest(user_text="统一源图是什么？"),
        unified_execution_enabled=True,
    )
    marked = plan_rag_turn(
        RagTurnRequest(user_text="根据知识库，统一源图是什么？"),
        unified_execution_enabled=True,
    )
    attached = plan_rag_turn(
        RagTurnRequest(
            user_text="统一源图是什么？",
            context_files=["SCM优化方案.pdf"],
        ),
        unified_execution_enabled=True,
    )

    assert bare.policy is RagExecutionPolicy.OPTIONAL_TOOL
    assert marked.policy is RagExecutionPolicy.FORCED_PRELOAD
    assert marked.policy_reason == "document_intent"
    assert attached.policy is RagExecutionPolicy.FORCED_PRELOAD
    assert attached.policy_reason == "attached_context_files"
