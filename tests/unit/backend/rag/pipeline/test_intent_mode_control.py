from dataclasses import replace
from unittest.mock import patch

import pytest

import backend.rag.pipeline as rag_pipeline
from backend.chat.rag_execution import RagExecutionPolicy, RagTurnRequest, plan_rag_turn
from backend.chat.tools import (
    reset_tool_call_guards,
    search_knowledge_base,
    set_force_comprehensive,
    set_rag_context_files,
)
from backend.contracts.schemas import ChatRequest, RagTrace
from backend.rag.intent import (
    IntentDecision,
    IntentRoutingMode,
    build_intent_parse_result,
    resolve_intent_routing_mode,
)
from backend.rag.query_plan import ComprehensiveQueryPlan, PreciseQueryPlan
from backend.rag.runtime_config import load_runtime_config


pytestmark = pytest.mark.unit


class RecordingClassifier:
    model_name = "fake-fast"

    def __init__(self, decision=None, error=None):
        self.decision = decision
        self.error = error
        self.calls = []

    def classify(self, raw_query, *, force_comprehensive=False):
        self.calls.append((raw_query, force_comprehensive))
        if self.error:
            raise self.error
        return self.decision, 7.0


def comprehensive_decision():
    return IntentDecision.model_validate({
        "intent": "comprehensive_analysis",
        "confidence": 0.9,
        "analysis_type": "comparison",
        "sub_queries": [
            {"query": "方案 A", "domain": "A", "priority": 1},
            {"query": "方案 B", "domain": "B", "priority": 1},
        ],
    })


@pytest.mark.parametrize(
    ("forced", "enabled", "expected"),
    [
        (True, False, IntentRoutingMode.FORCED_COMPREHENSIVE),
        (True, True, IntentRoutingMode.FORCED_COMPREHENSIVE),
        (False, True, IntentRoutingMode.AUTO_CLASSIFIER),
        (False, False, IntentRoutingMode.PRECISE_ONLY),
    ],
)
def test_resolver_has_one_request_first_precedence(forced, enabled, expected):
    assert resolve_intent_routing_mode(
        force_comprehensive=forced,
        classifier_enabled=enabled,
    ) is expected


def test_forced_comprehensive_reuses_classifier_and_existing_plan():
    classifier = RecordingClassifier(comprehensive_decision())

    result = build_intent_parse_result(
        "对比方案",
        classifier=classifier,
        routing_mode=IntentRoutingMode.FORCED_COMPREHENSIVE,
    )

    assert isinstance(result.query_plan, ComprehensiveQueryPlan)
    assert classifier.calls == [("对比方案", True)]
    assert result.trace["intent_requested_mode"] == "forced_comprehensive"
    assert result.trace["intent_effective_mode"] == "forced_comprehensive"
    assert result.trace["intent_mode_source"] == "user"
    assert result.trace["intent_classifier_invoked"] is True
    assert result.trace["intent_forced_comprehensive_succeeded"] is True


@pytest.mark.parametrize(
    "classifier",
    [
        RecordingClassifier(error=RuntimeError("model unavailable")),
        RecordingClassifier(error=TimeoutError("timed out")),
        RecordingClassifier(IntentDecision.model_validate({
            "intent": "precise_lookup",
            "target_granularity": "paragraph",
        })),
    ],
)
def test_forced_comprehensive_degrades_explicitly_to_precise(classifier):
    result = build_intent_parse_result(
        "综合分析",
        classifier=classifier,
        routing_mode=IntentRoutingMode.FORCED_COMPREHENSIVE,
    )

    assert isinstance(result.query_plan, PreciseQueryPlan)
    assert result.trace["intent_requested_mode"] == "forced_comprehensive"
    assert result.trace["intent_effective_mode"] == "precise_only"
    assert result.trace["intent_forced_comprehensive_succeeded"] is False
    assert result.trace["intent_mode_degradation_error"]


def test_intent_node_resolves_forced_mode_even_when_environment_classifier_is_off():
    config = replace(
        load_runtime_config({}),
        intent_classifier_enabled=False,
        query_plan_enabled=False,
    )
    classifier = RecordingClassifier(comprehensive_decision())

    with (
        patch("backend.rag.pipeline.load_runtime_config", return_value=config),
        patch("backend.rag.pipeline.load_query_filename_registry", return_value=[]),
        patch("backend.rag.pipeline.IntentClassifier", return_value=classifier),
    ):
        result = rag_pipeline.intent_parse_node({
            "question": "对比方案",
            "context_files": [],
            "force_comprehensive": True,
        })

    assert isinstance(result["query_plan"], ComprehensiveQueryPlan)
    assert classifier.calls == [("对比方案", True)]


def test_chat_contract_defaults_old_clients_and_forces_preload_for_user_override():
    old_client = ChatRequest.model_validate({"message": "hello"})
    forced = ChatRequest.model_validate({
        "message": "hello",
        "force_comprehensive": True,
    })

    assert old_client.force_comprehensive is False
    assert forced.force_comprehensive is True
    turn = plan_rag_turn(
        RagTurnRequest(user_text="hello", force_comprehensive=True),
        unified_execution_enabled=False,
    )
    assert turn.policy is RagExecutionPolicy.FORCED_PRELOAD
    assert turn.policy_reason == "user_forced_comprehensive"
    assert turn.force_comprehensive is True


def test_public_trace_schema_keeps_intent_mode_identity():
    trace = RagTrace.model_validate({
        "tool_used": True,
        "tool_name": "search_knowledge_base",
        "intent_requested_mode": "forced_comprehensive",
        "intent_effective_mode": "precise_only",
        "intent_mode_source": "user",
        "intent_classifier_invoked": True,
        "intent_forced_comprehensive_succeeded": False,
        "intent_mode_degradation_error": "timed out",
    })

    assert trace.model_dump()["intent_mode_degradation_error"] == "timed out"


@pytest.mark.parametrize("forced", [False, True])
def test_optional_tool_passes_current_turn_override_without_resolving_mode(forced):
    reset_tool_call_guards()
    set_rag_context_files(["manual.pdf"])
    set_force_comprehensive(forced)
    with patch(
        "backend.rag.pipeline.run_rag_graph",
        return_value={"docs": [], "context": "", "rag_trace": {}},
    ) as run_graph:
        search_knowledge_base.invoke({"query": "compare"})

    assert run_graph.call_args.args == ("compare",)
    assert run_graph.call_args.kwargs == {
        "context_files": ["manual.pdf"],
        "force_comprehensive": forced,
    }
    set_rag_context_files(None)
    set_force_comprehensive(False)
