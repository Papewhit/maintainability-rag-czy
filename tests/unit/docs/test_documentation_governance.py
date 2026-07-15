from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest


TOOLS = Path(__file__).resolve().parents[3] / "scripts" / "documentation"
sys.path.insert(0, str(TOOLS))
import _governance as validator


def _load_cli(filename: str, module_name: str):
    spec = importlib.util.spec_from_file_location(module_name, TOOLS / filename)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


validate_cli = _load_cli("validate.py", "documentation_validate_cli")
check_change_cli = _load_cli("check_change.py", "documentation_check_change_cli")
catalog_cli = _load_cli("catalog.py", "documentation_catalog_cli")


def _repo(tmp_path: Path, finding: str = "") -> Path:
    (tmp_path / "docs/findings").mkdir(parents=True)
    (tmp_path / "docs/templates").mkdir(parents=True)
    (tmp_path / "openspec/changes/sample").mkdir(parents=True)
    (tmp_path / "openspec/specs").mkdir(parents=True)
    for name in ("finding", "change-findings", "adr", "known-issue", "enhancement", "validation-report"):
        (tmp_path / f"docs/templates/{name}.md").write_text(f"# {name}\n", encoding="utf-8")
    (tmp_path / "docs/evidence-governance.md").write_text(
        "# Governance\n"
        "## OpenSpec Producer Workflow\n"
        "## Non-OpenSpec Producer Workflow\n"
        "## Finding and Using Governed Documentation\n"
        "## Operational Procedures\n"
        "### Global Finding Inbox Report Procedure\n",
        encoding="utf-8",
    )
    (tmp_path / "AGENTS.md").write_text(
        "[Architecture](docs/ARCHITECTURE.md)\n"
        "[Governance](docs/evidence-governance.md)\n"
        "Architecture impact: yes/no\nNew Finding: yes/no\n",
        encoding="utf-8",
    )
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
    assert "# Governed Documentation Catalog" in text
    assert "Regenerate: `uv run python scripts/documentation/catalog.py build`" in text
    assert "[Documentation Evidence Governance](evidence-governance.md)" in text


@pytest.mark.unit
def test_catalog_fingerprint_ignores_unrelated_equal_length_edit(tmp_path: Path):
    root = _repo(tmp_path)
    path = root / "docs/note.md"
    path.write_text("alpha", encoding="utf-8")
    first = validator.catalog(validator.Result(), root)
    path.write_text("bravo", encoding="utf-8")
    second = validator.catalog(validator.Result(), root)
    assert first == second


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
def test_planned_change_slug_inside_filename_is_not_rejected(tmp_path: Path):
    root = _repo(tmp_path)
    (root / "docs/ARCHITECTURE.md").write_text(
        "# Architecture\n"
        "The `.env.rag-intent-routing-workflow.example` file is validation-only.\n"
        "## Feature Status Matrix\n"
        "| Intent | Implemented, default disabled |\n",
        encoding="utf-8",
    )

    result = validator.Result()
    validator._validate_architecture(root, result)

    assert not any("appears in active flow" in error for error in result.errors)


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


@pytest.mark.unit
@pytest.mark.parametrize(
    ("state", "disposition", "resolution"),
    [
        ("observed", "pending", ""),
        ("confirmed", "closed_in_place", "verified and accepted"),
        ("invalidated", "closed_in_place", "disproved"),
    ],
)
def test_valid_global_finding_lifecycle_combinations(
    tmp_path: Path, state: str, disposition: str, resolution: str
):
    root = _repo(tmp_path)
    finding = validator.Finding(
        id="FIND-0001", path=root / "docs/findings/FIND-0001.md",
        kind="design_ambiguity", scope="system", evidence_status=state,
        disposition=disposition, evidence="review", resolution=resolution,
        last_verified_date="2026-07-01", observation="Observed behavior.",
    )
    result = validator.Result(findings=[finding])
    validator._validate_findings(result, root)
    assert not any("invalid global Finding lifecycle" in error for error in result.errors)


