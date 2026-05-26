"""Tests for M4: Index-time chunk terminology scanning and schema integration."""
from __future__ import annotations

import pytest

from backend.rag.terminology.table import (
    EntityType,
    TerminologyEntry,
    TerminologyTable,
    set_terminology_table,
)


@pytest.fixture
def _load_table() -> TerminologyTable:
    entries = [
        TerminologyEntry(
            canonical="主减速齿轮箱",
            entity_type=EntityType.COMPONENT,
            variants=("主齿轮箱", "MRG"),
        ),
        TerminologyEntry(
            canonical="拆卸",
            entity_type=EntityType.MAINTENANCE_ACTION,
            variants=("分解", "拆解"),
        ),
    ]
    table = TerminologyTable()
    table.reload_from_db(entries)
    set_terminology_table(table)
    return table


class TestScanTerminology:
    def test_annotates_chunks(self, _load_table: TerminologyTable) -> None:
        from backend.documents.loader import _scan_terminology

        chunks = [
            {
                "chunk_id": "chunk-1",
                "retrieval_text": "MRG 拆卸时需要使用专用扳手",
                "text": "MRG 拆卸时需要使用专用扳手",
            },
        ]
        result = _scan_terminology(chunks)
        assert len(result) == 1
        c = result[0]
        assert "component" in c["entity_types"]
        assert "maintenance_action" in c["entity_types"]
        assert c["term_match_count"] >= 2
        assert len(c["term_matches"]) >= 2
        assert "MRG" in c["protected_tokens"]
        assert "拆卸" in c["protected_tokens"]

    def test_empty_chunk_no_errors(self, _load_table: TerminologyTable) -> None:
        from backend.documents.loader import _scan_terminology

        chunks: list[dict] = []
        result = _scan_terminology(chunks)
        assert result == []

    def test_no_terms_in_chunk(self, _load_table: TerminologyTable) -> None:
        from backend.documents.loader import _scan_terminology

        chunks = [
            {
                "chunk_id": "chunk-2",
                "retrieval_text": "这是一个普通的句子没有任何术语",
                "text": "text",
            },
        ]
        result = _scan_terminology(chunks)
        c = result[0]
        assert c["entity_types"] == []
        assert c["term_match_count"] == 0
        assert c["term_matches"] == []
        assert c["protected_tokens"] == []

    def test_no_table_loaded_graceful(self) -> None:
        """When no terminology table is loaded, chunks pass through unchanged."""
        from backend.rag.terminology.table import _terminology_table
        import backend.rag.terminology.table as tbl
        from backend.documents.loader import _scan_terminology

        old = _terminology_table
        try:
            tbl._terminology_table = TerminologyTable()  # not loaded
            chunks = [{"chunk_id": "x", "retrieval_text": "MRG 拆卸"}]
            result = _scan_terminology(chunks)
            assert result == chunks  # Pass through unchanged
        finally:
            tbl._terminology_table = old


class TestParentChunkStoreTermFields:
    def test_payload_includes_term_fields(self) -> None:
        from backend.infra.vector_store.parent_chunk_store import ParentChunkStore
        from datetime import datetime, timezone, timedelta

        store = ParentChunkStore(index_profile="I3")
        doc = {
            "chunk_id": "test-chunk-abc",
            "text": "text",
            "filename": "f.pdf",
            "term_matches": [{"surface": "MRG", "canonical": "主减速齿轮箱", "entity_type": "component", "start": 0, "end": 3}],
            "protected_tokens": ["MRG"],
        }
        now = datetime.now(timezone(timedelta(hours=8))).replace(tzinfo=None)
        payload = store._payload_from_doc(doc, now)
        assert payload["term_matches"] == doc["term_matches"]
        assert payload["protected_tokens"] == doc["protected_tokens"]

        cache = store._cache_payload(payload)
        assert cache["term_matches"] == doc["term_matches"]
        assert cache["protected_tokens"] == doc["protected_tokens"]
