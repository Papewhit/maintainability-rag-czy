from dataclasses import fields
import time
from unittest.mock import patch

import pytest

import backend.rag.query_plan as query_plan
from backend.rag.intent import (
    IntentClassifier,
    IntentDecision,
    build_intent_parse_result,
)
from backend.rag.query_plan import ComprehensiveQueryPlan, PreciseQueryPlan


class FakeStructuredInvoker:
    def __init__(self, schema, payload=None, error=None):
        self.schema = schema
        self.payload = payload
        self.error = error
        self.messages = None
        self.invoke_count = 0

    def invoke(self, messages):
        self.invoke_count += 1
        self.messages = messages
        if self.error:
            raise self.error
        return self.schema.model_validate(self.payload)


class FakeModel:
    def __init__(self, payload=None, error=None):
        self.payload = payload
        self.error = error
        self.invoker = None

    def with_structured_output(self, schema):
        self.invoker = FakeStructuredInvoker(schema, self.payload, self.error)
        return self.invoker


class SlowStructuredInvoker(FakeStructuredInvoker):
    def invoke(self, messages):
        time.sleep(0.05)
        return super().invoke(messages)


class SlowModel(FakeModel):
    def with_structured_output(self, schema):
        self.invoker = SlowStructuredInvoker(schema, self.payload, self.error)
        return self.invoker


REGISTRY = [
    {"raw": "部署手册.pdf", "normalized": "部署手册"},
]


@pytest.mark.unit
def test_classifier_returns_structured_precise_decision_with_few_shot_prompt():
    model = FakeModel(
        {
            "intent": "precise_lookup",
            "confidence": 0.91,
            "scope_hint": "filter",
            "anchors": ["第三章"],
            "target_granularity": "step_list",
        }
    )
    classifier = IntentClassifier(model=model, model_name="fake-fast", timeout_seconds=1)

    decision, elapsed_ms = classifier.classify("《部署手册》第三章的回滚步骤")

    assert isinstance(decision, IntentDecision)
    assert decision.intent == "precise_lookup"
    assert decision.target_granularity == "step_list"
    assert elapsed_ms >= 0
    system_prompt = model.invoker.messages[0]["content"]
    assert system_prompt.count("示例") >= 3
    assert "terminology" in system_prompt
    assert model.invoker.invoke_count == 1


@pytest.mark.unit
def test_precise_decision_builds_deterministic_plan_without_llm_semantic_query():
    decision = IntentDecision.model_validate(
        {
            "intent": "precise_lookup",
            "confidence": 0.9,
            "scope_hint": "filter",
            "anchors": ["第三章"],
            "target_granularity": "step_list",
        }
    )

    result = build_intent_parse_result(
        "《部署手册》中，第三章的回滚步骤",
        decision=decision,
        filename_registry=REGISTRY,
        llm_model="fake-fast",
        llm_ms=1.2,
    )

    assert isinstance(result.query_plan, PreciseQueryPlan)
    assert result.query_plan.target_granularity == "step_list"
    assert "部署手册" not in result.query_plan.semantic_query
    assert "第三章" not in result.query_plan.semantic_query
    assert not hasattr(result.query_plan, "entities")


@pytest.mark.unit
def test_comprehensive_decision_builds_runtime_clean_query_and_profile():
    decision = IntentDecision.model_validate(
        {
            "intent": "comprehensive_analysis",
            "confidence": 0.88,
            "analysis_type": "comparison",
            "sub_queries": [
                {"query": "方案 A 的优点", "domain": "A", "priority": 1},
                {"query": "方案 B 的风险", "domain": "B", "priority": 2},
            ],
        }
    )

    result = build_intent_parse_result(
        "对比方案 A 和方案 B",
        decision=decision,
        postprocess_profile="quality_first_v1",
        llm_model="fake-fast",
        llm_ms=2.0,
    )

    assert isinstance(result.query_plan, ComprehensiveQueryPlan)
    assert result.query_plan.clean_query == "对比方案 A 和方案 B"
    assert result.query_plan.postprocess_profile == "quality_first_v1"
    assert result.query_plan.coverage_domains == ("A", "B")
    assert result.trace["sub_query_count"] == 2
    assert result.trace["retrieval_branch_count"] == 3
    assert "entities" not in {item.name for item in fields(ComprehensiveQueryPlan)}


