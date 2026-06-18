"""Tests for M1: Terminology table storage, loading, and the Aho-Corasick matcher."""
from __future__ import annotations

import pytest

from backend.rag.terminology.matcher import (
    AhoCorasick,
    TermMatch,
    longest_non_overlapping,
    scan_text,
)
from backend.rag.terminology.table import (
    EntityType,
    QueryTerminologyResult,
    TerminologyEntry,
    TerminologyTable,
)


# ---------------------------------------------------------------------------
# Aho-Corasick matcher tests
# ---------------------------------------------------------------------------

class TestAhoCorasick:
    def test_single_pattern_match(self) -> None:
        ac = AhoCorasick()
        ac.add_pattern("主减速齿轮箱", "主减速齿轮箱", "component")
        ac.build()
        matches = ac.scan("拆卸主减速齿轮箱时需要专用工具")
        assert len(matches) == 1
        m = matches[0]
        assert m.surface == "主减速齿轮箱"
        assert m.canonical == "主减速齿轮箱"
        assert m.entity_type == "component"
        assert m.start == 2
        assert m.end == 8

    def test_multiple_non_overlapping(self) -> None:
        ac = AhoCorasick()
        ac.add_pattern("主减速齿轮箱", "主减速齿轮箱", "component")
        ac.add_pattern("拆卸", "拆卸", "maintenance_action")
        ac.build()
        matches = ac.scan("拆卸主减速齿轮箱")
        surfaces = {m.surface for m in matches}
        assert "主减速齿轮箱" in surfaces
        assert "拆卸" in surfaces

    def test_no_match(self) -> None:
        ac = AhoCorasick()
        ac.add_pattern("燃气轮机", "燃气轮机", "equipment")
        ac.build()
        matches = ac.scan("这是一段无关文本")
        assert len(matches) == 0

    def test_overlapping_longest_match_preference(self) -> None:
        """Longest non-overlapping should prefer '主减速齿轮箱' over '齿轮箱'."""
        ac = AhoCorasick()
        ac.add_pattern("齿轮箱", "齿轮箱", "component")
        ac.add_pattern("主减速齿轮箱", "主减速齿轮箱", "component")
        ac.build()
        raw = ac.scan("检查主减速齿轮箱的齿轮箱油位")
        kept = longest_non_overlapping(raw)
        canonicals = {m.canonical for m in kept}
        # "主减速齿轮箱" covers positions 2-7; "齿轮箱" at positions 8-10 is separate
        assert "主减速齿轮箱" in canonicals
        # The second "齿轮箱" should still match
        assert len(kept) >= 1

    def test_english_mixed_terms(self) -> None:
        ac = AhoCorasick()
        ac.add_pattern("MRG", "主减速齿轮箱", "component")
        ac.add_pattern("PLC", "PLC控制器", "equipment")
        ac.build()
        matches = ac.scan("MRG和PLC需要定期维护")
        surfaces = {m.surface for m in matches}
        assert "MRG" in surfaces
        assert "PLC" in surfaces

    def test_empty_text(self) -> None:
        ac = AhoCorasick()
        ac.add_pattern("test", "test", "component")
        ac.build()
        assert ac.scan("") == []


class TestLongestNonOverlapping:
    def test_contained_match_discarded(self) -> None:
        matches = [
            TermMatch("主减速齿轮箱", "主减速齿轮箱", "component", 0, 6),
            TermMatch("减速", "减速", "parameter", 1, 3),  # contained inside above
        ]
        kept = longest_non_overlapping(matches)
        assert len(kept) == 1
        assert kept[0].surface == "主减速齿轮箱"

    def test_adjacent_non_overlapping_kept(self) -> None:
        matches = [
            TermMatch("拆卸", "拆卸", "maintenance_action", 0, 2),
            TermMatch("主减速齿轮箱", "主减速齿轮箱", "component", 2, 8),
        ]
        kept = longest_non_overlapping(matches)
        assert len(kept) == 2

    def test_same_start_longer_wins(self) -> None:
        matches = [
            TermMatch("齿轮箱", "齿轮箱", "component", 0, 3),
            TermMatch("齿轮箱体", "齿轮箱体", "component", 0, 4),
        ]
        kept = longest_non_overlapping(matches)
        assert len(kept) == 1
        assert kept[0].surface == "齿轮箱体"


