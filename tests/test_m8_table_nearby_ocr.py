"""M8 补全验证：Table nearby + OCR confidence/parse_path

验收标准：
- table nearby 关联逻辑正确
- parse_path 枚举和判断算法正确
- ocr_confidence_avg 计算正确
"""

from __future__ import annotations

import os
import time
from pathlib import Path

import numpy as np
import pytest

from backend.documents.normalizer.base import NormalizedBlock
from backend.documents.normalizer.pipeline import run_normalizer
from backend.documents.normalizer.table_nearby import (
    _extract_table_number,
    _extract_all_table_numbers,
    associate_nearby_blocks,
)
from backend.documents.parse_adapter.base import ParsedBlock, ParsedDocument, ParsedTable, ParseMeta
from backend.documents.parse_adapter.converters import parsed_to_chunks
from backend.documents.parse_adapter.deepdoc.adapter import (
    DeepDocAdapter,
    _summarize_pdf_parse_path,
)

ASSETS_DIR = Path(__file__).resolve().parent / "assets"

_MODEL_DIR = os.environ.get("DEEPDOC_MODEL_DIR") or str(
    Path(__file__).resolve().parents[1]
    / "backend"
    / "documents"
    / "parse_adapter"
    / "deepdoc"
    / "models"
)
_REQUIRED_MODELS = ["det.onnx", "rec.onnx", "layout.onnx", "tsr.onnx"]


def _models_available() -> bool:
    model_path = Path(_MODEL_DIR)
    if not model_path.is_dir():
        return False
    return all((model_path / f).exists() for f in _REQUIRED_MODELS)


needs_models_skip = pytest.mark.skipif(
    not _models_available(),
    reason=f"DeepDoc ONNX models not found at {_MODEL_DIR}. Required: {_REQUIRED_MODELS}.",
)


def test_table_number_extraction():
    """验证表格编号提取逻辑"""
    assert _extract_table_number("表 3-2 参数表") == "3-2"
    assert _extract_table_number("Table 5 数据") == "5"
    assert _extract_table_number("表3-2参数表") == "3-2"
    assert _extract_table_number("Table.3-2") == "3-2"
    assert _extract_table_number("无编号") is None


def test_table_number_extraction_from_text():
    """验证从文本中提取所有表格引用"""
    text = "参见表 3-2 和 Table 5 的数据"
    refs = _extract_all_table_numbers(text)
    assert "3-2" in refs
    assert "5" in refs


def test_associate_nearby_blocks_bbox_proximity():
    """验证 bbox proximity 策略"""
    table = ParsedTable(
        table_id="t1",
        page_no=1,
        caption="表 1 参数表",
        cells_markdown="| A | B |\n|---|---|\n| 1 | 2 |",
        bbox=(100, 200, 100, 200),  # x0, x1, top, bottom
    )

    # 同页、靠近表格的 block
    nearby_block = NormalizedBlock(
        block_id="b1",
        page_no=1,
        block_type="paragraph",
        text="这是表格的说明文字",
        bbox=(100, 200, 80, 95),  # 垂直距离 = 5，小于 150
        order_index=0,
    )

    # 同页但距离远的 block
    far_block = NormalizedBlock(
        block_id="b2",
        page_no=1,
        block_type="paragraph",
        text="无关段落",
        bbox=(100, 200, 400, 450),  # 垂直距离 = 200，大于 150
        order_index=1,
    )

    enriched = associate_nearby_blocks([table], [nearby_block, far_block])
    assert len(enriched) == 1
    assert "b1" in enriched[0].nearby_block_ids
    assert "b2" not in enriched[0].nearby_block_ids


def test_associate_nearby_blocks_text_reference():
    """验证 text reference 策略"""
    table = ParsedTable(
        table_id="t1",
        page_no=1,
        caption="表 3-2 参数表",
        cells_markdown="| A | B |",
    )

    # 包含表格引用的 block
    ref_block = NormalizedBlock(
        block_id="b1",
        page_no=1,
        block_type="paragraph",
        text="如表 3-2 所示，参数范围为...",
        order_index=0,
    )

    # 无引用的 block
    no_ref_block = NormalizedBlock(
        block_id="b2",
        page_no=1,
        block_type="paragraph",
        text="其他内容",
        order_index=1,
    )

    enriched = associate_nearby_blocks([table], [ref_block, no_ref_block])
    assert len(enriched) == 1
    assert enriched[0].nearby_block_ids == ["b1"]


def test_associate_nearby_blocks_text_reference_respects_anchor_window():
    """Text references outside the anchored nearby window are ignored."""
    table = ParsedTable(
        table_id="t1",
        page_no=1,
        caption="表 3-2 参数表",
        cells_markdown="| A | B |",
        bbox=(100, 200, 100, 200),
    )
    anchor_block = NormalizedBlock(
        block_id="anchor",
        page_no=1,
        block_type="paragraph",
        text="表格附近说明",
        bbox=(100, 200, 80, 95),
        order_index=10,
    )
    in_window_ref = NormalizedBlock(
        block_id="near_ref",
        page_no=1,
        block_type="paragraph",
        text="如表 3-2 所示。",
        order_index=12,
    )
    out_window_ref = NormalizedBlock(
        block_id="far_ref",
        page_no=1,
        block_type="paragraph",
        text="如表 3-2 所示。",
        order_index=20,
    )

    enriched = associate_nearby_blocks(
        [table],
        [anchor_block, in_window_ref, out_window_ref],
        window_size=3,
    )

    assert enriched[0].nearby_block_ids == ["anchor", "near_ref"]


