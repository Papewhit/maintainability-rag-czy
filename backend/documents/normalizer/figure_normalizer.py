"""Figure-nearby normalizer — creates FigureAssociations.

For each ParsedFigureAnchor in the document, finds nearby blocks
on the same page using bbox proximity and text-reference matching.
"""

from __future__ import annotations

import re
from typing import Sequence

from backend.documents.normalizer.base import FigureAssociation, NormalizedBlock
from backend.documents.parse_adapter.base import ParsedFigureAnchor

# ── Figure caption number patterns ──

_FIG_REF_PATTERNS = [
    re.compile(r"图\s*[0-9]+[\-－][0-9]+"),   # "图 3-2", "图3-2"
    re.compile(r"Fig\.?\s*[0-9]+[\-－][0-9]+", re.IGNORECASE),  # "Fig.3-2"
    re.compile(r"Figure\s*[0-9]+[\-－][0-9]+", re.IGNORECASE),
]


def _extract_figure_number(caption: str) -> str | None:
    """Extract figure reference number from caption, e.g. '3-2' from '图3-2 主轴承'."""
    for pat in _FIG_REF_PATTERNS:
        m = pat.search(caption)
        if m:
            return m.group(0)
    return None


def _extract_all_figure_numbers(text: str) -> set[str]:
    """Extract ALL figure reference numbers mentioned in *text*."""
    found: set[str] = set()
    for pat in _FIG_REF_PATTERNS:
        for m in pat.finditer(text):
            found.add(m.group(0))
    return found


# ── Figure role inference ──

def _infer_figure_role(caption: str) -> str:
    """Heuristic figure role from caption keywords (spec: schematic/photo/assembly)."""
    cl = caption.lower()
    if any(w in cl for w in ["示意图", "原理", "schematic", "框图", "流程图"]):
        return "schematic"
    if any(w in cl for w in ["照片", "实物", "photo", "图像"]):
        return "photo"
    if any(w in cl for w in ["装配", "爆炸", "分解", "assembly", "总成", "结构"]):
        return "assembly"
    if any(w in cl for w in ["曲线", "chart", "趋势", "分布"]):
        return "chart"
    return "diagram"


# ── Main matching logic ──


def build_figure_associations(
    figures: Sequence[ParsedFigureAnchor],
    blocks: Sequence[NormalizedBlock],
    *,
    nearby_distance: float = 200.0,
    window_size: int = 4,
) -> list[FigureAssociation]:
    """Create FigureAssociations by matching figures to nearby blocks.

    Args:
        figures: Figure anchors from the parse adapter.
        blocks: Normalized blocks (already enriched with section info).
        nearby_distance: Max vertical distance (in doc units) for bbox matching.
        window_size: Number of blocks before/after to check for text references.

    Returns:
        One FigureAssociation per figure.
    """
    associations: list[FigureAssociation] = []

    for figure in figures:
        nearby_ids: list[str] = []
        fig_number = _extract_figure_number(figure.caption)

        # ── Strategy 1: bbox proximity on same page ──
        for block in blocks:
            if block.page_no != figure.page_no:
                continue
            if block.bbox is None or figure.bbox is None:
                continue
            # Vertical distance between figure and block
            # bbox = (x0, x1, top, bottom)
            fig_top = figure.bbox[2]    # top
            fig_bottom = figure.bbox[3]  # bottom
            blk_top = block.bbox[2]
            blk_bottom = block.bbox[3]
            vert_gap = min(
                abs(fig_bottom - blk_top),
                abs(blk_bottom - fig_top),
                abs(fig_top - blk_top),
            )
            if vert_gap <= nearby_distance:
                nearby_ids.append(block.block_id)

        # ── Strategy 2: text reference matching (same/adjacent pages only) ──
        if fig_number:
            # Constrain to same page and adjacent pages (±1)
            allowed_pages = {figure.page_no}
            if figure.page_no > 1:
                allowed_pages.add(figure.page_no - 1)
            allowed_pages.add(figure.page_no + 1)

            for block in blocks:
                if block.block_id in nearby_ids:
                    continue  # already matched by bbox
                if block.page_no not in allowed_pages:
                    continue
                # Window: order_index within ±window_size of blocks already near the figure
                refs = _extract_all_figure_numbers(block.text)
                if fig_number in refs:
                    nearby_ids.append(block.block_id)

        associations.append(
            FigureAssociation(
                figure_id=figure.figure_id,
                caption=figure.caption,
                page_no=figure.page_no,
                nearby_block_ids=nearby_ids,
            )
        )

    return associations
