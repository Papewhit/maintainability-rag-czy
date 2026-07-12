"""Rescan task: re-scans all chunks in the collection after terminology updates.

Design Decision 6: Full rescan is simple but takes 10-30 min for 100k chunks.
v1 focuses on correctness; incremental rescan is deferred to future optimization.
"""
from __future__ import annotations

import json
import logging
import os
import shutil
import threading
import time
import uuid
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from backend.infra.db.database import SessionLocal
from backend.infra.db.models import RescanTaskModel

logger = logging.getLogger(__name__)

_BJ_TZ = timezone(timedelta(hours=8))

_rescan_lock = threading.Lock()


def _local_now() -> datetime:
    return datetime.now(_BJ_TZ).replace(tzinfo=None)


def is_rescan_running() -> bool:
    return _rescan_lock.locked()


def _set_task_status(db: Session, task_id: str, **kwargs: Any) -> None:
    task = db.query(RescanTaskModel).filter(RescanTaskModel.task_id == task_id).first()
    if task:
        for key, value in kwargs.items():
            setattr(task, key, value)
        db.commit()


def run_rescan(triggered_by: str = "admin") -> str:
    """Trigger a rescan task. Returns task_id for progress tracking."""
    if not _rescan_lock.acquire(blocking=False):
        raise RuntimeError("Another rescan is already in progress")

    task_id = uuid.uuid4().hex[:16]
    db = SessionLocal()
    try:
        db.add(RescanTaskModel(task_id=task_id, status="pending"))
        db.commit()
    finally:
        db.close()

    thread = threading.Thread(
        target=_rescan_worker,
        args=(task_id, triggered_by),
        daemon=True,
        name=f"rescan-{task_id}",
    )
    thread.start()
    return task_id


def get_task_status(task_id: str) -> dict[str, Any] | None:
    db = SessionLocal()
    try:
        task = db.query(RescanTaskModel).filter(RescanTaskModel.task_id == task_id).first()
        if not task:
            return None
        return {
            "task_id": task.task_id,
            "status": task.status,
            "started_at": task.started_at.isoformat() if task.started_at else None,
            "ended_at": task.ended_at.isoformat() if task.ended_at else None,
            "processed_chunks": task.processed_chunks,
            "total_chunks": task.total_chunks,
            "error": task.error,
        }
    finally:
        db.close()


# ---------------------------------------------------------------------------
# BM25 snapshot / restore
# ---------------------------------------------------------------------------

def _backup_bm25_state() -> Path | None:
    from backend.infra.embedding import embedding_service
    state_path = embedding_service._state_path
    if not state_path.is_file():
        return None
    backup = state_path.with_suffix(".json.bak")
    shutil.copy2(state_path, backup)
    logger.info("BM25 state backed up to %s", backup)
    return backup


def _restore_bm25_state(backup: Path | None) -> None:
    if backup is None or not backup.is_file():
        return
    from backend.infra.embedding import embedding_service
    state_path = embedding_service._state_path
    shutil.copy2(backup, state_path)
    embedding_service._load_state()
    logger.info("BM25 state restored from backup: %s", backup)


# ---------------------------------------------------------------------------
# Milvus metadata snapshot / restore
# ---------------------------------------------------------------------------

def _snapshot_milvus_metadata(milvus) -> list[dict]:
    """Fetch id + entity_types + term_match_count for all chunks before rescan."""
    snapshot: list[dict] = []
    offset = 0
    page_size = 16384
    while True:
        page = _fetch_chunk_page(milvus, offset, page_size, fields=["id", "entity_types", "term_match_count"])
        if not page:
            break
        snapshot.extend(page)
        if len(page) < page_size:
            break
        offset += page_size
    logger.info("Milvus metadata snapshot: %d chunks", len(snapshot))
    return snapshot


def _restore_milvus_metadata(milvus, snapshot: list[dict]) -> None:
    """Restore entity_types / term_match_count from pre-rescan snapshot."""
    if not snapshot:
        return
    batch_size = 100
    for i in range(0, len(snapshot), batch_size):
        batch = snapshot[i:i + batch_size]
        data = [
            {
                "id": r["id"],
                "entity_types": r.get("entity_types", "[]"),
                "term_match_count": r.get("term_match_count", 0),
            }
            for r in batch
        ]
        milvus._call_with_reconnect(
            lambda c, d=data: c.upsert(collection_name=milvus.collection_name, data=d),
            operation_name="rescan_rollback_milvus",
        )
    logger.info("Milvus metadata restored from snapshot: %d chunks", len(snapshot))


