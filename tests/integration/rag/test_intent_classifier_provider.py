import os

import pytest

from backend.config import ARK_API_KEY, BASE_URL, FAST_MODEL, MODEL
from backend.rag.intent import IntentClassifier, build_intent_parse_result


pytestmark = pytest.mark.integration


def _provider_smoke_enabled() -> bool:
    return os.getenv("RAG_INTENT_PROVIDER_SMOKE", "").strip().lower() in {"1", "true"}


@pytest.mark.skipif(
    not _provider_smoke_enabled(),
    reason="set RAG_INTENT_PROVIDER_SMOKE=1 to call the configured intent provider",
)
def test_configured_provider_returns_schema_valid_intent_without_rules_fallback():
    model_name = os.getenv("RAG_INTENT_PROVIDER_SMOKE_MODEL") or FAST_MODEL or MODEL
    if not ARK_API_KEY or not BASE_URL or not model_name:
        pytest.skip("configured provider smoke requires ARK_API_KEY, BASE_URL, and a smoke/FAST/default model")

    timeout_seconds = float(os.getenv("RAG_INTENT_PROVIDER_SMOKE_TIMEOUT_SECONDS", "20"))
    classifier = IntentClassifier(model_name=model_name, timeout_seconds=timeout_seconds)

    result = build_intent_parse_result(
        "请比较两种设备维护方案的适用条件、风险和取舍。",
        classifier=classifier,
        classifier_enabled=True,
    )

    assert result.trace["intent_fallback_to_rules"] is False, result.trace.get("intent_llm_error")
    assert result.trace["intent_llm_model"] == model_name
    assert result.trace["intent_confidence"] >= 0.0
    assert result.trace["query_plan_type"] in {"precise", "comprehensive"}
