from __future__ import annotations

import pytest

from backend.rag.level3_answer import generate_level3_answer
from backend.rag.query_plan import (
    ComprehensiveQueryPlan,
    PreciseQueryPlan,
    RetrievalScope,
    SubQuery,
)


pytestmark = pytest.mark.unit


def _precise(scope_mode: str = "none") -> PreciseQueryPlan:
    return PreciseQueryPlan(
        raw_query="说明泵体拆卸步骤",
        clean_query="说明泵体拆卸步骤",
        semantic_query="说明泵体拆卸步骤",
        scope_mode=scope_mode,
        matched_files=(("manual.pdf", 1.0),) if scope_mode != "none" else (),
        route="scoped_hybrid" if scope_mode != "none" else "global_hybrid",
    )


def _comprehensive() -> ComprehensiveQueryPlan:
    return ComprehensiveQueryPlan(
        raw_query="比较方案 A 与 B",
        clean_query="比较方案 A 与 B",
        analysis_type="comparison",
        sub_queries=(
            SubQuery(query="方案 A 的成本", domain="成本", priority=1),
            SubQuery(query="方案 B 的风险", domain="风险", priority=2),
        ),
        coverage_domains=("成本", "风险"),
        retrieval_scope=RetrievalScope(),
    )


def test_precise_unscoped_template_reports_attempts_and_suggestions():
    answer = generate_level3_answer(_precise(), [1, 2, 3])

    assert answer.startswith("未在当前知识库中找到与当前查询及结构范围匹配的足够依据")
    assert "已尝试: Level 1 → Level 2 → Level 3" in answer
    assert "检查相关文档是否已上传" in answer


def test_precise_filter_template_never_claims_the_whole_knowledge_base_was_searched():
    answer = generate_level3_answer(_precise("filter"), [1, 3])

    assert answer.startswith("未在你指定的文档范围内找到足够依据")
    assert "本次没有搜索该范围之外的知识库" in answer
    assert "当前知识库中" not in answer


def test_comprehensive_partial_template_authorizes_only_sourced_dimension_answers():
    plan = _comprehensive()
    final_documents = (
        {
            "chunk_id": "a",
            "text": "方案 A 的成本证据",
            "filename": "cost.pdf",
            "page_number": 3,
            "matched_branch_ids": ["sub_query_0"],
        },
    )

    answer = generate_level3_answer(
        plan,
        [1, 2, 3],
        final_documents=final_documents,
    )

    assert answer.startswith("已完成 1/2 个分析维度")
    assert "成本（证据摘录，不是生成答案）" in answer
    assert "方案 A 的成本证据" in answer
    assert "来源：cost.pdf，第 3 页" in answer
    assert "未覆盖维度: [风险]" in answer
    assert "仅基于上述证据，为已覆盖维度分别生成部分解答" in answer
    assert "保留对应来源" in answer
    assert "明确说明整体证据不足" in answer
    assert "不得回答未覆盖维度" in answer
    assert "不得生成跨维度比较、汇总或总体建议" in answer


def test_comprehensive_baseline_only_keeps_coverage_zero_and_labels_background():
    plan = _comprehensive()
    final_documents = (
        {
            "chunk_id": "base",
            "text": "方案比较的一般背景",
            "matched_branch_ids": ["baseline"],
            "baseline_matched": True,
        },
    )

    answer = generate_level3_answer(
        plan,
        [1, 2, 3],
        final_documents=final_documents,
    )

    assert answer.startswith("已完成 0/2 个分析维度")
    assert "一般背景证据（不得计入分析覆盖率）" in answer
    assert "方案比较的一般背景" in answer
    assert "已完成 1/2" not in answer
    assert "仅展示上述一般背景证据，不生成分析解答" in answer
    assert "生成部分解答" not in answer


def test_comprehensive_no_evidence_contains_only_insufficiency_and_suggestion():
    plan = _comprehensive()

    answer = generate_level3_answer(plan, [3])

    assert answer.startswith("证据不足")
    assert "建议:" in answer
    assert "证据摘录" not in answer
    assert "chunk" not in answer.lower()


def test_comprehensive_full_coverage_low_confidence_has_dedicated_guidance():
    plan = _comprehensive()
    final_documents = (
        {
            "chunk_id": "cost",
            "text": "方案 A 的成本证据",
            "filename": "cost.pdf",
            "page_number": 3,
            "matched_branch_ids": ["sub_query_0"],
        },
        {
            "chunk_id": "risk",
            "text": "方案 B 的风险证据",
            "filename": "risk.pdf",
            "page_number": 7,
            "matched_branch_ids": ["sub_query_1"],
        },
    )

    answer = generate_level3_answer(
        plan,
        [1, 2, 3],
        final_documents=final_documents,
    )

    assert answer.startswith("已完成 2/2 个分析维度")
    assert "全部维度已有相关证据，但整体置信度不足" in answer
    assert "来源：cost.pdf，第 3 页" in answer
    assert "来源：risk.pdf，第 7 页" in answer
    assert "未覆盖维度: []" in answer
    assert "核对证据来源或补充更具判别力的查询条件" in answer
    assert "补充未覆盖维度" not in answer
    assert "仅展示上述证据摘录，不生成综合解答" in answer
    assert "生成部分解答" not in answer
