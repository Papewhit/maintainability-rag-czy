"""Table-nearby normalizer — associates tables with explanatory blocks.

For each ParsedTable, finds nearby blocks on the same page using
bbox proximity and text-reference matching (similar to figure_normalizer
but with tighter thresholds).
"""

from __future__ import annotations

import re
from typing import Sequence

from backend.documents.normalizer.base import NormalizedBlock
from backend.documents.parse_adapter.base import ParsedTable

# ── Table caption number patterns ──

_TABLE_REF_PATTERNS = [
    re.compile(r"表\s*[0-9]+[\-－][0-9]+"),   # "表 3-2", "表3-2"
    re.compile(r"Table\.?\s*[0-9]+[\-－][0-9]+", re.IGNORECASE),  # "Table.3-2"
    re.compile(r"表\s*[0-9]+"),  # "表 3"
    re.compile(r"Table\.?\s*[0-9]+", re.IGNORECASE),  # "Table 3"
]


def _normalize_table_number(raw: str) -> str:
    """Normalize table ref to a common key, e.g. '表 3-2' → '3-2'.

    This ensures "表3-2" and "表 3-2" are treated as the same reference.
    """
    m = re.search(r"([0-9]+)[\-－]([0-9]+)", raw)
    if m:
        return f"{m.group(1)}-{m.group(2)}"
    m = re.search(r"([0-9]+)", raw)
    if m:
        return m.group(1)
    return raw


def _extract_table_number(caption: str) -> str | None:
    """Extract normalized table number, e.g. '表 3-2' → '3-2'."""
    for pat in _TABLE_REF_PATTERNS:
        m = pat.search(caption)
        if m:
            return _normalize_table_number(m.group(0))
    return None


def _extract_all_table_numbers(text: str) -> set[str]:
    """Extract all normalized table reference numbers."""
    found: set[str] = set()
    for pat in _TABLE_REF_PATTERNS:
        for m in pat.finditer(text):
            found.add(_normalize_table_number(m.group(0)))
    return found


def _compute_vertical_gap(
    table_bbox: tuple[float, float, float, float],
    block_bbox: tuple[float, float, float, float],
) -> float:
    """Compute minimum vertical distance between table and block.

    bbox format: (x0, x1, top, bottom)
    """
    tbl_top, tbl_bottom = table_bbox[2], table_bbox[3]
    blk_top, blk_bottom = block_bbox[2], block_bbox[3]
    return min(
        abs(tbl_bottom - blk_top),
        abs(blk_bottom - tbl_top),
        abs(tbl_top - blk_top),
    )


# ── Main matching logic ──


def associate_nearby_blocks(
    tables: Sequence[ParsedTable],
    blocks: Sequence[NormalizedBlock],
    *,
    nearby_distance: float = 150.0,
    window_size: int = 3,
) -> list[ParsedTable]:
    """Associate tables with nearby explanatory blocks.

    Similar to figure nearby matching but with tighter distance threshold
    (150 vs 200 for figures) and smaller window (3 vs 4 for figures).

    Args:
        tables: Parsed tables from the parse adapter.
        blocks: Normalized blocks (already enriched with section info).
        nearby_distance: Max vertical distance (in doc units) for bbox matching.
        window_size: Number of blocks before/after to check for text references.

    Returns:
        Enriched tables with nearby_block_ids populated.
    """
    enriched: list[ParsedTable] = []

    for table in tables:
        nearby_ids: list[str] = []
        table_number = _extract_table_number(table.caption)

        # ── Strategy 1: bbox proximity on same page ──
        for block in blocks:
            if block.page_no != table.page_no:
                continue
            if block.bbox is None or table.bbox is None:
                continue
            vert_gap = _compute_vertical_gap(table.bbox, block.bbox)
            if vert_gap <= nearby_distance:
                nearby_ids.append(block.block_id)

        # ── Strategy 2: text reference matching (same/adjacent pages + order window) ──
        if table_number:
            # Constrain to same page and adjacent pages (±1)
            allowed_pages = {table.page_no}
            if table.page_no > 1:
                allowed_pages.add(table.page_no - 1)
            allowed_pages.add(table.page_no + 1)

            # Anchor the window on bbox-matched blocks (Strategy 1 results).
            # If no bbox anchor exists, skip the order window entirely.
            anchor_orders = [
                b.order_index for b in blocks
                if b.block_id in nearby_ids
            ]
            use_window = len(anchor_orders) > 0
            anchor = sorted(anchor_orders)[len(anchor_orders) // 2] if use_window else 0

            for block in blocks:
                if block.block_id in nearby_ids:
                    continue  # already matched by bbox
                if block.page_no not in allowed_pages:
                    continue
                # Within ±window_size of the bbox-anchor in reading order
                if use_window and abs(block.order_index - anchor) > window_size:
                    continue
                refs = _extract_all_table_numbers(block.text)
                if table_number in refs:
                    nearby_ids.append(block.block_id)

        enriched.append(
            ParsedTable(
                table_id=table.table_id,
                page_no=table.page_no,
                caption=table.caption,
                cells_markdown=table.cells_markdown,
                cells_structured=table.cells_structured,
                bbox=table.bbox,
                nearby_block_ids=nearby_ids,
            )
        )

    return enriched
