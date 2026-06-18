"""Tests for figure chunking (M3)."""

from __future__ import annotations

from backend.documents.chunker.step_chunker import _chunk_figure, chunk_normalized
from backend.documents.normalizer.base import (
    FigureAssociation,
    NormalizedBlock,
    NormalizedDocument,
)
from backend.documents.parse_adapter.base import (
    ParsedDocument,
    ParseMeta,
)


def _block(bid, page=1, text="x", bt="paragraph"):
    return NormalizedBlock(block_id=bid, page_no=page, block_type=bt, text=text)


class TestChunkFigure:
    def test_produces_root_and_leaf(self) -> None:
        fa = FigureAssociation(
            figure_id="f_1", caption="图 3-2 主轴承装配示意图", page_no=1,
            nearby_block_ids=["b1", "b2"],
        )
        blocks = [
            _block("b1", text="图 3-2 主轴承装配示意图"),
            _block("b2", text="安装时需注意对中"),
        ]
        chunks = _chunk_figure(fa, "test.pdf", "/tmp/test.pdf", blocks, 2000, 500)
        roots = [c for c in chunks if c["chunk_role"] == "root"]
        leaves = [c for c in chunks if c["chunk_role"] == "leaf"]
        assert len(roots) == 1
        assert len(leaves) >= 1

    def test_figure_fields_populated(self) -> None:
        fa = FigureAssociation(
            figure_id="f_1", caption="图 3-2 装配图", page_no=1,
            nearby_block_ids=["b1"],
        )
        blocks = [_block("b1", text="图 3-2 装配图", bt="figure_caption")]
        chunks = _chunk_figure(fa, "test.pdf", "/tmp/test.pdf", blocks, 2000, 500)
        root = [c for c in chunks if c["chunk_role"] == "root"][0]
        assert root["figure_id"] == "f_1"
        assert root["figure_role"] in ("schematic", "assembly", "diagram", "photo", "chart")
        assert root["block_type"] == "figure"
        assert "nearby_block_ids" in root.get("parent_extras", {})

    def test_caption_first_line(self) -> None:
        # Caption comes from the FigureAssociation (authoritative), not guessed from blocks
        fa = FigureAssociation(
            figure_id="f_1", caption="图4-1 结构图", page_no=1,
            nearby_block_ids=["b1"],
        )
        blocks = [_block("b1", text="详细说明如下")]
        chunks = _chunk_figure(fa, "test.pdf", "/tmp/test.pdf", blocks, 2000, 500)
        root_text = [c for c in chunks if c["chunk_role"] == "root"][0]["text"]
        # Caption must be first line (spec)
        assert root_text.startswith("图4-1 结构图")

    def test_integrated_in_chunk_normalized(self) -> None:
        doc = NormalizedDocument(
            parsed=ParsedDocument(
                filename="test.pdf", file_type="pdf",
                parse_meta=ParseMeta(parse_engine="test"),
            ),
            normalized_blocks=[
                _block("b1", text="图 1-1 示意"),
                _block("b2", text="参见图 1-1"),
            ],
            list_groups=[],
            figure_associations=[
                FigureAssociation(figure_id="f_0", caption="图 1-1 示意", page_no=1, nearby_block_ids=["b1", "b2"]),
            ],
        )
        chunks = chunk_normalized(doc, "/tmp/test.pdf", profile="v4_full")
        fig_chunks = [c for c in chunks if c["block_type"] == "figure"]
        assert len(fig_chunks) >= 2  # root + at least 1 leaf
