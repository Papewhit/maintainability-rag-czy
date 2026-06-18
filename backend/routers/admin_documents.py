"""Admin endpoints for document diagnostics (parse_meta, reindex)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from backend.infra.db.database import SessionLocal
from backend.infra.db.models import DocumentParseMeta

router = APIRouter(prefix="/admin/documents", tags=["admin"])


@router.get("/{document_id}/parse_meta")
async def get_parse_meta(document_id: str):
    """Return parse metadata for a document (M6)."""
    db = SessionLocal()
    try:
        row = db.query(DocumentParseMeta).filter(
            DocumentParseMeta.document_id == document_id
        ).first()
        if row is None:
            raise HTTPException(status_code=404, detail="Parse metadata not found")
        return {
            "document_id": row.document_id,
            "parse_engine": row.parse_engine,
            "parse_engine_version": row.parse_engine_version,
            "parse_duration_ms": row.parse_duration_ms,
            "total_pages": row.total_pages,
            "parse_warnings": row.parse_warnings or [],
        }
    finally:
        db.close()


@router.post("/reindex")
async def batch_reindex(
    filenames: list[str] | None = None,
    profile: str = Query(default="v4_full"),
):
    """Trigger a batch reindex for the given filenames (M6.4).

    This is a stub — the reindex infrastructure requires async task
    support (Redis queue) which is not yet wired in this phase.
    """
    # Stub: real implementation needs background task infrastructure
    return {
        "status": "stub",
        "message": "Batch reindex not yet implemented — requires async task support",
        "filenames": filenames or [],
        "profile": profile,
    }
