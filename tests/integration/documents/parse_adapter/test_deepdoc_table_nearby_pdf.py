"""DeepDoc integration coverage for table nearby enrichment on real PDFs."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from backend.documents.parse_adapter.converters import parsed_to_chunks
from backend.documents.parse_adapter.deepdoc.adapter import DeepDocAdapter

DOCUMENT_FIXTURES_DIR = Path(__file__).resolve().parents[3] / "fixtures" / "documents"

_MODEL_DIR = os.environ.get("DEEPDOC_MODEL_DIR") or str(
    Path(__file__).resolve().parents[4]
    / "backend"
    / "documents"
    / "parse_adapter"
    / "deepdoc"
    / "models"
)
_REQUIRED_MODELS = ["det.onnx", "rec.onnx", "layout.onnx", "tsr.onnx"]


def _models_available() -> bool:
    model_path = Path(_MODEL_DIR)
    if not model_path.is_dir():
        return False
    return all((model_path / filename).exists() for filename in _REQUIRED_MODELS)


needs_models_skip = pytest.mark.skipif(
    not _models_available(),
    reason=f"DeepDoc ONNX models not found at {_MODEL_DIR}. Required: {_REQUIRED_MODELS}.",
)


@pytest.mark.slow
@needs_models_skip
def test_scm_table_pdf_v4_full_populates_table_nearby_blocks():
    pdf_path = DOCUMENT_FIXTURES_DIR / "节选表格_SCM优化方案.pdf"
    if not pdf_path.exists():
        pytest.skip(f"Sample PDF not found: {pdf_path}")

    doc = DeepDocAdapter().parse(str(pdf_path))
    chunks = parsed_to_chunks(doc, str(pdf_path), profile="v4_full")
    table_roots = [
        chunk
        for chunk in chunks
        if chunk["block_type"] == "table" and chunk["chunk_level"] == 1
    ]
    table5_root = next(chunk for chunk in table_roots if "表5" in chunk["text"])

    assert table5_root["parent_extras"]["nearby_block_ids"]
    assert "<table><caption>表5" in table5_root["text"]
    assert "节点关键属性定义如表5 所示" in table5_root["text"]
