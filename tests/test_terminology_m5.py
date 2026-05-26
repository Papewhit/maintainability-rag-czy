"""Tests for M5: Admin CRUD API validation, parsing, and schema logic."""
from __future__ import annotations

import json

import pytest
from fastapi import HTTPException

from backend.routers.admin_terminology import (
    TerminologyEntryRequest,
    TerminologyEntryResponse,
    TerminologyStats,
    VALID_ENTITY_TYPES,
    _clean_variants,
    _parse_csv,
    _parse_json,
    _row_to_response,
    _validate_entry,
)


class TestValidation:
    def test_valid_entry(self) -> None:
        req = TerminologyEntryRequest(
            canonical="主减速齿轮箱",
            entity_type="component",
            variants=["MRG", "主齿轮箱"],
        )
        _validate_entry(req)  # Should not raise

    def test_empty_canonical(self) -> None:
        req = TerminologyEntryRequest(canonical="   ", entity_type="component")
        with pytest.raises(HTTPException, match="canonical is required"):
            _validate_entry(req)

    def test_invalid_entity_type(self) -> None:
        req = TerminologyEntryRequest(canonical="test", entity_type="invalid_type")
        with pytest.raises(HTTPException, match="Invalid entity_type"):
            _validate_entry(req)

    def test_all_valid_entity_types(self) -> None:
        for et in VALID_ENTITY_TYPES:
            req = TerminologyEntryRequest(canonical=f"test_{et}", entity_type=et)
            _validate_entry(req)  # Should not raise


class TestCleanVariants:
    def test_dedup_and_trim(self) -> None:
        result = _clean_variants(["  MRG  ", "MRG", "", "主减速器"])
        assert result == ["MRG", "主减速器"]

    def test_empty_list(self) -> None:
        assert _clean_variants([]) == []

    def test_all_empty(self) -> None:
        assert _clean_variants(["", "   "]) == []


class TestCSVParse:
    def test_valid_csv(self) -> None:
        content = "canonical,entity_type,variants,description\r\n主减速齿轮箱,component,MRG|主齿轮箱,main gearbox\r\n拆卸,maintenance_action,分解,disassemble\r\n"
        entries = _parse_csv(content.encode("utf-8"))
        assert len(entries) == 2
        assert entries[0]["canonical"] == "主减速齿轮箱"
        assert entries[0]["variants"] == ["MRG", "主齿轮箱"]
        assert entries[1]["canonical"] == "拆卸"
        assert entries[1]["variants"] == ["分解"]

    def test_csv_no_variants(self) -> None:
        content = "canonical,entity_type,variants,description\r\n齿轮箱,component,,"
        entries = _parse_csv(content.encode("utf-8"))
        assert entries[0]["variants"] == []


class TestJSONParse:
    def test_valid_json(self) -> None:
        data = json.dumps([
            {"canonical": "主减速齿轮箱", "entity_type": "component", "variants": ["MRG"]},
            {"canonical": "拆卸", "entity_type": "maintenance_action", "variants": ["分解"]},
        ])
        entries = _parse_json(data.encode("utf-8"))
        assert len(entries) == 2

    def test_not_array(self) -> None:
        data = json.dumps({"canonical": "x"})
        with pytest.raises(HTTPException, match="must be an array"):
            _parse_json(data.encode("utf-8"))


class TestStats:
    def test_stats_when_not_loaded(self) -> None:
        stats = TerminologyStats(entry_count=0, surface_count=0, loaded=False)
        assert stats.entry_count == 0
        assert not stats.loaded