@pytest.mark.unit
@pytest.mark.parametrize(
    ("state", "disposition"),
    [("observed", "architecture"), ("confirmed", "pending"), ("invalidated", "pending")],
)
def test_invalid_global_finding_lifecycle_combinations_are_rejected(
    tmp_path: Path, state: str, disposition: str
):
    root = _repo(tmp_path)
    finding = validator.Finding(
        id="FIND-0001", path=root / "docs/findings/FIND-0001.md",
        kind="design_ambiguity", scope="system", evidence_status=state,
        disposition=disposition, evidence="review", last_verified_date="2026-07-01",
        observation="Observed behavior.",
    )
    result = validator.Result(findings=[finding])
    validator._validate_findings(result, root)
    assert any("invalid global Finding lifecycle" in error for error in result.errors)


@pytest.mark.unit
def test_change_local_observed_pending_remains_valid_during_work(tmp_path: Path):
    root = _repo(tmp_path)
    finding = validator.Finding(
        id="SAMPLE-F001", path=root / "openspec/changes/sample/findings.md",
        kind="design_ambiguity", scope="system", evidence_status="observed",
        disposition="pending", evidence="review", observation="Observed behavior.",
    )
    result = validator.Result(findings=[finding])
    validator._validate_findings(result, root)
    assert not any("invalid global Finding lifecycle" in error for error in result.errors)


@pytest.mark.unit
def test_finding_inbox_filters_global_records_and_orders_oldest_first(tmp_path: Path):
    root = _repo(tmp_path)
    findings = [
        validator.Finding("FIND-0002", root / "docs/findings/b.md", "evidence_gap", "test", "observed", "pending", last_verified_date="2026-07-02"),
        validator.Finding("FIND-0001", root / "docs/findings/a.md", "evidence_gap", "test", "observed", "pending", last_verified_date="2026-07-01"),
        validator.Finding("FIND-0003", root / "docs/findings/c.md", "evidence_gap", "test", "confirmed", "closed_in_place", resolution="done", last_verified_date="2026-06-01"),
        validator.Finding("SAMPLE-F001", root / "openspec/changes/sample/findings.md", "evidence_gap", "test", "observed", "pending", last_verified_date="2026-05-01"),
    ]
    result = validator.Result(findings=findings)
    assert [finding.id for finding in validator.finding_inbox(result, root)] == ["FIND-0001", "FIND-0002"]


@pytest.mark.unit
def test_finding_inbox_uses_id_as_equal_date_tiebreak(tmp_path: Path):
    root = _repo(tmp_path)
    findings = [
        validator.Finding("FIND-0002", root / "docs/findings/b.md", "evidence_gap", "test", "observed", "pending", last_verified_date="2026-07-01"),
        validator.Finding("FIND-0001", root / "docs/findings/a.md", "evidence_gap", "test", "observed", "pending", last_verified_date="2026-07-01"),
    ]
    result = validator.Result(findings=findings)
    assert [finding.id for finding in validator.finding_inbox(result, root)] == ["FIND-0001", "FIND-0002"]


@pytest.mark.unit
def test_finding_inbox_report_has_required_columns_and_empty_success(tmp_path: Path):
    root = _repo(tmp_path)
    text = validator.finding_inbox_report(validator.Result(), root)
    assert "| ID | Kind | Scope | Last verified date | Source |" in text
    assert "| _None_ |" in text


@pytest.mark.unit
def test_finding_inbox_cli_does_not_write_catalog(tmp_path: Path, monkeypatch):
    root = _repo(tmp_path)
    monkeypatch.setattr(catalog_cli, "DEFAULT_ROOT", root)
    monkeypatch.setattr(sys, "argv", [str(TOOLS / "catalog.py"), "inbox"])
    assert catalog_cli.main() == 0
    assert not (root / "docs/evidence-catalog.md").exists()


@pytest.mark.unit
def test_catalog_inbox_matches_selector_and_uses_clickable_links(tmp_path: Path):
    root = _repo(tmp_path)
    source = root / "docs/findings/FIND-0001.md"
    source.write_text("# Finding\n", encoding="utf-8")
    finding = validator.Finding(
        "FIND-0001", source, "evidence_gap", "test",
        "observed", "pending", last_verified_date="2026-07-01",
    )
    result = validator.Result(findings=[finding])
    text = validator.catalog(result, root)
    inbox = validator.finding_inbox(result, root)
    assert [item.id for item in inbox] == ["FIND-0001"]
    assert "## Global Finding Inbox" in text
    assert "[docs/findings/FIND-0001.md](findings/FIND-0001.md)" in text
    assert "`docs/findings/FIND-0001.md`" not in text
    catalog_path = root / "docs/evidence-catalog.md"
    catalog_path.write_text(text, encoding="utf-8")
    link_result = validator.Result()
    validator._validate_links(catalog_path, text, root, link_result)
    assert link_result.errors == []