@pytest.mark.unit
def test_comprehensive_document_hints_default_to_shared_boost_scope():
    decision = IntentDecision.model_validate(
        {
            "intent": "comprehensive_analysis",
            "confidence": 0.88,
            "analysis_type": "comparison",
            "sub_queries": [
                {"query": "部署方案", "domain": "deployment", "priority": 1},
                {"query": "运维方案", "domain": "operations", "priority": 2},
            ],
        }
    )
    registry = [
        {"raw": "部署手册.pdf", "normalized": "部署手册"},
        {"raw": "运维手册.pdf", "normalized": "运维手册"},
    ]

    result = build_intent_parse_result(
        "比较《部署手册》和《运维手册》的方案取舍",
        decision=decision,
        filename_registry=registry,
    )

    assert isinstance(result.query_plan, ComprehensiveQueryPlan)
    assert result.query_plan.retrieval_scope.scope_mode == "boost"
    assert {item[0] for item in result.query_plan.retrieval_scope.matched_files} == {
        "部署手册.pdf",
        "运维手册.pdf",
    }
    assert "部署手册" not in result.query_plan.clean_query
    assert "运维手册" not in result.query_plan.clean_query


@pytest.mark.unit
@pytest.mark.parametrize(
    "query",
    [
        "仅在《部署手册》中综合分析回滚与恢复策略",
        "请仅在《部署手册》中综合分析回滚与恢复策略",
        "综合分析时，仅在《部署手册》中取证",
        "检索范围限定为《部署手册》，综合分析回滚与恢复策略",
    ],
)
def test_comprehensive_explicit_closed_wording_creates_shared_filter_scope(query):
    decision = IntentDecision.model_validate(
        {
            "intent": "comprehensive_analysis",
            "confidence": 0.88,
            "analysis_type": "general",
            "sub_queries": [{"query": "回滚策略", "domain": "rollback", "priority": 1}],
        }
    )

    result = build_intent_parse_result(query, decision=decision, filename_registry=REGISTRY)

    assert isinstance(result.query_plan, ComprehensiveQueryPlan)
    assert result.query_plan.retrieval_scope.scope_mode == "filter"
    assert result.query_plan.retrieval_scope.source == "explicit_closed_scope"
    assert "仅在" not in result.query_plan.clean_query
    assert "范围限定" not in result.query_plan.clean_query
    assert "部署手册" not in result.query_plan.clean_query


@pytest.mark.unit
@pytest.mark.parametrize(
    "query",
    [
        "不仅在《部署手册》中，也从全局资料综合分析回滚策略",
        "不只在《部署手册》中，也从全局资料综合分析回滚策略",
        "并非仅在《部署手册》中，而要综合全局资料分析回滚策略",
        "不是仅在《部署手册》中，而要检索全局资料",
        "并不是只在《部署手册》中，而要检索全局资料",
        "不应当仅在《部署手册》中，而要检索全局资料",
        "不应该仅在《部署手册》中，而要检索全局资料",
    ],
)
def test_comprehensive_negative_closed_wording_remains_shared_boost(query):
    decision = IntentDecision.model_validate(
        {
            "intent": "comprehensive_analysis",
            "confidence": 0.88,
            "analysis_type": "general",
            "sub_queries": [{"query": "回滚策略", "domain": "rollback", "priority": 1}],
        }
    )

    result = build_intent_parse_result(
        query,
        decision=decision,
        filename_registry=REGISTRY,
    )

    assert isinstance(result.query_plan, ComprehensiveQueryPlan)
    assert result.query_plan.retrieval_scope.scope_mode == "boost"


@pytest.mark.unit
def test_closed_scope_cleanup_preserves_unrelated_restrictive_language():
    decision = IntentDecision.model_validate(
        {
            "intent": "comprehensive_analysis",
            "confidence": 0.88,
            "analysis_type": "general",
            "sub_queries": [{"query": "验证记录", "domain": "evidence", "priority": 1}],
        }
    )

    result = build_intent_parse_result(
        "仅在《部署手册》中说明，只参考已验证记录，不使用传闻",
        decision=decision,
        filename_registry=REGISTRY,
    )

    assert isinstance(result.query_plan, ComprehensiveQueryPlan)
    assert result.query_plan.retrieval_scope.scope_mode == "filter"
    assert "只参考已验证记录" in result.query_plan.clean_query


