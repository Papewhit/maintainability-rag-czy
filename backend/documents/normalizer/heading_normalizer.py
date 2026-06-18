"""Heading tree builder — ports section-hierarchy logic from DocumentLoader.

Enriches NormalizedBlocks with section_path, section_title, and anchor_id.
Builds a nested heading_tree dict for downstream optional use.
"""

from __future__ import annotations

import re
from typing import Any

from backend.documents.normalizer.base import NormalizedBlock

# ── Patterns (from loader.py) ──

_ARTICLE_PATTERN = re.compile(
    r"^第[一二三四五六七八九十百千万零两0-9]+[编章节条部分款项]\s*"
)
_DECIMAL_PATTERN = re.compile(r"^\d+(?:\.\d+){0,4}\s+\S+")
_LIST_PATTERN = re.compile(r"^[一二三四五六七八九十]+、\s*\S+")
_PAREN_LIST_PATTERN = re.compile(r"^[（(][一二三四五六七八九十0-9A-Za-z]+[)）]\s*\S+")
_ANCHOR_PATTERN = re.compile(
    r"(第[一二三四五六七八九十百千万零两0-9]+[编章节条部分款项]|"
    r"\d+(?:\.\d+){1,4}|"
    r"[一二三四五六七八九十]+、|"
    r"[（(][一二三四五六七八九十0-9A-Za-z]+[)）]|"
    r"附录[A-Za-z0-9一二三四五六七八九十]+|"
    r"附件[0-9一二三四五六七八九十]+)"
)


def _normalize_title(value: str | None) -> str:
    text = re.sub(r"\s+", " ", (value or "").strip())
    return text.strip(" -:：|")


def _heading_depth(line: str) -> int:
    """Port of DocumentLoader._heading_depth()."""
    normalized = _normalize_title(line)
    if not normalized:
        return 0
    if _ARTICLE_PATTERN.match(normalized):
        if "编" in normalized or "部分" in normalized or "章" in normalized:
            return 1
        if "节" in normalized:
            return 2
        return 3
    match = re.match(r"^(\d+(?:\.\d+){0,4})\s+\S+", normalized)
    if match:
        return match.group(1).count(".") + 1
    if _LIST_PATTERN.match(normalized):
        return 1
    if _PAREN_LIST_PATTERN.match(normalized):
        return 2
    return 0


def _is_heading(line: str) -> bool:
    """True if *line* looks like a section heading."""
    normalized = _normalize_title(line)
    if not normalized or len(normalized) > 80:
        return False
    return _heading_depth(normalized) > 0


def _extract_anchor_id(title: str | None) -> str:
    normalized = _normalize_title(title)
    if not normalized:
        return ""
    match = _ANCHOR_PATTERN.search(normalized)
    return match.group(0) if match else ""


def build_heading_tree(
    blocks: list[NormalizedBlock],
) -> tuple[list[NormalizedBlock], dict[str, Any]]:
    """Enrich blocks with section_path, section_title, anchor_id.

    Returns (enriched_blocks, heading_tree).
    """
    enriched: list[NormalizedBlock] = []
    heading_stack: dict[int, str] = {}  # depth → heading_text
    section_meta: dict[str, Any] = {"_blocks": []}
    tree_cursor = section_meta

    for block in blocks:
        text_head = block.text.strip().split("\n")[0].strip()
        is_heading_block = block.block_type == "heading" or (
            block.block_type == "paragraph" and _is_heading(text_head)
        )
        depth = _heading_depth(text_head) if is_heading_block else 0

        section_path = ""
        section_title = ""
        anchor_id = block.anchor_id

        if depth > 0:
            # Prune stack: remove entries at or deeper than current depth
            heading_stack = {k: v for k, v in heading_stack.items() if k < depth}
            heading_stack[depth] = text_head

            # Build section_path from sorted stack
            section_path = " > ".join(
                heading_stack[i] for i in sorted(heading_stack)
            )
            section_title = text_head
            anchor_id = anchor_id or _extract_anchor_id(text_head)

            # Update heading_tree
            tree_cursor = section_meta
            for i in sorted(heading_stack):
                key = heading_stack[i]
                if key not in tree_cursor:
                    tree_cursor[key] = {"_blocks": []}
                tree_cursor = tree_cursor[key]
        else:
            # Body line: inherit section context from stack
            if heading_stack:
                section_path = " > ".join(
                    heading_stack[i] for i in sorted(heading_stack)
                )
                # Current section title = deepest heading
                section_title = heading_stack[max(heading_stack)]
            tree_cursor.setdefault("_blocks", []).append(block.block_id)

        # Create enriched block (frozen → use __dict__ + rebuild)
        enriched_block = NormalizedBlock(
            block_id=block.block_id,
            page_no=block.page_no,
            block_type=block.block_type,
            text=block.text,
            bbox=block.bbox,
            ocr_confidence=block.ocr_confidence,
            order_index=block.order_index,
            style=dict(block.style),
            section_path=section_path,
            section_title=section_title,
            anchor_id=anchor_id,
            list_marker=block.list_marker,
            list_level=block.list_level,
            list_item_index=block.list_item_index,
        )
        enriched.append(enriched_block)

    return enriched, section_meta
