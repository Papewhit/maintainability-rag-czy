"""Tests for ExcelParser adapter."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from backend.documents.parse_adapter.excel import ExcelParser
from backend.documents.parse_adapter.base import ParseError


class TestExcelParser:
    """Tests that require openpyxl to create real xlsx files."""

    @pytest.fixture
    def sample_xlsx(self) -> Path:
        openpyxl = pytest.importorskip("openpyxl")
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Sheet1"
        ws.append(["Name", "Value", "Unit"])
        ws.append(["Pressure", "0.5", "MPa"])
        ws.append(["Temperature", "120", "C"])
        tmp = tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False)
        wb.save(tmp.name)
        wb.close()
        yield Path(tmp.name)
        # cleanup — ignore Windows file-locking races
        try:
            Path(tmp.name).unlink(missing_ok=True)
        except PermissionError:
            pass

    def test_parses_simple_file(self, sample_xlsx: Path) -> None:
        parser = ExcelParser()
        doc = parser.parse(str(sample_xlsx))
        assert doc.filename.endswith(".xlsx")
        assert doc.file_type == "XLSX"
        assert len(doc.tables) == 1
        assert len(doc.blocks) == 1
        assert doc.parse_meta is not None
        assert doc.parse_meta.parse_engine == "excel_openpyxl"
        assert doc.parse_meta.total_pages == 1

    def test_multi_sheet(self) -> None:
        openpyxl = pytest.importorskip("openpyxl")
        wb = openpyxl.Workbook()
        ws1 = wb.active
        ws1.title = "A"
        ws1.append(["X"])
        ws2 = wb.create_sheet("B")
        ws2.append(["Y"])
        tmp = tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False)
        wb.save(tmp.name)
        wb.close()
        try:
            parser = ExcelParser()
            doc = parser.parse(tmp.name)
            assert doc.parse_meta is not None
            assert doc.parse_meta.total_pages == 2
            assert len(doc.tables) == 2
        finally:
            try:
                Path(tmp.name).unlink(missing_ok=True)
            except PermissionError:
                pass

    def test_empty_workbook_produces_empty_doc(self) -> None:
        openpyxl = pytest.importorskip("openpyxl")
        wb = openpyxl.Workbook()
        # empty sheet with no data rows
        tmp = tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False)
        wb.save(tmp.name)
        wb.close()
        try:
            parser = ExcelParser()
            doc = parser.parse(tmp.name)
            assert doc.blocks == []
            assert doc.tables == []
        finally:
            try:
                Path(tmp.name).unlink(missing_ok=True)
            except PermissionError:
                pass

    def test_missing_file_raises(self) -> None:
        parser = ExcelParser()
        with pytest.raises(ParseError, match="not found"):
            parser.parse("/nonexistent/path/file.xlsx")

    def test_unsupported_extension_raises(self) -> None:
        parser = ExcelParser()
        with pytest.raises(ParseError, match="does not support"):
            parser.parse("/path/to/file.pdf")