@pytest.mark.unit
def test_unresolved_closed_scope_stays_comprehensive_and_preserves_query_text(monkeypatch):
    monkeypatch.setattr(query_plan, "DOC_SCOPE_MATCH_BOOST", 0.60)
    decision = IntentDecision.model_validate(
        {
            "intent": "comprehensive_analysis",
            "confidence": 0.88,
            "analysis_type": "general",
            "sub_queries": [{"query": "回滚策略", "domain": "rollback", "priority": 1}],
        }
    )
    raw_query = "仅在《未知手册》中综合分析回滚策略"

    result = build_intent_parse_result(
        raw_query,
        decision=decision,
        filename_registry=REGISTRY,
    )

    assert isinstance(result.query_plan, ComprehensiveQueryPlan)
    assert result.intent == "comprehensive_analysis"
    assert result.query_plan.retrieval_scope.scope_mode == "none"
    assert result.query_plan.retrieval_scope.matched_files == ()
    assert result.query_plan.clean_query == raw_query
    assert result.trace["intent_fallback_to_rules"] is False


@pytest.mark.unit
def test_comprehensive_context_files_create_shared_filter_scope():
    decision = IntentDecision.model_validate(
        {
            "intent": "comprehensive_analysis",
            "confidence": 0.88,
            "analysis_type": "general",
            "sub_queries": [{"query": "回滚策略", "domain": "rollback", "priority": 1}],
        }
    )

    result = build_intent_parse_result(
        "综合分析回滚与恢复策略",
        decision=decision,
        context_files=["部署手册.pdf"],
    )

    assert isinstance(result.query_plan, ComprehensiveQueryPlan)
    assert result.query_plan.retrieval_scope.scope_mode == "filter"
    assert result.query_plan.retrieval_scope.matched_files == (("部署手册.pdf", 1.0),)
    assert result.query_plan.retrieval_scope.source == "context_files"


@pytest.mark.unit
def test_llm_cannot_supply_entities_semantic_query_or_postprocess_profile():
    payload = {
        "intent": "comprehensive_analysis",
        "confidence": 0.8,
        "analysis_type": "general",
        "sub_queries": [{"query": "q1", "domain": "d", "priority": 1}],
        "entities": [{"type": "product", "value": "x"}],
        "semantic_query": "generated",
        "postprocess_profile": "untrusted",
    }

    with pytest.raises(ValueError):
        IntentDecision.model_validate(payload)


@pytest.mark.unit
def test_classifier_error_falls_back_to_compatible_precise_plan():
    classifier = IntentClassifier(
        model=FakeModel(error=RuntimeError("model down")),
        model_name="fake-fast",
        timeout_seconds=1,
    )

    result = build_intent_parse_result(
        "《部署手册》中，如何回滚？",
        classifier=classifier,
        query_plan_enabled=False,
        filename_registry=REGISTRY,
    )

    assert isinstance(result.query_plan, PreciseQueryPlan)
    assert result.query_plan.semantic_query == result.query_plan.raw_query
    assert result.trace["intent_fallback_to_rules"] is True
    assert "model down" in result.trace["intent_llm_error"]
    assert result.trace["intent_llm_ms"] > 0


@pytest.mark.unit
def test_classifier_timeout_falls_back_without_retry_and_records_actual_duration():
    model = SlowModel(
        {
            "intent": "precise_lookup",
            "confidence": 0.9,
            "target_granularity": "paragraph",
        }
    )
    classifier = IntentClassifier(model=model, model_name="fake-fast", timeout_seconds=0.01)

    result = build_intent_parse_result("查询部署要求", classifier=classifier)

    assert isinstance(result.query_plan, PreciseQueryPlan)
    assert result.trace["intent_fallback_to_rules"] is True
    assert "timed out" in result.trace["intent_llm_error"]
    assert result.trace["intent_llm_ms"] >= 10
    time.sleep(0.06)
    assert model.invoker.invoke_count == 1


@pytest.mark.unit
def test_invalid_structured_output_falls_back_without_entities_or_terminology_state():
    classifier = IntentClassifier(
        model=FakeModel(
            {
                "intent": "comprehensive_analysis",
                "confidence": 0.8,
                "analysis_type": "general",
                "sub_queries": [],
                "entities": [{"type": "product", "value": "x"}],
            }
        ),
        model_name="fake-fast",
        timeout_seconds=1,
    )

    result = build_intent_parse_result("综合分析维护记录", classifier=classifier)

    assert isinstance(result.query_plan, PreciseQueryPlan)
    assert result.trace["intent_fallback_to_rules"] is True
    assert not hasattr(result.query_plan, "entities")
    assert "term_matches" not in result.trace


