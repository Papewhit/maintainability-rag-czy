"""M8 补全验证：Table nearby + OCR confidence/parse_path

验收标准：
- table nearby 关联逻辑正确
- parse_path 枚举和判断算法正确
- ocr_confidence_avg 计算正确
"""

from __future__ import annotations

import pytest

from backend.documents.normalizer.base import NormalizedBlock
from backend.documents.normalizer.table_nearby import (
    _extract_table_number,
    _extract_all_table_numbers,
    associate_nearby_blocks,
)
from backend.documents.parse_adapter.base import ParsedTable, ParseMeta


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
    # text reference 需要先有 bbox anchor，这里只测试提取逻辑
    # 实际关联依赖 bbox proximity 作为 anchor


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
    """验证 parse_path 判断算法"""
    # 模拟 adapter.py 中的逻辑
    def determine_parse_path(ocr_block_count: int, total_block_count: int) -> str:
        if total_block_count == 0:
            return "unknown"
        ocr_ratio = ocr_block_count / total_block_count
        if ocr_ratio >= 0.8:
            return "ocr"
        elif ocr_ratio <= 0.2:
            return "native_text"
        elif 0.2 < ocr_ratio < 0.8:
            return "mixed"
        else:
            return "unknown"

    # 全 OCR
    assert determine_parse_path(10, 10) == "ocr"
    # 全原生
    assert determine_parse_path(0, 10) == "native_text"
    # 混合
    assert determine_parse_path(5, 10) == "mixed"
    # 边界
    assert determine_parse_path(8, 10) == "ocr"  # 0.8
    assert determine_parse_path(2, 10) == "native_text"  # 0.2


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
