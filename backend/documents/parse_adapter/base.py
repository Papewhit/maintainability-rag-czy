"""ParseAdapter protocol and output data classes.

Layer 1 of the parse → normalize → chunk pipeline.
Every parser produces a ParsedDocument — the stable contract
that downstream layers consume.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, Protocol

# ---------------------------------------------------------------------------
# Block type — granular unit within a page
# ---------------------------------------------------------------------------

BlockType = Literal[
    "heading",
    "paragraph",
    "list_item",
    "table_caption",
    "figure_caption",
    "footnote",
]


@dataclass(frozen=True)
class ParsedBlock:
    """A single text block extracted from a page.

    Every block carries its page position and extraction confidence
    so that downstream normalizers and chunkers can make informed
    structural decisions.
    """

    block_id: str
    page_no: int
    block_type: BlockType
    text: str

    # Position on the page (x0, x1, top, bottom) in document-native units.
    # None when the source format does not provide positional data.
    bbox: tuple[float, float, float, float] | None = None

    # OCR confidence for blocks sourced from image-based PDFs.
    # None for native-text formats (docx, html, etc.).
    ocr_confidence: float | None = None

    # Reading order within the page.
    order_index: int = 0

    # Source-specific metadata: font name, font size, bold/italic, colour, etc.
    style: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Table — extracted tabular data
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ParsedTable:
    """A table extracted from the document.

    Tables carry dual representations: cells_markdown for LLM consumption
    and cells_structured for programmatic access. Both are derived from the
    same underlying extraction.
    """

    table_id: str
    page_no: int

    # Table caption / title, if detected.
    caption: str = ""

    # Markdown table representation — ready for LLM context injection.
    cells_markdown: str = ""

    # Structured cells as row-major 2-D list. Empty cells are "".
    cells_structured: list[list[str]] = field(default_factory=list)

    # Page position.
    bbox: tuple[float, float, float, float] | None = None

    # IDs of ParsedBlocks that appear near this table (same page,
    # small vertical gap). Used for contextual enrichment.
    nearby_block_ids: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Figure anchor — image / diagram reference
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ParsedFigureAnchor:
    """A figure (image, diagram, chart) detected in the document.

    Figures are *anchors* — the actual image data is not stored here.
    The caption and nearby block IDs provide enough context to include
    the figure's content in retrieval results.
    """

    figure_id: str
    page_no: int

    # Figure caption, if detected.
    caption: str = ""

    # Page position.
    bbox: tuple[float, float, float, float] | None = None

    # IDs of blocks near this figure — typically the caption paragraph
    # and immediately preceding / following text.
    nearby_block_ids: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Parse metadata — diagnostics and observability
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ParseMeta:
    """Parse-level diagnostics.

    Every parse operation records its engine, version, duration, and
    any warnings encountered. This data feeds into document management
    APIs and trace / debug views.
    """

    parse_engine: str
    parse_engine_version: str = ""
    parse_duration_ms: float = 0.0
    total_pages: int = 0
    parse_warnings: list[str] = field(default_factory=list)

    # Aggregate OCR quality signal (if applicable).
    ocr_confidence_avg: float | None = None

    # Proportion of watermark-like tokens filtered during parsing.
    watermark_filter_ratio: float | None = None

    # Warnings from heading tree validation (M6).
    hierarchy_validation_warnings: list[str] = field(default_factory=list)

    # M8: Parse path - distinguishes native text vs OCR extraction.
    # Values: "native_text" | "ocr" | "mixed" | "unknown"
    parse_path: str | None = None


# ---------------------------------------------------------------------------
# ParsedDocument — the unified parse output
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ParsedDocument:
    """Complete output of a ParseAdapter.

    A ParsedDocument is filename-keyed and carries all blocks, tables,
    and figure anchors extracted from a single source document.
    """

    filename: str
    file_type: str  # e.g. "pdf", "docx", "xlsx"
    parse_meta: ParseMeta

    blocks: list[ParsedBlock] = field(default_factory=list)
    tables: list[ParsedTable] = field(default_factory=list)
    figures: list[ParsedFigureAnchor] = field(default_factory=list)


# ---------------------------------------------------------------------------
# ParseAdapter protocol — structural typing (no ABC)
# ---------------------------------------------------------------------------


class ParseAdapter(Protocol):
    """Structural protocol for document parsers.

    Any object with a ``parse(file_path) -> ParsedDocument`` method
    satisfies this protocol — no explicit inheritance required.

    Parsers are expected to be stateless across calls. Heavyweight
    resources (ML models) may be initialised once in ``__init__``
    and reused across ``parse()`` invocations.
    """

    def parse(self, file_path: str) -> ParsedDocument:
        """Parse a document file and return structured output.

        Args:
            file_path: Absolute path to the source document.

        Returns:
            ParsedDocument with blocks, tables, figures, and metadata.

        Raises:
            ParseError: The document cannot be parsed at all
                (corrupted file, unsupported encryption, etc.).
        """
        ...


# ---------------------------------------------------------------------------
# Error hierarchy
# ---------------------------------------------------------------------------


class ParseError(Exception):
    """Raised when a document cannot be parsed."""


class UnsupportedFileType(ParseError):
    """Raised when no adapter is registered for a file extension."""
