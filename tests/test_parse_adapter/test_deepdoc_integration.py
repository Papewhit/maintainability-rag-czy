"""Integration tests for DeepDocAdapter against real sample documents.

These tests require:
1. DeepDoc ONNX models (set ``DEEPDOC_MODEL_DIR`` or copy to the
   default ``backend/documents/parse_adapter/deepdoc/models/``).
2. Sample documents in ``tests/assets/``.

Run with:
    uv run pytest tests/test_parse_adapter/test_deepdoc_integration.py -v
Skip in CI with:
    uv run pytest tests/ -v -m "not slow"
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Determine if DeepDoc models are available
# ---------------------------------------------------------------------------

ASSETS_DIR = Path(__file__).resolve().parents[1] / "assets"

_MODEL_DIR = os.environ.get("DEEPDOC_MODEL_DIR") or str(
    Path(__file__).resolve().parents[2]
    / "backend" / "documents" / "parse_adapter" / "deepdoc" / "models"
)

_REQUIRED_MODELS = ["det.onnx", "rec.onnx", "layout.onnx", "tsr.onnx"]


def _models_available() -> bool:
    """True if the model directory exists and contains required ONNX files."""
    model_path = Path(_MODEL_DIR)
    if not model_path.is_dir():
        return False
    return all((model_path / f).exists() for f in _REQUIRED_MODELS)


_has_models = _models_available()
slow = pytest.mark.slow

needs_models_skip = pytest.mark.skipif(
    not _has_models,
    reason=(
        f"DeepDoc ONNX models not found at {_MODEL_DIR}. "
        f"Required: {_REQUIRED_MODELS}. "
        f"Set DEEPDOC_MODEL_DIR to the model directory."
    ),
)


def _ensure_nltk() -> None:
    """Download NLTK data if missing."""
    try:
        import nltk
        for pkg, kind in [("punkt_tab", "tokenizers"), ("wordnet", "corpora"),
                           ("averaged_perceptron_tagger_eng", "taggers")]:
            try:
                nltk.data.find(f"{kind}/{pkg}")
            except LookupError:
                nltk.download(pkg, quiet=True)
    except ImportError:
        pass


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestDeepDocIntegrationPDF:
    """End-to-end PDF parsing with real sample document."""

    @pytest.fixture(autouse=True)
    def setup(self) -> None:
        _ensure_nltk()

    @slow
    @needs_models_skip
    def test_parse_sample_pdf(self) -> None:
        """Parse the sample Chinese PDF and verify output structure."""
        pdf_path = ASSETS_DIR / "国电电力.pdf"
        if not pdf_path.exists():
            pytest.skip(f"Sample PDF not found: {pdf_path}")

        from backend.documents.parse_adapter.deepdoc.adapter import DeepDocAdapter

        adapter = DeepDocAdapter()
        doc = adapter.parse(str(pdf_path))

        # Contract checks
        assert doc.filename == "国电电力.pdf"
        assert doc.file_type == "pdf"
        assert doc.parse_meta is not None
        assert doc.parse_meta.parse_engine == "deepdoc"
        assert doc.parse_meta.parse_duration_ms > 0
        assert doc.parse_meta.total_pages >= 1
        assert isinstance(doc.parse_meta.parse_warnings, list)

        # Should have content
        assert len(doc.blocks) > 0, "Expected at least one text block"
        assert len(doc.tables) + len(doc.figures) > 0, "Expected tables or figures"

        # Block structure
        first_block = doc.blocks[0]
        assert first_block.block_id
        assert first_block.page_no >= 1
        assert first_block.block_type in (
            "heading", "paragraph", "list_item",
            "table_caption", "figure_caption", "footnote",
        )
        assert len(first_block.text) > 0
        assert first_block.bbox is not None  # PDF should have position data
        assert len(first_block.bbox) == 4

        # Tables should have content
        for table in doc.tables:
            assert table.table_id
            assert table.page_no >= 0
            assert table.cells_markdown or table.cells_structured, (
                f"Table {table.table_id} has no content"
            )

        # Figures should have captions
        for figure in doc.figures:
            assert figure.figure_id
            assert figure.page_no >= 0


class TestDeepDocIntegrationDOCX:
    """End-to-end DOCX parsing with real sample document."""

    @slow
    def test_parse_sample_docx(self) -> None:
        """Parse the sample DOCX and verify output structure."""
        docx_path = ASSETS_DIR / "test_docx.docx"
        if not docx_path.exists():
            pytest.skip(f"Sample DOCX not found: {docx_path}")

        from backend.documents.parse_adapter.deepdoc.adapter import DeepDocAdapter

        adapter = DeepDocAdapter()
        doc = adapter.parse(str(docx_path))

        assert doc.filename == "test_docx.docx"
        assert doc.file_type == "docx"
        assert doc.parse_meta.parse_engine == "deepdoc"
        assert doc.parse_meta.parse_duration_ms > 0

        # Should have some blocks
        assert len(doc.blocks) > 0, "Expected at least one text block"

        # Check block integrity
        for block in doc.blocks:
            assert block.block_id
            assert block.block_type in (
                "heading", "paragraph", "list_item",
                "table_caption", "figure_caption", "footnote",
            )
            assert block.text.strip()


class TestExcelIntegration:
    """End-to-end Excel parsing with real sample document."""

    def test_parse_sample_xlsx(self) -> None:
        """Parse the sample XLSX and verify output structure."""
        xlsx_path = ASSETS_DIR / "output_rev1.xlsx"
        if not xlsx_path.exists():
            pytest.skip(f"Sample XLSX not found: {xlsx_path}")

        from backend.documents.parse_adapter.excel import ExcelParser

        parser = ExcelParser()
        doc = parser.parse(str(xlsx_path))

        assert doc.filename == "output_rev1.xlsx"
        assert doc.file_type == "XLSX"
        assert doc.parse_meta.parse_engine == "excel_openpyxl"
        assert doc.parse_meta.total_pages >= 1
        assert doc.parse_meta.parse_duration_ms > 0

        # Should have at least one table
        assert len(doc.tables) > 0, "Expected at least one table from xlsx"
        for table in doc.tables:
            assert table.table_id
            assert table.cells_markdown or table.cells_structured


class TestParsedToChunks:
    """Verify the ParsedDocument → chunk dicts converter."""

    def test_blocks_become_chunks(self) -> None:
        from backend.documents.parse_adapter.base import (
            ParsedBlock, ParsedDocument, ParseMeta,
        )
        from backend.documents.parse_adapter.converters import parsed_to_chunks

        doc = ParsedDocument(
            filename="test.pdf",
            file_type="pdf",
            parse_meta=ParseMeta(parse_engine="test"),
            blocks=[
                ParsedBlock(
                    block_id="b1", page_no=1, block_type="paragraph",
                    text="Hello world. This is a test document.",
                ),
            ],
        )

        chunks = parsed_to_chunks(doc, "/tmp/test.pdf")
        # At least 1 root + 1 leaf
        assert len(chunks) >= 2
        roots = [c for c in chunks if c["chunk_role"] == "root"]
        leaves = [c for c in chunks if c["chunk_role"] == "leaf"]
        assert len(roots) >= 1
        assert len(leaves) >= 1

    def test_tables_become_chunks(self) -> None:
        from backend.documents.parse_adapter.base import (
            ParsedDocument, ParsedTable, ParseMeta,
        )
        from backend.documents.parse_adapter.converters import parsed_to_chunks

        doc = ParsedDocument(
            filename="test.xlsx",
            file_type="xlsx",
            parse_meta=ParseMeta(parse_engine="test"),
            tables=[
                ParsedTable(
                    table_id="t1", page_no=0,
                    caption="Sheet1",
                    cells_markdown="| A | B |\n|---|---|\n| 1 | 2 |",
                    cells_structured=[["A", "B"], ["1", "2"]],
                ),
            ],
        )

        chunks = parsed_to_chunks(doc, "/tmp/test.xlsx")
        assert len(chunks) >= 2
        tbl_chunks = [c for c in chunks if c["block_type"] == "table"]
        assert len(tbl_chunks) >= 1
        assert tbl_chunks[0]["parent_extras"]["table_markdown"]
