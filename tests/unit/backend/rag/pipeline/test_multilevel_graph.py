from __future__ import annotations

import time
from dataclasses import replace
from unittest.mock import patch
from types import SimpleNamespace

import pytest

import backend.rag.pipeline as rag_pipeline
from backend.rag.comprehensive_postprocess import BranchRetrievalResult, build_retrieval_branches
from backend.rag.query_plan import (
    ComprehensiveQueryPlan,
    PreciseQueryPlan,
    RetrievalScope,
    SubQuery,
)
from backend.rag.runtime_config import load_runtime_config


pytestmark = pytest.mark.unit


def _plan() -> PreciseQueryPlan:
    return PreciseQueryPlan(
        raw_query="仅在《Manual》中说明第三章的拆卸步骤",
        clean_query="说明第三章的拆卸步骤",
        semantic_query="说明第三章的拆卸步骤",
        doc_hints=("Manual",),
        scope_mode="filter",
        matched_files=(("manual.pdf", 1.0),),
        anchors=("第三章",),
        route="scoped_hybrid",
    )


def _enabled_config(**updates):
    return replace(
        load_runtime_config({}),
        fallback_enabled=True,
        fallback_total_budget_ms=8000,
        fallback_level1_budget_ms=3000,
        fallback_level2_budget_ms=2500,
        **updates,
    )


def test_fallback_router_records_level_zero_when_current_confidence_passes():
    state = {
        "query_plan": _plan(),
        "attempted_levels": [],
        "fallback_decisions": [],
        "fallback_started_at": time.perf_counter(),
        "rag_trace": {"fallback_required": False, "confidence_reasons": []},
    }

    with (
        patch("backend.rag.pipeline.load_runtime_config", return_value=_enabled_config()),
        patch("backend.rag.pipeline.emit_rag_step") as emit,
    ):
        result = rag_pipeline.fallback_router_node(state)

    assert result["route"] == "generate_answer"
    assert result["fallback_decisions"][-1].target_level == 0
    assert result["rag_trace"]["fallback_level"] == 0
    assert result["rag_trace"]["fallback_path"] == []
    assert emit.call_args.kwargs == {"level": 0, "signal": "confidence_sufficient"}


def test_fallback_router_routes_anchor_mismatch_to_level_one():
    state = {
        "query_plan": _plan(),
        "attempted_levels": [],
        "fallback_decisions": [],
        "fallback_started_at": time.perf_counter(),
        "rag_trace": {
            "fallback_required": True,
            "confidence_reasons": ["anchor_mismatch"],
        },
    }

    with patch("backend.rag.pipeline.load_runtime_config", return_value=_enabled_config()):
        result = rag_pipeline.fallback_router_node(state)

    assert result["route"] == "level1"
    assert result["fallback_decisions"][-1].primary_signal == "anchor_mismatch"
    assert result["rag_trace"]["fallback_level"] == 1


def test_fallback_router_after_level_one_uses_fresh_confidence_and_routes_level_two():
    state = {
        "query_plan": _plan(),
        "attempted_levels": [1],
        "fallback_decisions": [],
        "fallback_started_at": time.perf_counter(),
        "rag_trace": {
            "fallback_required": True,
            "confidence_reasons": ["low_score_and_margin"],
            "confidence_round": "level1",
        },
    }

    with patch("backend.rag.pipeline.load_runtime_config", return_value=_enabled_config()):
        result = rag_pipeline.fallback_router_node(state)

    assert result["route"] == "level2"
    assert result["fallback_decisions"][-1].target_level == 2
    assert result["rag_trace"]["fallback_path"] == [1]


def test_fallback_router_disabled_keeps_level_zero_final_context():
    state = {
        "query_plan": _plan(),
        "attempted_levels": [],
        "fallback_decisions": [],
        "fallback_started_at": time.perf_counter(),
        "docs": [{"chunk_id": "l0"}],
        "rag_trace": {
            "fallback_required": True,
            "confidence_reasons": ["anchor_mismatch"],
        },
    }

    config = replace(_enabled_config(), fallback_enabled=False)
    with patch("backend.rag.pipeline.load_runtime_config", return_value=config):
        result = rag_pipeline.fallback_router_node(state)

    assert result["route"] == "generate_answer"
    assert result["rag_trace"]["fallback_disabled"] is True
    assert result["rag_trace"]["fallback_required_raw"] is True
    assert result["rag_trace"]["fallback_level"] == 0


def test_compiled_graph_contains_multilevel_router_cycles():
    graph = rag_pipeline.build_rag_graph().get_graph()
    assert {
        "fallback_router",
        "level1_query_rewrite",
        "level2_scope_relax",
        "level3_insufficient_evidence",
    }.issubset(graph.nodes)
    edges = {(edge.source, edge.target) for edge in graph.edges}
    assert ("grade_documents", "fallback_router") in edges
    assert ("shared_postprocess", "grade_documents") in edges
    assert ("level1_query_rewrite", "fallback_router") in edges
    assert ("level2_scope_relax", "fallback_router") in edges


