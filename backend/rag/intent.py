from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
from dataclasses import dataclass, replace
from threading import BoundedSemaphore
from typing import Any, Literal

from langchain.chat_models import init_chat_model
from pydantic import BaseModel, ConfigDict, Field, model_validator

from backend.config import ARK_API_KEY, BASE_URL, FAST_MODEL
from backend.rag.query_plan import (
    ComprehensiveQueryPlan,
    IntentQueryPlan,
    PreciseQueryPlan,
    SubQuery,
    build_compatible_precise_plan,
    parse_query_plan,
    precise_plan_from_legacy,
)


INTENT_SYSTEM_PROMPT = """你是 RAG graph 内部的意图解析器。一次调用只完成意图分类和计划提示。
只输出 schema 允许的字段。禁止输出 semantic_query、terminology normalization、entities 或 postprocess profile。

精确查找 precise_lookup：定位具体文档、章节、表格、步骤或图。
综合分析 comprehensive_analysis：需要跨来源比较、归纳、复用或多维综合。

示例 1："《部署手册》第三章的回滚步骤" -> precise_lookup，target_granularity=step_list。
示例 2："表 2 的额定参数是多少" -> precise_lookup，target_granularity=table。
示例 3："对比方案 A 与方案 B 的取舍" -> comprehensive_analysis，analysis_type=comparison，拆成独立维度。
示例 4："综合多份维修记录给出操作流程" -> comprehensive_analysis，analysis_type=procedure_synthesis。
"""


_INTENT_EXECUTOR = ThreadPoolExecutor(max_workers=4, thread_name_prefix="rag-intent")
_INTENT_SLOTS = BoundedSemaphore(4)


