"""Tests for DeepDoc parse metadata and table conversion helpers."""

from __future__ import annotations

import time

import numpy as np
import pytest

from backend.documents.parse_adapter.base import ParsedBlock, ParseMeta
from backend.documents.parse_adapter.deepdoc.adapter import DeepDocAdapter, _summarize_pdf_parse_path


def test_parse_meta_parse_path():
    meta_native = ParseMeta(
        parse_engine="deepdoc",
        parse_path="native_text",
    )
    assert meta_native.parse_path == "native_text"

    meta_ocr = ParseMeta(
        parse_engine="deepdoc",
        parse_path="ocr",
        ocr_confidence_avg=0.95,
    )
    assert meta_ocr.parse_path == "ocr"
    assert meta_ocr.ocr_confidence_avg == 0.95

    meta_mixed = ParseMeta(
        parse_engine="deepdoc",
        parse_path="mixed",
        ocr_confidence_avg=0.75,
    )
    assert meta_mixed.parse_path == "mixed"


def test_parse_path_algorithm():
    def block(i: int, source: str) -> ParsedBlock:
        return ParsedBlock(
            block_id=f"b{i}",
            page_no=1,
            block_type="paragraph",
            text=str(i),
            ocr_confidence=0.9 if source == "ocr" else None,
            style={"parse_sources": [source]},
        )

    assert _summarize_pdf_parse_path([block(i, "ocr") for i in range(10)], [])[0] == "ocr"
    assert _summarize_pdf_parse_path([block(i, "native_text") for i in range(10)], [])[0] == "native_text"
    assert _summarize_pdf_parse_path(
        [block(i, "ocr" if i < 5 else "native_text") for i in range(10)],
        [],
    )[0] == "mixed"
    assert _summarize_pdf_parse_path(
        [block(i, "ocr" if i < 8 else "native_text") for i in range(10)],
        [],
    )[0] == "ocr"
    assert _summarize_pdf_parse_path(
        [block(i, "ocr" if i < 2 else "native_text") for i in range(10)],
        [],
    )[0] == "native_text"


def test_deepdoc_convert_text_blocks_reads_score_and_source_tags():
    text_output = (
        "OCR line@@1\t10.0\t20.0\t30.0\t40.0\t0.8123\t0##\n\n"
        "Native line@@1\t10.0\t20.0\t50.0\t60.0\t1.0000\t1##"
    )
    warnings: list[str] = []

    blocks = DeepDocAdapter._convert_text_blocks(text_output, warnings)

    assert blocks[0].ocr_confidence == pytest.approx(0.8123)
    assert blocks[0].style["parse_sources"] == ["ocr"]
    assert blocks[1].ocr_confidence is None
    assert blocks[1].style["parse_sources"] == ["native_text"]


def test_deepdoc_convert_tables_extracts_html_caption_and_preserves_html():
    html = (
        "<table><caption>表5 统一源图节点关键属性定义</caption>"
        "<tr><th>字段</th></tr><tr><td>node_id</td></tr></table>"
    )

    tables, figures = DeepDocAdapter._convert_tables_figures([(None, html)])

    assert figures == []
    assert len(tables) == 1
    assert tables[0].caption == "表5 统一源图节点关键属性定义"
    assert tables[0].cells_markdown == html


def test_deepdoc_convert_tables_extracts_html_cells_structured():
    html = (
        "<table><caption>表5 属性定义</caption>"
        "<tr><th>字段</th><th>含义</th></tr>"
        "<tr><td>node_id</td><td>节点唯一标识</td></tr>"
        "</table>"
    )

    tables, _ = DeepDocAdapter._convert_tables_figures([(None, html)])

    assert tables[0].caption == "表5 属性定义"
    assert tables[0].cells_markdown == html
    assert tables[0].cells_structured == [
        ["字段", "含义"],
        ["node_id", "节点唯一标识"],
    ]


def test_deepdoc_convert_tables_handles_unquoted_colspan_and_rowspan():
    html = (
        "<table><caption>表6 跨行跨列表</caption>"
        "<tr><th>对象</th><th colspan=2>属性</th></tr>"
        "<tr><td rowspan=2>node</td><td>id</td><td>唯一标识</td></tr>"
        "<tr><td>name</td><td>名称</td></tr>"
        "</table>"
    )

    tables, _ = DeepDocAdapter._convert_tables_figures([(None, html)])

    assert tables[0].cells_structured == [
        ["对象", "属性", ""],
        ["node", "id", "唯一标识"],
        ["node", "name", "名称"],
    ]


