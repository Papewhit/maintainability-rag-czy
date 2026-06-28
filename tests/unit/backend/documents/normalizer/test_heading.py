"""Tests for heading normalizer."""

from __future__ import annotations

from backend.documents.normalizer.base import NormalizedBlock
from backend.documents.normalizer.heading_normalizer import (
    _heading_depth,
    _extract_anchor_id,
    _normalize_title,
    build_heading_tree,
)


class TestHeadingDepth:
    def test_chapter(self) -> None:
        assert _heading_depth("第一章  概述") == 1
        assert _heading_depth("第二章 系统设计") == 1
        assert _heading_depth("第十二章  测试") == 1

    def test_section(self) -> None:
        assert _heading_depth("第一节  方案") == 2
        assert _heading_depth("第3节 安装步骤") == 2

    def test_article(self) -> None:
        assert _heading_depth("第三条  适用范围") == 3
        assert _heading_depth("第五十条  附则") == 3

    def test_decimal(self) -> None:
        assert _heading_depth("1 引言") == 1
        assert _heading_depth("1.2 背景") == 2
        assert _heading_depth("3.4.1 详细设计") == 3

    def test_chinese_list(self) -> None:
        assert _heading_depth("一、项目概要") == 1
        assert _heading_depth("三、验收标准") == 1

    def test_paren_list(self) -> None:
        assert _heading_depth("（一）准备工作") == 2
        assert _heading_depth("(1) 检查电源") == 2

    def test_not_heading(self) -> None:
        assert _heading_depth("这是一段普通文本") == 0
        assert _heading_depth("系统提供以下功能：") == 0


class TestExtractAnchorId:
    def test_chapter(self) -> None:
        assert _extract_anchor_id("第三章 维修流程") == "第三章"

    def test_decimal(self) -> None:
        assert _extract_anchor_id("2.3.1 拆解步骤") == "2.3.1"


class TestBuildHeadingTree:
    def test_flat_headings(self) -> None:
        blocks = [
            NormalizedBlock(block_id="h1", page_no=1, block_type="heading", text="第一章 概述"),
            NormalizedBlock(block_id="p1", page_no=1, block_type="paragraph", text="这是内容"),
            NormalizedBlock(block_id="h2", page_no=2, block_type="heading", text="第二章 方法"),
            NormalizedBlock(block_id="p2", page_no=2, block_type="paragraph", text="方法内容"),
        ]
        enriched, tree = build_heading_tree(blocks)
        assert enriched[0].section_path == "第一章 概述"
        assert enriched[1].section_path == "第一章 概述"
        assert enriched[1].section_title == "第一章 概述"
        assert enriched[2].section_path == "第二章 方法"
        assert enriched[3].section_path == "第二章 方法"

    def test_nested_headings(self) -> None:
        blocks = [
            NormalizedBlock(block_id="h1", page_no=1, block_type="heading", text="第一章 概述"),
            NormalizedBlock(block_id="h1_1", page_no=1, block_type="heading", text="1.1 背景"),
            NormalizedBlock(block_id="p1", page_no=1, block_type="paragraph", text="内容"),
        ]
        enriched, _ = build_heading_tree(blocks)
        assert enriched[1].section_path == "第一章 概述 > 1.1 背景"
        assert enriched[2].section_path == "第一章 概述 > 1.1 背景"

    def test_heading_has_anchor(self) -> None:
        blocks = [
            NormalizedBlock(block_id="h1", page_no=1, block_type="heading", text="第三章 维修"),
        ]
        enriched, _ = build_heading_tree(blocks)
        assert enriched[0].anchor_id == "第三章"

    def test_paragraph_detected_as_heading(self) -> None:
        """A paragraph matching a heading pattern should be treated as a heading."""
        blocks = [
            NormalizedBlock(block_id="h1", page_no=1, block_type="paragraph", text="2.1 安装准备"),
            NormalizedBlock(block_id="p1", page_no=1, block_type="paragraph", text="后续内容"),
        ]
        enriched, _ = build_heading_tree(blocks)
        assert enriched[0].section_path == "2.1 安装准备"
        assert enriched[1].section_path == "2.1 安装准备"