class IntentSubQuery(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query: str = Field(min_length=1)
    domain: str = Field(min_length=1)
    priority: int = Field(ge=1, le=3)


class IntentDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    intent: Literal["precise_lookup", "comprehensive_analysis"]
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    scope_hint: Literal["filter", "boost", "none"] | None = None
    anchors: list[str] = Field(default_factory=list)
    target_granularity: Literal["paragraph", "table", "step_list", "figure"] | None = None
    analysis_type: Literal["design_reuse", "comparison", "procedure_synthesis", "general"] | None = None
    sub_queries: list[IntentSubQuery] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_intent_fields(self) -> "IntentDecision":
        if self.intent == "precise_lookup":
            if self.target_granularity is None:
                raise ValueError("precise intent requires target_granularity")
            if self.analysis_type is not None or self.sub_queries:
                raise ValueError("precise intent must not contain comprehensive fields")
        else:
            if self.analysis_type is None or not self.sub_queries:
                raise ValueError("comprehensive intent requires analysis_type and sub_queries")
            if self.scope_hint is not None or self.target_granularity is not None or self.anchors:
                raise ValueError("comprehensive intent must not contain precise fields")
        return self


@dataclass(frozen=True)
class IntentParseResult:
    intent: Literal["precise_lookup", "comprehensive_analysis"]
    confidence: float
    query_plan: IntentQueryPlan
    trace: dict[str, Any]


class IntentClassifier:
    def __init__(
        self,
        *,
        model: Any | None = None,
        model_name: str | None = None,
        timeout_seconds: float = 2.0,
    ) -> None:
        self.model_name = model_name or FAST_MODEL or "unknown"
        self.timeout_seconds = max(0.001, float(timeout_seconds))
        self._model = model

    def _get_model(self) -> Any:
        if self._model is not None:
            return self._model
        if not ARK_API_KEY or not self.model_name or self.model_name == "unknown":
            raise RuntimeError("intent classifier model is not configured")
        self._model = init_chat_model(
            model=self.model_name,
            model_provider="openai",
            api_key=ARK_API_KEY,
            base_url=BASE_URL,
            temperature=0,
            stream_usage=True,
            timeout=self.timeout_seconds,
            max_retries=0,
        )
        return self._model

    def classify(self, raw_query: str) -> tuple[IntentDecision, float]:
        started = time.perf_counter()
        structured = self._get_model().with_structured_output(IntentDecision)
        if not _INTENT_SLOTS.acquire(blocking=False):
            raise RuntimeError("intent classifier capacity exhausted")
        try:
            future = _INTENT_EXECUTOR.submit(
                structured.invoke,
                [
                    {"role": "system", "content": INTENT_SYSTEM_PROMPT},
                    {"role": "user", "content": raw_query},
                ],
            )
        except Exception:
            _INTENT_SLOTS.release()
            raise
        future.add_done_callback(lambda _: _INTENT_SLOTS.release())
        try:
            value = future.result(timeout=self.timeout_seconds)
        except FutureTimeoutError as exc:
            future.cancel()
            raise TimeoutError(f"intent classifier timed out after {self.timeout_seconds:.3f}s") from exc
        decision = value if isinstance(value, IntentDecision) else IntentDecision.model_validate(value)
        return decision, (time.perf_counter() - started) * 1000


def _precise_plan_from_decision(
    raw_query: str,
    decision: IntentDecision,
    *,
    filename_registry: list[dict[str, str]] | None,
    context_files: list[str] | None,
) -> PreciseQueryPlan:
    legacy = parse_query_plan(
        raw_query,
        filename_registry=filename_registry,
        context_files=context_files,
        additional_anchors=decision.anchors,
        preferred_scope_mode=decision.scope_hint,
    )
    plan = precise_plan_from_legacy(
        legacy,
        target_granularity=decision.target_granularity or "paragraph",
    )
    return replace(plan, intent_type="precise_lookup")


def _comprehensive_plan_from_decision(
    raw_query: str,
    decision: IntentDecision,
    *,
    filename_registry: list[dict[str, str]] | None,
    context_files: list[str] | None,
    postprocess_profile: str,
) -> ComprehensiveQueryPlan:
    structural = parse_query_plan(
        raw_query,
        filename_registry=filename_registry,
        context_files=context_files,
        fallback_empty_queries=False,
    )
    sub_queries = tuple(
        SubQuery(query=item.query, domain=item.domain, priority=item.priority)
        for item in decision.sub_queries
    )
    coverage_domains = tuple(dict.fromkeys(item.domain for item in sub_queries))
    return ComprehensiveQueryPlan(
        raw_query=raw_query,
        clean_query=structural.clean_query,
        analysis_type=decision.analysis_type or "general",
        sub_queries=sub_queries,
        coverage_domains=coverage_domains,
        postprocess_profile=postprocess_profile,
    )


def build_intent_parse_result(
    raw_query: str,
    *,
    decision: IntentDecision | None = None,
    classifier: IntentClassifier | None = None,
    classifier_enabled: bool = True,
    query_plan_enabled: bool = False,
    filename_registry: list[dict[str, str]] | None = None,
    context_files: list[str] | None = None,
    postprocess_profile: str = "quality_first_v1",
    llm_model: str | None = None,
    llm_ms: float = 0.0,
) -> IntentParseResult:
    if not classifier_enabled:
        plan = build_compatible_precise_plan(
            raw_query,
            query_plan_enabled=query_plan_enabled,
            filename_registry=filename_registry,
            context_files=context_files,
        )
        return IntentParseResult(
            intent="precise_lookup",
            confidence=1.0,
            query_plan=plan,
            trace={
                "intent": "precise_lookup",
                "intent_confidence": 1.0,
                "query_plan_type": "precise",
                "intent_classifier_enabled": False,
                "intent_compatibility_source": "query_plan" if query_plan_enabled else "raw_query",
                "intent_fallback_to_rules": False,
            },
        )

    effective_classifier = classifier
    classify_started = time.perf_counter()
    try:
        if decision is None:
            effective_classifier = effective_classifier or IntentClassifier()
            decision, llm_ms = effective_classifier.classify(raw_query)
        effective_model = llm_model or (effective_classifier.model_name if effective_classifier else "provided")
        if decision.intent == "precise_lookup":
            plan: IntentQueryPlan = _precise_plan_from_decision(
                raw_query,
                decision,
                filename_registry=filename_registry,
                context_files=context_files,
            )
            plan_type = "precise"
        else:
            plan = _comprehensive_plan_from_decision(
                raw_query,
                decision,
                filename_registry=filename_registry,
                context_files=context_files,
                postprocess_profile=postprocess_profile,
            )
            plan_type = "comprehensive"
        trace: dict[str, Any] = {
            "intent": decision.intent,
            "intent_confidence": decision.confidence,
            "query_plan_type": plan_type,
            "intent_classifier_enabled": True,
            "intent_llm_model": effective_model,
            "intent_llm_ms": llm_ms,
            "intent_fallback_to_rules": False,
        }
        if isinstance(plan, ComprehensiveQueryPlan):
            trace.update(
                {
                    "analysis_type": plan.analysis_type,
                    "sub_query_count": len(plan.sub_queries),
                    "retrieval_branch_count": len(plan.sub_queries) + 1,
                }
            )
        return IntentParseResult(
            intent=decision.intent,
            confidence=decision.confidence,
            query_plan=plan,
            trace=trace,
        )
    except Exception as exc:
        if llm_ms <= 0:
            llm_ms = (time.perf_counter() - classify_started) * 1000
        plan = build_compatible_precise_plan(
            raw_query,
            query_plan_enabled=query_plan_enabled,
            filename_registry=filename_registry,
            context_files=context_files,
        )
        return IntentParseResult(
            intent="precise_lookup",
            confidence=0.0,
            query_plan=plan,
            trace={
                "intent": "precise_lookup",
                "intent_confidence": 0.0,
                "query_plan_type": "precise",
                "intent_classifier_enabled": True,
                "intent_llm_model": llm_model
                or (effective_classifier.model_name if effective_classifier else "unknown"),
                "intent_llm_ms": llm_ms,
                "intent_fallback_to_rules": True,
                "intent_llm_error": str(exc),
            },
        )
