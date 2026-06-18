"""Parse adapter layer — file-type dispatching to document parsers.

Public API:
    ParseAdapter    — structural protocol for parsers
    ParsedDocument  — unified parse output
    AdapterRegistry — extension-based dispatch
    get_registry()  — default registry singleton
    ParseError      — base exception for parse failures
    UnsupportedFileType — raised when no adapter matches
"""

from backend.documents.parse_adapter.base import (
    ParseAdapter,
    ParseError,
    ParsedBlock,
    ParsedDocument,
    ParsedFigureAnchor,
    ParsedTable,
    ParseMeta,
    UnsupportedFileType,
)
from backend.documents.parse_adapter.registry import AdapterRegistry, get_registry

__all__ = [
    "ParseAdapter",
    "ParseError",
    "ParsedBlock",
    "ParsedDocument",
    "ParsedFigureAnchor",
    "ParsedTable",
    "ParseMeta",
    "UnsupportedFileType",
    "AdapterRegistry",
    "get_registry",
]
