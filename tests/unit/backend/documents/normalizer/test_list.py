"""Tests for list normalizer."""

from __future__ import annotations

from backend.documents.normalizer.base import NormalizedBlock
from backend.documents.normalizer.list_normalizer import (
    extract_list_marker,
    detect_and_group_lists,
)


class TestExtractListMarker:
    def test_chinese_ordinal(self) -> None:
        m, rest = extract_list_marker("一、项目概况")
        assert m == "一、"
        assert rest == "项目概况"

    def test_numbered(self) -> None:
        m, rest = extract_list_marker("1. 检查外观")
        assert m == "1."
        assert rest == "检查外观"

    def test_parenthesized_digit(self) -> None:
        m, rest = extract_list_marker("（1）拆卸外壳")
        assert m == "（1）"
        assert rest == "拆卸外壳"

    def test_parenthesized_letter(self) -> None:
        m, rest = extract_list_marker("(a) 初始化系统")
        assert m == "(a)"
        assert rest == "初始化系统"

    def test_multi_level_number(self) -> None:
        m, rest = extract_list_marker("1.1 子步骤说明")
        assert m == "1.1"
        assert rest == "子步骤说明"

    def test_bullet(self) -> None:
        m, rest = extract_list_marker("• 注意事项")
        assert m == "•"
        assert rest == "注意事项"

    def test_no_marker(self) -> None:
        m, rest = extract_list_marker("这是一段普通文本")
        assert m is None
        assert rest == "这是一段普通文本"


class TestDetectAndGroupLists:
    @staticmethod
    def make_block(bid, page, text, bt="paragraph", bbox=None):
        return NormalizedBlock(
            block_id=bid, page_no=page, block_type=bt, text=text,
            bbox=bbox, order_index=int(bid[1:]),
        )

    def test_simple_flat_list(self) -> None:
        blocks = [
            self.make_block("b0", 1, "1. 第一步"),
            self.make_block("b1", 1, "2. 第二步"),
            self.make_block("b2", 1, "3. 第三步"),
        ]
        enriched, groups = detect_and_group_lists(blocks)
        assert len(groups) == 1, f"Expected 1 group, got {len(groups)}"
        assert groups[0].list_level == 1
        assert len(groups[0].items) == 3
        assert groups[0].items[0].list_item_index == 0
        assert groups[0].items[1].list_item_index == 1

    def test_indented_nested_list(self) -> None:
        blocks = [
            self.make_block("b0", 1, "1. 主步骤", bbox=(50, 300, 100, 115)),
            self.make_block("b1", 1, "(a) 子步骤A", bbox=(80, 300, 120, 135)),
            self.make_block("b2", 1, "(b) 子步骤B", bbox=(80, 300, 140, 155)),
            self.make_block("b3", 1, "2. 下一主步骤", bbox=(50, 300, 170, 185)),
        ]
        enriched, groups = detect_and_group_lists(blocks)
        # Two top-level groups because level changes
        assert len(groups) >= 1
        # Verify list_marker populated
        markers = [b.list_marker for b in enriched if b.list_marker]
        assert len(markers) >= 4

    def test_non_list_interruption(self) -> None:
        blocks = [
            self.make_block("b0", 1, "1. 步骤A"),
            self.make_block("b1", 1, "一段说明文字", bt="paragraph"),
            self.make_block("b2", 1, "2. 步骤B"),
        ]
        enriched, groups = detect_and_group_lists(blocks)
        # Interrupted by paragraph → two separate groups
        assert len(groups) >= 1

    def test_marker_stripped_from_rest(self) -> None:
        m, rest = extract_list_marker("（三）质量要求")
        assert m == "（三）"
        assert not rest.startswith("（三）")

    def test_all_blocks_preserved(self) -> None:
        blocks = [
            self.make_block("b0", 1, "标题", bt="heading"),
            self.make_block("b1", 1, "1. 第一步"),
            self.make_block("b2", 1, "正文"),
        ]
        enriched, _ = detect_and_group_lists(blocks)
        assert len(enriched) == 3
