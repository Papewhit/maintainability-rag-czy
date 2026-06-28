"""Integration tests for the terminology module against real DB.

Requires: docker compose up -d (PostgreSQL at 5433, Milvus at 19530)
"""
from __future__ import annotations

import pytest

from backend.infra.db.database import SessionLocal, init_db
from backend.infra.db.models import TerminologyEntryModel, AuditLog, RescanTaskModel


@pytest.fixture(scope="module")
def _ensure_db() -> None:
    """Create tables via init_db before integration tests."""
    init_db()


class TestTerminologyDBIntegration:
    """DB round-trip: create entries, load into TerminologyTable, scan."""

    def test_create_and_load(self, _ensure_db: None) -> None:
        from backend.rag.terminology.table import TerminologyTable, set_terminology_table

        db = SessionLocal()
        try:
            # Clean up any leftover test data
            db.query(TerminologyEntryModel).delete()
            db.commit()

            # Create entries
            db.add(TerminologyEntryModel(
                canonical="主减速齿轮箱",
                entity_type="component",
                variants=["MRG", "主齿轮箱"],
                description="Main reduction gearbox",
            ))
            db.add(TerminologyEntryModel(
                canonical="拆卸",
                entity_type="maintenance_action",
                variants=["分解", "拆解"],
            ))
            db.commit()

            # Load into TerminologyTable
            table = TerminologyTable.load_from_db(db)
            set_terminology_table(table)

            assert table.entry_count() == 2
            assert table.is_loaded

            # Verify lookup
            entry = table.get("component", "主减速齿轮箱")  # type: ignore[arg-type]
            assert entry is not None
            assert "MRG" in entry.variants

            # Verify resolve_canonical
            result = table.resolve_canonical("MRG")
            assert result == ("主减速齿轮箱", "component")

            # Verify scan
            matches = table.scan_text("MRG 拆卸时需专用工具")
            surfaces = {m.surface for m in matches}
            assert "MRG" in surfaces
            assert "拆卸" in surfaces
        finally:
            db.close()

    def test_rebuild_after_delete(self, _ensure_db: None) -> None:
        from backend.rag.terminology.table import TerminologyTable, set_terminology_table

        db = SessionLocal()
        try:
            db.query(TerminologyEntryModel).delete()
            db.commit()

            # Add only one entry
            db.add(TerminologyEntryModel(
                canonical="燃气轮机", entity_type="equipment",
                variants=["燃机", "gas turbine"],
            ))
            db.commit()

            table = TerminologyTable.load_from_db(db)
            set_terminology_table(table)

            assert table.entry_count() == 1
            result = table.resolve_canonical("燃机")
            assert result == ("燃气轮机", "equipment")

            # "MRG" should no longer resolve
            assert table.resolve_canonical("MRG") is None
        finally:
            db.close()


class TestTerminologySeedLoading:
    def test_seed_csv_parses_correctly(self) -> None:
        """Verify the seed CSV is well-formed and contains expected data."""
        from pathlib import Path
        import csv

        seed_path = Path(__file__).resolve().parent.parent / "data" / "terminology_seed.csv"
        assert seed_path.is_file(), f"Seed file not found at {seed_path}"

        with open(seed_path, encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            rows = list(reader)

        assert len(rows) >= 200, f"Seed should have at least 200 entries, got {len(rows)}"

        entity_types = {r["entity_type"].strip().lower() for r in rows if r["entity_type"].strip()}
        expected = {"product_model", "equipment", "component", "maintenance_action"}
        missing = expected - entity_types
        assert not missing, f"Missing entity types in seed: {missing}"

        # Check a few known entries
        canonicals = {r["canonical"].strip() for r in rows}
        assert "主减速齿轮箱" in canonicals
        assert "TBD234" in canonicals
        assert "拆卸" in canonicals

    def test_seed_loads_into_db(self, _ensure_db: None) -> None:
        """Test that seed CSV can be loaded into the DB."""
        from pathlib import Path
        import csv

        from backend.application.main import _load_seed_csv

        db = SessionLocal()
        try:
            db.query(TerminologyEntryModel).delete()
            db.commit()

            seed_path = Path(__file__).resolve().parent.parent / "data" / "terminology_seed.csv"
            _load_seed_csv(db, seed_path)

            count = db.query(TerminologyEntryModel).count()
            assert count >= 200, f"Expected at least 200 entries loaded, got {count}"

            # Verify some entries loaded correctly
            entry = db.query(TerminologyEntryModel).filter(
                TerminologyEntryModel.canonical == "主减速齿轮箱"
            ).first()
            assert entry is not None
            assert "MRG" in (entry.variants or [])
        finally:
            db.close()


class TestAuditLogIntegration:
    def test_audit_log_schema_exists(self, _ensure_db: None) -> None:
        """Verify the audit_log and rescan_tasks tables exist."""
        db = SessionLocal()
        try:
            # Should be able to query these tables without error
            count_audit = db.query(AuditLog).count()
            count_rescan = db.query(RescanTaskModel).count()
            assert isinstance(count_audit, int)
            assert isinstance(count_rescan, int)
        finally:
            db.close()