def test_run_rag_graph_records_total_fallback_time_for_every_request():
    result = {"rag_trace": {"fallback_level": 0}}

    with patch.object(rag_pipeline.rag_graph, "invoke", return_value=result):
        actual = rag_pipeline.run_rag_graph("q")

    assert actual["rag_trace"]["fallback_total_ms"] >= 0
    assert actual["rag_trace"]["timings"]["total_rag_graph_ms"] >= 0


def test_precise_level_one_uses_rewritten_semantic_query_and_fresh_confidence():
    plan = _plan()
    state = {
        "question": plan.raw_query,
        "query_plan": plan,
        "query_plan_type": "precise",
        "context_files": ["manual.pdf"],
        "attempted_levels": [],
        "fallback_decisions": [],
        "fallback_started_at": time.perf_counter(),
        "rag_trace": {
            "fallback_required": True,
            "confidence_reasons": ["anchor_mismatch"],
            "query_plan_enabled": True,
        },
    }
    rewrite_patch = {
        "expansion_type": "step_back",
        "expanded_query": "泵体拆卸的一般步骤",
        "step_back_question": "泵体通常如何拆卸？",
        "step_back_answer": "",
        "hypothetical_doc": "",
        "rag_trace": dict(state["rag_trace"]),
    }
    candidate_payload = {
        "candidates": [{"chunk_id": "fresh", "text": "fresh evidence"}],
        "meta": {
            "timings": {"total_retrieve_ms": 1.0},
            "stage_errors": [],
            "candidate_k": 50,
        },
    }
    retrieval = {
        "docs": [{"chunk_id": "fresh", "text": "fresh evidence"}],
        "meta": {
            "timings": {"total_retrieve_ms": 2.0},
            "stage_errors": [],
            "fallback_required": False,
            "confidence_reasons": [],
            "candidate_k": 50,
        },
    }

    with (
        patch("backend.rag.pipeline.load_runtime_config", return_value=_enabled_config()),
        patch("backend.rag.pipeline.rewrite_question_node", return_value=rewrite_patch),
        patch("backend.rag.pipeline.retrieve_candidate_pool", return_value=candidate_payload) as retrieve,
        patch("backend.rag.pipeline.finish_retrieval_pipeline", return_value=retrieval) as finish,
        patch("backend.rag.pipeline.emit_rag_step") as emit,
    ):
        result = rag_pipeline.level1_query_rewrite_node(state)

    assert retrieve.call_args.args[0] == "泵体拆卸的一般步骤"
    retry_plan = retrieve.call_args.kwargs["query_plan"]
    assert retry_plan.raw_query == plan.raw_query
    assert retry_plan.semantic_query == "泵体拆卸的一般步骤"
    assert retry_plan.scope_mode == "filter"
    assert retrieve.call_args.kwargs["strict_scope_filter"] is True
    assert finish.call_args.kwargs["query"] == "泵体拆卸的一般步骤"
    assert result["attempted_levels"] == [1]
    assert result["rag_trace"]["fallback_required"] is False
    assert result["rag_trace"]["confidence_reasons"] == []
    assert result["rag_trace"]["level1_strategy"] == "step_back"
    assert result["rag_trace"]["level1_rewritten_query"] == "泵体拆卸的一般步骤"
    assert emit.call_args_list[0].kwargs == {"level": 1, "signal": "anchor_mismatch"}
    assert emit.call_args_list[-1].kwargs == {
        "level": 1,
        "signal": "anchor_mismatch",
        "strategy": "step_back",
    }


@pytest.mark.parametrize(("scope_mode", "strict"), [("filter", True), ("boost", False)])
def test_precise_level_two_preserves_filter_or_atomically_drops_boost(scope_mode, strict):
    plan = replace(
        _plan(),
        scope_mode=scope_mode,
        route="scoped_hybrid",
    )
    state = {
        "question": plan.raw_query,
        "semantic_query": plan.semantic_query,
        "query_plan": plan,
        "query_plan_type": "precise",
        "context_files": ["manual.pdf"],
        "attempted_levels": [1],
        "fallback_decisions": [],
        "fallback_started_at": time.perf_counter(),
        "fallback_deadline": time.perf_counter() + 5,
        "rag_trace": {
            "fallback_required": True,
            "confidence_reasons": ["weak_margin_and_root"],
            "candidate_k": 40,
            "query_plan_enabled": True,
        },
    }
    candidate_payload = {
        "candidates": [{"chunk_id": "fresh", "text": "fresh"}],
        "meta": {"candidate_k": 50, "timings": {}, "stage_errors": []},
    }
    final_payload = {
        "docs": [{"chunk_id": "fresh", "text": "fresh"}],
        "meta": {
            "candidate_k": 50,
            "same_root_cap": 3,
            "fallback_required": False,
            "confidence_reasons": [],
            "timings": {},
            "stage_errors": [],
        },
    }

    config = replace(_enabled_config(), fallback_expanded_candidate_k=50, same_root_cap=2)
    with (
        patch("backend.rag.pipeline.load_runtime_config", return_value=config),
        patch("backend.rag.pipeline.retrieve_candidate_pool", return_value=candidate_payload) as retrieve,
        patch("backend.rag.pipeline.finish_retrieval_pipeline", return_value=final_payload) as finish,
        patch("backend.rag.pipeline.emit_rag_step") as emit,
    ):
        result = rag_pipeline.level2_scope_relax_node(state)

    retry_plan = retrieve.call_args.kwargs["query_plan"]
    assert retrieve.call_args.kwargs["candidate_k"] == 50
    assert retrieve.call_args.kwargs["strict_scope_filter"] is strict
    assert finish.call_args.kwargs["same_root_cap_override"] == 3
    if scope_mode == "filter":
        assert retry_plan.scope_mode == "filter"
        assert retry_plan.matched_files == plan.matched_files
        assert result["query_plan"] == plan
    else:
        assert retry_plan.scope_mode == "none"
        assert retry_plan.matched_files == ()
        assert retry_plan.route == "global_hybrid"
    assert result["attempted_levels"] == [1, 2]
    assert result["rag_trace"]["fallback_required"] is False
    assert result["rag_trace"]["level2_new_scope_mode"] == retry_plan.scope_mode
    assert emit.call_args_list[0].kwargs == {"level": 2, "signal": "weak_margin_and_root"}
    assert emit.call_args_list[-1].kwargs == {
        "level": 2,
        "signal": "weak_margin_and_root",
        "strategy": "scope_relax",
    }


