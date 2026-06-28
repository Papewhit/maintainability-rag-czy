from __future__ import annotations

from pathlib import Path

import pytest

from backend.documents.parse_adapter.base import (
    ParsedBlock, ParsedDocument, ParseAdapter, ParseError, ParseMeta,
    UnsupportedFileType,
)
from backend.rag.profiles import current_index_profile
from backend.services.document_service import DocumentProcessingError, DocumentService


class FakeLoader:
    def __init__(self, docs):
        self.docs = docs
        self.calls = []

    def load_document(self, path, filename):
        self.calls.append((Path(path), filename))
        return list(self.docs)


# ── Fake registry / adapter for controlling the parse path in tests ──


class FakeAdapter:
    """Returns a fixed ParsedDocument, or raises on demand."""

    def __init__(self, doc: ParsedDocument | None = None, exc: type[Exception] | None = None):
        self._doc = doc or ParsedDocument(
            filename="fake.pdf", file_type="pdf",
            parse_meta=ParseMeta(parse_engine="fake"),
        )
        self._exc = exc

    def parse(self, file_path: str) -> ParsedDocument:
        if self._exc:
            raise self._exc("injected failure")
        return self._doc


class FakeRegistry:
    """Registry that by default reports everything as unsupported (→ legacy loader).

    Call ``.register(ext, adapter)`` to steer specific extensions to a fake adapter.
    """

    def __init__(self):
        self._adapters: dict[str, ParseAdapter] = {}

    def register(self, ext: str, adapter: ParseAdapter) -> None:
        self._adapters[ext.lower().lstrip(".")] = adapter

    def get_adapter(self, filename: str) -> ParseAdapter:
        ext = filename.lower().rsplit(".", 1)[-1] if "." in filename else ""
        a = self._adapters.get(ext)
        if a is None:
            raise UnsupportedFileType(f"no adapter for .{ext}")
        return a


class FakeMilvus:
    def __init__(self):
        self.init_calls = 0
        self.delete_calls = []
        self.query_all_calls = []
        self.query_rows = [
            {"filename": "manual.pdf", "file_type": "pdf"},
            {"filename": "manual.pdf", "file_type": "pdf"},
            {"filename": "sheet.xlsx", "file_type": "xlsx"},
        ]

    def init_collection(self):
        self.init_calls += 1

    def query(self, output_fields, limit, filter_expr=""):
        return list(self.query_rows)

    def query_all(self, filter_expr, output_fields):
        self.query_all_calls.append((filter_expr, tuple(output_fields)))
        return [{"text": "old chunk"}]

    def delete(self, expr):
        self.delete_calls.append(expr)
        return {"delete_count": 2}


class FakeWriter:
    def __init__(self):
        self.written = []

    def write_documents(self, docs):
        self.written.append(list(docs))


class FakeParentStore:
    def __init__(self):
        self.deleted = []
        self.upserted = []

    def delete_by_filename(self, filename):
        self.deleted.append(filename)

    def upsert_documents(self, docs):
        self.upserted.append(list(docs))


class FakeEmbedding:
    def __init__(self):
        self.removed = []

    def increment_remove_documents(self, texts):
        self.removed.append(list(texts))


def make_service(tmp_path, docs, *, registry=None):
    milvus = FakeMilvus()
    writer = FakeWriter()
    parent = FakeParentStore()
    embedding = FakeEmbedding()
    service = DocumentService(
        FakeLoader(docs),
        milvus,
        writer,
        parent,
        tmp_path,
        embedding,
        registry=registry,
    )
    return service, milvus, writer, parent, embedding


def profile_expr() -> str:
    return f'index_profile == "{current_index_profile()}"'


def test_list_documents_aggregates_chunk_counts(tmp_path):
    service, *_ = make_service(tmp_path, [])

    docs = sorted(service.list_documents(), key=lambda item: item["filename"])

    assert docs == [
        {"filename": "manual.pdf", "file_type": "pdf", "chunk_count": 2},
        {"filename": "sheet.xlsx", "file_type": "xlsx", "chunk_count": 1},
    ]


def test_upload_document_replaces_old_index_and_writes_leaf_chunks(tmp_path):
    source_docs = [
        {"chunk_level": 1, "chunk_id": "parent"},
        {"chunk_level": 3, "chunk_id": "leaf"},
    ]
    service, milvus, writer, parent, embedding = make_service(
        tmp_path, source_docs, registry=FakeRegistry(),
    )

    result = service.upload_document("manual.pdf", b"content")

    assert (tmp_path / "manual.pdf").read_bytes() == b"content"
    assert milvus.delete_calls == [f'filename == "manual.pdf" and {profile_expr()}']
    assert parent.deleted == ["manual.pdf"]
    assert parent.upserted == [[source_docs[0]]]
    assert writer.written == [[source_docs[1]]]
    assert embedding.removed == [["old chunk"]]
    assert result["filename"] == "manual.pdf"
    assert result["chunks_processed"] == 1


