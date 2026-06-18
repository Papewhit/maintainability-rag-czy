"""Structure normalizer layer — enriches parsed blocks with document structure.

Public API:
    NormalizedBlock     — ParsedBlock + section/list/heading metadata
    ListGroup           — contiguous run of same-level list items
    FigureAssociation   — figure ↔ nearby-block links
    NormalizedDocument  — full normalizer output
"""

from backend.documents.normalizer.base import (
    FigureAssociation,
    ListGroup,
    NormalizedBlock,
    NormalizedDocument,
)

__all__ = [
    "FigureAssociation",
    "ListGroup",
    "NormalizedBlock",
    "NormalizedDocument",
]