def test_level_three_emits_structured_entry_and_exit_events():
    plan = _plan()
    state = {
        "query_plan": plan,
        "attempted_levels": [1, 2],
        "fallback_decisions": [],
        "rag_trace": {"confidence_reasons": ["no_docs"]},
    }

    with (
        patch("backend.rag.pipeline.emit_rag_step") as emit,
        patch("backend.rag.pipeline.retrieve_candidate_pool") as retrieve,
    ):
        result = rag_pipeline.level3_insufficient_evidence_node(state)

    retrieve.assert_not_called()
    assert result["attempted_levels"] == [1, 2, 3]
    assert result["rag_trace"]["level3_ms"] >= 0
    assert result["context"] == result["rag_trace"]["level3_answer"]
    assert result["docs"] == []
    assert emit.call_args_list[0].kwargs == {"level": 3, "signal": "no_docs"}
    assert emit.call_args_list[-1].kwargs == {
        "level": 3,
        "signal": "no_docs",
        "strategy": "template",
    }


def _comprehensive_plan() -> ComprehensiveQueryPlan:
    return ComprehensiveQueryPlan(
        raw_query="综合比较",
        clean_query="综合比较",
        analysis_type="comparison",
        sub_queries=(
            SubQuery("高优先级失败", "a", 1),
            SubQuery("低优先级失败", "b", 2),
            SubQuery("成功分支", "c", 1),
        ),
        coverage_domains=("a", "b", "c"),
        postprocess_profile="quality_first_v1",
        retrieval_scope=RetrievalScope(
            scope_mode="boost",
            matched_files=(("manual.pdf", 0.9),),
            source="document_hints",
        ),
    )


class _SequentialRewriteModel:
    def __init__(self):
        self.calls = []

    def with_structured_output(self, _schema):
        return self

    def invoke(self, messages):
        self.calls.append(messages)
        index = len(self.calls)
        return SimpleNamespace(
            strategy="replace",
            new_sub_queries=[
                SimpleNamespace(query=f"替代查询 {index}", domain=f"r{index}", priority=1)
            ],
            reason="替换失败分支",
        )


def test_comprehensive_level_one_rewrites_selected_failure_window_and_rebuilds_baseline():
    plan = _comprehensive_plan()
    branches = build_retrieval_branches(plan)
    branch_results = [
        BranchRetrievalResult(branches[0], ({"chunk_id": "base"},), {}),
        BranchRetrievalResult(branches[1], (), {}, "failed a"),
        BranchRetrievalResult(branches[2], (), {}, "failed b"),
        BranchRetrievalResult(branches[3], ({"chunk_id": "ok"},), {}),
    ]
    model = _SequentialRewriteModel()
    captured = {}

    def rerun(next_state):
        captured.update(next_state)
        return {
            **next_state,
            "rag_trace": {
                **next_state["rag_trace"],
                "fallback_required": False,
                "confidence_reasons": [],
                "confidence_round": "level1",
            },
        }

    state = {
        "question": plan.raw_query,
        "query_plan": plan,
        "query_plan_type": "comprehensive",
        "branch_retrieval_results": branch_results,
        "attempted_levels": [],
        "fallback_decisions": [],
        "fallback_started_at": time.perf_counter(),
        "rag_trace": {
            "fallback_required": True,
            "confidence_reasons": ["generated_branch_failure"],
            "branch_retrieval_diagnostics": [],
        },
    }

    with (
        patch("backend.rag.pipeline.load_runtime_config", return_value=_enabled_config()),
        patch("backend.rag.pipeline._get_router_model", return_value=model),
        patch("backend.rag.pipeline._run_comprehensive_round", side_effect=rerun),
    ):
        result = rag_pipeline.level1_query_rewrite_node(state)

    updated_plan = captured["query_plan"]
    assert updated_plan.clean_query == plan.clean_query
    assert [item.query for item in updated_plan.sub_queries] == [
        "替代查询 1",
        "替代查询 2",
        "成功分支",
    ]
    assert updated_plan.postprocess_profile == plan.postprocess_profile
    assert len(model.calls) == 2
    assert result["attempted_levels"] == [1]
    assert result["rag_trace"]["level1_comprehensive_strategy"] == ["replace", "replace"]
    assert result["rag_trace"]["level1_strategy"] == "comprehensive"
    assert result["rag_trace"]["level1_rewritten_query"] == [
        "替代查询 1",
        "替代查询 2",
    ]
    assert result["rag_trace"]["level1_sub_query_replaced"] == [
        "sub_query_0",
        "sub_query_1",
    ]


