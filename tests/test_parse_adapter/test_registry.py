"""Tests for AdapterRegistry."""

from __future__ import annotations

import pytest

from backend.documents.parse_adapter.registry import AdapterRegistry, get_registry
from backend.documents.parse_adapter.base import ParseAdapter, ParsedDocument, ParseMeta, UnsupportedFileType


class FakeAdapter:
    """A minimal adapter that satisfies ParseAdapter structurally."""

    def parse(self, file_path: str) -> ParsedDocument:
        return ParsedDocument(
            filename=file_path, file_type="fake",
            parse_meta=ParseMeta(parse_engine="fake"),
        )


class TestAdapterRegistry:
    def test_register_and_get(self) -> None:
        r = AdapterRegistry()
        a = FakeAdapter()
        r.register("pdf", a)
        assert r.get_adapter("file.pdf") is a
        assert r.get_adapter("/path/to/doc.PDF") is a  # case insensitive

    def test_dot_prefix_is_stripped(self) -> None:
        r = AdapterRegistry()
        a = FakeAdapter()
        r.register(".xlsx", a)
        assert r.get_adapter("data.xlsx") is a

    def test_unsupported_extension_raises(self) -> None:
        r = AdapterRegistry()
        with pytest.raises(UnsupportedFileType, match=".ppt"):
            r.get_adapter("slides.ppt")

    def test_no_extension_raises(self) -> None:
        r = AdapterRegistry()
        with pytest.raises(UnsupportedFileType):
            r.get_adapter("noextension")

    def test_supported_extensions(self) -> None:
        r = AdapterRegistry()
        r.register("pdf", FakeAdapter())
        r.register("docx", FakeAdapter())
        assert r.supported_extensions == frozenset({"pdf", "docx"})

    def test_default_registry_has_all_adapters(self) -> None:
        registry = get_registry()
        for ext in ("pdf", "docx", "doc", "xlsx", "xls"):
            adapter = registry.get_adapter(f"test.{ext}")
            assert adapter is not None

    def test_default_registry_is_singleton(self) -> None:
        r1 = get_registry()
        r2 = get_registry()
        assert r1 is r2