@pytest.mark.unit
def test_empty_comprehensive_clean_query_is_invalid_and_falls_back_to_precise():
    decision = IntentDecision.model_validate(
        {
            "intent": "comprehensive_analysis",
            "confidence": 0.8,
            "analysis_type": "general",
            "sub_queries": [{"query": "第三章概要", "domain": "overview", "priority": 1}],
        }
    )

    result = build_intent_parse_result("第三章", decision=decision, query_plan_enabled=False)

    assert isinstance(result.query_plan, PreciseQueryPlan)
    assert result.query_plan.semantic_query == "第三章"
    assert result.trace["intent_fallback_to_rules"] is True


@pytest.mark.unit
def test_llm_anchor_is_removed_only_after_being_recorded_as_consumed():
    decision = IntentDecision.model_validate(
        {
            "intent": "precise_lookup",
            "confidence": 0.9,
            "scope_hint": "none",
            "anchors": ["表2"],
            "target_granularity": "table",
        }
    )

    result = build_intent_parse_result("请给出表2的额定参数", decision=decision)

    assert isinstance(result.query_plan, PreciseQueryPlan)
    assert result.query_plan.anchors == ("表2",)
    assert "表2" not in result.query_plan.semantic_query
    assert any(span.text == "表2" and span.owner == "anchor" for span in result.query_plan.consumed_spans)


@pytest.mark.unit
def test_scope_hint_cannot_override_a_deterministic_precise_range():
    boost = IntentDecision.model_validate(
        {
            "intent": "precise_lookup",
            "confidence": 0.9,
            "scope_hint": "boost",
            "target_granularity": "paragraph",
        }
    )
    none = boost.model_copy(update={"scope_hint": "none"})

    boosted = build_intent_parse_result("《部署手册》中，回滚要求", decision=boost, filename_registry=REGISTRY)
    unscoped = build_intent_parse_result("《部署手册》中，回滚要求", decision=none, filename_registry=REGISTRY)

    assert isinstance(boosted.query_plan, PreciseQueryPlan)
    assert boosted.query_plan.scope_mode == "filter"
    assert "部署手册" not in boosted.query_plan.semantic_query
    assert isinstance(unscoped.query_plan, PreciseQueryPlan)
    assert unscoped.query_plan.scope_mode == "filter"
    assert "部署手册" not in unscoped.query_plan.semantic_query


@pytest.mark.unit
def test_lazy_model_configures_provider_timeout_and_disables_provider_retry():
    classifier = IntentClassifier(model_name="fake-fast", timeout_seconds=0.25)

    with (
        patch("backend.rag.intent.ARK_API_KEY", "key"),
        patch("backend.rag.intent.init_chat_model", return_value=object()) as init_model,
    ):
        classifier._get_model()

    assert init_model.call_args.kwargs["timeout"] == 0.25
    assert init_model.call_args.kwargs["max_retries"] == 0


@pytest.mark.unit
def test_classifier_rejects_work_when_bounded_capacity_is_exhausted():
    class ExhaustedSlots:
        @staticmethod
        def acquire(*, blocking):
            assert blocking is False
            return False

    model = FakeModel(
        {
            "intent": "precise_lookup",
            "confidence": 0.9,
            "target_granularity": "paragraph",
        }
    )
    classifier = IntentClassifier(model=model, model_name="fake-fast", timeout_seconds=1)

    with patch("backend.rag.intent._INTENT_SLOTS", ExhaustedSlots()):
        with pytest.raises(RuntimeError, match="capacity exhausted"):
            classifier.classify("查询部署要求")

    assert model.invoker.invoke_count == 0


@pytest.mark.unit
def test_classifier_disabled_never_invokes_model_or_enables_query_rules():
    model = FakeModel({"intent": "comprehensive_analysis"})
    classifier = IntentClassifier(model=model, model_name="fake-fast", timeout_seconds=1)

    result = build_intent_parse_result(
        "《部署手册》中，比较两种回滚方案",
        classifier=classifier,
        classifier_enabled=False,
        query_plan_enabled=False,
        filename_registry=REGISTRY,
    )

    assert model.invoker is None
    assert isinstance(result.query_plan, PreciseQueryPlan)
    assert result.query_plan.semantic_query == result.query_plan.raw_query
    assert result.trace["intent_classifier_enabled"] is False
    assert result.trace["intent_fallback_to_rules"] is False
    assert "intent_llm_error" not in result.trace