def test_level_three_uses_only_final_top_k_branch_evidence_and_trace():
    plan = _comprehensive_plan()
    branches = build_retrieval_branches(plan)
    state = {
        "query_plan": plan,
        "attempted_levels": [1, 2],
        "fallback_decisions": [],
        "branch_retrieval_results": [
            BranchRetrievalResult(
                branches[1],
                ({"chunk_id": "raw-a", "text": "RAW_A_REJECTED"},),
                {},
            ),
            BranchRetrievalResult(
                branches[2],
                ({"chunk_id": "final-b", "text": "FINAL_B"},),
                {},
            ),
            BranchRetrievalResult(branches[3], (), {}, "failed c"),
        ],
        "docs": [
            {
                "chunk_id": "final-b",
                "text": "FINAL_B",
                "matched_branch_ids": ["sub_query_1"],
            }
        ],
        "rag_trace": {
            "confidence_reasons": ["missing_generated_branch_representation"],
            "represented_generated_branch_ids": ["sub_query_1"],
            "baseline_selected": False,
        },
    }

    result = rag_pipeline.level3_insufficient_evidence_node(state)

    assert "已完成 1/3 个分析维度" in result["context"]
    assert "FINAL_B" in result["context"]
    assert "RAW_A_REJECTED" not in result["context"]
    assert result["rag_trace"]["level3_uncovered_sub_queries"] == [
        "高优先级失败",
        "成功分支",
    ]
    assert result["rag_trace"]["level3_baseline_evidence_used"] is False


def test_comprehensive_baseline_failure_does_not_call_rewriter():
    plan = _comprehensive_plan()
    branches = build_retrieval_branches(plan)
    state = {
        "question": plan.raw_query,
        "query_plan": plan,
        "query_plan_type": "comprehensive",
        "branch_retrieval_results": [
            BranchRetrievalResult(branches[0], (), {}, "baseline failed"),
            BranchRetrievalResult(branches[1], ({"chunk_id": "ok"},), {}),
        ],
        "attempted_levels": [],
        "fallback_started_at": time.perf_counter(),
        "rag_trace": {"fallback_required": True, "confidence_reasons": ["baseline_failure"]},
    }

    with (
        patch("backend.rag.pipeline.load_runtime_config", return_value=_enabled_config()),
        patch("backend.rag.pipeline.rewrite_failed_sub_query", side_effect=AssertionError("baseline")),
        patch("backend.rag.pipeline._run_comprehensive_round", side_effect=AssertionError("rerun")),
    ):
        result = rag_pipeline.level1_query_rewrite_node(state)

    assert result["query_plan"] == plan
    assert result["rag_trace"]["level1_baseline_rewrite_attempted"] is False
    assert result["rag_trace"]["level1_sub_query_replaced"] == []


def test_comprehensive_level_two_uses_shared_relaxed_scope_and_keeps_profile():
    plan = _comprehensive_plan()
    captured = {}

    def rerun(next_state):
        captured.update(next_state)
        return {
            **next_state,
            "rag_trace": {
                **next_state["rag_trace"],
                "fallback_required": False,
                "confidence_reasons": [],
                "candidate_k": 50,
            },
        }

    state = {
        "question": plan.raw_query,
        "query_plan": plan,
        "query_plan_type": "comprehensive",
        "attempted_levels": [1],
        "fallback_started_at": time.perf_counter(),
        "rag_trace": {"candidate_k": 40, "fallback_required": True},
    }
    config = replace(_enabled_config(), fallback_expanded_candidate_k=50, same_root_cap=2)

    with (
        patch("backend.rag.pipeline.load_runtime_config", return_value=config),
        patch("backend.rag.pipeline._run_comprehensive_round", side_effect=rerun),
    ):
        result = rag_pipeline.level2_scope_relax_node(state)

    relaxed = captured["query_plan"]
    assert relaxed.retrieval_scope.scope_mode == "none"
    assert relaxed.retrieval_scope.matched_files == ()
    assert relaxed.retrieval_scope.source == "document_hints"
    assert relaxed.clean_query == plan.clean_query
    assert relaxed.postprocess_profile == plan.postprocess_profile
    assert captured["candidate_k_override"] == 50
    assert captured["same_root_cap_override"] == 3
    assert result["attempted_levels"] == [1, 2]