@pytest.mark.unit
def test_agent_routing_requires_named_workflow_anchor(tmp_path: Path):
    root = _repo(tmp_path)
    governance = root / "docs/evidence-governance.md"
    governance.write_text(governance.read_text(encoding="utf-8").replace("## OpenSpec Producer Workflow", "## Missing"), encoding="utf-8")
    result = validator.Result()
    validator._validate_agent_routing(root, result)
    assert any("OpenSpec Producer Workflow" in error for error in result.errors)


@pytest.mark.unit
def test_malformed_change_ledger_cannot_bypass_closure(tmp_path: Path):
    root = _repo(tmp_path)
    (root / "openspec/changes/sample/findings.md").write_text(
        "# Change Findings\n\n## SAMPLE-F001\n\n"
        "- Kind: design_ambiguity\n- Primary scope: system\n"
        "- Evidence status: observed\n- Observation: Ambiguous.\n"
        "- Evidence: Review.\n- Disposition: pending\n",
        encoding="utf-8",
    )
    result = validator.check_change(root, "sample")
    assert any("expected document_type 'finding_ledger'" in error for error in result.errors)


@pytest.mark.unit
def test_invalidated_finding_requires_evidence(tmp_path: Path):
    root = _repo(tmp_path)
    finding = validator.Finding(
        "FIND-0001", root / "docs/findings/FIND-0001.md", "evidence_gap", "test",
        "invalidated", "closed_in_place", resolution="disproved",
        last_verified_date="2026-07-01", observation="Reported behavior.",
    )
    result = validator.Result(findings=[finding])
    validator._validate_findings(result, root)
    assert any("invalidation requires Evidence" in error for error in result.errors)


@pytest.mark.unit
def test_global_inbox_record_requires_observation_and_evidence(tmp_path: Path):
    root = _repo(tmp_path)
    path = root / "docs/findings/FIND-0001.md"
    path.write_text(
        "---\ndocument_type: finding\nid: FIND-0001\nkind: evidence_gap\n"
        "primary_scope: test\nevidence_status: observed\nintroduced_by: review\n"
        "disposition: pending\nlast_verified_commit: COMMIT\nlast_verified_date: 2026-07-01\n---\n"
        "# Unsupported inbox entry\n## Observation\n\n## Evidence\n",
        encoding="utf-8",
    )
    result = validator.validate(root, delivery=False)
    assert any("Finding lacks Observation" in error for error in result.errors)
    assert any("Finding lacks Evidence" in error for error in result.errors)


@pytest.mark.unit
def test_catalog_fingerprint_changes_when_change_ledger_changes(tmp_path: Path):
    root = _repo(tmp_path)
    ledger = root / "openspec/changes/sample/findings.md"
    ledger.write_text("alpha", encoding="utf-8")
    first = validator.catalog(validator.Result(), root)
    ledger.write_text("bravo", encoding="utf-8")
    second = validator.catalog(validator.Result(), root)
    assert first != second


@pytest.mark.unit
def test_catalog_exposes_intended_work_and_active_changes(tmp_path: Path):
    root = _repo(tmp_path)
    text = validator.catalog(validator.Result(), root)
    assert "| Intended work | [Active OpenSpec changes](../openspec/changes/)" in text
    assert "## Active OpenSpec Changes" in text
    assert "[openspec/changes/sample](../openspec/changes/sample)" in text


@pytest.mark.unit
def test_governed_discovery_is_fixed_and_non_recursive(tmp_path: Path):
    root = _repo(tmp_path)
    (root / "docs/known-issues").mkdir()
    direct = root / "docs/known-issues/direct.md"
    direct.write_text("# Direct\n", encoding="utf-8")
    (root / "docs/known-issues/nested").mkdir()
    nested = root / "docs/known-issues/nested/hidden.md"
    nested.write_text("# Nested\n", encoding="utf-8")
    unrelated = root / "docs/unrelated.md"
    unrelated.write_text("# Unrelated\n", encoding="utf-8")

    discovered = set(validator.governed_sources(root))

    assert direct in discovered
    assert nested not in discovered
    assert unrelated not in discovered


