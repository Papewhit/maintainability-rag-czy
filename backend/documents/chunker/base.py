"""Maintainability Chunker data classes (Layer 3).

The Chunker converts NormalizedDocuments into MaintenanceChunks —
the final unit written to Milvus and the parent chunk store.

In M1, only the data class is defined. Chunking logic is
implemented in M2+ when the MaintainabilityChunker is built.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

ChunkRole = Literal["root", "leaf"]


@dataclass(frozen=True)
class MaintenanceChunk:
    """A chunk ready for indexing and retrieval.

    Every chunk belongs to a parent (root) chunk hierarchy.
    Root chunks hold complete evidence context; leaf chunks
    are the units actually retrieved via Milvus.

    The rich metadata fields (list_group_id, table_id, figure_id,
    entity_types, etc.) power downstream rerank, evidence building,
    and citation formatting.
    """

    # ── Identity ──
    chunk_id: str
    parent_chunk_id: str = ""
    root_chunk_id: str = ""

    # ── Hierarchy ──
    chunk_level: int = 0          # 1=root, 2=mid, 3=leaf
    chunk_role: ChunkRole = "leaf"

    # ── Content ──
    block_type: str = ""           # heading / paragraph / list_item / table / figure
    text: str = ""                 # full evidence text (stored in parent store)
    retrieval_text: str = ""       # leaf-only searchable text (stored in Milvus)

    # ── Section context ──
    section_title: str = ""
    section_path: str = ""         # e.g. "Ch3 > 3.2 > Maintenance Steps"
    anchor_id: str = ""            # cross-reference anchor

    # ── Page range ──
    page_start: int = 0
    page_end: int = 0

    # ── List / step-chain fields ──
    list_group_id: str | None = None
    list_order: int | None = None       # ordinal within the group
    list_marker: str | None = None      # e.g. "(1)", "a)", "Step 3"
    list_level: int | None = None       # nesting depth
    list_complete: bool = True          # False if this chunk is a partial group

    # ── Table fields ──
    table_id: str | None = None
    table_role: str | None = None       # "data" / "parameter" / "catalogue"

    # ── Figure fields ──
    figure_id: str | None = None
    figure_role: str | None = None      # "diagram" / "photo" / "chart"

    # ── Terminology (populated after terminology scanner) ──
    entity_types: list[str] = field(default_factory=list)
    term_match_count: int = 0

    # ── Extended payload (parent store only, not Milvus) ──
    parent_extras: dict[str, Any] = field(default_factory=dict)