# ---------------------------------------------------------------------------
# ParentChunkStore snapshot / restore
# ---------------------------------------------------------------------------

def _snapshot_parent_store(parent_store, chunk_ids: list[str]) -> list[dict]:
    """Fetch term_matches + protected_tokens for the given chunk_ids."""
    if not chunk_ids:
        return []
    snapshots = parent_store.get_documents_by_ids(chunk_ids)
    # Keep only the term fields + chunk_id for rollback
    return [
        {"chunk_id": d.get("chunk_id", ""),
         "term_matches": d.get("term_matches", []),
         "protected_tokens": d.get("protected_tokens", [])}
        for d in snapshots
    ]


def _restore_parent_store(snapshot: list[dict]) -> None:
    """Restore term_matches / protected_tokens via direct UPDATE — only touches those columns."""
    if not snapshot:
        return
    from backend.infra.db.database import SessionLocal
    from backend.infra.db.models import ParentChunk
    from backend.rag.profiles import normalize_index_profile, current_index_profile, storage_chunk_id

    from backend.infra.cache import cache
    from backend.rag.profiles import LEGACY_INDEX_PROFILE, display_chunk_id

    db = SessionLocal()
    try:
        profile = normalize_index_profile(current_index_profile())
        cache_keys: list[str] = []
        for doc in snapshot:
            original_id = doc.get("chunk_id", "")
            chunk_id = storage_chunk_id(original_id, profile)
            if not chunk_id:
                continue
            db.query(ParentChunk).filter(ParentChunk.chunk_id == chunk_id).update(
                {
                    ParentChunk.term_matches: doc.get("term_matches") or [],
                    ParentChunk.protected_tokens: doc.get("protected_tokens") or [],
                },
                synchronize_session=False,
            )
            # Collect cache keys to invalidate
            display_id = display_chunk_id(original_id, profile)
            cache_key = f"parent_chunk:{display_id}" if profile == LEGACY_INDEX_PROFILE else f"parent_chunk:{profile}:{display_id}"
            cache_keys.append(cache_key)
        db.commit()

        # Invalidate Redis cache so next read fetches restored DB values
        if cache_keys:
            cache.delete_many(cache_keys)
    finally:
        db.close()
    logger.info("ParentChunkStore term fields restored: %d chunks", len(snapshot))


# ---------------------------------------------------------------------------
# Worker
# ---------------------------------------------------------------------------

def _rescan_worker(task_id: str, triggered_by: str) -> None:
    """Background worker: performs the full rescan pipeline."""
    db = SessionLocal()
    try:
        task = db.query(RescanTaskModel).filter(RescanTaskModel.task_id == task_id).first()
        if not task:
            return
        task.status = "running"
        task.started_at = _local_now()
        db.commit()

        bm25_backup = _backup_bm25_state()
        milvus_snapshot: list[dict] | None = None
        parent_snapshot: list[dict] | None = None
        try:
            milvus_snapshot, parent_snapshot = _do_rescan(task_id, db)
            task.status = "completed"
            task.ended_at = _local_now()
            db.commit()
            logger.info("Rescan %s completed: %d/%d chunks processed",
                        task_id, task.processed_chunks, task.total_chunks)
        except Exception as exc:
            task.status = "failed"
            task.ended_at = _local_now()
            task.error = str(exc)[:2000]
            db.commit()

            # Roll back all three layers
            _restore_bm25_state(bm25_backup)
            if milvus_snapshot:
                try:
                    from backend.infra.vector_store.milvus_client import MilvusManager
                    _restore_milvus_metadata(MilvusManager(), milvus_snapshot)
                except Exception as rollback_exc:
                    logger.exception("Rescan %s: Milvus rollback failed: %s", task_id, rollback_exc)
            if parent_snapshot:
                try:
                    _restore_parent_store(parent_snapshot)
                except Exception as rollback_exc:
                    logger.exception("Rescan %s: ParentChunkStore rollback failed: %s", task_id, rollback_exc)

            logger.exception("Rescan %s failed, all layers rolled back", task_id)
    finally:
        db.close()
        _rescan_lock.release()


