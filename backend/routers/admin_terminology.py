"""Admin API for terminology table CRUD and bulk import."""
from __future__ import annotations

import csv
import io
import json
import logging
import uuid
from datetime import datetime, timezone, timedelta
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from backend.infra.db.database import get_db
from backend.infra.db.models import TerminologyEntryModel, AuditLog
from backend.rag.terminology.rescan import get_task_status, is_rescan_running, run_rescan
from backend.rag.terminology.table import (
    EntityType,
    TerminologyEntry,
    TerminologyTable,
    get_terminology_table,
    set_terminology_table,
)
from backend.security.auth import get_current_user, require_admin

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin/terminology", tags=["admin-terminology"])

_BJ_TZ = timezone(timedelta(hours=8))

VALID_ENTITY_TYPES = frozenset(e.value for e in EntityType)


def _check_not_rescanning() -> None:
    if is_rescan_running():
        raise HTTPException(status_code=423, detail="Terminology rescan in progress; writes are temporarily blocked")


def _local_now() -> datetime:
    return datetime.now(_BJ_TZ).replace(tzinfo=None)


# --- Pydantic schemas ---


class TerminologyEntryRequest(BaseModel):
    canonical: str = Field(..., min_length=1, max_length=200)
    entity_type: str = Field(..., min_length=1, max_length=50)
    variants: list[str] = Field(default_factory=list)
    description: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class TerminologyEntryResponse(BaseModel):
    id: int
    canonical: str
    entity_type: str
    variants: list[str]
    description: str | None
    metadata: dict[str, Any]
    created_at: datetime
    updated_at: datetime


class BulkImportResult(BaseModel):
    total: int
    succeeded: int
    failed: int
    details: list[dict[str, Any]]


class TerminologyStats(BaseModel):
    entry_count: int
    surface_count: int
    loaded: bool


def _rebuild_memory_table(db: Session) -> None:
    """Rebuild the in-memory terminology table from DB and re-inject jieba."""
    table = TerminologyTable.load_from_db(db)
    set_terminology_table(table)
    if table.entry_count() > 0:
        try:
            from backend.rag.terminology.jieba_dict import get_terminology_surfaces, reload_jieba_with_terminology
            surfaces = get_terminology_surfaces(table)
            reload_jieba_with_terminology(surfaces)
            logger.info("Terminology table + jieba rebuilt: %d entries", table.entry_count())
        except Exception:
            logger.warning("Terminology table rebuilt but jieba reload failed", exc_info=True)


def _audit_log(db: Session, user_id: str, action: str, target_id: str,
               before: dict | None, after: dict | None, summary: str | None = None) -> None:
    try:
        db.add(AuditLog(
            user_id=user_id,
            action=action,
            target_type="terminology_entry",
            target_id=target_id,
            snapshot_before=before,
            snapshot_after=after,
            summary=summary,
        ))
        db.commit()
    except Exception:
        logger.exception("Failed to write audit log for %s/%s", action, target_id)


# --- Endpoints ---


@router.get("/stats", response_model=TerminologyStats)
def get_stats(_: Any = Depends(require_admin)) -> TerminologyStats:
    """Return current terminology table statistics."""
    try:
        table = get_terminology_table()
        return TerminologyStats(
            entry_count=table.entry_count(),
            surface_count=table.surface_count(),
            loaded=table.is_loaded,
        )
    except RuntimeError:
        return TerminologyStats(entry_count=0, surface_count=0, loaded=False)


@router.post("/rescan", status_code=202)
def trigger_rescan(
    current_user: Any = Depends(require_admin),
) -> dict[str, str]:
    """Trigger a background rescan of all chunks with current terminology."""
    try:
        task_id = run_rescan(triggered_by=str(current_user.username))
        return {"task_id": task_id, "status": "started"}
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc))


@router.get("/rescan/{task_id}")
def query_rescan_progress(
    task_id: str,
    _: Any = Depends(require_admin),
) -> dict[str, Any]:
    """Query the progress of a rescan task."""
    status = get_task_status(task_id)
    if status is None:
        raise HTTPException(status_code=404, detail="Task not found")
    return status


