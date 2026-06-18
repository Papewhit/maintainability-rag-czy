"""Tests for MaintenanceChunk data class."""

from __future__ import annotations

import pytest

from backend.documents.chunker.base import MaintenanceChunk


class TestMaintenanceChunk:
    def test_minimal(self) -> None:
        mc = MaintenanceChunk(chunk_id="c1")
        assert mc.chunk_id == "c1"
        assert mc.chunk_role == "leaf"
        assert mc.chunk_level == 0
        assert mc.text == ""
        assert mc.retrieval_text == ""

    def test_root_chunk(self) -> None:
        mc = MaintenanceChunk(
            chunk_id="root_1", parent_chunk_id="root_0", root_chunk_id="root_0",
            chunk_level=1, chunk_role="root",
        )
        assert mc.chunk_role == "root"
        assert mc.chunk_level == 1
        assert mc.root_chunk_id == "root_0"

    def test_list_fields(self) -> None:
        mc = MaintenanceChunk(
            chunk_id="c_step1",
            list_group_id="lg_1", list_order=0, list_marker="(1)",
            list_level=0, list_complete=True,
        )
        assert mc.list_group_id == "lg_1"
        assert mc.list_order == 0
        assert mc.list_marker == "(1)"
        assert mc.list_complete is True

    def test_table_fields(self) -> None:
        mc = MaintenanceChunk(
            chunk_id="c_tbl", table_id="tbl_1", table_role="parameter",
        )
        assert mc.table_id == "tbl_1"
        assert mc.table_role == "parameter"

    def test_figure_fields(self) -> None:
        mc = MaintenanceChunk(
            chunk_id="c_fig", figure_id="fig_1", figure_role="diagram",
        )
        assert mc.figure_id == "fig_1"
        assert mc.figure_role == "diagram"

    def test_terminology_fields(self) -> None:
        mc = MaintenanceChunk(
            chunk_id="c_term",
            entity_types=["equipment", "action"],
            term_match_count=5,
        )
        assert mc.entity_types == ["equipment", "action"]
        assert mc.term_match_count == 5

    def test_parent_extras(self) -> None:
        mc = MaintenanceChunk(
            chunk_id="c_extra",
            parent_extras={"table_markdown": "| A | B |", "parameter_keys": ["P", "T"]},
        )
        assert mc.parent_extras == {"table_markdown": "| A | B |", "parameter_keys": ["P", "T"]}

    def test_defaults_are_empty_containers(self) -> None:
        mc1 = MaintenanceChunk(chunk_id="c1")
        mc2 = MaintenanceChunk(chunk_id="c2")
        # Each instance gets its own empty list/dict
        mc1.entity_types.append("test")
        assert mc2.entity_types == []

    def test_frozen(self) -> None:
        mc = MaintenanceChunk(chunk_id="c1")
        with pytest.raises(Exception):
            mc.chunk_id = "c2"  # type: ignore[misc]
