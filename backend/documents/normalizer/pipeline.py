"""Normalizer pipeline — orchestrates heading and list passes.

ParsedDocument → heading_normalizer → list_normalizer → NormalizedDocument
"""

from __future__ import annotations

from backend.documents.normalizer.base import NormalizedBlock, NormalizedDocument
from backend.documents.normalizer.heading_normalizer import build_heading_tree
from backend.documents.normalizer.list_normalizer import detect_and_group_lists
from backend.documents.parse_adapter.base import ParsedDocument


def run_normalizer(doc: ParsedDocument) -> NormalizedDocument:
    """Convert a ParsedDocument into a NormalizedDocument.

    Applies two passes:
    1. Heading tree — enriches section_path, section_title, anchor_id
    2. List detection — extracts markers, infers levels, aggregates groups
    """
    # Convert ParsedBlocks → NormalizedBlocks (copy)
    normalized: list[NormalizedBlock] = [
        NormalizedBlock(
            block_id=b.block_id,
            page_no=b.page_no,
            block_type=b.block_type,
            text=b.text,
            bbox=b.bbox,
            ocr_confidence=b.ocr_confidence,
            order_index=b.order_index,
            style=dict(b.style),
        )
        for b in doc.blocks
    ]

    # Pass 1: heading tree
    normalized, heading_tree = build_heading_tree(normalized)

    # Pass 2: list detection + grouping
    normalized, list_groups = detect_and_group_lists(normalized)

    return NormalizedDocument(
        parsed=doc,
        normalized_blocks=normalized,
        list_groups=list_groups,
        heading_tree=heading_tree,
    )
