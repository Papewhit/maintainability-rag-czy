"""Tests for M3: Query-time terminology preflight integration."""
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
    """Set up the process-level singleton so terminology_preflight works."""
    entries = [
        TerminologyEntry(
            canonical="主减速齿轮箱",
            entity_type=EntityType.COMPONENT,
            variants=("主齿轮箱", "主减速器", "MRG", "main reduction gearbox"),
        ),
        TerminologyEntry(
            canonical="拆卸",
            entity_type=EntityType.MAINTENANCE_ACTION,
            variants=("分解", "拆解", "disassembly"),
        ),
        TerminologyEntry(
            canonical="XYZ123",
            entity_type=EntityType.PRODUCT_MODEL,
            variants=("XYZ123-A", "XYZ123A"),
        ),
    ]
    table = TerminologyTable()
    table.reload_from_db(entries)
    set_terminology_table(table)
    return table


class TestTerminologyPreflight:
    def test_returns_none_when_not_loaded(self) -> None:
        set_terminology_table(TerminologyTable())
        from backend.rag.query_plan import terminology_preflight
        assert terminology_preflight("anything") is None

    def test_returns_data_when_loaded(self, _load_table: TerminologyTable) -> None:
        from backend.rag.query_plan import terminology_preflight
        result = terminology_preflight("MRG 拆卸怎么做")
        assert result is not None
        assert result["normalized_query"] == "主减速齿轮箱 拆卸怎么做"
        assert "主减速齿轮箱" in result["sparse_expansion"]
        assert "MRG" in result["sparse_expansion"]
        assert "拆卸" in result["sparse_expansion"]
        assert "分解" in result["sparse_expansion"]
        assert len(result["term_matches"]) >= 2
        surfaces = {m["surface"] for m in result["term_matches"]}
        assert "MRG" in surfaces
        assert "拆卸" in surfaces

    def test_returns_none_for_table_error(self) -> None:
        """When table singleton is None, should return None gracefully."""
        from backend.rag.terminology.table import _terminology_table
        import backend.rag.terminology.table as tbl
        old = _terminology_table
        try:
            tbl._terminology_table = None
            from backend.rag.query_plan import terminology_preflight
            assert terminology_preflight("anything") is None
        finally:
            tbl._terminology_table = old

    def test_no_terms_query(self, _load_table: TerminologyTable) -> None:
        from backend.rag.query_plan import terminology_preflight
        result = terminology_preflight("今天天气怎么样")
        assert result is not None
        assert result["normalized_query"] == "今天天气怎么样"
        assert result["sparse_expansion"] == "今天天气怎么样"
        assert len(result["term_matches"]) == 0
        assert result["protected_tokens"] == []


