"""Tests for figure normalizer."""

from __future__ import annotations

from backend.documents.normalizer.base import NormalizedBlock
from backend.documents.normalizer.figure_normalizer import (
    _extract_figure_number,
    _infer_figure_role,
    build_figure_associations,
)
from backend.documents.parse_adapter.base import ParsedFigureAnchor


class TestExtractFigureNumber:
    def test_chinese(self) -> None:
        assert _extract_figure_number("图 3-2 主轴承装配") == "图 3-2"
        assert _extract_figure_number("图3-2 结构示意") == "图3-2"

    def test_english(self) -> None:
        assert _extract_figure_number("Fig. 3-2 Bearing") == "Fig. 3-2"

    def test_no_match(self) -> None:
        assert _extract_figure_number("示意图") is None


class TestInferFigureRole:
    def test_schematic(self) -> None:
        assert _infer_figure_role("系统原理示意图") == "schematic"

    def test_assembly(self) -> None:
        assert _infer_figure_role("装配图 总成") == "assembly"
        assert _infer_figure_role("爆炸分解图") == "assembly"

    def test_default(self) -> None:
        assert _infer_figure_role("图 1-1") == "diagram"


class TestBuildFigureAssociations:
    def test_bbox_proximity(self) -> None:
        figures = [
            ParsedFigureAnchor(figure_id="f0", page_no=1, caption="图1-1", bbox=(50, 200, 100, 150)),
        ]
        blocks = [
            NormalizedBlock(block_id="b1", page_no=1, block_type="paragraph", text="text", bbox=(50, 200, 160, 180)),
            NormalizedBlock(block_id="b2", page_no=1, block_type="paragraph", text="far", bbox=(50, 200, 500, 520)),
            NormalizedBlock(block_id="b3", page_no=2, block_type="paragraph", text="other page", bbox=(50, 200, 100, 120)),
        ]
        assocs = build_figure_associations(figures, blocks, nearby_distance=200)
        assert len(assocs) == 1
        assert assocs[0].caption == "图1-1"  # from anchor
        assert assocs[0].page_no == 1        # from anchor
        assert "b1" in assocs[0].nearby_block_ids
        assert "b2" not in assocs[0].nearby_block_ids  # too far
        assert "b3" not in assocs[0].nearby_block_ids  # different page

    def test_text_reference(self) -> None:
        figures = [
            ParsedFigureAnchor(figure_id="f0", page_no=1, caption="图 3-2 装配", bbox=(50, 200, 100, 150)),
        ]
        blocks = [
            NormalizedBlock(block_id="b1", page_no=1, block_type="paragraph", text="参见图 3-2 的安装方式", bbox=None),
            NormalizedBlock(block_id="b2", page_no=1, block_type="paragraph", text="无关文本", bbox=None),
        ]
        assocs = build_figure_associations(figures, blocks)
        assert len(assocs) == 1
        assert "b1" in assocs[0].nearby_block_ids

    def test_no_nearby_blocks(self) -> None:
        figures = [ParsedFigureAnchor(figure_id="f0", page_no=1, caption="孤立图")]
        blocks = [NormalizedBlock(block_id="b1", page_no=2, block_type="paragraph", text="other")]
        assocs = build_figure_associations(figures, blocks)
        assert len(assocs) == 1
        assert assocs[0].nearby_block_ids == []
