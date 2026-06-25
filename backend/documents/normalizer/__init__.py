"""Structure normalizer layer — enriches parsed blocks with document structure.

Public API:
    NormalizedBlock     — ParsedBlock + section/list/heading metadata
    ListGroup           — contiguous run of same-level list items
    FigureAssociation   — figure ↔ nearby-block links
    NormalizedDocument  — full normalizer output
    run_normalizer      — pipeline: ParsedDocument → NormalizedDocument
    associate_nearby_blocks — table ↔ nearby-block matching (M8)
"""

from backend.documents.normalizer.base import (
    FigureAssociation,
    ListGroup,
    NormalizedBlock,
    NormalizedDocument,
)
from backend.documents.normalizer.pipeline import run_normalizer
from backend.documents.normalizer.table_nearby import associate_nearby_blocks

__all__ = [
    "FigureAssociation",
    "ListGroup",
    "NormalizedBlock",
    "NormalizedDocument",
    "run_normalizer",
    "associate_nearby_blocks",
]
