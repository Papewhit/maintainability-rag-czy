from __future__ import annotations

import asyncio
import unittest

import pytest

from backend.chat.tools import emit_rag_step, set_rag_step_queue


pytestmark = pytest.mark.unit


class RagStepEmissionTests(unittest.IsolatedAsyncioTestCase):
    async def test_emit_rag_step_preserves_structured_fallback_fields(self):
        queue: asyncio.Queue = asyncio.Queue()
        set_rag_step_queue(queue)
        try:
            emit_rag_step(
                "✏️",
                "Level 1：重写查询",
                "进入查询重写",
                level=1,
                signal="anchor_mismatch",
                strategy="step_back",
            )
            step = await asyncio.wait_for(queue.get(), timeout=1)
        finally:
            set_rag_step_queue(None)

        self.assertEqual(
            step,
            {
                "icon": "✏️",
                "label": "Level 1：重写查询",
                "detail": "进入查询重写",
                "level": 1,
                "signal": "anchor_mismatch",
                "strategy": "step_back",
            },
        )

    async def test_emit_rag_step_omits_optional_strategy_but_keeps_required_schema(self):
        queue: asyncio.Queue = asyncio.Queue()
        set_rag_step_queue(queue)
        try:
            emit_rag_step(
                "✅",
                "检索完成",
                "Level 0 证据充足",
                level=0,
                signal="confidence_passed",
            )
            step = await asyncio.wait_for(queue.get(), timeout=1)
        finally:
            set_rag_step_queue(None)

        self.assertEqual(
            step,
            {
                "icon": "✅",
                "label": "检索完成",
                "detail": "Level 0 证据充足",
                "level": 0,
                "signal": "confidence_passed",
            },
        )
