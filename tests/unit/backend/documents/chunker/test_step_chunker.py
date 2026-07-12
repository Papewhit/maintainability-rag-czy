"""Tests for step-protected chunker."""

from __future__ import annotations

from backend.documents.chunker.step_chunker import (
    _split_by_maintenance_actions,
    _split_by_toplevel,
    _starts_with_maintenance_action,
    chunk_normalized,
)
from backend.documents.normalizer.base import (
    ListGroup,
    NormalizedBlock,
    NormalizedDocument,
)
from backend.documents.parse_adapter.base import (
    ParsedDocument,
    ParseMeta,
)


def _block(bid, page=1, text="x", level=None, marker=None, index=None):
    return NormalizedBlock(
        block_id=bid, page_no=page, block_type="list_item", text=text,
        list_level=level, list_marker=marker, list_item_index=index,
    )


class TestMaintenanceActionDetection:
    def test_action_detected(self) -> None:
        assert _starts_with_maintenance_action("拆卸 前盖板")
        assert _starts_with_maintenance_action("检查电源连接")
        assert _starts_with_maintenance_action("更换滤芯组件")
        assert _starts_with_maintenance_action("安装新密封圈")
        assert _starts_with_maintenance_action("复验螺栓扭矩")

    def test_non_action(self) -> None:
        assert not _starts_with_maintenance_action("准备工作")
        assert not _starts_with_maintenance_action("注意事项")


class TestSplitByMaintenanceActions:
    def test_split_at_action_boundaries(self) -> None:
        items = [
            _block("a", text="拆卸 外壳"),
            _block("b", text="取下旧滤芯"),
            _block("c", text="检查 密封面"),
            _block("d", text="安装 新滤芯"),
            _block("e", text="复验 压力"),
        ]
        result = _split_by_maintenance_actions(items)
        # Should split at 检查, 安装, 复验
        assert len(result) >= 3


class TestSplitByTopLevel:
    def test_children_follow_parent(self) -> None:
        """Per spec: top-level items have list_level=1, children level=2."""
        items = [
            _block("a", level=1, text="主步骤1"),
            _block("a1", level=2, text="子步骤a"),
            _block("a2", level=2, text="子步骤b"),
            _block("b", level=1, text="主步骤2"),
        ]
        result = _split_by_toplevel(items)
        assert len(result) == 2
        # First group has parent + 2 children
        assert len(result[0]) == 3
        # Second group has 1 parent
        assert len(result[1]) == 1


class TestChunkNormalized:
    def test_produces_chunks(self) -> None:
        doc = NormalizedDocument(
            parsed=ParsedDocument(
                filename="test.pdf", file_type="pdf",
                parse_meta=ParseMeta(parse_engine="test"),
            ),
            normalized_blocks=[
                _block("b1", text="1. 检查外观"),
                _block("b2", text="2. 功能测试"),
            ],
            list_groups=[
                ListGroup(
                    group_id="lg_p1_l1_s0", list_level=1,
                    items=[
                        _block("b1", text="1. 检查外观", level=1, marker="1.", index=0),
                        _block("b2", text="2. 功能测试", level=1, marker="2.", index=1),
                    ],
                ),
            ],
        )
        chunks = chunk_normalized(doc, "/tmp/test.pdf")
        assert len(chunks) > 0
        # Should have at least 1 parent + 2 leaf chunks
        roots = [c for c in chunks if c["chunk_role"] == "root"]
        leaves = [c for c in chunks if c["chunk_role"] == "leaf"]
        assert len(roots) >= 1
        assert len(leaves) >= 2

    def test_list_fields_populated(self) -> None:
        doc = NormalizedDocument(
            parsed=ParsedDocument(
                filename="test.pdf", file_type="pdf",
                parse_meta=ParseMeta(parse_engine="test"),
            ),
            normalized_blocks=[
                _block("b1", text="1. 第一步", level=1, marker="1.", index=0),
            ],
            list_groups=[
                ListGroup(
                    group_id="lg_1", list_level=1,
                    items=[
                        _block("b1", text="1. 第一步", level=1, marker="1.", index=0),
                    ],
                ),
            ],
        )
        chunks = chunk_normalized(doc, "/tmp/test.pdf")
        leaf = [c for c in chunks if c["chunk_role"] == "leaf"]
        assert len(leaf) >= 1
        assert leaf[0]["list_group_id"] == "lg_1"
        assert leaf[0]["list_marker"] == "1."
        assert leaf[0]["list_order"] == 0

    def test_split_list_parents_have_one_based_subgroup_order(self) -> None:
        items = [
            _block("b1", text="1. 拆卸外壳并记录状态", level=1, marker="1.", index=0),
            _block("b2", text="2. 检查密封面并记录状态", level=1, marker="2.", index=1),
            _block("b3", text="3. 安装新密封圈并复验", level=1, marker="3.", index=2),
        ]
        doc = NormalizedDocument(
            parsed=ParsedDocument(
                filename="test.pdf", file_type="pdf",
                parse_meta=ParseMeta(parse_engine="test"),
            ),
            normalized_blocks=items,
            list_groups=[ListGroup(group_id="lg_1", list_level=1, items=items)],
        )

        chunks = chunk_normalized(doc, "/tmp/test.pdf", root_tokens=5)
        roots = [chunk for chunk in chunks if chunk["chunk_role"] == "root"]

        assert len(roots) > 1
        assert [root["list_order"] for root in roots] == list(range(1, len(roots) + 1))
        assert all(root["list_complete"] is False for root in roots)
        assert [root["parent_extras"]["list_order"] for root in roots] == list(range(1, len(roots) + 1))
        assert all(root["parent_extras"]["list_group_id"] == "lg_1" for root in roots)
        assert all(root["parent_extras"]["list_complete"] is False for root in roots)

    def test_long_chinese_list_item_leaf_respects_milvus_byte_budget(self) -> None:
        item_text = "6.4.3 沿用、改进软件变更关联功能优化需求符合性\n" + ("该需求强调多型号软件变更同步关联。" * 120)
        doc = NormalizedDocument(
            parsed=ParsedDocument(
                filename="test.pdf", file_type="pdf",
                parse_meta=ParseMeta(parse_engine="test"),
            ),
            normalized_blocks=[
                _block("b1", text=item_text, level=1, marker="6.4.3", index=0),
            ],
            list_groups=[
                ListGroup(
                    group_id="lg_1", list_level=1,
                    items=[
                        _block("b1", text=item_text, level=1, marker="6.4.3", index=0),
                    ],
                ),
            ],
        )

        chunks = chunk_normalized(doc, "/tmp/test.pdf", profile="v4_full")
        leaves = [c for c in chunks if c["chunk_role"] == "leaf"]

        assert len(leaves) > 1
        assert all(len(c["text"].encode("utf-8")) <= 2000 for c in leaves)
        assert all(len(c["retrieval_text"].encode("utf-8")) <= 4000 for c in leaves)

    def test_non_list_block_still_chunked(self) -> None:
        doc = NormalizedDocument(
            parsed=ParsedDocument(
                filename="test.pdf", file_type="pdf",
                parse_meta=ParseMeta(parse_engine="test"),
            ),
            normalized_blocks=[
                _block("b1", text="一段普通正文", level=None, marker=None),
            ],
            list_groups=[],
        )
        chunks = chunk_normalized(doc, "/tmp/test.pdf")
        assert len(chunks) > 0