# ---------------------------------------------------------------------------
# TerminologyTable tests
# ---------------------------------------------------------------------------

@pytest.fixture
def sample_entries() -> list[TerminologyEntry]:
    return [
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


@pytest.fixture
def loaded_table(sample_entries: list[TerminologyEntry]) -> TerminologyTable:
    table = TerminologyTable()
    table.reload_from_db(sample_entries)
    return table


class TestTerminologyTableLoading:
    def test_entry_count(self, loaded_table: TerminologyTable) -> None:
        assert loaded_table.entry_count() == 3

    def test_by_canonical(self, loaded_table: TerminologyTable) -> None:
        entry = loaded_table.get(EntityType.COMPONENT, "主减速齿轮箱")
        assert entry is not None
        assert entry.canonical == "主减速齿轮箱"
        assert "MRG" in entry.variants

    def test_resolve_canonical_from_variant(self, loaded_table: TerminologyTable) -> None:
        result = loaded_table.resolve_canonical("MRG")
        assert result is not None
        assert result == ("主减速齿轮箱", EntityType.COMPONENT)

    def test_resolve_canonical_from_canonical(self, loaded_table: TerminologyTable) -> None:
        result = loaded_table.resolve_canonical("拆卸")
        assert result is not None
        assert result == ("拆卸", EntityType.MAINTENANCE_ACTION)

    def test_resolve_unknown(self, loaded_table: TerminologyTable) -> None:
        assert loaded_table.resolve_canonical("不存在的术语") is None

    def test_is_loaded(self, loaded_table: TerminologyTable) -> None:
        assert loaded_table.is_loaded

    def test_not_loaded_by_default(self) -> None:
        t = TerminologyTable()
        assert not t.is_loaded


class TestTerminologyTableScan:
    def test_scan_chinese_text(self, loaded_table: TerminologyTable) -> None:
        matches = loaded_table.scan_text("MRG 拆卸时需要使用专用扳手")
        surfaces = {m.surface for m in matches}
        assert "MRG" in surfaces
        assert "拆卸" in surfaces

    def test_scan_longest_match(self, loaded_table: TerminologyTable) -> None:
        # "主减速齿轮箱" is explicit; "齿轮箱" is not in the table, but variants include "主齿轮箱"
        matches = loaded_table.scan_text("检查主齿轮箱并拆卸")
        surfaces = {m.surface for m in matches}
        assert "主齿轮箱" in surfaces
        assert "拆卸" in surfaces

    def test_scan_no_matches(self, loaded_table: TerminologyTable) -> None:
        matches = loaded_table.scan_text("这是一个普通的句子")
        assert len(matches) == 0

    def test_scan_model_number(self, loaded_table: TerminologyTable) -> None:
        matches = loaded_table.scan_text("设备型号 XYZ123-A 需要校准")
        surfaces = {m.surface for m in matches}
        assert "XYZ123-A" in surfaces


class TestQueryPreflight:
    def test_normalized_query(self, loaded_table: TerminologyTable) -> None:
        result = loaded_table.query_preflight("MRG 拆卸怎么做")
        assert result.normalized_query == "主减速齿轮箱 拆卸怎么做"

    def test_sparse_expansion(self, loaded_table: TerminologyTable) -> None:
        result = loaded_table.query_preflight("MRG 拆卸")
        assert "主减速齿轮箱" in result.sparse_expansion
        assert "主齿轮箱" in result.sparse_expansion
        assert "MRG" in result.sparse_expansion
        assert "拆卸" in result.sparse_expansion
        assert "分解" in result.sparse_expansion

    def test_protected_tokens(self, loaded_table: TerminologyTable) -> None:
        result = loaded_table.query_preflight("MRG 拆卸")
        assert "MRG" in result.protected_tokens
        assert "拆卸" in result.protected_tokens

    def test_no_terms(self, loaded_table: TerminologyTable) -> None:
        result = loaded_table.query_preflight("今天天气怎么样")
        assert len(result.query_entities) == 0
        assert result.normalized_query == "今天天气怎么样"
        assert result.sparse_expansion == "今天天气怎么样"

    def test_dedup_variants_in_expansion(self, loaded_table: TerminologyTable) -> None:
        result = loaded_table.query_preflight("MRG MRG MRG")
        # MRG should appear only once in expansion parts
        count = result.sparse_expansion.count("MRG")
        assert count == 1
