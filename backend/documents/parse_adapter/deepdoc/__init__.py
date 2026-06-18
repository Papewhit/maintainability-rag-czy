"""DeepDoc-based ParseAdapter for PDF and DOCX documents.

Wraps the copied DeepDoc vision (ONNX) and parser modules.
"""

from backend.documents.parse_adapter.deepdoc.adapter import DeepDocAdapter

__all__ = ["DeepDocAdapter"]
