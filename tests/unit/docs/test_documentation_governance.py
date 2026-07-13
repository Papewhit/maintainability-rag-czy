from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest


SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "validate_documentation.py"
SPEC = importlib.util.spec_from_file_location("validate_documentation", SCRIPT)
validator = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
sys.modules[SPEC.name] = validator
SPEC.loader.exec_module(validator)


def _repo(tmp_path: Path, finding: str = "") -> Path:
    (tmp_path / "docs/findings").mkdir(parents=True)
    (tmp_path / "openspec/changes/sample").mkdir(parents=True)
    (tmp_path / "docs/ARCHITECTURE.md").write_text(
        "---\ndocument_type: current_architecture\n---\n# Architecture\n## Feature Status Matrix\n", encoding="utf-8"
    )
    if finding:
        (tmp_path / "openspec/changes/sample/findings.md").write_text(finding, encoding="utf-8")
    (tmp_path / "openspec/changes/sample/tasks.md").write_text(
        "## Evidence Disposition Gate\n\n"
        "- [x] No new findings classified\n"
        "- [x] Evidence linked\n"
        "- [x] Durable disposition selected\n"
        "- [x] Durable typed documents created\n"
        "- [x] OpenSpec change or issue assessed\n"
        "- [x] Architecture impact assessed\n"
        "- [x] Design ambiguity dispositioned\n", encoding="utf-8"
    )
    return tmp_path


@pytest.mark.unit
def test_change_gate_accepts_explicit_no_findings(tmp_path: Path):
    root = _repo(tmp_path)
    result = validator.Result()
    validator.validate_change_gate(root / "openspec/changes/sample", result)
    assert result.errors == []


@pytest.mark.unit
def test_change_gate_rejects_silent_absence(tmp_path: Path):
    root = _repo(tmp_path)
    (root / "openspec/changes/sample/tasks.md").write_text("# Tasks\n", encoding="utf-8")
    result = validator.Result()
    validator.validate_change_gate(root / "openspec/changes/sample", result)
    assert any("missing Evidence" in error for error in result.errors)
    assert any("No new findings" in error for error in result.errors)


@pytest.mark.unit
def test_change_gate_rejects_unchecked_declaration(tmp_path: Path):
    root = _repo(tmp_path)
    (root / "openspec/changes/sample/tasks.md").write_text(
        "## Evidence Disposition Gate\n\n- [ ] No new findings\n", encoding="utf-8"
    )
    result = validator.Result()
    validator.validate_change_gate(root / "openspec/changes/sample", result)
    assert any("unchecked" in error for error in result.errors)
    assert any("checked No new findings" in error for error in result.errors)


@pytest.mark.unit
@pytest.mark.parametrize("state,disposition", [("observed", "adr"), ("confirmed", "pending")])
def test_finding_blocks_closure(state: str, disposition: str):
    result = validator.Result(findings=[validator.Finding(
        id="FIND-0001", path=Path("finding.md"), kind="design_ambiguity",
        scope="system", evidence_status=state, disposition=disposition,
        target="ADR-0001" if disposition != "pending" else "", evidence="code",
    )])
    validator._validate_findings(result, Path.cwd(), {Path("finding.md").resolve()})
    assert any("blocks closure" in error for error in result.errors)


@pytest.mark.unit
def test_duplicate_finding_ids_are_rejected():
    finding = dict(id="FIND-0001", kind="documentation_drift", scope="documentation", evidence_status="confirmed", disposition="architecture", target="docs/ARCHITECTURE.md", evidence="code")
    result = validator.Result(findings=[validator.Finding(path=Path("a.md"), **finding), validator.Finding(path=Path("b.md"), **finding)])
    validator._validate_findings(result, Path.cwd())
    assert any("duplicate Finding ID" in error for error in result.errors)


@pytest.mark.unit
def test_residual_risk_requires_durable_disposition():
    result = validator.Result(findings=[validator.Finding(
        id="FIND-0001", path=Path("finding.md"), kind="system_limitation",
        scope="system", evidence_status="confirmed", disposition="closed_in_place",
        evidence="code", resolution="accepted", residual_risk="Failure can recur.",
    )])
    validator._validate_findings(result, Path.cwd())
    assert any("residual risk has non-durable disposition" in error for error in result.errors)


@pytest.mark.unit
def test_last_verified_date_rejects_timestamp(tmp_path: Path):
    root = _repo(tmp_path)
    path = root / "docs/findings/FIND-0001.md"
    path.write_text(
        "---\ndocument_type: finding\nid: FIND-0001\nkind: documentation_drift\n"
        "primary_scope: documentation\nevidence_status: observed\nintroduced_by: review\n"
        "disposition: pending\nlast_verified_commit: COMMIT\n"
        "last_verified_date: 2026-07-12T00:00:00Z\n---\n"
        "# Finding\n## Observation\nDrift.\n## Evidence\nReview.\n",
        encoding="utf-8",
    )
    result = validator.Result()
    validator._validate_document(path, root, result)
    assert any("last_verified_date must use YYYY-MM-DD" in error for error in result.errors)