@pytest.mark.unit
def test_structural_delivery_warnings_ignore_unrelated_files_and_baseline(tmp_path: Path):
    root = tmp_path
    (root / "docs/known-issues").mkdir(parents=True)
    (root / "scripts/documentation").mkdir(parents=True)
    (root / "docs/known-issues/local.md").write_text("local", encoding="utf-8")
    (root / "docs/unrelated.md").write_text("unrelated", encoding="utf-8")
    (root / "scripts/documentation/local.py").write_text("", encoding="utf-8")
    (root / "scripts/spike.py").write_text("", encoding="utf-8")
    (root / "docs/documentation-ignore-baseline.txt").write_text("docs/known-issues/*\n", encoding="utf-8")
    (root / ".gitignore").write_text("docs/*\nscripts/\n", encoding="utf-8")
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    result = validator.Result()

    validator._delivery_warnings(root, result)

    assert any("docs/known-issues/local.md" in warning for warning in result.warnings)
    assert any("scripts/documentation/local.py" in warning for warning in result.warnings)
    assert not any("docs/unrelated.md" in warning for warning in result.warnings)
    assert not any("scripts/spike.py" in warning for warning in result.warnings)


@pytest.mark.unit
def test_validate_command_is_read_only_and_warnings_do_not_fail(tmp_path: Path, monkeypatch):
    root = _repo(tmp_path)
    catalog_path = root / "docs/evidence-catalog.md"
    catalog_path.write_text("unchanged", encoding="utf-8")
    monkeypatch.setattr(validate_cli, "DEFAULT_ROOT", root)
    monkeypatch.setattr(validator, "_delivery_warnings", lambda _root, result: result.warnings.append("local detail"))

    assert validate_cli.main([]) == 0
    assert catalog_path.read_text(encoding="utf-8") == "unchanged"


@pytest.mark.unit
def test_check_change_command_has_one_read_only_purpose(tmp_path: Path, monkeypatch):
    root = _repo(tmp_path)
    monkeypatch.setattr(check_change_cli, "DEFAULT_ROOT", root)
    monkeypatch.setattr(sys, "argv", [str(TOOLS / "check_change.py"), "sample"])

    assert check_change_cli.main() == 0
    assert not (root / "docs/evidence-catalog.md").exists()


@pytest.mark.unit
def test_catalog_build_is_atomic_when_sources_are_invalid(tmp_path: Path, monkeypatch):
    root = _repo(tmp_path)
    (root / "docs/known-issues").mkdir()
    (root / "docs/known-issues/invalid.md").write_text("# Missing metadata\n", encoding="utf-8")
    catalog_path = root / "docs/evidence-catalog.md"
    catalog_path.write_text("previous", encoding="utf-8")
    monkeypatch.setattr(catalog_cli, "DEFAULT_ROOT", root)
    monkeypatch.setattr(sys, "argv", [str(TOOLS / "catalog.py"), "build"])

    assert catalog_cli.main() == 1
    assert catalog_path.read_text(encoding="utf-8") == "previous"
    assert not (root / "docs/.evidence-catalog.md.tmp").exists()


@pytest.mark.unit
def test_catalog_build_writes_concise_summary(tmp_path: Path, monkeypatch, capsys):
    root = _repo(tmp_path)
    monkeypatch.setattr(catalog_cli, "DEFAULT_ROOT", root)
    monkeypatch.setattr(sys, "argv", [str(TOOLS / "catalog.py"), "build"])

    assert catalog_cli.main() == 0
    output = capsys.readouterr().out
    assert "Wrote docs/evidence-catalog.md" in output
    assert "Documents:" in output
    assert "Inbox entries:" in output
    assert "Fingerprint: sha256:" in output
    assert "# Governed Documentation Catalog" not in output


@pytest.mark.unit
def test_current_governance_uses_three_command_surface():
    governance = (Path(__file__).resolve().parents[3] / "docs/evidence-governance.md").read_text(encoding="utf-8")
    assert "scripts/documentation/validate.py" in governance
    assert "scripts/documentation/check_change.py" in governance
    assert "scripts/documentation/catalog.py build" in governance
    assert "scripts/documentation/catalog.py inbox" in governance
    assert "scripts/validate_documentation.py" not in governance
    assert "documentation-ignore-baseline.txt" not in governance
