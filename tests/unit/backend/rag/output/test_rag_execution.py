import unittest
from dataclasses import replace
from types import SimpleNamespace

from backend.chat.rag_execution import (
    RagExecutionPolicy,
    RagTurnRequest,
    answer_with_rag_context,
    apply_rag_trace_to_turn_context,
    mark_rag_execution_policy,
    plan_rag_turn,
    prepare_rag_answer_messages,
    stream_answer_with_rag_context,
)


class RagExecutionPolicyTests(unittest.TestCase):
    def test_context_files_force_preload_without_unified_flag(self):
        turn = plan_rag_turn(
            RagTurnRequest(user_text="总结附件", context_files=["manual.pdf"], stream=False),
            unified_execution_enabled=False,
        )

        self.assertEqual(turn.policy, RagExecutionPolicy.FORCED_PRELOAD)
        self.assertEqual(turn.delivery_mode, "system_message")
        self.assertEqual(turn.policy_reason, "attached_context_files")

    def test_no_context_defaults_to_optional_tool(self):
        turn = plan_rag_turn(
            RagTurnRequest(user_text="你好", context_files=[], stream=False),
            unified_execution_enabled=False,
        )

        self.assertEqual(turn.policy, RagExecutionPolicy.OPTIONAL_TOOL)
        self.assertEqual(turn.delivery_mode, "tool_response")

    def test_unified_flag_can_preload_obvious_document_question(self):
        turn = plan_rag_turn(
            RagTurnRequest(user_text="根据知识库说明一下配置步骤", context_files=[], stream=False),
            unified_execution_enabled=True,
        )

        self.assertEqual(turn.policy, RagExecutionPolicy.FORCED_PRELOAD)
        self.assertEqual(turn.policy_reason, "document_intent")

    def test_mark_policy_adds_shared_trace_fields(self):
        turn = plan_rag_turn(
            RagTurnRequest(user_text="总结附件", context_files=["manual.pdf"], stream=False),
            unified_execution_enabled=False,
        )

        trace = mark_rag_execution_policy({"retrieval_mode": "hybrid"}, turn)

        self.assertEqual(trace["retrieval_policy"], "forced_preload")
        self.assertEqual(trace["context_delivery_mode"], "system_message")
        self.assertEqual(trace["context_format_version"], "retrieved-chunks-v1")
        self.assertFalse(trace["rag_unified_execution_enabled"])


class FakeModel:
    def __init__(self):
        self.invoked_with = None

    def invoke(self, messages):
        self.invoked_with = messages
        return SimpleNamespace(content="model answer")

    async def astream(self, messages):
        self.invoked_with = messages
        yield SimpleNamespace(content="model stream")


class FakeAgent:
    def __init__(self):
        self.invoked_with = None
        self.config = None

    def invoke(self, payload, config=None):
        self.invoked_with = payload
        self.config = config
        return {"messages": [SimpleNamespace(content="agent answer")]}

    async def astream(self, payload, stream_mode=None, config=None):
        self.invoked_with = payload
        self.config = config
        yield SimpleNamespace(content="agent stream"), {"stream_mode": stream_mode}