@pytest.mark.unit
def test_catalog_is_grouped_and_fingerprinted(tmp_path: Path, monkeypatch):
    root = _repo(tmp_path)
    result = validator.Result(findings=[validator.Finding(id="FIND-0001", path=root / "docs/findings/a.md", kind="implementation_fact", scope="system", evidence_status="confirmed", disposition="closed_in_place")])
    text = validator.catalog(result, root)
    assert "Source fingerprint: `sha256:" in text
    assert "## Findings" in text
    assert "## Decisions" in text


@pytest.mark.unit
def test_catalog_fingerprint_changes_for_equal_length_edit(tmp_path: Path):
    root = _repo(tmp_path)
    path = root / "docs/note.md"
    path.write_text("alpha", encoding="utf-8")
    first = validator.catalog(validator.Result(), root)
    path.write_text("bravo", encoding="utf-8")
    second = validator.catalog(validator.Result(), root)
    assert first != second


@pytest.mark.unit
def test_governed_directory_cannot_omit_document_type(tmp_path: Path):
    root = _repo(tmp_path)
    path = root / "docs/findings/FIND-0001.md"
    path.write_text("# Escaped finding\n", encoding="utf-8")
    result = validator.Result()
    validator._validate_document(path, root, result)
    assert any("expected document_type" in error for error in result.errors)


@pytest.mark.unit
def test_target_change_closure_ignores_other_pending_finding(tmp_path: Path):
    root = _repo(tmp_path)
    target = root / "openspec/changes/sample/findings.md"
    other = root / "docs/findings/other.md"
    other.write_text("", encoding="utf-8")
    result = validator.Result(findings=[
        validator.Finding("FIND-0001", target, "documentation_drift", "documentation", "confirmed", "closed_in_place", evidence="code", resolution="fixed"),
        validator.Finding("FIND-0002", other, "technical_debt", "system", "observed", "pending"),
    ])
    validator._validate_findings(result, root, {target.resolve()})
    assert not any("FIND-0002: blocks closure" in error for error in result.errors)


@pytest.mark.unit
def test_gate_rejects_missing_fixed_items(tmp_path: Path):
    root = _repo(tmp_path)
    (root / "openspec/changes/sample/tasks.md").write_text(
        "## Evidence Disposition Gate\n\n- [x] No new findings\n", encoding="utf-8"
    )
    result = validator.Result()
    validator.validate_change_gate(root / "openspec/changes/sample", result)
    assert any("missing fixed items" in error for error in result.errors)


@pytest.mark.unit
def test_gate_rejects_one_checkbox_stuffed_with_all_keywords(tmp_path: Path):
    root = _repo(tmp_path)
    (root / "openspec/changes/sample/tasks.md").write_text(
        "## Evidence Disposition Gate\n\n"
        "- [x] No new findings classified evidence durable disposition durable typed OpenSpec change or issue architecture impact design ambiguity\n",
        encoding="utf-8",
    )
    result = validator.Result()
    validator.validate_change_gate(root / "openspec/changes/sample", result)
    assert any("seven distinct" in error for error in result.errors)


@pytest.mark.unit
def test_planned_change_after_status_matrix_is_rejected(tmp_path: Path):
    root = _repo(tmp_path)
    (root / "docs/ARCHITECTURE.md").write_text(
        "# Architecture\n## Feature Status Matrix\n| Intent | Planned |\n"
        "## Current Flow\nrag-intent-routing is active\n", encoding="utf-8"
    )
    result = validator.Result()
    validator._validate_architecture(root, result)
    assert any("appears in active flow" in error for error in result.errors)


@pytest.mark.unit
def test_ledger_rejects_unrecognized_finding_heading(tmp_path: Path):
    path = tmp_path / "findings.md"
    path.write_text("# Change Findings\n\n## BAD-1\n\n- Evidence status: observed\n", encoding="utf-8")
    findings = validator._ledger_findings(path, path.read_text(encoding="utf-8"))
    result = validator.Result(findings=findings)
    validator._validate_findings(result, tmp_path)
    assert any("invalid Finding ID" in error for error in result.errors)


@pytest.mark.unit
def test_validation_directory_requires_typed_document(tmp_path: Path):
    root = _repo(tmp_path)
    (root / "docs/validation").mkdir()
    path = root / "docs/validation/report.md"
    path.write_text("# Untyped report\n", encoding="utf-8")
    result = validator.Result()
    validator._validate_document(path, root, result)
    assert any("expected document_type" in error for error in result.errors)