@router.get("", response_model=list[TerminologyEntryResponse])
def list_entries(
    entity_type: str | None = Query(None, description="Filter by entity type"),
    _: Any = Depends(require_admin),
    db: Session = Depends(get_db),
) -> list[TerminologyEntryResponse]:
    query = db.query(TerminologyEntryModel)
    if entity_type:
        query = query.filter(TerminologyEntryModel.entity_type == entity_type)
    rows = query.order_by(TerminologyEntryModel.id).all()
    return [_row_to_response(r) for r in rows]


@router.get("/{entry_id}", response_model=TerminologyEntryResponse)
def get_entry(
    entry_id: int,
    _: Any = Depends(require_admin),
    db: Session = Depends(get_db),
) -> TerminologyEntryResponse:
    row = db.query(TerminologyEntryModel).filter(TerminologyEntryModel.id == entry_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Terminology entry not found")
    return _row_to_response(row)


@router.post("", response_model=TerminologyEntryResponse, status_code=201)
def create_entry(
    body: TerminologyEntryRequest,
    current_user: Any = Depends(require_admin),
    db: Session = Depends(get_db),
) -> TerminologyEntryResponse:
    _check_not_rescanning()
    _validate_entry(body)

    existing = (
        db.query(TerminologyEntryModel)
        .filter(
            TerminologyEntryModel.entity_type == body.entity_type,
            TerminologyEntryModel.canonical == body.canonical,
        )
        .first()
    )
    if existing:
        raise HTTPException(status_code=409, detail=f"Entry ({body.entity_type}, {body.canonical}) already exists")

    variants = _clean_variants(body.variants)
    row = TerminologyEntryModel(
        canonical=body.canonical.strip(),
        entity_type=body.entity_type.strip().lower(),
        variants=variants,
        description=body.description,
        metadata_json=body.metadata or {},
    )
    db.add(row)
    db.commit()
    db.refresh(row)

    _audit_log(db, str(current_user.username), "create", str(row.id), None, _row_snapshot(row))
    _rebuild_memory_table(db)
    return _row_to_response(row)


@router.put("/{entry_id}", response_model=TerminologyEntryResponse)
def update_entry(
    entry_id: int,
    body: TerminologyEntryRequest,
    current_user: Any = Depends(require_admin),
    db: Session = Depends(get_db),
) -> TerminologyEntryResponse:
    _check_not_rescanning()
    _validate_entry(body)

    row = db.query(TerminologyEntryModel).filter(TerminologyEntryModel.id == entry_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Terminology entry not found")

    snapshot_before = _row_snapshot(row)
    variants = _clean_variants(body.variants)
    row.canonical = body.canonical.strip()
    row.entity_type = body.entity_type.strip().lower()
    row.variants = variants
    row.description = body.description
    row.metadata_json = body.metadata or {}
    row.updated_at = _local_now()
    db.commit()
    db.refresh(row)

    _audit_log(db, str(current_user.username), "update", str(row.id), snapshot_before, _row_snapshot(row))
    _rebuild_memory_table(db)
    return _row_to_response(row)


@router.delete("/{entry_id}", status_code=204)
def delete_entry(
    entry_id: int,
    current_user: Any = Depends(require_admin),
    db: Session = Depends(get_db),
) -> None:
    _check_not_rescanning()
    row = db.query(TerminologyEntryModel).filter(TerminologyEntryModel.id == entry_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Terminology entry not found")

    snapshot_before = _row_snapshot(row)
    db.delete(row)
    db.commit()

    _audit_log(db, str(current_user.username), "delete", str(entry_id), snapshot_before, None)
    _rebuild_memory_table(db)


@router.post("/bulk", response_model=BulkImportResult)
def bulk_import(
    file: UploadFile,
    current_user: Any = Depends(require_admin),
    db: Session = Depends(get_db),
) -> BulkImportResult:
    """Import terminology entries from CSV or JSON file.

    CSV format: canonical,entity_type,variants (pipe-separated),description
    JSON format: array of {canonical, entity_type, variants[], description}
    """
    _check_not_rescanning()
    content = file.file.read()
    filename = (file.filename or "").lower()

    if filename.endswith(".csv"):
        entries = _parse_csv(content)
    elif filename.endswith(".json"):
        entries = _parse_json(content)
    else:
        raise HTTPException(status_code=400, detail="Unsupported file format. Use .csv or .json")

    details: list[dict[str, Any]] = []
    succeeded = 0
    failed = 0
    for entry_data in entries:
        try:
            _validate_entry(entry_data)
            canonical = entry_data.get("canonical", "").strip()
            entity_type = entry_data.get("entity_type", "").strip().lower()
            existing = (
                db.query(TerminologyEntryModel)
                .filter(
                    TerminologyEntryModel.entity_type == entity_type,
                    TerminologyEntryModel.canonical == canonical,
                )
                .first()
            )
            if existing:
                raise ValueError(f"Already exists: ({entity_type}, {canonical})")

            row = TerminologyEntryModel(
                canonical=canonical,
                entity_type=entity_type,
                variants=_clean_variants(entry_data.get("variants", [])),
                description=entry_data.get("description"),
                metadata_json=entry_data.get("metadata") or {},
            )
            db.add(row)
            db.commit()
            db.refresh(row)
            details.append({"row": row.canonical, "status": "created", "id": row.id})
            succeeded += 1
        except Exception as exc:
            details.append({"row": entry_data.get("canonical", ""), "status": "failed", "error": str(exc)})
            failed += 1
            db.rollback()

    _audit_log(
        db, str(current_user.username), "bulk_import", "batch",
        None, None, f"Bulk import: {succeeded} succeeded, {failed} failed out of {len(entries)}"
    )
    if succeeded > 0:
        _rebuild_memory_table(db)

    return BulkImportResult(total=len(entries), succeeded=succeeded, failed=failed, details=details)


# --- Helpers ---


def _validate_entry(body: TerminologyEntryRequest | dict[str, Any]) -> None:
    canonical = getattr(body, "canonical", body.get("canonical", "")) if not isinstance(body, TerminologyEntryRequest) else body.canonical
    entity_type = getattr(body, "entity_type", body.get("entity_type", "")) if not isinstance(body, TerminologyEntryRequest) else body.entity_type
    if not canonical or not canonical.strip():
        raise HTTPException(status_code=400, detail="canonical is required")
    et = entity_type.strip().lower()
    if et not in VALID_ENTITY_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid entity_type: {entity_type}. Must be one of: {sorted(VALID_ENTITY_TYPES)}",
        )


def _clean_variants(variants: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for v in variants:
        s = v.strip()
        if s and s not in seen:
            seen.add(s)
            out.append(s)
    return out


def _row_to_response(r: TerminologyEntryModel) -> TerminologyEntryResponse:
    return TerminologyEntryResponse(
        id=r.id,
        canonical=r.canonical,
        entity_type=r.entity_type,
        variants=r.variants or [],
        description=r.description,
        metadata=r.metadata_json or {},
        created_at=r.created_at,
        updated_at=r.updated_at,
    )


def _row_snapshot(r: TerminologyEntryModel) -> dict[str, Any]:
    return {
        "id": r.id,
        "canonical": r.canonical,
        "entity_type": r.entity_type,
        "variants": r.variants,
        "description": r.description,
        "metadata": r.metadata_json,
    }


def _parse_csv(content: bytes) -> list[dict[str, Any]]:
    reader = csv.DictReader(io.StringIO(content.decode("utf-8-sig")))
    results: list[dict[str, Any]] = []
    for row in reader:
        variants_raw = row.get("variants", "")
        variants = [v.strip() for v in variants_raw.split("|") if v.strip()] if variants_raw.strip() else []
        results.append({
            "canonical": row.get("canonical", "").strip(),
            "entity_type": row.get("entity_type", "").strip().lower(),
            "variants": variants,
            "description": row.get("description", "").strip() or None,
            "metadata": {},
        })
    return results


def _parse_json(content: bytes) -> list[dict[str, Any]]:
    data = json.loads(content.decode("utf-8"))
    if not isinstance(data, list):
        raise HTTPException(status_code=400, detail="JSON must be an array of entries")
    return data