def test_pipeline_populates_normalized_tables_nearby_blocks():
    """Table nearby association belongs to the normalizer pipeline."""
    doc = ParsedDocument(
        filename="x.pdf",
        file_type="pdf",
        parse_meta=ParseMeta(parse_engine="test"),
        blocks=[
            ParsedBlock(
                block_id="b1",
                page_no=1,
                block_type="paragraph",
                text="表 1 给出了关键参数。",
                bbox=(100, 200, 80, 95),
                order_index=0,
            ),
        ],
        tables=[
            ParsedTable(
                table_id="t1",
                page_no=1,
                caption="表 1 参数表",
                cells_markdown="| A | B |\n|---|---|\n| 1 | 2 |",
                bbox=(100, 200, 100, 200),
            ),
        ],
    )

    normalized = run_normalizer(doc)

    assert normalized.normalized_tables[0].nearby_block_ids == ["b1"]


def test_converter_uses_normalizer_table_nearby_output():
    """Table parent text includes nearby explanatory blocks from normalizer output."""
    doc = ParsedDocument(
        filename="x.pdf",
        file_type="pdf",
        parse_meta=ParseMeta(parse_engine="test"),
        blocks=[
            ParsedBlock(
                block_id="b1",
                page_no=1,
                block_type="paragraph",
                text="表 1 说明了额定压力范围。",
                bbox=(100, 200, 80, 95),
                order_index=0,
            ),
        ],
        tables=[
            ParsedTable(
                table_id="t1",
                page_no=1,
                caption="表 1 参数表",
                cells_markdown="| 参数 | 值 |\n|---|---|\n| 压力 | 10MPa |",
                cells_structured=[["参数", "值"], ["压力", "10MPa"]],
                bbox=(100, 200, 100, 200),
            ),
        ],
    )

    chunks = parsed_to_chunks(doc, "/tmp/x.pdf", profile="v4_full")
    table_roots = [
        c for c in chunks
        if c["block_type"] == "table" and c["chunk_level"] == 1
    ]

    assert table_roots
    assert "表 1 说明了额定压力范围。" in table_roots[0]["text"]
    assert table_roots[0]["parent_extras"]["nearby_block_ids"] == ["b1"]


@pytest.mark.slow
@needs_models_skip
def test_scm_table_pdf_v4_full_populates_table_nearby_blocks():
    """Real SCM table PDF produces table roots enriched with nearby paragraphs."""
    pdf_path = ASSETS_DIR / "节选表格_SCM优化方案.pdf"
    if not pdf_path.exists():
        pytest.skip(f"Sample PDF not found: {pdf_path}")

    doc = DeepDocAdapter().parse(str(pdf_path))
    chunks = parsed_to_chunks(doc, str(pdf_path), profile="v4_full")
    table_roots = [
        c for c in chunks
        if c["block_type"] == "table" and c["chunk_level"] == 1
    ]
    table5_root = next(c for c in table_roots if "表5" in c["text"])

    assert table5_root["parent_extras"]["nearby_block_ids"]
    assert "<table><caption>表5" in table5_root["text"]
    assert "节点关键属性定义如表5 所示" in table5_root["text"]


def test_parse_meta_parse_path():
    """验证 parse_path 字段"""
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
    """验证真实 parse_path 判断算法"""

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
    """DeepDoc line tags carry score/source into ParsedBlock metadata."""
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
    """DeepDoc HTML table captions are promoted without changing table HTML."""
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
    """DeepDoc HTML table rows are mapped into ParsedTable.cells_structured."""
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
    """HTML span attributes keep rows rectangular without horizontal text bloat."""
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
    """DeepDoc positioned table items populate bbox from the first table region."""
    html = (
        "<table><caption>表6 统一源图边关键属性定义</caption>"
        "<tr><td>A</td></tr></table>"
    )
    positioned_item = ((None, html), [(0, 12.5, 240.0, 32.0, 98.5)])

    tables, _ = DeepDocAdapter._convert_tables_figures([positioned_item])

    assert tables[0].page_no == 1
    assert tables[0].bbox == (12.5, 240.0, 32.0, 98.5)


def test_deepdoc_convert_tables_accepts_numpy_position_scalars():
    """Real DeepDoc positions may contain NumPy scalar coordinates."""
    html = "<table><caption>表6 统一源图边关键属性定义</caption><tr><td>A</td></tr></table>"
    positioned_item = (
        (None, html),
        [(np.int64(0), np.float32(12.5), np.float64(240.0), np.float32(32.0), np.float64(98.5))],
    )

    tables, _ = DeepDocAdapter._convert_tables_figures([positioned_item])

    assert tables[0].caption == "表6 统一源图边关键属性定义"
    assert tables[0].bbox == (12.5, 240.0, 32.0, 98.5)


def test_deepdoc_convert_tables_leaves_bbox_none_without_position():
    """DeepDoc table conversion degrades cleanly when no position is available."""
    tables, _ = DeepDocAdapter._convert_tables_figures(
        [(None, "<table><caption>表7 字段定义</caption><tr><td>A</td></tr></table>")]
    )

    assert tables[0].caption == "表7 字段定义"
    assert tables[0].bbox is None


def test_deepdoc_convert_tables_uses_only_explicit_non_html_caption():
    """Non-HTML content is not guessed as a caption unless DeepDoc provides one."""
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
    """The PDF adapter requests DeepDoc table positions for nearby anchoring."""
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
    """parse_path counts converted ParsedBlocks, not raw parser boxes."""
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


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