def test_level_one_entry_rechecks_minimum_budget_before_any_rewrite():
    plan = _plan()
    state = {
        "question": plan.raw_query,
        "query_plan": plan,
        "query_plan_type": "precise",
        "attempted_levels": [],
        "fallback_started_at": time.perf_counter() - 6,
        "rag_trace": {"fallback_required": True, "confidence_reasons": ["anchor_mismatch"]},
    }

    with (
        patch("backend.rag.pipeline.load_runtime_config", return_value=_enabled_config()),
        patch("backend.rag.pipeline.rewrite_question_node", side_effect=AssertionError("rewrite")),
    ):
        result = rag_pipeline.level1_query_rewrite_node(state)

    assert result["attempted_levels"] == []
    assert result["rag_trace"]["level1_timeout"] is True


def test_level_two_entry_rechecks_minimum_budget_before_scope_change():
    plan = _plan()
    state = {
        "question": plan.raw_query,
        "query_plan": plan,
        "query_plan_type": "precise",
        "attempted_levels": [1],
        "fallback_started_at": time.perf_counter() - 6,
        "rag_trace": {"fallback_required": True, "confidence_reasons": ["weak_margin_and_root"]},
    }

    with (
        patch("backend.rag.pipeline.load_runtime_config", return_value=_enabled_config()),
        patch("backend.rag.pipeline.relax_scope", side_effect=AssertionError("relax")),
    ):
        result = rag_pipeline.level2_scope_relax_node(state)

    assert result["attempted_levels"] == [1]
    assert result["query_plan"] == plan
    assert result["rag_trace"]["level2_timeout"] is True


def test_precise_rewrite_prompt_uses_level_zero_query_and_includes_raw_scope_context():
    plan = _plan()

    class Router:
        def __init__(self):
            self.messages = None

        def with_structured_output(self, _schema):
            return self

        def invoke(self, messages):
            self.messages = messages
            return SimpleNamespace(strategy="step_back")

    router = Router()
    config = _enabled_config()
    with (
        patch("backend.rag.pipeline.load_runtime_config", return_value=config),
        patch("backend.rag.pipeline._get_router_model", return_value=router),
        patch(
            "backend.rag.pipeline.step_back_expand",
            return_value={
                "step_back_question": "一般拆卸步骤",
                "step_back_answer": "",
                "expanded_query": "扩展后的拆卸步骤",
            },
        ) as step_back,
    ):
        result = rag_pipeline.rewrite_question_node(
            {
                "question": plan.raw_query,
                "semantic_query": plan.semantic_query,
                "query_plan": plan,
                "fallback_deadline": time.perf_counter() + 5,
                "rag_trace": {},
            }
        )

    prompt = router.messages[0]["content"]
    assert plan.raw_query in prompt
    assert plan.semantic_query in prompt
    assert "第三章" in prompt
    assert "Manual" in prompt
    assert "filter" in prompt
    step_back.assert_called_once()
    assert step_back.call_args.args == (plan.semantic_query,)
    generation_context = step_back.call_args.kwargs["rewrite_context"]
    assert plan.raw_query in generation_context
    assert "第三章" in generation_context
    assert "Manual" in generation_context
    assert "filter" in generation_context
    assert result["expanded_query"] == "扩展后的拆卸步骤"


def test_comprehensive_rewrite_validation_failure_returns_to_router_with_stage_error():
    plan = _comprehensive_plan()
    branches = build_retrieval_branches(plan)
    model = _SequentialRewriteModel()
    state = {
        "question": plan.raw_query,
        "query_plan": plan,
        "query_plan_type": "comprehensive",
        "branch_retrieval_results": [
            BranchRetrievalResult(branches[1], (), {}, "failed"),
        ],
        "attempted_levels": [],
        "fallback_started_at": time.perf_counter(),
        "rag_trace": {"fallback_required": True, "confidence_reasons": ["generated_branch_failure"]},
    }

    with (
        patch("backend.rag.pipeline.load_runtime_config", return_value=_enabled_config()),
        patch("backend.rag.pipeline._get_router_model", return_value=model),
        patch(
            "backend.rag.pipeline.rewrite_failed_sub_query",
            side_effect=ValueError("new_sub_queries duplicates a succeeded sub-query"),
        ),
        patch("backend.rag.pipeline._run_comprehensive_round", side_effect=AssertionError("rerun")),
    ):
        result = rag_pipeline.level1_query_rewrite_node(state)

    assert result["attempted_levels"] == [1]
    assert result["query_plan"] == plan
    assert result["rag_trace"]["level1_sub_query_replaced"] == []
    assert result["rag_trace"]["stage_errors"][-1]["stage"] == "comprehensive_rewriter"
    assert result["rag_trace"]["stage_errors"][-1]["fallback_to"] == "fallback_router"