def test_deepdoc_convert_tables_maps_first_position_to_bbox_anchor():
    html = (
        "<table><caption>表6 统一源图边关键属性定义</caption>"
        "<tr><td>A</td></tr></table>"
    )
    positioned_item = ((None, html), [(0, 12.5, 240.0, 32.0, 98.5)])

    tables, _ = DeepDocAdapter._convert_tables_figures([positioned_item])

    assert tables[0].page_no == 1
    assert tables[0].bbox == (12.5, 240.0, 32.0, 98.5)


def test_deepdoc_convert_tables_accepts_numpy_position_scalars():
    html = "<table><caption>表6 统一源图边关键属性定义</caption><tr><td>A</td></tr></table>"
    positioned_item = (
        (None, html),
        [(np.int64(0), np.float32(12.5), np.float64(240.0), np.float32(32.0), np.float64(98.5))],
    )

    tables, _ = DeepDocAdapter._convert_tables_figures([positioned_item])

    assert tables[0].caption == "表6 统一源图边关键属性定义"
    assert tables[0].bbox == (12.5, 240.0, 32.0, 98.5)


def test_deepdoc_convert_tables_leaves_bbox_none_without_position():
    tables, _ = DeepDocAdapter._convert_tables_figures(
        [(None, "<table><caption>表7 字段定义</caption><tr><td>A</td></tr></table>")]
    )

    assert tables[0].caption == "表7 字段定义"
    assert tables[0].bbox is None


def test_deepdoc_convert_tables_uses_only_explicit_non_html_caption():
    explicit = {
        "content": "A;B\n1;2",
        "caption": "表8 显式标题",
        "position": (0, 1.0, 2.0, 3.0, 4.0),
    }

    explicit_tables, _ = DeepDocAdapter._convert_tables_figures([(None, explicit)])
    guessed_tables, _ = DeepDocAdapter._convert_tables_figures(
        [(None, "表9 看起来像标题但只是普通非 HTML 内容")]
    )

    assert explicit_tables[0].caption == "表8 显式标题"
    assert explicit_tables[0].bbox == (1.0, 2.0, 3.0, 4.0)
    assert guessed_tables[0].caption == ""


def test_deepdoc_parse_pdf_requests_table_positions(monkeypatch):
    captured: dict[str, object] = {}

    class FakeParser:
        total_page = 1

        def __call__(
            self,
            file_path,
            *,
            need_image=True,
            zoomin=3,
            return_html=False,
            need_position=False,
        ):
            captured["need_position"] = need_position
            html = "<table><caption>表5 属性定义</caption><tr><td>A</td></tr></table>"
            return "说明@@1\t1\t2\t3\t4\t1.0\t1##", [((None, html), [(0, 1, 2, 3, 4)])]

    import backend.documents.parse_adapter.deepdoc._pdf_parser as pdf_parser

    monkeypatch.setattr(pdf_parser, "RAGFlowPdfParser", FakeParser)

    doc = DeepDocAdapter()._parse_pdf("fake.pdf", time.perf_counter())

    assert captured["need_position"] is True
    assert doc.tables[0].bbox == (1.0, 2.0, 3.0, 4.0)


def test_summarize_pdf_parse_path_uses_converted_blocks():
    warnings: list[str] = []
    blocks = [
        ParsedBlock(
            block_id="ocr",
            page_no=1,
            block_type="paragraph",
            text="ocr",
            ocr_confidence=0.7,
            style={"parse_sources": ["ocr"]},
        ),
        ParsedBlock(
            block_id="native",
            page_no=1,
            block_type="paragraph",
            text="native",
            style={"parse_sources": ["native_text"]},
        ),
    ]

    parse_path, confidence = _summarize_pdf_parse_path(blocks, warnings)

    assert parse_path == "mixed"
    assert confidence == pytest.approx(0.7)
    assert warnings == []


def test_summarize_pdf_parse_path_unknown_when_no_confidence_available():
    warnings: list[str] = []

    parse_path, confidence = _summarize_pdf_parse_path(
        [
            ParsedBlock(
                block_id="b1",
                page_no=1,
                block_type="paragraph",
                text="no source",
            )
        ],
        warnings,
    )

    assert parse_path == "unknown"
    assert confidence is None
    assert warnings
