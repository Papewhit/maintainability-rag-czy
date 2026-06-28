"""Tests for table nearby association in the structure normalizer."""

from __future__ import annotations

from backend.documents.normalizer.base import NormalizedBlock
from backend.documents.normalizer.pipeline import run_normalizer
from backend.documents.normalizer.table_nearby import (
    _extract_all_table_numbers,
    _extract_table_number,
    associate_nearby_blocks,
)
from backend.documents.parse_adapter.base import ParsedBlock, ParsedDocument, ParsedTable, ParseMeta
from backend.documents.parse_adapter.converters import parsed_to_chunks


def test_table_number_extraction():
    assert _extract_table_number("表 3-2 参数表") == "3-2"
    assert _extract_table_number("Table 5 数据") == "5"
    assert _extract_table_number("表3-2参数表") == "3-2"
    assert _extract_table_number("Table.3-2") == "3-2"
    assert _extract_table_number("无编号") is None


def test_table_number_extraction_from_text():
    refs = _extract_all_table_numbers("参见表 3-2 和 Table 5 的数据")
    assert "3-2" in refs
    assert "5" in refs


def test_associate_nearby_blocks_bbox_proximity():
    table = ParsedTable(
        table_id="t1",
        page_no=1,
        caption="表 1 参数表",
        cells_markdown="| A | B |\n|---|---|\n| 1 | 2 |",
        bbox=(100, 200, 100, 200),
    )
    nearby_block = NormalizedBlock(
        block_id="b1",
        page_no=1,
        block_type="paragraph",
        text="这是表格的说明文字",
        bbox=(100, 200, 80, 95),
        order_index=0,
    )
    far_block = NormalizedBlock(
        block_id="b2",
        page_no=1,
        block_type="paragraph",
        text="无关段落",
        bbox=(100, 200, 400, 450),
        order_index=1,
    )

    enriched = associate_nearby_blocks([table], [nearby_block, far_block])

    assert len(enriched) == 1
    assert "b1" in enriched[0].nearby_block_ids
    assert "b2" not in enriched[0].nearby_block_ids


def test_associate_nearby_blocks_text_reference():
    table = ParsedTable(
        table_id="t1",
        page_no=1,
        caption="表 3-2 参数表",
        cells_markdown="| A | B |",
    )
    ref_block = NormalizedBlock(
        block_id="b1",
        page_no=1,
        block_type="paragraph",
        text="如表 3-2 所示，参数范围为...",
        order_index=0,
    )
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
        chunk
        for chunk in chunks
        if chunk["block_type"] == "table" and chunk["chunk_level"] == 1
    ]

    assert table_roots
    assert "表 1 说明了额定压力范围。" in table_roots[0]["text"]
    assert table_roots[0]["parent_extras"]["nearby_block_ids"] == ["b1"]