def test_compiled_graph_executes_level_one_then_level_two_using_each_round_confidence():
    plan = _plan()
    config = _enabled_config()

    def intent(_state):
        return {
            "query_plan": plan,
            "query_plan_type": "precise",
            "semantic_query": plan.semantic_query,
            "rag_trace": {},
        }

    def initial(_state):
        return {
            "docs": [{"chunk_id": "l0"}],
            "rag_trace": {"fallback_required": True, "confidence_reasons": ["anchor_mismatch"]},
        }

    def level1(state):
        return {
            "attempted_levels": [*state.get("attempted_levels", []), 1],
            "rag_trace": {"fallback_required": True, "confidence_reasons": ["low_score_and_margin"]},
        }

    def level2(state):
        return {
            "attempted_levels": [*state.get("attempted_levels", []), 2],
            "rag_trace": {"fallback_required": False, "confidence_reasons": []},
        }

    with (
        patch("backend.rag.pipeline.load_runtime_config", return_value=config),
        patch("backend.rag.pipeline.intent_parse_node", side_effect=intent),
        patch("backend.rag.pipeline.retrieve_initial", side_effect=initial),
        patch("backend.rag.pipeline.level1_query_rewrite_node", side_effect=level1),
        patch("backend.rag.pipeline.level2_scope_relax_node", side_effect=level2),
    ):
        graph = rag_pipeline.build_rag_graph()
        result = graph.invoke(
            {
                "question": plan.raw_query,
                "context_files": [],
                "attempted_levels": [],
                "fallback_decisions": [],
                "fallback_started_at": time.perf_counter(),
                "rag_trace": {},
            }
        )

    assert result["attempted_levels"] == [1, 2]
    assert result["rag_trace"]["confidence_reasons"] == []
    assert result["rag_trace"]["fallback_level"] == 2
    assert result["rag_trace"]["fallback_path"] == [1, 2]


def test_precise_level_one_times_out_complete_postprocess_round():
    plan = _plan()
    config = replace(
        _enabled_config(),
        fallback_total_budget_ms=1000,
        fallback_level1_budget_ms=30,
    )
    state = {
        "question": plan.raw_query,
        "semantic_query": plan.semantic_query,
        "query_plan": plan,
        "query_plan_type": "precise",
        "context_files": [],
        "docs": [{"chunk_id": "l0", "text": "level zero"}],
        "attempted_levels": [],
        "fallback_started_at": time.perf_counter(),
        "rag_trace": {
            "fallback_required": True,
            "confidence_reasons": ["anchor_mismatch"],
            "query_plan_enabled": True,
        },
    }
    rewrite_patch = {
        "expansion_type": "step_back",
        "expanded_query": "rewritten",
        "rag_trace": dict(state["rag_trace"]),
    }
    candidate_payload = {
        "candidates": [{"chunk_id": "candidate", "text": "candidate"}],
        "meta": {"candidate_k": 50, "timings": {}, "stage_errors": []},
    }

    def slow_finish(**_kwargs):
        time.sleep(0.2)
        return {"docs": [{"chunk_id": "late"}], "meta": {}}

    started = time.perf_counter()
    with (
        patch("backend.rag.pipeline.load_runtime_config", return_value=config),
        patch("backend.rag.pipeline.rewrite_question_node", return_value=rewrite_patch),
        patch("backend.rag.pipeline.retrieve_candidate_pool", return_value=candidate_payload),
        patch("backend.rag.pipeline.finish_retrieval_pipeline", side_effect=slow_finish),
    ):
        result = rag_pipeline.level1_query_rewrite_node(state)
    elapsed = time.perf_counter() - started

    assert elapsed < 0.15
    assert result["docs"] == state["docs"]
    assert result["attempted_levels"] == [1]
    assert result["rag_trace"]["level1_timeout"] is True
    assert result["rag_trace"]["stage_errors"][-1]["stage"] == "level1_postprocess"


def test_comprehensive_level_one_times_out_complete_rerun_round():
    plan = _comprehensive_plan()
    branches = build_retrieval_branches(plan)
    config = replace(
        _enabled_config(),
        fallback_total_budget_ms=1000,
        fallback_level1_budget_ms=30,
    )
    state = {
        "question": plan.raw_query,
        "query_plan": plan,
        "query_plan_type": "comprehensive",
        "branch_retrieval_results": [
            BranchRetrievalResult(branches[1], (), {}, "failed"),
        ],
        "attempted_levels": [],
        "fallback_started_at": time.perf_counter(),
        "rag_trace": {"fallback_required": True, "confidence_reasons": ["generated_branch_failure"]},
    }

    def slow_round(next_state):
        time.sleep(0.2)
        return next_state

    with (
        patch("backend.rag.pipeline.load_runtime_config", return_value=config),
        patch("backend.rag.pipeline._get_router_model", return_value=_SequentialRewriteModel()),
        patch("backend.rag.pipeline._run_comprehensive_round", side_effect=slow_round),
    ):
        result = rag_pipeline.level1_query_rewrite_node(state)

    assert result["attempted_levels"] == [1]
    assert result["rag_trace"]["level1_timeout"] is True
    assert result["rag_trace"]["stage_errors"][-1]["stage"] == "level1_comprehensive_round"


