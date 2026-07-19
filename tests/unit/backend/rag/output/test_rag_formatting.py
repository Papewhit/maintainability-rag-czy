import unittest
from unittest.mock import patch

from backend.chat import tools as chat_tools
from backend.chat.agent import _attached_context_payload
from backend.chat.rag_execution import RagTurnRequest, plan_rag_turn
from backend.rag.formatting import (
    NO_RELEVANT_DOCUMENTS_MESSAGE,
    format_rag_documents,
    format_rag_tool_response,
)
from backend.rag.pipeline import _format_docs


class RagFormattingTests(unittest.TestCase):
    def test_pipeline_context_uses_shared_chunk_format(self):
        docs = [
            {"filename": "manual.pdf", "page_number": 2, "text": "alpha"},
            {"filename": "guide.pdf", "page_number": 5, "text": "beta"},
        ]
        expected = "[1] manual.pdf (Page 2):\nalpha\n\n---\n\n[2] guide.pdf (Page 5):\nbeta"

        self.assertEqual(format_rag_documents(docs), expected)
        self.assertEqual(_format_docs(docs), expected)

    def test_tool_response_reuses_graph_context_when_present(self):
        docs = [{"filename": "manual.pdf", "page_number": 2, "text": "alpha"}]

        self.assertEqual(
            format_rag_tool_response(docs, context="[1] already formatted"),
            "Retrieved Chunks:\n[1] already formatted",
        )

    def test_tool_response_can_include_compact_retrieval_meta(self):
        docs = [{"filename": "manual.pdf", "page_number": 2, "text": "alpha"}]
        trace = {
            "candidate_strategy_requested": "standard",
            "candidate_strategy_effective": "standard",
            "candidate_strategy_detail": "global_hybrid",
            "rerank_contract_version": "shared-rerank-v2",
            "postprocess_contract_version": "shared-postprocess-v1",
            "rerank_execution_mode": "executed",
        }

        response = format_rag_tool_response(docs, context="[1] already formatted", retrieval_meta=trace)

        self.assertIn("Retrieval Metadata:", response)
        self.assertIn("candidate_strategy_effective=standard", response)
        self.assertIn("rerank_contract_version=shared-rerank-v2", response)
        self.assertIn("Retrieved Chunks:\n[1] already formatted", response)

    def test_tool_response_keeps_empty_result_contract(self):
        self.assertEqual(format_rag_tool_response([]), NO_RELEVANT_DOCUMENTS_MESSAGE)

    def test_optional_tool_level_two_prepends_same_scope_disclosure(self):
        docs = [{"filename": "manual.pdf", "page_number": 2, "text": "alpha"}]
        trace = {
            "fallback_level": 2,
            "level2_previous_scope_mode": "none",
            "level2_new_scope_mode": "none",
        }

        response = format_rag_tool_response(docs, retrieval_meta=trace)

        self.assertTrue(response.startswith("Fallback Delivery Instruction:"))
        self.assertIn("扩大候选池及放宽结构限制", response)
        self.assertIn("本轮没有改变文档检索范围", response)
        self.assertIn("Retrieved Chunks:", response)

    def test_optional_tool_level_three_returns_template_constraint_even_without_docs(self):
        partial_template = (
            "已完成 1/2 个分析维度。"
            "仅基于上述证据，为已覆盖维度分别生成部分解答；"
            "不得回答未覆盖维度，也不得生成跨维度比较、汇总或总体建议。"
        )
        response = format_rag_tool_response(
            [],
            context=partial_template,
            retrieval_meta={
                "fallback_level": 3,
                "level3_answer": partial_template,
            },
        )

        self.assertTrue(response.startswith("Fallback Delivery Instruction:"))
        self.assertIn(partial_template, response)
        self.assertIn("不得回答未覆盖维度", response)
        self.assertNotEqual(response, NO_RELEVANT_DOCUMENTS_MESSAGE)

    def test_search_tool_reuses_graph_context_and_marks_delivery(self):
        chat_tools.get_last_rag_context(clear=True)
        chat_tools.reset_tool_call_guards()
        rag_result = {
            "docs": [{"filename": "manual.pdf", "page_number": 2, "text": "alpha"}],
            "context": "[1] graph formatted context",
            "rag_trace": {
                "retrieval_mode": "hybrid",
                "candidate_strategy_effective": "standard",
                "rerank_contract_version": "shared-rerank-v2",
                "postprocess_contract_version": "shared-postprocess-v1",
                "rerank_execution_mode": "executed",
            },
        }

        with patch("backend.rag.pipeline.run_rag_graph", return_value=rag_result):
            response = chat_tools.search_knowledge_base.invoke({"query": "q"})

        self.assertIn("Retrieved Chunks:\n[1] graph formatted context", response)
        self.assertIn("Retrieval Metadata:", response)
        stored = chat_tools.get_last_rag_context(clear=True)
        self.assertEqual(stored["rag_trace"]["context_delivery_mode"], "tool_response")
        self.assertEqual(stored["rag_trace"]["retrieval_policy"], "optional_tool")
        self.assertEqual(stored["docs"][0]["filename"], "manual.pdf")

    def test_search_tool_call_guard_survives_tool_invoke_context(self):
        chat_tools.get_last_rag_context(clear=True)
        chat_tools.reset_tool_call_guards()
        rag_result = {
            "docs": [{"filename": "manual.pdf", "page_number": 2, "text": "alpha"}],
            "context": "[1] context",
            "rag_trace": {"retrieval_mode": "hybrid"},
        }

        with patch("backend.rag.pipeline.run_rag_graph", return_value=rag_result):
            first = chat_tools.search_knowledge_base.invoke({"query": "q"})
            second = chat_tools.search_knowledge_base.invoke({"query": "q again"})

        self.assertEqual(first, "Retrieved Chunks:\n[1] context")
        self.assertIn("TOOL_CALL_LIMIT_REACHED", second)

    def test_search_tool_delivers_level_two_scope_instruction_before_chunks(self):
        chat_tools.get_last_rag_context(clear=True)
        chat_tools.reset_tool_call_guards()
        rag_result = {
            "docs": [{"filename": "manual.pdf", "page_number": 2, "text": "alpha"}],
            "context": "[1] context",
            "rag_trace": {
                "fallback_level": 2,
                "level2_previous_scope_mode": "boost",
                "level2_new_scope_mode": "none",
            },
        }

        with patch("backend.rag.pipeline.run_rag_graph", return_value=rag_result):
            response = chat_tools.search_knowledge_base.invoke({"query": "q"})

        self.assertTrue(response.startswith("Fallback Delivery Instruction:"))
        self.assertLess(response.index("范围外相关参考"), response.index("Retrieved Chunks:"))

    def test_search_tool_delivers_level_three_template_when_graph_has_no_docs(self):
        chat_tools.get_last_rag_context(clear=True)
        chat_tools.reset_tool_call_guards()
        rag_result = {
            "docs": [],
            "context": "未在指定范围找到足够依据。",
            "rag_trace": {
                "fallback_level": 3,
                "level3_answer": "未在指定范围找到足够依据。",
            },
        }

        with patch("backend.rag.pipeline.run_rag_graph", return_value=rag_result):
            response = chat_tools.search_knowledge_base.invoke({"query": "q"})

        self.assertTrue(response.startswith("Fallback Delivery Instruction:"))
        self.assertIn("未在指定范围找到足够依据", response)
        self.assertNotEqual(response, NO_RELEVANT_DOCUMENTS_MESSAGE)

    def test_attached_context_payload_marks_direct_delivery(self):
        turn = plan_rag_turn(
            RagTurnRequest(user_text="summarize", context_files=["manual.pdf"]),
            unified_execution_enabled=False,
        )
        context, trace, updated_turn = _attached_context_payload(
            {
                "docs": [{"filename": "manual.pdf", "page_number": 2, "text": "alpha"}],
                "context": "[1] direct context",
                "rag_trace": {
                    "retrieval_mode": "hybrid_scoped",
                    "fallback_level": 2,
                    "level2_previous_scope_mode": "filter",
                    "level2_new_scope_mode": "filter",
                },
            },
            turn,
        )

        self.assertEqual(context, "[1] direct context")
        self.assertEqual(trace["context_delivery_mode"], "system_message")
        self.assertEqual(updated_turn.fallback_level, 2)
        self.assertEqual(updated_turn.scope_mode_after, "filter")


if __name__ == "__main__":
    unittest.main()
