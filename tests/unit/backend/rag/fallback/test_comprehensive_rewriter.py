from __future__ import annotations

from types import SimpleNamespace

import pytest

from backend.rag.comprehensive_postprocess import build_retrieval_branches
from backend.rag.comprehensive_rewriter import (
    select_failed_generated_branches,
    rewrite_failed_sub_query,
)
from backend.rag.query_plan import ComprehensiveQueryPlan, RetrievalScope, SubQuery


pytestmark = pytest.mark.unit


class _StructuredModel:
    def __init__(self, response):
        self.response = response
        self.messages = None

    def with_structured_output(self, _schema):
        return self

    def invoke(self, messages):
        self.messages = messages
        return self.response


def _plan() -> ComprehensiveQueryPlan:
    return ComprehensiveQueryPlan(
        raw_query="比较 A 与 B 的安装和维护",
        clean_query="比较安装和维护",
        analysis_type="comparison",
        sub_queries=(
            SubQuery("A 的安装步骤", "installation", 1),
            SubQuery("B 的维护要求", "maintenance", 2),
        ),
        coverage_domains=("installation", "maintenance"),
        postprocess_profile="quality_first_v1",
        retrieval_scope=RetrievalScope(
            scope_mode="filter",
            matched_files=(("manual.pdf", 1.0),),
            source="context_files",
        ),
    )


def test_rewriter_replaces_only_failed_generated_sub_query_and_preserves_baseline_contract():
    plan = _plan()
    failed_branch = build_retrieval_branches(plan)[1]
    model = _StructuredModel(
        SimpleNamespace(
            strategy="generalize",
            new_sub_queries=[
                SimpleNamespace(query="设备安装的一般流程", domain="installation", priority=1)
            ],
            reason="原查询过于具体",
        )
    )

    result = rewrite_failed_sub_query(
        plan,
        failed_branch=failed_branch,
        failure_signal={"candidate_count": 0, "top_score": None},
        succeeded_sub_queries=(plan.sub_queries[1],),
        model=model,
    )

    assert result.plan.clean_query == plan.clean_query
    assert result.plan.sub_queries == (
        SubQuery("设备安装的一般流程", "installation", 1),
        plan.sub_queries[1],
    )
    assert result.plan.retrieval_scope == plan.retrieval_scope
    assert result.plan.postprocess_profile == plan.postprocess_profile
    assert result.strategy == "generalize"
    assert result.replaced_branch_id == "sub_query_0"
    assert "original_plan" in model.messages[1]["content"]
    assert "failed_sub_query" in model.messages[1]["content"]
    assert "failure_signal" in model.messages[1]["content"]
    assert "succeeded_sub_queries" in model.messages[1]["content"]


def test_rewriter_decompose_replaces_one_failed_sub_query_with_two():
    plan = _plan()
    model = _StructuredModel(
        SimpleNamespace(
            strategy="decompose",
            new_sub_queries=[
                SimpleNamespace(query="安装前检查", domain="installation", priority=1),
                SimpleNamespace(query="安装执行步骤", domain="installation", priority=1),
            ],
            reason="拆分范围",
        )
    )

    result = rewrite_failed_sub_query(
        plan,
        failed_branch=build_retrieval_branches(plan)[1],
        failure_signal={"candidate_count": 1},
        succeeded_sub_queries=(plan.sub_queries[1],),
        model=model,
    )

    assert [item.query for item in result.plan.sub_queries] == [
        "安装前检查",
        "安装执行步骤",
        "B 的维护要求",
    ]
    assert result.plan.coverage_domains == ("installation", "maintenance")


def test_rewriter_rejects_baseline_without_calling_model():
    plan = _plan()
    model = _StructuredModel(AssertionError("model must not be called"))

    with pytest.raises(ValueError, match="baseline"):
        rewrite_failed_sub_query(
            plan,
            failed_branch=build_retrieval_branches(plan)[0],
            failure_signal={"candidate_count": 0},
            succeeded_sub_queries=plan.sub_queries,
            model=model,
        )

    assert model.messages is None


def test_rewriter_rejects_duplicate_of_succeeded_sub_query():
    plan = _plan()
    model = _StructuredModel(
        SimpleNamespace(
            strategy="replace",
            new_sub_queries=[
                SimpleNamespace(query="  B 的维护要求  ", domain="maintenance", priority=2)
            ],
            reason="换角度",
        )
    )

    with pytest.raises(ValueError, match="duplicates a succeeded sub-query"):
        rewrite_failed_sub_query(
            plan,
            failed_branch=build_retrieval_branches(plan)[1],
            failure_signal={"candidate_count": 0},
            succeeded_sub_queries=(plan.sub_queries[1],),
            model=model,
        )


@pytest.mark.parametrize(
    ("strategy", "queries"),
    [
        ("generalize", [SimpleNamespace(query="q1", domain="d", priority=1), SimpleNamespace(query="q2", domain="d", priority=1)]),
        ("decompose", [SimpleNamespace(query="q1", domain="d", priority=1)]),
    ],
)
def test_rewriter_validates_strategy_output_count(strategy, queries):
    plan = _plan()
    model = _StructuredModel(
        SimpleNamespace(strategy=strategy, new_sub_queries=queries, reason="invalid count")
    )

    with pytest.raises(ValueError, match="new_sub_queries"):
        rewrite_failed_sub_query(
            plan,
            failed_branch=build_retrieval_branches(plan)[1],
            failure_signal={"candidate_count": 0},
            succeeded_sub_queries=(plan.sub_queries[1],),
            model=model,
        )


def test_failed_generated_branch_selection_uses_priority_then_branch_id_and_window():
    plan = ComprehensiveQueryPlan(
        raw_query="raw",
        clean_query="clean",
        analysis_type="general",
        sub_queries=(
            SubQuery("priority two", "d2", 2),
            SubQuery("priority one b", "d1b", 1),
            SubQuery("priority one a", "d1a", 1),
        ),
        coverage_domains=("d2", "d1b", "d1a"),
    )
    branches = build_retrieval_branches(plan)
    failed_results = [
        SimpleNamespace(branch=branches[3], candidates=(), error="failed"),
        SimpleNamespace(branch=branches[0], candidates=(), error="baseline failed"),
        SimpleNamespace(branch=branches[1], candidates=(), error="failed"),
        SimpleNamespace(branch=branches[2], candidates=(), error="failed"),
    ]

    selected = select_failed_generated_branches(failed_results, window=2)

    assert [item.branch.branch_id for item in selected] == ["sub_query_1", "sub_query_2"]