def test_comprehensive_decompose_timeout_keeps_previous_completed_plan_and_evidence():
    plan = _comprehensive_plan()
    branches = build_retrieval_branches(plan)
    old_final_docs = [
        {
            "chunk_id": "old-b",
            "text": "OLD_B_FINAL",
            "filename": "old-b.pdf",
            "page_number": 4,
            "matched_branch_ids": ["sub_query_1"],
        }
    ]

    class DecomposeModel:
        def with_structured_output(self, _schema):
            return self

        def invoke(self, _messages):
            return SimpleNamespace(
                strategy="decompose",
                new_sub_queries=[
                    SimpleNamespace(query="new A1", domain="A1", priority=1),
                    SimpleNamespace(query="new A2", domain="A2", priority=1),
                ],
                reason="split old A",
            )

    config = replace(
        _enabled_config(),
        fallback_comprehensive_rewrite_window=1,
        fallback_total_budget_ms=1000,
        fallback_level1_budget_ms=30,
    )
    state = {
        "question": plan.raw_query,
        "query_plan": plan,
        "query_plan_type": "comprehensive",
        "branch_retrieval_results": [
            BranchRetrievalResult(branches[0], (), {}),
            BranchRetrievalResult(branches[1], (), {}, "failed a"),
            BranchRetrievalResult(
                branches[2],
                ({"chunk_id": "old-b", "text": "OLD_B_FINAL"},),
                {},
            ),
            BranchRetrievalResult(
                branches[3],
                ({"chunk_id": "old-c", "text": "OLD_C_FINAL"},),
                {},
            ),
        ],
        "docs": old_final_docs,
        "attempted_levels": [],
        "fallback_started_at": time.perf_counter(),
        "rag_trace": {
            "fallback_required": True,
            "confidence_reasons": ["generated_branch_failure"],
            "branch_retrieval_diagnostics": [],
        },
    }

    def slow_round(next_state):
        time.sleep(0.2)
        return next_state

    with (
        patch("backend.rag.pipeline.load_runtime_config", return_value=config),
        patch("backend.rag.pipeline._get_router_model", return_value=DecomposeModel()),
        patch("backend.rag.pipeline._run_comprehensive_round", side_effect=slow_round),
    ):
        result = rag_pipeline.level1_query_rewrite_node(state)

    assert result["rag_trace"]["level1_timeout"] is True
    assert result["query_plan"] == plan
    assert result["docs"] == old_final_docs

    level3 = rag_pipeline.level3_insufficient_evidence_node(
        {
            **result,
            "fallback_decisions": [],
        }
    )
    assert (
        "b（证据摘录，不是生成答案）[来源：old-b.pdf，第 4 页]：OLD_B_FINAL"
        in level3["context"]
    )
    assert "A2（证据摘录，不是生成答案）" not in level3["context"]


def test_precise_level_two_uses_own_deadline_for_complete_postprocess_round():
    plan = replace(
        _plan(),
        raw_query="参考《Manual》说明第三章的拆卸步骤",
        scope_mode="boost",
    )
    config = replace(
        _enabled_config(),
        fallback_total_budget_ms=1000,
        fallback_level2_budget_ms=30,
        fallback_expanded_candidate_k=50,
    )
    state = {
        "question": plan.raw_query,
        "semantic_query": plan.semantic_query,
        "query_plan": plan,
        "query_plan_type": "precise",
        "context_files": [],
        "docs": [{"chunk_id": "l0", "text": "level zero"}],
        "attempted_levels": [],
        "fallback_started_at": time.perf_counter(),
        "rag_trace": {
            "fallback_required": True,
            "confidence_reasons": ["weak_margin_and_root"],
            "candidate_k": 40,
            "query_plan_enabled": True,
        },
    }
    candidate_payload = {
        "candidates": [{"chunk_id": "candidate", "text": "candidate"}],
        "meta": {"candidate_k": 50, "timings": {}, "stage_errors": []},
    }

    def slow_finish(**_kwargs):
        time.sleep(0.2)
        return {"docs": [{"chunk_id": "late"}], "meta": {}}

    with (
        patch("backend.rag.pipeline.load_runtime_config", return_value=config),
        patch("backend.rag.pipeline.retrieve_candidate_pool", return_value=candidate_payload),
        patch("backend.rag.pipeline.finish_retrieval_pipeline", side_effect=slow_finish),
    ):
        result = rag_pipeline.level2_scope_relax_node(state)

    assert result["docs"] == state["docs"]
    assert result["query_plan"] == plan
    assert result["rag_trace"]["level2_new_scope_mode"] == "boost"
    assert result["attempted_levels"] == [2]
    assert result["rag_trace"]["level2_timeout"] is True
    assert result["rag_trace"]["stage_errors"][-1]["stage"] == "level2_postprocess"


