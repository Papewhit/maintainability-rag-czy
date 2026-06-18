"""Tests for Normalizer data classes."""

from __future__ import annotations

import pytest

from backend.documents.parse_adapter.base import ParsedBlock, ParsedDocument, ParseMeta
from backend.documents.normalizer.base import (
    FigureAssociation,
    ListGroup,
    NormalizedBlock,
    NormalizedDocument,
)


class TestNormalizedBlock:
    def test_inherits_parsed_block(self) -> None:
        nb = NormalizedBlock(
            block_id="b1", page_no=1, block_type="list_item", text="Step 1",
            list_marker="(1)", list_level=0, list_item_index=0,
        )
        # Inherited fields
        assert nb.block_id == "b1"
        assert nb.block_type == "list_item"
        assert nb.text == "Step 1"
        # New fields
        assert nb.list_marker == "(1)"
        assert nb.list_level == 0
        assert nb.list_item_index == 0
        # Defaults
        assert nb.section_path == ""
        assert nb.anchor_id == ""

    def test_is_frozen(self) -> None:
        nb = NormalizedBlock(block_id="b1", page_no=1, block_type="paragraph", text="x")
        with pytest.raises(Exception):
            nb.list_marker = "changed"  # type: ignore[misc]


class TestListGroup:
    def test_minimal(self) -> None:
        lg = ListGroup(group_id="g1", list_level=0)
        assert lg.group_id == "g1"
        assert lg.items == []
        assert lg.parent_group_id is None

    def test_with_items(self) -> None:
        items = [
            NormalizedBlock(block_id="b1", page_no=1, block_type="list_item", text="A", list_marker="1.", list_level=0, list_item_index=0),
            NormalizedBlock(block_id="b2", page_no=1, block_type="list_item", text="B", list_marker="2.", list_level=0, list_item_index=1),
        ]
        lg = ListGroup(group_id="g1", list_level=0, items=items)
        assert len(lg.items) == 2
        assert lg.items[0].list_item_index == 0


class TestFigureAssociation:
    def test_minimal(self) -> None:
        fa = FigureAssociation(figure_id="f1")
        assert fa.figure_id == "f1"
        assert fa.nearby_block_ids == []


class TestNormalizedDocument:
    def test_minimal(self) -> None:
        pd = ParsedDocument(filename="x.pdf", file_type="pdf", parse_meta=ParseMeta(parse_engine="test"))
        nd = NormalizedDocument(parsed=pd)
        assert nd.parsed is pd
        assert nd.normalized_blocks == []
        assert nd.list_groups == []
        assert nd.figure_associations == []
        assert nd.heading_tree is None

    def test_with_blocks(self) -> None:
        pd = ParsedDocument(filename="x.pdf", file_type="pdf", parse_meta=ParseMeta(parse_engine="test"))
        nb = NormalizedBlock(block_id="b1", page_no=1, block_type="paragraph", text="hello")
        nd = NormalizedDocument(parsed=pd, normalized_blocks=[nb])
        assert len(nd.normalized_blocks) == 1
        assert nd.normalized_blocks[0].text == "hello"
