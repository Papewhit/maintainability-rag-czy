from pathlib import Path

import pytest
from dotenv import dotenv_values

from backend.rag.runtime_config import load_runtime_config


pytestmark = pytest.mark.unit


WORKSPACE_ROOT = Path(__file__).resolve().parents[5]
WORKFLOW_VALIDATION_CONFIG = WORKSPACE_ROOT / ".env.rag-intent-routing-workflow.example"


def test_intent_classifier_config_defaults_are_safe():
    config = load_runtime_config({})

    assert config.intent_classifier_enabled is False
    assert config.intent_classifier_model is None
    assert config.intent_classifier_timeout_seconds == 2.0
    assert config.comprehensive_postprocess_profile == "quality_first_v1"
    assert config.comprehensive_max_sub_queries == 4
    assert config.fallback_comprehensive_rewrite_window == 2


def test_intent_classifier_config_reads_explicit_environment():
    config = load_runtime_config(
        {
            "RAG_INTENT_CLASSIFIER_ENABLED": "true",
            "RAG_INTENT_CLASSIFIER_MODEL": "fast-intent-model",
            "RAG_INTENT_CLASSIFIER_TIMEOUT_SECONDS": "1.25",
            "RAG_COMPREHENSIVE_POSTPROCESS_PROFILE": "quality_first_v2",
            "RAG_COMPREHENSIVE_MAX_SUB_QUERIES": "6",
            "RAG_FALLBACK_COMPREHENSIVE_REWRITE_WINDOW": "3",
        }
    )

    assert config.intent_classifier_enabled is True
    assert config.intent_classifier_model == "fast-intent-model"
    assert config.intent_classifier_timeout_seconds == 1.25
    assert config.comprehensive_postprocess_profile == "quality_first_v2"
    assert config.comprehensive_max_sub_queries == 6
    assert config.fallback_comprehensive_rewrite_window == 3


@pytest.mark.parametrize(
    ("configured", "expected"),
    [("0", 1), ("999", 8)],
)
def test_comprehensive_sub_query_limit_has_safe_runtime_bounds(configured, expected):
    config = load_runtime_config({"RAG_COMPREHENSIVE_MAX_SUB_QUERIES": configured})

    assert config.comprehensive_max_sub_queries == expected


def test_workflow_validation_config_enables_anchor_consumers_as_a_group():
    raw_config = WORKFLOW_VALIDATION_CONFIG.read_text(encoding="utf-8")
    config = load_runtime_config(dotenv_values(WORKFLOW_VALIDATION_CONFIG))

    assert "WORKFLOW VALIDATION ONLY" in raw_config
    assert "NOT A PRODUCTION RECOMMENDATION" in raw_config
    assert config.intent_classifier_enabled is True
    assert config.query_plan_enabled is True
    assert config.heading_lexical_enabled is True
    assert config.confidence_gate_enabled is True
    assert config.enable_anchor_gate is True
    assert config.fallback_enabled is True