# ---------------------------------------------------------------------------
# Core rescan logic
# ---------------------------------------------------------------------------

def _do_rescan(task_id: str, db: Session) -> tuple[list[dict], list[dict]]:
    """Core rescan logic. Returns (milvus_snapshot, parent_snapshot) for rollback."""
    from backend.infra.embedding import embedding_service
    from backend.infra.vector_store.milvus_client import MilvusManager
    from backend.infra.vector_store.metadata_codec import encode_entity_types
    from backend.infra.vector_store.parent_chunk_store import ParentChunkStore
    from backend.rag.terminology.table import get_terminology_table
    from backend.rag.terminology.jieba_dict import get_terminology_surfaces, reload_jieba_with_terminology

    # 1. Reload jieba
    table = get_terminology_table()
    surfaces = get_terminology_surfaces(table)
    reload_jieba_with_terminology(surfaces)
    logger.info("Rescan %s: jieba reloaded with %d terms", task_id, len(surfaces))

    # 2. Setup
    milvus = MilvusManager()
    parent_store = ParentChunkStore()
    milvus_snapshot = _snapshot_milvus_metadata(milvus)

    total = _count_chunks(milvus)
    _set_task_status(db, task_id, total_chunks=total)

    # Collect parent chunk IDs for snapshot BEFORE any writes
    all_chunk_ids: list[str] = []
    offset = 0
    page_size = 16384
    while True:
        id_page = _fetch_chunk_page(milvus, offset, page_size, fields=["chunk_id"])
        if not id_page:
            break
        all_chunk_ids.extend(r.get("chunk_id", "") for r in id_page if r.get("chunk_id"))
        if len(id_page) < page_size:
            break
        offset += page_size
    parent_snapshot = _snapshot_parent_store(parent_store, all_chunk_ids)

    # 3. Iterate in pages and update
    batch_size = 100
    offset = 0
    processed = 0
    all_texts: list[str] = []
    page = _fetch_chunk_page(milvus, offset, batch_size)

    while page:
        updated_milvus: list[dict] = []
        updated_parent: list[dict] = []

        for chunk in page:
            retrieval_text = chunk.get("retrieval_text", "") or chunk.get("text", "")
            matches = table.scan_text(retrieval_text)

            entity_types: list[str] = list(dict.fromkeys(m.entity_type for m in matches))
            term_matches: list[dict] = [
                {"surface": m.surface, "canonical": m.canonical,
                 "entity_type": m.entity_type, "start": m.start, "end": m.end}
                for m in matches
            ]
            protected_tokens: list[str] = list(dict.fromkeys(
                m.surface for m in matches if len(m.surface) >= 2
            ))

            chunk_id = chunk.get("chunk_id", "")
            row_id = chunk.get("id")

            if row_id is not None:
                updated_milvus.append({
                    "id": row_id,
                    "entity_types": encode_entity_types(entity_types),
                    "term_match_count": len(term_matches),
                })

            updated_parent.append({
                "chunk_id": chunk_id,
                "text": chunk.get("text", ""),
                "filename": chunk.get("filename", ""),
                "file_type": chunk.get("file_type", ""),
                "file_path": chunk.get("file_path", ""),
                "page_number": chunk.get("page_number", 0),
                "parent_chunk_id": chunk.get("parent_chunk_id", ""),
                "root_chunk_id": chunk.get("root_chunk_id", ""),
                "chunk_level": chunk.get("chunk_level", 0),
                "chunk_idx": chunk.get("chunk_idx", 0),
                "term_matches": term_matches,
                "protected_tokens": protected_tokens,
            })

            if retrieval_text.strip():
                all_texts.append(retrieval_text)

        # Write ParentChunkStore (non-fatal: on failure we rollback parent_snapshot)
        if updated_parent:
            parent_store.upsert_documents(updated_parent)

        # Write Milvus (fatal: spec requires fail on Milvus update error)
        if updated_milvus:
            milvus._call_with_reconnect(
                lambda client, d=updated_milvus: client.upsert(
                    collection_name=milvus.collection_name,
                    data=d,
                ),
                operation_name="rescan_upsert",
            )

        processed += len(page)
        _set_task_status(db, task_id, processed_chunks=processed)

        offset += batch_size
        page = _fetch_chunk_page(milvus, offset, batch_size)

    # 4. Rebuild BM25 state atomically
    if all_texts:
        _rebuild_bm25_atomic(embedding_service, all_texts)

    logger.info("Rescan %s: complete, processed %d chunks", task_id, processed)
    return milvus_snapshot, parent_snapshot


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _count_chunks(milvus) -> int:
    """Count total chunks in the current collection via paginated query."""
    try:
        total = 0
        offset = 0
        page_size = 16384
        while True:
            page = milvus._call_with_reconnect(
                lambda c, off=offset: c.query(
                    collection_name=milvus.collection_name,
                    filter="chunk_id != \"\"",
                    output_fields=["chunk_id"],
                    limit=page_size,
                    offset=off,
                ),
                operation_name="rescan_count",
            )
            if not page:
                break
            total += len(page)
            if len(page) < page_size:
                break
            offset += page_size
        return total
    except Exception:
        return 0


