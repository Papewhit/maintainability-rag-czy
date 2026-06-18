"""Service layer for document operations, decoupled from FastAPI protocol."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from backend.documents.loader import DocumentLoader
from backend.infra.vector_store.milvus_client import MilvusManager
from backend.infra.vector_store.milvus_writer import MilvusWriter
from backend.infra.embedding import embedding_service
from backend.infra.vector_store.parent_chunk_store import ParentChunkStore
from backend.rag.profiles import current_index_profile
from backend.shared.filename_normalization import raw_filename_basename
from backend.documents.parse_adapter.base import UnsupportedFileType
from backend.documents.parse_adapter.registry import get_registry
from backend.documents.parse_adapter.converters import parsed_to_chunks


class DocumentProcessingError(RuntimeError):
    """Raised when source content cannot be converted into searchable chunks."""


def _escape_milvus_string(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def _filename_filter(filename: str) -> str:
    return f'filename == "{_escape_milvus_string(filename)}"'


class DocumentService:
    """Encapsulates document ingestion, listing, and deletion logic."""

    def __init__(
        self,
        loader: DocumentLoader,
        milvus_manager: MilvusManager,
        milvus_writer: MilvusWriter,
        parent_store: ParentChunkStore,
        upload_dir: Path,
        embedding,
        *,
        registry=None,
    ):
        self._loader = loader
        self._milvus = milvus_manager
        self._writer = milvus_writer
        self._parent = parent_store
        self._upload_dir = upload_dir
        self._embedding = embedding
        self._registry = registry  # None → use get_registry() lazily
        self._index_profile = current_index_profile()

    @classmethod
    def create_default(cls, upload_dir: Path | None = None) -> "DocumentService":
        loader = DocumentLoader()
        milvus = MilvusManager()
        writer = MilvusWriter(embedding_service=embedding_service, milvus_manager=milvus)
        parent = ParentChunkStore()
        base = upload_dir or (Path(__file__).resolve().parents[1] / "data" / "documents")
        return cls(loader, milvus, writer, parent, base, embedding_service)

    def list_documents(self) -> list[dict[str, Any]]:
        self._milvus.init_collection()
        results = self._milvus.query(
            filter_expr=f'index_profile == "{_escape_milvus_string(self._index_profile)}"',
            output_fields=["filename", "file_type"],
            limit=10000,
        )
        stats: dict[str, dict] = {}
        for item in results:
            fn = item.get("filename", "")
            ft = item.get("file_type", "")
            if fn not in stats:
                stats[fn] = {"filename": fn, "file_type": ft, "chunk_count": 0}
            stats[fn]["chunk_count"] += 1
        return list(stats.values())

    def _remove_bm25_stats(self, filename: str) -> None:
        rows = self._milvus.query_all(
            filter_expr=f'{_filename_filter(filename)} and index_profile == "{_escape_milvus_string(self._index_profile)}"',
            output_fields=["text"],
        )
        texts = [r.get("text") or "" for r in rows]
        self._embedding.increment_remove_documents(texts)

    def _persist_parse_meta(self, filename: str, meta: dict) -> None:
        """Write parse metadata to document_parse_meta table."""
        try:
            from backend.infra.db.database import SessionLocal
            from backend.infra.db.models import DocumentParseMeta
            from sqlalchemy.dialects.postgresql import insert as pg_insert
            from sqlalchemy import insert as sql_insert

            db = SessionLocal()
            try:
                row = {
                    "document_id": filename,
                    "parse_engine": meta.get("parse_engine", ""),
                    "parse_engine_version": meta.get("parse_engine_version", ""),
                    "parse_duration_ms": int(meta.get("parse_duration_ms", 0) or 0),
                    "total_pages": int(meta.get("total_pages", 0) or 0),
                    "parse_warnings": meta.get("parse_warnings"),
                    "watermark_filter_ratio": meta.get("watermark_filter_ratio"),
                    "ocr_confidence_avg": meta.get("ocr_confidence_avg"),
                    "hierarchy_validation_warnings": meta.get("hierarchy_validation_warnings"),
                }
                is_pg = db.get_bind().dialect.name == "postgresql"
                stmt = (
                    pg_insert(DocumentParseMeta).values(**row).on_conflict_do_update(
                        index_elements=["document_id"],
                        set_=row,
                    )
                ) if is_pg else (
                    sql_insert(DocumentParseMeta).values(**row).prefix_with("OR REPLACE")
                )
                db.execute(stmt)
                db.commit()
            finally:
                db.close()
        except Exception:
            pass  # best-effort; parse_meta is non-critical for retrieval

    def _load_via_adapter(
        self, file_path: str, filename: str, *, final_path: str | None = None,
    ) -> tuple[list[dict[str, object]], dict | None]:
        """Try the ParseAdapter pipeline for this file.

        If an adapter is registered for the file type, it is the sole
        parse path — failure raises ``DocumentProcessingError`` immediately
        (no fallback to the legacy ``DocumentLoader`` for PDF/DOCX/XLSX).

        Only unregistered extensions (e.g. ``.txt``, ``.csv``) still go
        through the legacy loader.

        Returns (chunks, parse_meta_dict_or_None).
        """
        registry = (self._registry or get_registry())
        try:
            adapter = registry.get_adapter(filename)
        except UnsupportedFileType:
            return self._loader.load_document(file_path, filename), None

        try:
            parsed = adapter.parse(file_path)
        except Exception as exc:
            raise DocumentProcessingError(
                f"Failed to parse {filename} with {type(adapter).__name__}"
            ) from exc

        # Use canonical filename + final path for chunk identity
        chunk_path = final_path or file_path
        chunks = parsed_to_chunks(parsed, chunk_path, filename=filename)
        parse_meta_dict = _parse_meta_to_dict(parsed.parse_meta)
        return chunks, parse_meta_dict  # type: ignore[return-value]

    def upload_document(self, filename: str, content: bytes) -> dict[str, Any]:
        filename = raw_filename_basename(filename)
        if not filename:
            raise DocumentProcessingError("Filename is required")
        os.makedirs(self._upload_dir, exist_ok=True)
        self._milvus.init_collection()

        upload_root = self._upload_dir.resolve()
        file_path = self._upload_dir / filename
        if file_path.resolve().parent != upload_root:
            raise DocumentProcessingError("Unsafe upload path")
        pending_path = self._upload_dir / f".pending-{filename}"
        if pending_path.resolve().parent != upload_root:
            raise DocumentProcessingError("Unsafe upload path")
        pending_path.write_bytes(content)

        try:
            new_docs, parse_meta_dict = self._load_via_adapter(
                str(pending_path), filename, final_path=str(file_path),
            )
        except Exception as doc_err:
            pending_path.unlink(missing_ok=True)
            raise DocumentProcessingError(f"Failed to load document: {doc_err}") from doc_err
        if not new_docs:
            pending_path.unlink(missing_ok=True)
            raise DocumentProcessingError("Document processing failed: no content extracted")

        parent_docs = [d for d in new_docs if int(d.get("chunk_level", 0) or 0) in (1, 2)]
        leaf_docs = [d for d in new_docs if int(d.get("chunk_level", 0) or 0) == 3]
        if not leaf_docs:
            pending_path.unlink(missing_ok=True)
            raise DocumentProcessingError("Document processing failed: no leaf chunks generated")

        delete_expr = f'{_filename_filter(filename)} and index_profile == "{_escape_milvus_string(self._index_profile)}"'
        self._remove_bm25_stats(filename)
        self._milvus.delete(delete_expr)
        self._parent.delete_by_filename(filename)
        pending_path.replace(file_path)

        self._parent.upsert_documents(parent_docs)
        self._writer.write_documents(leaf_docs)

        if parse_meta_dict:
            self._persist_parse_meta(filename, parse_meta_dict)

        return {
            "filename": filename,
            "chunks_processed": len(leaf_docs),
            "message": (
                f"Uploaded {filename}; indexed {len(leaf_docs)} leaf chunks "
                f"and stored {len(parent_docs)} parent chunks"
            ),
        }

    def delete_document(self, filename: str) -> dict[str, Any]:
        filename = raw_filename_basename(filename)
        if not filename:
            raise DocumentProcessingError("Filename is required")
        self._milvus.init_collection()
        delete_expr = f'{_filename_filter(filename)} and index_profile == "{_escape_milvus_string(self._index_profile)}"'
        self._remove_bm25_stats(filename)
        result = self._milvus.delete(delete_expr)
        self._parent.delete_by_filename(filename)
        return {
            "filename": filename,
            "chunks_deleted": result.get("delete_count", 0) if isinstance(result, dict) else 0,
            "message": f"Deleted document {filename} from vector store and parent chunk storage",
        }


# ── Helpers ──


def _parse_meta_to_dict(meta) -> dict:
    """Convert ParseMeta dataclass to a plain dict for DB persistence."""
    return {
        "parse_engine": meta.parse_engine,
        "parse_engine_version": meta.parse_engine_version,
        "parse_duration_ms": meta.parse_duration_ms,
        "total_pages": meta.total_pages,
        "parse_warnings": meta.parse_warnings,
        "watermark_filter_ratio": meta.watermark_filter_ratio,
        "ocr_confidence_avg": meta.ocr_confidence_avg,
    }
