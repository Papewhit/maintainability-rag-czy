"""Structure Normalizer data classes (Layer 2).

The Normalizer enriches parsed blocks with document structure
information: heading hierarchy, list detection, figure associations.
In M1, only the data classes are defined — the normalization logic
is implemented in M2+.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from backend.documents.parse_adapter.base import ParsedBlock, ParsedDocument


@dataclass(frozen=True)
class NormalizedBlock(ParsedBlock):
    """A ParsedBlock enriched with document-structure metadata.

    Inherits all ParsedBlock fields and adds section hierarchy,
    list positioning, and anchor references.
    """

    # Section hierarchy (populated by heading tree builder in M2).
    section_path: str = ""
    section_title: str = ""

    # Anchor ID for cross-referencing (chapter/section/step anchors).
    anchor_id: str = ""

    # List detection fields (populated by list recogniser in M2).
    list_marker: str | None = None       # e.g. "(1)", "①", "a)", "—"
    list_level: int | None = None        # 0-based nesting depth
    list_item_index: int | None = None   # ordinal within the parent list


@dataclass(frozen=True)
class ListGroup:
    """A contiguous run of same-level list items.

    ListGroups are the atomic unit for step-chain protection:
    a group is never split across chunks unless a single item
    exceeds the token budget.
    """

    group_id: str       # stable ID e.g. "lg_page3_seq2"
    list_level: int     # nesting depth (0 = top-level list)

    items: list[NormalizedBlock] = field(default_factory=list)

    # Parent group for nested lists (None for top-level groups).
    parent_group_id: str | None = None


@dataclass(frozen=True)
class FigureAssociation:
    """A figure and its associated nearby blocks.

    Created during the 'figure-nearby' normalizer pass (M3).
    """

    figure_id: str
    nearby_block_ids: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class NormalizedDocument:
    """The complete output of the Structure Normalizer.

    Wraps the original ParsedDocument and adds all structural
    enrichments computed by the normalizer passes.
    """

    # The original parsed document (reference, not copy).
    parsed: ParsedDocument

    # All blocks with structure metadata added.
    normalized_blocks: list[NormalizedBlock] = field(default_factory=list)

    # Detected list groups across the document.
    list_groups: list[ListGroup] = field(default_factory=list)

    # Figure ↔ nearby-block associations.
    figure_associations: list[FigureAssociation] = field(default_factory=list)

    # Heading tree (concrete type defined in M2 normalizer implementation).
    heading_tree: Any = None
