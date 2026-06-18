"""Structure normalizer layer — enriches parsed blocks with document structure.

Public API:
    NormalizedBlock     — ParsedBlock + section/list/heading metadata
    ListGroup           — contiguous run of same-level list items
    FigureAssociation   — figure ↔ nearby-block links
    NormalizedDocument  — full normalizer output
    run_normalizer      — pipeline: ParsedDocument → NormalizedDocument
"""

from backend.documents.normalizer.base import (
    FigureAssociation,
    ListGroup,
    NormalizedBlock,
    NormalizedDocument,
)
from backend.documents.normalizer.pipeline import run_normalizer

__all__ = [
    "FigureAssociation",
    "ListGroup",
    "NormalizedBlock",
    "NormalizedDocument",
    "run_normalizer",
]
