"""Normalizer pipeline — orchestration.

ParsedDocument → heading → list → figure → table → NormalizedDocument
"""

from __future__ import annotations

from backend.documents.normalizer.base import NormalizedBlock, NormalizedDocument
from backend.documents.normalizer.heading_normalizer import build_heading_tree
from backend.documents.normalizer.list_normalizer import detect_and_group_lists
from backend.documents.normalizer.figure_normalizer import build_figure_associations
from backend.documents.normalizer.table_normalizer import validate_and_enrich_tables
from backend.documents.parse_adapter.base import ParsedDocument, ParsedTable


def run_normalizer(doc: ParsedDocument) -> NormalizedDocument:
    """Convert a ParsedDocument into a NormalizedDocument.

    Passes:
    1. Heading tree — section_path, section_title, anchor_id
    2. List detection — markers, levels, groups
    3. Figure nearby — associations
    4. Table validation — markdown fallback, row/col check
    """
    normalized: list[NormalizedBlock] = [
        NormalizedBlock(
            block_id=b.block_id, page_no=b.page_no, block_type=b.block_type,
            text=b.text, bbox=b.bbox, ocr_confidence=b.ocr_confidence,
            order_index=b.order_index, style=dict(b.style),
        )
        for b in doc.blocks
    ]

    normalized, heading_tree = build_heading_tree(normalized)
    normalized, list_groups = detect_and_group_lists(normalized)
    figure_associations = build_figure_associations(doc.figures, normalized)

    return NormalizedDocument(
        parsed=doc,
        normalized_blocks=normalized,
        list_groups=list_groups,
        figure_associations=figure_associations,
        heading_tree=heading_tree,
    )
