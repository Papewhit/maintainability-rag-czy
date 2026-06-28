"""Tests for M2: jieba userdict injection and term protection."""
from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

jieba = pytest.importorskip("jieba", reason="jieba not available")


@pytest.fixture(autouse=True)
def _clear_jieba_between_tests() -> None:
    """Ensure jieba state is clean before each test."""
    jieba.setLogLevel(20)  # WARNING
    try:
        from jieba.dt import FREQ
        FREQ.clear()
    except Exception:
        pass
    yield
    try:
        from jieba.dt import FREQ
        FREQ.clear()
    except Exception:
        pass


def _tokenize(text: str) -> list[str]:
    return list(jieba.cut(text))


class TestJiebaUserdictBuild:
    def test_writes_valid_jieba_format(self) -> None:
        from backend.rag.terminology.jieba_dict import build_jieba_userdict_file

        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "userdict.txt"
            surfaces = [("主减速齿轮箱", "component"), ("拆卸", "maintenance_action")]
            result = build_jieba_userdict_file(surfaces, output_path=path)

            assert result == path
            content = path.read_text(encoding="utf-8")
            assert "主减速齿轮箱 1000 nz" in content
            assert "拆卸 1000 nz" in content

    def test_deduplicates_surfaces(self) -> None:
        from backend.rag.terminology.jieba_dict import build_jieba_userdict_file

        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "userdict.txt"
            surfaces = [("主减速齿轮箱", "component"), ("主减速齿轮箱", "equipment")]
            result = build_jieba_userdict_file(surfaces, output_path=path)

            content = path.read_text(encoding="utf-8")
            assert content.count("主减速齿轮箱") == 1


class TestJiebaTermProtection:
    def test_term_protected_after_reload(self) -> None:
        """After injecting '主减速齿轮箱', it should stay as one token."""
        from backend.rag.terminology.jieba_dict import reload_jieba_with_terminology

        surfaces = [("主减速齿轮箱", "component"), ("拆卸", "maintenance_action")]
        reload_jieba_with_terminology(surfaces)

        tokens_after = _tokenize("拆卸主减速齿轮箱时需要专用工具")
        assert "主减速齿轮箱" in tokens_after, f"Expected '主减速齿轮箱' as single token, got {tokens_after}"

    def test_english_abbreviation_protected(self) -> None:
        from backend.rag.terminology.jieba_dict import reload_jieba_with_terminology

        surfaces = [("MRG", "component")]
        reload_jieba_with_terminology(surfaces)

        tokens = _tokenize("检查 MRG 状态")
        assert "MRG" in tokens, f"Expected 'MRG' in tokens, got {tokens}"

    def test_multiple_terms_protected(self) -> None:
        from backend.rag.terminology.jieba_dict import reload_jieba_with_terminology

        surfaces = [
            ("主减速齿轮箱", "component"),
            ("拆卸", "maintenance_action"),
            ("XYZ123-A", "product_model"),
        ]
        reload_jieba_with_terminology(surfaces)

        tokens = _tokenize("XYZ123-A 主减速齿轮箱拆卸")
        assert "XYZ123-A" in tokens, f"Missing XYZ123-A in {tokens}"
        assert "主减速齿轮箱" in tokens, f"Missing 主减速齿轮箱 in {tokens}"


class TestJiebaTermRemoval:
    def test_removed_term_no_longer_protected(self) -> None:
        """After reloading without a previously-injected term, it should split again."""
        from backend.rag.terminology.jieba_dict import reload_jieba_with_terminology

        surfaces = [("主减速齿轮箱", "component")]
        reload_jieba_with_terminology(surfaces)

        tokens_with = _tokenize("拆卸主减速齿轮箱时需要专用工具")
        assert "主减速齿轮箱" in tokens_with

        reload_jieba_with_terminology([])

        tokens_without = _tokenize("拆卸主减速齿轮箱时需要专用工具")
        assert "主减速齿轮箱" not in tokens_without or len(tokens_without) > 3


class TestGetTerminologySurfaces:
    def test_extracts_all_surfaces(self) -> None:
        from backend.rag.terminology.jieba_dict import get_terminology_surfaces
        from backend.rag.terminology.table import EntityType, TerminologyEntry, TerminologyTable

        entries = [
            TerminologyEntry(
                canonical="主减速齿轮箱",
                entity_type=EntityType.COMPONENT,
                variants=("MRG", "主减速器"),
            ),
            TerminologyEntry(
                canonical="拆卸",
                entity_type=EntityType.MAINTENANCE_ACTION,
                variants=(),
            ),
        ]
        table = TerminologyTable()
        table.reload_from_db(entries)

        surfaces = get_terminology_surfaces(table)
        surface_values = {s for s, _ in surfaces}
        assert "主减速齿轮箱" in surface_values
        assert "MRG" in surface_values
        assert "主减速器" in surface_values
        assert "拆卸" in surface_values
        assert len(surfaces) == 4