class RagAnswerExecutionTests(unittest.IsolatedAsyncioTestCase):
    def test_prepare_forced_preload_messages_injects_retrieved_context(self):
        turn = plan_rag_turn(
            RagTurnRequest(user_text="summarize", context_files=["manual.pdf"], stream=False),
            unified_execution_enabled=False,
        )
        messages = [SimpleNamespace(type="human", content="summarize")]

        prepared = prepare_rag_answer_messages(
            messages,
            turn,
            retrieved_context="evidence",
        )

        self.assertEqual(prepared[-1], messages[-1])
        self.assertIn("Retrieved document context", prepared[-2].content)
        self.assertIn("evidence", prepared[-2].content)

    def test_level_two_boost_to_none_appends_outside_preferred_files_disclosure(self):
        turn = replace(
            plan_rag_turn(
                RagTurnRequest(user_text="summarize", context_files=["manual.pdf"]),
                unified_execution_enabled=False,
            ),
            fallback_level=2,
            scope_mode_before="boost",
            scope_mode_after="none",
        )
        messages = [SimpleNamespace(type="human", content="summarize")]

        prepared = prepare_rag_answer_messages(messages, turn, retrieved_context="evidence")

        self.assertIn("Retrieved document context", prepared[-3].content)
        self.assertIn("未在优先文件中找到精确匹配", prepared[-2].content)
        self.assertIn("范围外相关参考", prepared[-2].content)

    def test_level_two_filter_preserved_never_claims_scope_expansion(self):
        turn = replace(
            plan_rag_turn(
                RagTurnRequest(user_text="summarize", context_files=["manual.pdf"]),
                unified_execution_enabled=False,
            ),
            fallback_level=2,
            scope_mode_before="filter",
            scope_mode_after="filter",
        )

        prepared = prepare_rag_answer_messages(
            [SimpleNamespace(type="human", content="summarize")],
            turn,
            retrieved_context="evidence",
        )

        self.assertIn("以下是该范围内的相关参考", prepared[-2].content)
        self.assertIn("本次没有搜索范围外知识库", prepared[-2].content)
        self.assertNotIn("包含范围外相关参考", prepared[-2].content)

    def test_level_two_none_preserved_describes_candidate_relaxation_only(self):
        turn = replace(
            plan_rag_turn(RagTurnRequest(user_text="search"), unified_execution_enabled=True),
            fallback_level=2,
            scope_mode_before="none",
            scope_mode_after="none",
        )

        prepared = prepare_rag_answer_messages(
            [SimpleNamespace(type="human", content="search")],
            turn,
            retrieved_context="evidence",
        )

        self.assertIn("扩大候选池及放宽结构限制", prepared[-2].content)
        self.assertIn("本轮没有改变文档检索范围", prepared[-2].content)
        self.assertNotIn("优先文件", prepared[-2].content)

    def test_level_three_uses_template_constraint_instead_of_regular_context(self):
        partial_template = (
            "已完成 1/2 个分析维度。"
            "仅基于上述证据，为已覆盖维度分别生成部分解答；"
            "不得回答未覆盖维度，也不得生成跨维度比较、汇总或总体建议。"
        )
        turn = replace(
            plan_rag_turn(
                RagTurnRequest(user_text="summarize", context_files=["manual.pdf"]),
                unified_execution_enabled=False,
            ),
            fallback_level=3,
            level3_answer=partial_template,
        )

        prepared = prepare_rag_answer_messages(
            [SimpleNamespace(type="human", content="summarize")],
            turn,
            retrieved_context="must not be injected",
        )

        self.assertEqual(len(prepared), 2)
        self.assertIn(partial_template, prepared[-2].content)
        self.assertIn("不得回答未覆盖维度", prepared[-2].content)
        self.assertNotIn("must not be injected", prepared[-2].content)

    def test_level_three_partial_uses_typed_contract_as_control_input(self):
        delivery = {
            "mode": "partial_synthesis",
            "covered_count": 1,
            "total_count": 2,
            "covered_dimensions": ["成本"],
            "uncovered_dimensions": ["风险"],
            "dimension_evidence": [{
                "dimension_id": "sub_query_0",
                "label": "成本",
                "evidence_refs": [{
                    "candidate_id": "cost",
                    "chunk_id": "cost",
                    "filename": "cost.pdf",
                    "page_number": 3,
                    "excerpt": "成本证据",
                }],
            }],
            "baseline_evidence": [],
            "constraints": ["answer_covered_dimensions_only"],
            "attempted_levels": [1, 2, 3],
        }
        turn = replace(
            plan_rag_turn(RagTurnRequest(user_text="compare", context_files=["manual.pdf"])),
            fallback_level=3,
            level3_delivery=delivery,
            level3_answer="legacy text must not control",
        )

        prepared = prepare_rag_answer_messages(
            [SimpleNamespace(type="human", content="compare")],
            turn,
            retrieved_context="must not be injected",
        )

        self.assertIn("不是可直接复述的最终答案", prepared[-2].content)
        self.assertIn("不得输出‘证据摘录’", prepared[-2].content)
        self.assertIn("成本证据", prepared[-2].content)
        self.assertNotIn("legacy text must not control", prepared[-2].content)

    def test_other_levels_do_not_add_fallback_delivery_instruction(self):
        turn = replace(
            plan_rag_turn(
                RagTurnRequest(user_text="summarize", context_files=["manual.pdf"]),
                unified_execution_enabled=False,
            ),
            fallback_level=1,
        )

        prepared = prepare_rag_answer_messages(
            [SimpleNamespace(type="human", content="summarize")],
            turn,
            retrieved_context="evidence",
        )

        self.assertEqual(len(prepared), 2)
        self.assertNotIn("非精确匹配", prepared[-2].content)

    def test_rag_trace_maps_delivery_fields_into_turn_context(self):
        turn = plan_rag_turn(
            RagTurnRequest(user_text="summarize", context_files=["manual.pdf"]),
            unified_execution_enabled=False,
        )

        updated = apply_rag_trace_to_turn_context(
            turn,
            {
                "fallback_level": 2,
                "level2_previous_scope_mode": "boost",
                "level2_new_scope_mode": "none",
                "level3_answer": None,
            },
        )

        self.assertEqual(updated.fallback_level, 2)
        self.assertEqual(updated.scope_mode_before, "boost")
        self.assertEqual(updated.scope_mode_after, "none")

    def test_answer_with_rag_context_hides_model_agent_branch_from_callers(self):
        turn = plan_rag_turn(
            RagTurnRequest(user_text="summarize", context_files=["manual.pdf"], stream=False),
            unified_execution_enabled=False,
        )
        model = FakeModel()
        agent = FakeAgent()

        result = answer_with_rag_context(
            messages=[SimpleNamespace(type="human", content="summarize")],
            turn_context=turn,
            retrieved_context="evidence",
            agent_instance=agent,
            model_instance=model,
        )

        self.assertEqual(result.raw_result.content, "model answer")
        self.assertEqual(result.execution_mode, "preloaded_model")
        self.assertIsNotNone(model.invoked_with)
        self.assertIsNone(agent.invoked_with)

    async def test_stream_answer_with_rag_context_uses_same_execution_contract(self):
        turn = plan_rag_turn(
            RagTurnRequest(user_text="hello", context_files=[], stream=True),
            unified_execution_enabled=False,
        )
        model = FakeModel()
        agent = FakeAgent()

        chunks = [
            item
            async for item in stream_answer_with_rag_context(
                messages=[SimpleNamespace(type="human", content="hello")],
                turn_context=turn,
                retrieved_context="",
                agent_instance=agent,
                model_instance=model,
            )
        ]

        self.assertEqual(chunks[0].content, "agent stream")
        self.assertEqual(agent.config, {"recursion_limit": 8})
        self.assertIsNone(model.invoked_with)


if __name__ == "__main__":
    unittest.main()
