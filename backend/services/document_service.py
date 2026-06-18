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
from backend.documents.parse_adapter.base import UnsupportedFileType, ParseError
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

    def _load_via_adapter(
        self, file_path: str, filename: str, *, final_path: str | None = None,
    ) -> list[dict[str, object]]:
        """Try the ParseAdapter pipeline for this file.

        If an adapter is registered for the file type, it is the sole
        parse path — failure raises ``DocumentProcessingError`` immediately
        (no fallback to the legacy ``DocumentLoader`` for PDF/DOCX/XLSX).

        Only unregistered extensions (e.g. ``.txt``, ``.csv``) still go
        through the legacy loader.

        Args:
            file_path: Path to the file on disk (may be a temp / pending path).
            filename: Canonical filename for chunk identity.
            final_path: Final on-disk path for chunk ``file_path`` metadata.
                Defaults to *file_path* when not given.
        """
        registry = (self._registry or get_registry())
        try:
            adapter = registry.get_adapter(filename)
        except UnsupportedFileType:
            # No adapter for this extension — use legacy loader
            return self._loader.load_document(file_path, filename)

        try:
            parsed = adapter.parse(file_path)
        except Exception as exc:
            raise DocumentProcessingError(
                f"Failed to parse {filename} with {type(adapter).__name__}"
            ) from exc

        # Use canonical filename + final path for chunk identity
        chunk_path = final_path or file_path
        return parsed_to_chunks(parsed, chunk_path, filename=filename)  # type: ignore[no-any-return]

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
            new_docs = self._load_via_adapter(
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
