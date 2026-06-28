"""Tests for ParseAdapter data classes and protocol."""

from __future__ import annotations

import pytest

from backend.documents.parse_adapter.base import (
    ParsedBlock,
    ParsedDocument,
    ParsedFigureAnchor,
    ParsedTable,
    ParseAdapter,
    ParseError,
    ParseMeta,
    UnsupportedFileType,
)


class TestParsedBlock:
    def test_minimal_block(self) -> None:
        b = ParsedBlock(block_id="b1", page_no=1, block_type="paragraph", text="Hello")
        assert b.block_id == "b1"
        assert b.block_type == "paragraph"
        assert b.text == "Hello"
        assert b.page_no == 1
        assert b.bbox is None
        assert b.ocr_confidence is None
        assert b.order_index == 0
        assert b.style == {}

    def test_frozen_prevents_mutation(self) -> None:
        b = ParsedBlock(block_id="b1", page_no=1, block_type="paragraph", text="Hello")
        with pytest.raises(Exception):
            b.text = "changed"  # type: ignore[misc]

    def test_with_bbox(self) -> None:
        b = ParsedBlock(
            block_id="b2", page_no=2, block_type="heading", text="Title",
            bbox=(10.0, 200.0, 5.0, 20.0),
        )
        assert b.bbox == (10.0, 200.0, 5.0, 20.0)

    def test_all_block_types(self) -> None:
        for bt in ("heading", "paragraph", "list_item", "table_caption", "figure_caption", "footnote"):
            b = ParsedBlock(block_id="x", page_no=1, block_type=bt, text="test")  # type: ignore[arg-type]
            assert b.block_type == bt


class TestParsedTable:
    def test_minimal(self) -> None:
        t = ParsedTable(table_id="t1", page_no=3)
        assert t.table_id == "t1"
        assert t.caption == ""
        assert t.cells_markdown == ""
        assert t.cells_structured == []
        assert t.bbox is None
        assert t.nearby_block_ids == []

    def test_with_data(self) -> None:
        t = ParsedTable(
            table_id="t2", page_no=4,
            caption="Parameters",
            cells_markdown="| A | B |\n|---|---|",
            cells_structured=[["A", "B"], ["1", "2"]],
            nearby_block_ids=["b1", "b2"],
        )
        assert t.cells_structured == [["A", "B"], ["1", "2"]]
        assert t.nearby_block_ids == ["b1", "b2"]

    def test_frozen(self) -> None:
        t = ParsedTable(table_id="t1", page_no=3)
        with pytest.raises(Exception):
            t.caption = "new"  # type: ignore[misc]


class TestParsedFigureAnchor:
    def test_minimal(self) -> None:
        f = ParsedFigureAnchor(figure_id="f1", page_no=5)
        assert f.figure_id == "f1"
        assert f.caption == ""

    def test_with_caption(self) -> None:
        f = ParsedFigureAnchor(figure_id="f2", page_no=6, caption="Fig 1. Overview")
        assert f.caption == "Fig 1. Overview"


class TestParseMeta:
    def test_minimal(self) -> None:
        m = ParseMeta(parse_engine="test")
        assert m.parse_engine == "test"
        assert m.parse_engine_version == ""
        assert m.parse_duration_ms == 0.0
        assert m.total_pages == 0
        assert m.parse_warnings == []

    def test_with_data(self) -> None:
        m = ParseMeta(
            parse_engine="deepdoc",
            parse_engine_version="2.0",
            parse_duration_ms=1500.5,
            total_pages=7,
            parse_warnings=["low ocr confidence on page 3"],
            ocr_confidence_avg=0.85,
        )
        assert m.parse_duration_ms == 1500.5
        assert len(m.parse_warnings) == 1


class TestParsedDocument:
    def test_minimal(self) -> None:
        d = ParsedDocument(filename="test.pdf", file_type="pdf", parse_meta=ParseMeta(parse_engine="test"))
        assert d.filename == "test.pdf"
        assert d.blocks == []
        assert d.tables == []
        assert d.figures == []
        assert d.parse_meta.parse_engine == "test"

    def test_frozen(self) -> None:
        d = ParsedDocument(filename="x.pdf", file_type="pdf", parse_meta=ParseMeta(parse_engine="test"))
        with pytest.raises(Exception):
            d.filename = "y.pdf"  # type: ignore[misc]


class TestParseError:
    def test_basic(self) -> None:
        with pytest.raises(ParseError, match="test error"):
            raise ParseError("test error")

    def test_unsupported_file_type(self) -> None:
        with pytest.raises(UnsupportedFileType, match=".xyz"):
            raise UnsupportedFileType("No adapter for .xyz")
