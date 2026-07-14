from dataclasses import FrozenInstanceError, fields

import pytest

from backend.rag.query_plan import (
    ComprehensiveQueryPlan,
    ComprehensiveRetrievalBranch,
    PreciseQueryPlan,
    SubQuery,
    build_compatible_precise_plan,
    parse_query_plan,
)


REGISTRY = [
    {"raw": "主减速齿轮箱维修手册.pdf", "normalized": "主减速齿轮箱维修手册"},
]


@pytest.mark.unit
def test_intent_plan_types_are_frozen_and_exclude_semantic_entities():
    precise = build_compatible_precise_plan("如何拆卸？", query_plan_enabled=False)
    comprehensive = ComprehensiveQueryPlan(
        raw_query="比较方案",
        clean_query="比较方案",
        analysis_type="comparison",
        sub_queries=(SubQuery(query="方案 A", domain="A", priority=1),),
        coverage_domains=("A",),
    )

    assert "entities" not in {item.name for item in fields(PreciseQueryPlan)}
    assert "entities" not in {item.name for item in fields(ComprehensiveQueryPlan)}
    with pytest.raises(FrozenInstanceError):
        precise.raw_query = "changed"
    with pytest.raises(TypeError):
        ComprehensiveQueryPlan(
            raw_query="q",
            clean_query="q",
            analysis_type="general",
            sub_queries=(SubQuery(query="q1", domain="d", priority=1),),
            coverage_domains=("d",),
            entities=(),
        )
    assert comprehensive.postprocess_profile == "quality_first_v1"


@pytest.mark.unit
def test_compatibility_plan_disabled_preserves_raw_global_behavior():
    plan = build_compatible_precise_plan(
        "《主减速齿轮箱维修手册》中，MRG 怎么拆卸？",
        query_plan_enabled=False,
        filename_registry=REGISTRY,
    )

    assert plan.raw_query == plan.clean_query == plan.semantic_query
    assert plan.scope_mode == "none"
    assert plan.route == "global_hybrid"
    assert plan.matched_files == ()


@pytest.mark.unit
def test_compatibility_plan_enabled_losslessly_adapts_existing_parser():
    raw = "《主减速齿轮箱维修手册》中，第3章 MRG 怎么拆卸？"
    legacy = parse_query_plan(raw, REGISTRY)
    plan = build_compatible_precise_plan(
        raw,
        query_plan_enabled=True,
        filename_registry=REGISTRY,
    )

    assert plan.raw_query == legacy.raw_query
    assert plan.clean_query == legacy.clean_query
    assert plan.semantic_query == legacy.semantic_query
    assert plan.doc_hints == tuple(legacy.doc_hints)
    assert plan.matched_files == tuple(legacy.matched_files)
    assert plan.scope_mode == legacy.scope_mode
    assert plan.route == legacy.route
    assert plan.anchors == tuple(legacy.anchors)


@pytest.mark.unit
def test_unresolved_document_hint_is_retained_for_retrieval():
    raw = "《未知主减速齿轮箱手册》中，MRG 怎么拆卸？"
    unrelated_registry = [{"raw": "部署手册.pdf", "normalized": "部署手册"}]
    plan = parse_query_plan(raw, unrelated_registry)

    assert "《未知主减速齿轮箱手册》" in plan.clean_query
    assert "《未知主减速齿轮箱手册》" in plan.semantic_query
    assert plan.scope_mode == "none"


@pytest.mark.unit
def test_anchor_like_text_inside_unresolved_document_hint_is_not_consumed():
    raw = "《未知第三章维修手册》中，MRG 故障"
    unrelated_registry = [{"raw": "部署手册.pdf", "normalized": "部署手册"}]

    plan = parse_query_plan(raw, unrelated_registry)

    assert "《未知第三章维修手册》" in plan.clean_query
    assert plan.anchors == []
    assert not plan.consumed_spans


@pytest.mark.unit
def test_model_number_is_retained_when_document_scope_does_not_own_it():
    registry = [{"raw": "部署手册.pdf", "normalized": "部署手册"}]

    plan = parse_query_plan("《部署手册》中，AB1234 故障", registry)

    assert plan.scope_mode == "filter"
    assert "AB1234" in plan.semantic_query
    assert not any(span.kind == "model" for span in plan.consumed_spans)


@pytest.mark.unit
def test_consumed_document_and_anchor_spans_are_removed_but_represented():
    raw = "《主减速齿轮箱维修手册》中，第3章 MRG 怎么拆卸？"
    plan = parse_query_plan(raw, REGISTRY)

    assert plan.scope_mode == "filter"
    assert plan.anchors == ["第3章"]
    assert "主减速齿轮箱维修手册" not in plan.clean_query
    assert "第3章" not in plan.clean_query
    assert "MRG" in plan.semantic_query
    assert {(span.kind, span.owner) for span in plan.consumed_spans} == {
        ("document", "scope"),
        ("anchor", "anchor"),
    }


@pytest.mark.unit
def test_context_files_only_consume_document_hint_owned_by_final_hard_scope():
    raw = "《主减速齿轮箱维修手册》中，如何拆卸？"
    plan = parse_query_plan(
        raw,
        REGISTRY,
        context_files=["另一本部署手册.pdf"],
    )

    assert plan.scope_mode == "filter"
    assert plan.matched_files == [("另一本部署手册.pdf", 1.0)]
    assert "《主减速齿轮箱维修手册》" in plan.semantic_query
    assert not any(span.kind == "document" for span in plan.consumed_spans)


@pytest.mark.unit
def test_retrieval_branch_validates_identity_and_priority():
    baseline = ComprehensiveRetrievalBranch.baseline("比较方案")
    generated = ComprehensiveRetrievalBranch.from_sub_query(
        SubQuery(query="方案 A", domain="A", priority=1),
        index=0,
    )

    assert baseline.branch_id == "baseline"
    assert baseline.branch_kind == "baseline"
    assert baseline.priority == 2
    assert generated.branch_id == "sub_query_0"
    assert generated.branch_kind == "sub_query"
    with pytest.raises(ValueError):
        SubQuery(query="bad", domain="d", priority=4)


@pytest.mark.unit
def test_comprehensive_plan_rejects_empty_query_or_subqueries():
    with pytest.raises(ValueError, match="clean_query"):
        ComprehensiveQueryPlan(
            raw_query="q",
            clean_query="   ",
            analysis_type="general",
            sub_queries=(SubQuery(query="q1", domain="d", priority=1),),
            coverage_domains=("d",),
        )
    with pytest.raises(ValueError, match="sub-query"):
        ComprehensiveQueryPlan(
            raw_query="q",
            clean_query="q",
            analysis_type="general",
            sub_queries=(),
            coverage_domains=(),
        )