def test_upload_document_requires_leaf_chunks(tmp_path):
    service, *_ = make_service(
        tmp_path, [{"chunk_level": 1, "chunk_id": "parent"}], registry=FakeRegistry(),
    )

    with pytest.raises(DocumentProcessingError, match="no leaf chunks generated"):
        service.upload_document("manual.pdf", b"content")
    assert not (tmp_path / "manual.pdf").exists()


def test_upload_document_prepares_new_content_before_cleanup(tmp_path):
    class FailingLoader(FakeLoader):
        def load_document(self, path, filename):
            raise RuntimeError("parse failed")

    service, milvus, writer, parent, embedding = make_service(
        tmp_path, [], registry=FakeRegistry(),
    )
    service._loader = FailingLoader([])

    with pytest.raises(DocumentProcessingError, match="Failed to load document"):
        service.upload_document("manual.pdf", b"bad")

    assert milvus.delete_calls == []
    assert parent.deleted == []
    assert embedding.removed == []
    assert writer.written == []
    assert not (tmp_path / "manual.pdf").exists()


def test_upload_document_normalizes_unsafe_paths_to_basename(tmp_path):
    source_docs = [{"chunk_level": 3, "chunk_id": "leaf"}]
    service, milvus, *_ = make_service(
        tmp_path, source_docs, registry=FakeRegistry(),
    )

    result = service.upload_document("../manual.pdf", b"content")

    assert result["filename"] == "manual.pdf"
    assert (tmp_path / "manual.pdf").exists()
    assert milvus.delete_calls == [f'filename == "manual.pdf" and {profile_expr()}']


def test_delete_document_escapes_filename_filter(tmp_path):
    service, milvus, _, parent, _ = make_service(tmp_path, [])

    result = service.delete_document('manual "quoted".pdf')

    assert milvus.query_all_calls == [
        (
            f'filename == "manual \\"quoted\\".pdf" and {profile_expr()}',
            ("text",),
        )
    ]
    assert milvus.delete_calls == [f'filename == "manual \\"quoted\\".pdf" and {profile_expr()}']
    assert parent.deleted == ['manual "quoted".pdf']
    assert result["filename"] == 'manual "quoted".pdf'


# ── Adapter-path tests ──


def test_adapter_success_path_indexes_chunks(tmp_path):
    """PDF goes through the adapter, not the legacy loader."""
    parsed_doc = ParsedDocument(
        filename="manual.pdf", file_type="pdf",
        parse_meta=ParseMeta(parse_engine="test"),
        blocks=[ParsedBlock(block_id="b1", page_no=1, block_type="paragraph", text="hello world")],
    )

    reg = FakeRegistry()
    reg.register("pdf", FakeAdapter(doc=parsed_doc))

    loader = FakeLoader([])
    service, milvus, writer, parent, embedding = make_service(
        tmp_path, [], registry=reg,
    )
    service._loader = loader

    result = service.upload_document("manual.pdf", b"real pdf content")

    # Adapter was used, loader was NOT
    assert loader.calls == []
    assert result["chunks_processed"] > 0
    assert len(parent.upserted) > 0
    assert len(writer.written) > 0

    # Chunk identity must use canonical filename, not .pending-*
    for chunk_list in writer.written:
        for chunk in chunk_list:
            assert chunk["filename"] == "manual.pdf", (
                f"chunk filename leaked: {chunk['filename']!r}"
            )
            assert ".pending-" not in chunk.get("file_path", ""), (
                f"chunk file_path leaked .pending-: {chunk['file_path']!r}"
            )


def test_adapter_failure_raises_document_processing_error(tmp_path):
    """PDF adapter failure raises DocumentProcessingError, no fallback."""
    reg = FakeRegistry()
    reg.register("pdf", FakeAdapter(exc=ParseError))

    service, *_ = make_service(tmp_path, [], registry=reg)

    with pytest.raises(DocumentProcessingError, match="Failed to parse"):
        service.upload_document("manual.pdf", b"bad pdf")


def test_unregistered_extension_falls_back_to_legacy_loader(tmp_path):
    """TXT is not registered → legacy loader is used."""
    loader = FakeLoader(
        [{"chunk_level": 3, "chunk_id": "leaf", "text": "yes"}],
    )
    service, _, writer, _, _ = make_service(tmp_path, [], registry=FakeRegistry())
    service._loader = loader

    result = service.upload_document("notes.txt", b"text content")

    assert len(loader.calls) == 1
    assert result["chunks_processed"] == 1


def test_delete_document_removes_index_and_parent_chunks(tmp_path):
    service, milvus, _, parent, embedding = make_service(tmp_path, [])

    result = service.delete_document("manual.pdf")

    assert milvus.delete_calls == [f'filename == "manual.pdf" and {profile_expr()}']
    assert parent.deleted == ["manual.pdf"]
    assert embedding.removed == [["old chunk"]]
    assert result == {
        "filename": "manual.pdf",
        "chunks_deleted": 2,
        "message": "Deleted document manual.pdf from vector store and parent chunk storage",
    }
