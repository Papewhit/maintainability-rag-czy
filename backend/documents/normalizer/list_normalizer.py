"""List-item detector and ListGroup aggregator.

Two passes over NormalizedBlocks:
  Pass 1 — extract list markers, re-classify paragraphs as list_items
  Pass 2 — infer list_level, aggregate consecutive same-level items into ListGroups
"""

from __future__ import annotations

import re
from statistics import median
from typing import Sequence

from backend.documents.normalizer.base import ListGroup, NormalizedBlock

# ── List marker patterns (unioned from DeepDoc _match_proj + adapter classifier) ──

_LIST_MARKER_PATTERNS: list[tuple[str, int]] = [
    # (regex, base_level) — base_level is the default nesting depth
    # Chinese article / section (highest level)
    (r"^第[零一二三四五六七八九十百\d]+[章节条]", 0),
    # Chinese ordinal + separator
    (r"^[零一二三四五六七八九十百]+[、]", 0),
    # Parenthesized: (1) （一） (a) (iv)
    (r"^[\(（][零一二三四五六七八九十百\d]+[）\)]\s*", 1),
    (r"^[\(（][a-zA-Z]{1,2}[）\)]\s*", 2),
    # Multi-level numbers: 1.1  or 1.1.1
    (r"^\d+\.\d+(?:\.\d+)?\s+", 1),
    # Single number + separator: 1、 1. 1） 1)
    (r"^\d+[、.\)]\s*", 1),
    # Roman numerals
    (r"^[ivxlcdm]+[.\)]\s*", 2),
    # Single letter: a) b.
    (r"^[a-zA-Z][.\)]\s*", 2),
    # Bullet / dingbat characters
    (r"^[⚫•➢✓⚠※●○①②③➀➁➂]\s*", 1),
]

_LIST_MARKER_RE = re.compile("|".join(f"({p})" for p, _ in _LIST_MARKER_PATTERNS))


def extract_list_marker(text: str) -> tuple[str | None, str]:
    """Extract list marker from the beginning of *text*.

    Returns (marker, rest) where *marker* is the matched prefix or None.
    """
    m = _LIST_MARKER_RE.match(text.strip())
    if m:
        marker = m.group(0).strip()
        rest = text.strip()[m.end():].strip()
        return marker, rest
    return None, text.strip()


def _base_level_for_marker(marker: str) -> int:
    """Return the default base level for a given marker string."""
    for pattern, level in _LIST_MARKER_PATTERNS:
        if re.match(pattern, marker):
            return level
    return 2  # deepest fallback


# ── Maintenance action words (step boundary signals for M3.5) ──

_MAINTENANCE_ACTIONS = {
    "拆卸", "检查", "更换", "安装", "复验", "调试", "校准",
    "清理", "润滑", "紧固", "调整", "更换件", "备件",
    "分解", "组装", "测试", "测量", "记录", "确认",
    "拆解", "修复", "替换", "接通", "断开", "标记",
}


def _starts_with_maintenance_action(text: str) -> bool:
    """True if *text* begins with a maintenance action keyword."""
    head = text.strip()[:8]
    return any(head.startswith(w) for w in _MAINTENANCE_ACTIONS)


# ── Main processing ──