def test_comprehensive_level_two_uses_own_deadline_for_complete_rerun_round():
    plan = _comprehensive_plan()
    config = replace(
        _enabled_config(),
        fallback_total_budget_ms=1000,
        fallback_level2_budget_ms=30,
        fallback_expanded_candidate_k=50,
    )
    state = {
        "question": plan.raw_query,
        "query_plan": plan,
        "query_plan_type": "comprehensive",
        "attempted_levels": [],
        "fallback_started_at": time.perf_counter(),
        "rag_trace": {"candidate_k": 40, "fallback_required": True},
    }

    def slow_round(next_state):
        time.sleep(0.2)
        return next_state

    with (
        patch("backend.rag.pipeline.load_runtime_config", return_value=config),
        patch("backend.rag.pipeline._run_comprehensive_round", side_effect=slow_round),
    ):
        result = rag_pipeline.level2_scope_relax_node(state)

    assert result["attempted_levels"] == [2]
    assert result["rag_trace"]["level2_timeout"] is True
    assert result["rag_trace"]["stage_errors"][-1]["stage"] == "level2_comprehensive_round"


@pytest.mark.parametrize(
    ("strategy", "expected_queries"),
    [
        ("hyde", ["hypothetical evidence"]),
        ("complex", ["step-back expansion", "hypothetical evidence"]),
    ],
)
def test_level_two_preserves_level_one_rewrite_query_form(strategy, expected_queries):
    plan = _plan()
    config = replace(
        _enabled_config(),
        fallback_total_budget_ms=1000,
        fallback_level2_budget_ms=300,
        fallback_expanded_candidate_k=50,
    )
    calls = []

    def retrieve(query, **kwargs):
        calls.append(query)
        return {
            "candidates": [{"chunk_id": query, "text": query}],
            "meta": {"candidate_k": 50, "timings": {}, "stage_errors": []},
        }

    state = {
        "question": plan.raw_query,
        "semantic_query": plan.semantic_query,
        "query_plan": plan,
        "query_plan_type": "precise",
        "context_files": ["manual.pdf"],
        "expansion_type": strategy,
        "expanded_query": "step-back expansion",
        "hypothetical_doc": "hypothetical evidence",
        "attempted_levels": [1],
        "fallback_started_at": time.perf_counter(),
        "rag_trace": {
            "candidate_k": 40,
            "query_plan_enabled": True,
            "fallback_required": True,
            "confidence_reasons": ["weak_margin_and_root"],
        },
    }
    final_payload = {
        "docs": [{"chunk_id": "fresh", "text": "fresh"}],
        "meta": {"fallback_required": False, "confidence_reasons": [], "timings": {}, "stage_errors": []},
    }

    with (
        patch("backend.rag.pipeline.load_runtime_config", return_value=config),
        patch("backend.rag.pipeline.retrieve_candidate_pool", side_effect=retrieve),
        patch("backend.rag.pipeline.finish_retrieval_pipeline", return_value=final_payload),
    ):
        rag_pipeline.level2_scope_relax_node(state)

    assert len(calls) == len(expected_queries)
    assert set(calls) == set(expected_queries)


def test_comprehensive_level_two_filter_rebuilds_every_branch_with_same_hard_scope():
    context_files = ["manual-a.pdf", "manual-b.pdf"]
    base = _comprehensive_plan()
    plan = replace(
        base,
        retrieval_scope=RetrievalScope(
            scope_mode="filter",
            matched_files=(("manual-a.pdf", 1.0), ("manual-b.pdf", 1.0)),
            source="context_files",
        ),
    )
    config = replace(
        _enabled_config(),
        fallback_total_budget_ms=1000,
        fallback_level2_budget_ms=300,
        fallback_expanded_candidate_k=50,
    )
    calls = []

    def retrieve(query, **kwargs):
        calls.append((query, kwargs))
        return {
            "candidates": [],
            "meta": {"candidate_k": 50, "timings": {}, "stage_errors": []},
        }

    state = {
        "question": plan.raw_query,
        "query_plan": plan,
        "query_plan_type": "comprehensive",
        "context_files": context_files,
        "attempted_levels": [1],
        "fallback_started_at": time.perf_counter(),
        "rag_trace": {"candidate_k": 40, "fallback_required": True},
    }

    with (
        patch("backend.rag.pipeline.load_runtime_config", return_value=config),
        patch("backend.rag.pipeline.retrieve_candidate_pool", side_effect=retrieve),
    ):
        result = rag_pipeline.level2_scope_relax_node(state)

    assert len(calls) == len(plan.sub_queries) + 1
    assert all(kwargs["candidate_k"] == 50 for _, kwargs in calls)
    assert all(kwargs["context_files"] == context_files for _, kwargs in calls)
    assert all(kwargs["strict_scope_filter"] is True for _, kwargs in calls)
    assert all(
        kwargs["query_plan"].matched_files == plan.retrieval_scope.matched_files
        for _, kwargs in calls
    )
    assert result["query_plan"].retrieval_scope == plan.retrieval_scope
    assert result["query_plan"].postprocess_profile == plan.postprocess_profile
