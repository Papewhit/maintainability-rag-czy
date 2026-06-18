"""Maintainability chunker layer — generates index-ready MaintenanceChunks.

Public API:
    MaintenanceChunk — frozen dataclass with 25+ metadata fields
"""

from backend.documents.chunker.base import MaintenanceChunk

__all__ = ["MaintenanceChunk"]