def detect_and_group_lists(
    blocks: list[NormalizedBlock],
) -> tuple[list[NormalizedBlock], list[ListGroup]]:
    """Detect list items, infer levels, and aggregate into ListGroups.

    Returns (enriched_blocks, list_groups).
    """
    if not blocks:
        return [], []

    # ── Pass 1: extract markers, re-classify paragraphs ──
    enriched: list[NormalizedBlock] = []
    marker_map: dict[int, str | None] = {}  # block_idx → marker
    last_list_idx = -99

    for i, block in enumerate(blocks):
        marker = None
        bt = block.block_type

        if bt in ("list_item",):
            marker, _ = extract_list_marker(block.text)
        elif bt == "paragraph":
            marker, rest = extract_list_marker(block.text)
            if marker:
                # Re-classify as list_item if it follows a list or stands alone
                if (i - last_list_idx <= 2) or len(rest) <= 120:
                    bt = "list_item"  # type: ignore[assignment]
                    last_list_idx = i

        if marker:
            last_list_idx = i
        marker_map[i] = marker

        # Rebuild block with updated block_type
        enriched.append(
            NormalizedBlock(
                block_id=block.block_id,
                page_no=block.page_no,
                block_type=bt,  # type: ignore[arg-type]
                text=block.text,
                bbox=block.bbox,
                ocr_confidence=block.ocr_confidence,
                order_index=block.order_index,
                style=dict(block.style),
                section_path=block.section_path,
                section_title=block.section_title,
                anchor_id=block.anchor_id,
                list_marker=marker,
                list_level=None,
                list_item_index=None,
            )
        )

    # ── Pass 2: infer list_level using bbox indentation ──
    # Group by page for per-page indentation analysis
    page_blocks: dict[int, list[tuple[int, NormalizedBlock]]] = {}
    for i, block in enumerate(enriched):
        if block.list_marker:
            page_blocks.setdefault(block.page_no, []).append((i, block))

    level_map: dict[int, int] = {}  # block_idx → inferred level

    for _page, items in page_blocks.items():
        if len(items) < 2:
            for idx, blk in items:
                level_map[idx] = _base_level_for_marker(blk.list_marker or "")
            continue

        x0_values = [blk.bbox[0] for _, blk in items if blk.bbox]
        if not x0_values:
            for idx, blk in items:
                level_map[idx] = _base_level_for_marker(blk.list_marker or "")
            continue

        med_x0 = median(x0_values)
        threshold = 15.0  # minimum x-offset to count as indentation

        for idx, blk in items:
            base = _base_level_for_marker(blk.list_marker or "")
            if blk.bbox and blk.bbox[0] > med_x0 + threshold:
                # Indented further → deeper level
                level_map[idx] = base + 1
            else:
                level_map[idx] = base

    # ── Pass 3: aggregate consecutive same-level list items into ListGroups ──
    groups: list[ListGroup] = []
    group_seq_by_level: dict[int, int] = {}
    current_group_items: list[NormalizedBlock] = []
    current_level: int | None = None
    current_page: int | None = None

    def _flush_group() -> None:
        nonlocal current_group_items, current_level, current_page
        if not current_group_items:
            return
        lvl = current_level or 0
        pg = current_page or 0
        seq = group_seq_by_level.get(lvl, 0)
        group_seq_by_level[lvl] = seq + 1

        group_id = f"lg_p{pg}_l{lvl}_s{seq}"
        # Assign list_item_index within group
        for gi, gb in enumerate(current_group_items):
            gb_idx = next(i for i, b in enumerate(enriched) if b.block_id == gb.block_id)
            enriched[gb_idx] = NormalizedBlock(
                block_id=gb.block_id, page_no=gb.page_no,
                block_type=gb.block_type, text=gb.text,
                bbox=gb.bbox, ocr_confidence=gb.ocr_confidence,
                order_index=gb.order_index, style=dict(gb.style),
                section_path=gb.section_path, section_title=gb.section_title,
                anchor_id=gb.anchor_id,
                list_marker=gb.list_marker,
                list_level=gb.list_level,
                list_item_index=gi,
            )
            current_group_items[gi] = enriched[gb_idx]

        groups.append(
            ListGroup(
                group_id=group_id,
                list_level=lvl,
                items=list(current_group_items),
            )
        )
        current_group_items = []
        current_level = None
        current_page = None

    # Write levels into enriched blocks and aggregate
    final_enriched: list[NormalizedBlock] = []
    for i, block in enumerate(enriched):
        if block.list_marker and i in level_map:
            lvl = level_map[i]
            block = NormalizedBlock(
                block_id=block.block_id, page_no=block.page_no,
                block_type=block.block_type, text=block.text,
                bbox=block.bbox, ocr_confidence=block.ocr_confidence,
                order_index=block.order_index, style=dict(block.style),
                section_path=block.section_path, section_title=block.section_title,
                anchor_id=block.anchor_id,
                list_marker=block.list_marker,
                list_level=lvl,
                list_item_index=None,
            )

        # Determine if this block continues the current group
        if block.block_type == "list_item" and block.list_marker:
            blk_level = block.list_level if block.list_level is not None else 0
            # Break group on: level change, page change (if bbox-based), heading interruption
            if (current_level is not None and blk_level != current_level):
                _flush_group()
            if current_group_items:
                # Check for heading/non-list interruption
                prev_block = current_group_items[-1]
                if block.order_index - prev_block.order_index > 5:
                    _flush_group()
            current_group_items.append(block)
            current_level = blk_level
            current_page = block.page_no
        else:
            _flush_group()

        final_enriched.append(block)

    _flush_group()
    return final_enriched, groups