def _fetch_chunk_page(milvus, offset: int, limit: int, fields: list[str] | None = None) -> list[dict]:
    """Fetch a page of chunks from Milvus."""
    output_fields = fields or [
        "id", "chunk_id", "retrieval_text", "text",
        "filename", "file_type", "file_path",
        "page_number", "parent_chunk_id", "root_chunk_id",
        "chunk_level", "chunk_idx",
    ]
    try:
        return milvus._call_with_reconnect(
            lambda c: c.query(
                collection_name=milvus.collection_name,
                filter="chunk_id != \"\"",
                output_fields=output_fields,
                limit=limit,
                offset=offset,
            ),
            operation_name="rescan_fetch_page",
        )
    except Exception as exc:
        logger.warning("Rescan: fetch page failed at offset %d: %s", offset, exc)
        raise


def _rebuild_bm25_atomic(embedding_service, texts: list[str]) -> None:
    """Rebuild BM25 state atomically using a temp file + rename.

    On failure, restores both the file and the in-memory state to pre-rebuild
    values so the running process is not corrupted.
    """
    state_path = embedding_service._state_path
    new_state_path = state_path.with_suffix(".json.new")
    backup_path = state_path.with_suffix(".json.bak")
    original_path = state_path

    # Save in-memory snapshot before modifying the live service
    mem_snapshot = {
        "vocab": dict(embedding_service._vocab),
        "doc_freq": dict(embedding_service._doc_freq),
        "total_docs": embedding_service._total_docs,
        "sum_token_len": embedding_service._sum_token_len,
        "vocab_counter": embedding_service._vocab_counter,
    }

    try:
        with embedding_service._lock:
            embedding_service._vocab.clear()
            embedding_service._doc_freq.clear()
            embedding_service._total_docs = 0
            embedding_service._sum_token_len = 0
            embedding_service._vocab_counter = 0

            # Inline increment_add_documents to avoid re-acquiring the same lock
            for text in texts:
                tokens = embedding_service.tokenize(text)
                doc_len = len(tokens)
                embedding_service._sum_token_len += doc_len
                embedding_service._total_docs += 1
                for token in set(tokens):
                    if token not in embedding_service._vocab:
                        embedding_service._vocab[token] = embedding_service._vocab_counter
                        embedding_service._vocab_counter += 1
                    embedding_service._doc_freq[token] += 1
            embedding_service._recompute_avg_len()

            embedding_service._state_path = new_state_path
            try:
                embedding_service._persist_unlocked()
            finally:
                embedding_service._state_path = original_path

        if state_path.exists():
            state_path.replace(backup_path)
        new_state_path.replace(state_path)
        logger.info("BM25 rebuilt atomically: %d docs, %d tokens",
                     embedding_service._total_docs, len(embedding_service._vocab))
    except Exception:
        # Restore file
        if backup_path.exists():
            backup_path.replace(state_path)
        # Restore in-memory state so running process is not corrupted
        embedding_service._vocab.clear()
        embedding_service._vocab.update(mem_snapshot["vocab"])
        embedding_service._doc_freq.clear()
        embedding_service._doc_freq.update(mem_snapshot["doc_freq"])
        embedding_service._total_docs = mem_snapshot["total_docs"]
        embedding_service._sum_token_len = mem_snapshot["sum_token_len"]
        embedding_service._vocab_counter = mem_snapshot["vocab_counter"]
        embedding_service._recompute_avg_len()
        raise
    finally:
        if new_state_path.exists():
            try:
                os.remove(new_state_path)
            except OSError:
                pass
