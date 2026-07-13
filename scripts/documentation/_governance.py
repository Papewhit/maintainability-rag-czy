"""Shared model for governed documentation discovery, validation, and cataloging."""
from __future__ import annotations

import hashlib
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

DEFAULT_ROOT = Path(__file__).resolve().parents[2]
NAMED_SOURCES = ("docs/ARCHITECTURE.md", "docs/evidence-governance.md")
GOVERNED_DOC_DIRS = (
    "docs/findings",
    "docs/architecture/decisions",
    "docs/known-issues",
    "docs/enhancements",
    "docs/validation",
    "docs/templates",
)
FINDING_ID = re.compile(r"^(?:FIND-\d{4}|[A-Z][A-Z0-9-]*-F\d{3})$")
TYPED_IDS = {
    "adr": re.compile(r"^ADR-\d{4}$"),
    "known_issue": re.compile(r"^KI-[A-Z0-9]+-\d{4}$"),
    "enhancement": re.compile(r"^ENH-[A-Z0-9]+-\d{4}$"),
    "validation_report": re.compile(r"^VAL-[A-Z0-9-]+-\d{3}$"),
}
KINDS = {"implementation_fact", "documentation_drift", "design_ambiguity", "behavior_defect", "system_limitation", "technical_debt", "evidence_gap", "evaluation_result", "delivery_risk"}
TOP_SCOPES = {"system", "documentation", "rag", "test", "evaluation", "delivery"}
EVIDENCE_STATES = {"observed", "confirmed", "invalidated"}
DISPOSITIONS = {"pending", "architecture", "adr", "known_issue", "enhancement", "validation", "change", "issue", "closed_in_place"}
TYPE_STATUS = {
    "adr": {"proposed", "accepted", "superseded", "rejected"},
    "known_issue": {"open", "mitigated", "resolved", "invalidated"},
    "enhancement": {"candidate", "planned", "delivered", "declined"},
    "validation_report": {"passed", "failed", "partial", "historical", "superseded"},
}
REQUIRED = {
    "adr": {"adr_id", "status", "scope", "decision_date", "last_verified_commit", "last_verified_date"},
    "known_issue": {"issue_id", "status", "scope", "severity", "first_confirmed", "last_verified_commit", "last_verified_date"},
    "enhancement": {"enhancement_id", "status", "scope", "motivation", "last_verified_commit", "last_verified_date"},
    "validation_report": {"validation_id", "status", "scope", "source_commit", "source_fingerprint", "executed_at"},
    "finding": {"id", "kind", "primary_scope", "evidence_status", "introduced_by", "disposition", "last_verified_commit", "last_verified_date"},
    "finding_ledger": {"change", "last_verified_commit", "last_verified_date"},
}
EXPECTED_DIR_TYPES = {
    "findings": {"finding"},
    "architecture/decisions": {"adr"},
    "known-issues": {"known_issue"},
    "enhancements": {"enhancement"},
    "validation": {"validation_report", "validation_guide"},
}
TARGET_PREFIX = {
    "architecture": "docs/ARCHITECTURE.md",
    "adr": "docs/architecture/decisions/",
    "known_issue": "docs/known-issues/",
    "enhancement": "docs/enhancements/",
    "validation": "docs/validation/",
    "change": "openspec/changes/",
}


@dataclass
class Finding:
    id: str
    path: Path
    kind: str = ""
    scope: str = ""
    evidence_status: str = ""
    disposition: str = ""
    target: str = ""
    evidence: str = ""
    resolution: str = ""
    residual_risk: str = ""
    last_verified_date: str = ""
    observation: str = ""


@dataclass
class Result:
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    findings: list[Finding] = field(default_factory=list)
    documents: list[tuple[str, str, str, Path, list[str]]] = field(default_factory=list)
    sources: list[Path] = field(default_factory=list)


def _scalar(value: str):
    value = value.strip()
    if value in {"null", "~", ""}:
        return None
    if value.lower() in {"true", "false"}:
        return value.lower() == "true"
    if value == "[]":
        return []
    if value.startswith("[") and value.endswith("]"):
        return [item.strip().strip("'\"") for item in value[1:-1].split(",") if item.strip()]
    return value.strip("'\"")


def frontmatter(text: str) -> dict:
    if not text.startswith("---\n"):
        return {}
    end = text.find("\n---\n", 4)
    if end < 0:
        return {}
    data: dict = {}
    current = None
    for raw in text[4:end].splitlines():
        if raw.startswith("  - ") and current:
            data.setdefault(current, []).append(_scalar(raw[4:]))
            continue
        match = re.match(r"^([A-Za-z_][\w-]*):\s*(.*)$", raw)
        if match:
            current, value = match.groups()
            data[current] = [] if not value else _scalar(value)
    return data


def _fields(body: str) -> dict:
    return {key.lower().replace(" ", "_"): value.strip().strip("`") for key, value in re.findall(r"^- ([A-Za-z ]+):\s*(.*)$", body, re.M)}


def _ledger_findings(path: Path, text: str) -> list[Finding]:
    matches = list(re.finditer(r"^## (?!Evidence Disposition Gate)([^\r\n]+)\s*$", text, re.M))
    findings: list[Finding] = []
    for index, match in enumerate(matches):
        fields = _fields(text[match.end():matches[index + 1].start() if index + 1 < len(matches) else len(text)])
        target = fields.get("disposition_target", "")
        findings.append(Finding(
            match.group(1).strip(), path, fields.get("kind", ""), fields.get("primary_scope", ""),
            fields.get("evidence_status", ""), fields.get("disposition", ""),
            "" if target in {"null", "None"} else target, fields.get("evidence", ""),
            fields.get("resolution_evidence", "") or fields.get("invalidation_evidence", ""),
            fields.get("residual_risk", ""), observation=fields.get("observation", ""),
        ))
    return findings


def _section(text: str, name: str) -> str:
    match = re.search(rf"^## {name}\s*$([\s\S]*?)(?=^## |\Z)", text, re.M)
    return match.group(1).strip() if match else ""


def _global_finding(path: Path, meta: dict, text: str) -> Finding:
    return Finding(
        str(meta.get("id") or ""), path, str(meta.get("kind") or ""), str(meta.get("primary_scope") or ""),
        str(meta.get("evidence_status") or ""), str(meta.get("disposition") or ""),
        str(meta.get("disposition_target") or ""), _section(text, "Evidence"),
        _section(text, "Resolution Evidence") or _section(text, "Invalidation Evidence"),
        _section(text, "Residual Risk"), str(meta.get("last_verified_date") or ""), _section(text, "Observation"),
    )


def _relative(path: Path, root: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def governed_sources(root: Path) -> list[Path]:
    root = root.resolve()
    paths = [root / relative for relative in NAMED_SOURCES if (root / relative).is_file()]
    for relative in GOVERNED_DOC_DIRS:
        directory = root / relative
        if directory.is_dir():
            paths.extend(path for path in directory.glob("*.md") if path.name != "evidence-catalog.md")
    changes = root / "openspec/changes"
    if changes.is_dir():
        paths.extend(changes.glob("*/findings.md"))
    return sorted(set(paths), key=lambda path: _relative(path, root))


def _expected_type(path: Path, docs: Path):
    relative = _relative(path, docs)
    if relative.startswith("templates/") or path.name == "README.md":
        return False
    for prefix, document_types in EXPECTED_DIR_TYPES.items():
        if relative.startswith(prefix + "/"):
            return document_types
    return False


def _validate_links(path: Path, text: str, root: Path, result: Result):
    targets = re.findall(r"!?\[[^]]*\]\(([^)]+)\)", text) + re.findall(r"^\[[^]]+\]:\s*(\S+)", text, re.M)
    for raw in targets:
        target = raw.strip().strip("<>")
        if re.match(r"^[A-Za-z][A-Za-z0-9+.-]*://", target):
            continue
        filepart, _, fragment = target.partition("#")
        resolved = (path.parent / filepart).resolve() if filepart else path.resolve()
        try:
            resolved.relative_to(root.resolve())
        except ValueError:
            result.errors.append(f"{_relative(path, root)}: link escapes repository: {target}")
            continue
        if not resolved.exists():
            result.errors.append(f"{_relative(path, root)}: broken link {target}")
            continue
        if fragment and resolved.is_file() and resolved.suffix.lower() == ".md":
            headings = re.findall(r"^#{1,6}\s+(.+)$", resolved.read_text(encoding="utf-8"), re.M)
            anchors = {re.sub(r"[^a-z0-9\- ]", "", heading.lower()).replace(" ", "-") for heading in headings}
            if fragment.lower() not in anchors:
                result.errors.append(f"{_relative(path, root)}: missing anchor {target}")


def _validate_document(path: Path, root: Path, result: Result):
    text = path.read_text(encoding="utf-8")
    meta = frontmatter(text)
    docs = root / "docs"
    expected = _expected_type(path, docs) if path.is_relative_to(docs) else False
    document_type = str(meta.get("document_type") or "")
    relative = _relative(path, root)
    if re.fullmatch(r"openspec/changes/[^/]+/findings\.md", relative) and document_type != "finding_ledger":
        result.errors.append(f"{relative}: expected document_type 'finding_ledger', got {document_type!r}")
    if expected and document_type not in expected:
        result.errors.append(f"{relative}: expected document_type in {sorted(expected)!r}, got {document_type!r}")
    if document_type in REQUIRED and "templates" not in path.relative_to(root).parts:
        missing = [key for key in REQUIRED[document_type] if meta.get(key) in {None, "", ()}]
        if missing:
            result.errors.append(f"{relative}: missing/empty metadata {', '.join(sorted(missing))}")
    if "last_verified_date" in meta and not re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(meta["last_verified_date"])):
        result.errors.append(f"{relative}: last_verified_date must use YYYY-MM-DD")
    if document_type == "finding" and "templates" not in path.parts:
        result.findings.append(_global_finding(path, meta, text))
    if document_type == "finding_ledger" and "templates" not in path.parts:
        result.findings.extend(_ledger_findings(path, text))
    id_key = {"adr": "adr_id", "known_issue": "issue_id", "enhancement": "enhancement_id", "validation_report": "validation_id"}.get(document_type, "")
    identity = str(meta.get(id_key) or "")
    if document_type in TYPED_IDS and "templates" not in path.parts:
        status = str(meta.get("status") or "")
        sources = list(meta.get("source_findings") or [])
        result.documents.append((document_type, identity, status, path, sources))
        if not TYPED_IDS[document_type].match(identity):
            result.errors.append(f"{relative}: invalid {document_type} ID {identity!r}")
        if status not in TYPE_STATUS[document_type]:
            result.errors.append(f"{relative}: invalid {document_type} status {status!r}")
    if document_type == "validation_report" and "templates" not in path.parts:
        commit = str(meta.get("source_commit") or "")
        if not re.fullmatch(r"[0-9a-f]{40}", commit):
            result.errors.append(f"{relative}: source_commit must be 40 lowercase hex")
        if not re.fullmatch(r"sha256:[0-9a-f]{64}", str(meta.get("source_fingerprint") or "")):
            result.errors.append(f"{relative}: invalid source_fingerprint")
        if not re.match(r"^\d{4}-\d{2}-\d{2}T", str(meta.get("executed_at") or "")):
            result.errors.append(f"{relative}: invalid executed_at")
        if (root / ".git").exists() and subprocess.run(["git", "cat-file", "-e", f"{commit}^{{commit}}"], cwd=root, capture_output=True).returncode != 0:
            result.errors.append(f"{relative}: source_commit does not exist")
    _validate_links(path, text, root, result)


def _validate_architecture(root: Path, result: Result):
    path = root / "docs/ARCHITECTURE.md"
    if not path.exists():
        result.errors.append("docs/ARCHITECTURE.md: missing current architecture authority")
        return
    text = path.read_text(encoding="utf-8")
    for raw in re.findall(r"`((?:(?:backend|frontend|tests|scripts|openspec|docs)/[^`*]+|(?:pyproject\.toml|\.gitignore)))`", text):
        clean = raw.rstrip(".,;:")
        if not (root / clean).exists():
            result.errors.append(f"docs/ARCHITECTURE.md: missing repository path {clean}")
    matrix = re.search(r"^## Feature Status Matrix\s*$([\s\S]*?)(?=^## |\Z)", text, re.M)
    active = text if not matrix else text[:matrix.start()] + text[matrix.end():]
    for planned in ("rag-intent-routing", "rag-multilevel-fallback"):
        if planned in active:
            result.errors.append(f"docs/ARCHITECTURE.md: planned change {planned} appears in active flow")


def _validate_agent_routing(root: Path, result: Result):
    path = root / "AGENTS.md"
    if not path.exists():
        result.errors.append("AGENTS.md: missing repository instruction entry point")
        return
    text = path.read_text(encoding="utf-8")
    _validate_links(path, text, root, result)
    for required in ("docs/ARCHITECTURE.md", "docs/evidence-governance.md", "Architecture impact: yes/no", "New Finding: yes/no"):
        if required not in text:
            result.errors.append(f"AGENTS.md: missing architecture/evidence routing token {required!r}")
    governance = root / "docs/evidence-governance.md"
    governed = governance.read_text(encoding="utf-8") if governance.exists() else ""
    for heading in ("## OpenSpec Producer Workflow", "## Non-OpenSpec Producer Workflow", "## Finding and Using Governed Documentation", "## Operational Procedures", "### Global Finding Inbox Report Procedure"):
        if heading not in governed:
            result.errors.append(f"docs/evidence-governance.md: missing required workflow/procedure heading {heading}")
    for relative in ("docs/templates/finding.md", "docs/templates/change-findings.md", "docs/templates/adr.md", "docs/templates/known-issue.md", "docs/templates/enhancement.md", "docs/templates/validation-report.md"):
        if not (root / relative).is_file():
            result.errors.append(f"agent governance: missing template path {relative}")


def _is_global_finding(finding: Finding, root: Path) -> bool:
    return finding.path.resolve().is_relative_to((root / "docs/findings").resolve()) and finding.path.name != "README.md"


def _target_ok(finding: Finding, root: Path, doc_sources: dict[str, list[str]]) -> bool:
    if finding.disposition == "closed_in_place":
        return not finding.target and bool(finding.resolution)
    if finding.disposition == "issue":
        return bool(re.match(r"^https://", finding.target))
    prefix = TARGET_PREFIX.get(finding.disposition)
    if not prefix or not finding.target.startswith(prefix):
        return False
    target = root / finding.target
    if finding.disposition == "change":
        return target.is_dir()
    if not target.is_file():
        return False
    return finding.disposition == "architecture" or finding.id in doc_sources.get(finding.target, [])


def _validate_findings(result: Result, root: Path, closure_paths: set[Path] | None = None):
    seen: dict[str, Path] = {}
    doc_sources = {_relative(path, root): sources for _, _, _, path, sources in result.documents}
    typed_seen: dict[tuple[str, str], Path] = {}
    for document_type, identity, _, path, _ in result.documents:
        key = (document_type, identity)
        if key in typed_seen:
            result.errors.append(f"duplicate {document_type} ID {identity}: {_relative(typed_seen[key], root)} and {_relative(path, root)}")
        typed_seen[key] = path
    for finding in result.findings:
        if not FINDING_ID.match(finding.id):
            result.errors.append(f"{_relative(finding.path, root)}: invalid Finding ID {finding.id!r}")
        if finding.id in seen:
            result.errors.append(f"duplicate Finding ID {finding.id}: {_relative(seen[finding.id], root)} and {_relative(finding.path, root)}")
        seen[finding.id] = finding.path
        if finding.kind not in KINDS:
            result.errors.append(f"{finding.id}: invalid kind {finding.kind!r}")
        if finding.scope.split(".", 1)[0] not in TOP_SCOPES:
            result.errors.append(f"{finding.id}: invalid scope {finding.scope!r}")
        if finding.evidence_status not in EVIDENCE_STATES:
            result.errors.append(f"{finding.id}: invalid evidence status {finding.evidence_status!r}")
        if finding.disposition not in DISPOSITIONS:
            result.errors.append(f"{finding.id}: invalid disposition {finding.disposition!r}")
        if not finding.observation:
            result.errors.append(f"{finding.id}: Finding lacks Observation")
        if not finding.evidence:
            result.errors.append(f"{finding.id}: Finding lacks Evidence")
        if finding.evidence_status == "invalidated" and (not finding.evidence or finding.disposition != "closed_in_place" or not finding.resolution):
            result.errors.append(f"{finding.id}: invalidation requires Evidence and closed_in_place")
        if _is_global_finding(finding, root):
            valid = (
                (finding.evidence_status == "observed" and finding.disposition == "pending")
                or (finding.evidence_status == "confirmed" and finding.disposition != "pending")
                or (finding.evidence_status == "invalidated" and finding.disposition == "closed_in_place")
            )
            if not valid:
                result.errors.append(f"{finding.id}: invalid global Finding lifecycle combination ({finding.evidence_status}/{finding.disposition})")
        if finding.residual_risk and finding.residual_risk.lower() not in {"none", "n/a"} and finding.disposition not in {"pending", "known_issue", "enhancement", "change", "issue"}:
            result.errors.append(f"{finding.id}: residual risk has non-durable disposition")
        if finding.disposition != "pending" and not _target_ok(finding, root, doc_sources):
            result.errors.append(f"{finding.id}: invalid/missing disposition target or backlink")
        if closure_paths and finding.path.resolve() in closure_paths and (finding.evidence_status == "observed" or finding.disposition == "pending"):
            result.errors.append(f"{finding.id}: blocks closure ({finding.evidence_status}/{finding.disposition})")


def validate_change_gate(change_dir: Path, result: Result):
    tasks = change_dir / "tasks.md"
    ledger = change_dir / "findings.md"
    text = tasks.read_text(encoding="utf-8") if tasks.exists() else ""
    label = change_dir.as_posix()
    match = re.search(r"^## (?:\d+\. )?Evidence Disposition Gate\s*$([\s\S]*?)(?=^## |\Z)", text, re.M)
    if not match:
        result.errors.append(f"{label}: missing Evidence Disposition Gate")
        if not ledger.exists():
            result.errors.append(f"{label}: no ledger or checked No new findings declaration")
        return
    body = match.group(1)
    checks = re.findall(r"^- \[([ xX])\]\s+(.+)$", body, re.M)
    if not checks or any(mark == " " for mark, _ in checks):
        result.errors.append(f"{label}: Evidence Disposition Gate has unchecked or missing checklist items")
    required = ("classified", "evidence", "durable disposition", "durable typed", "openspec change or issue", "architecture impact", "design ambiguity")
    items = [item.lower() for _, item in checks]
    missing = [term for term in required if not any(term in item for item in items)]
    if len(checks) < len(required):
        missing.append("seven distinct checklist items")
    if missing:
        result.errors.append(f"{label}: Evidence Disposition Gate missing fixed items: {', '.join(missing)}")
    ledger_findings = _ledger_findings(ledger, ledger.read_text(encoding="utf-8")) if ledger.exists() else []
    if ledger.exists() and not ledger_findings:
        result.errors.append(f"{label}: empty findings ledger")
    if not ledger.exists() and not any(mark.lower() == "x" and "No new findings" in item for mark, item in checks):
        result.errors.append(f"{label}: no ledger or checked No new findings declaration")


def _is_delivery_path(relative: str) -> bool:
    path = Path(relative)
    if relative in NAMED_SOURCES:
        return True
    if path.suffix.lower() == ".md" and path.parent.as_posix() in GOVERNED_DOC_DIRS and path.name != "evidence-catalog.md":
        return True
    if path.suffix.lower() == ".py" and path.parent.as_posix() == "scripts/documentation":
        return True
    return bool(re.fullmatch(r"openspec/changes/[^/]+/findings\.md", relative))


def _delivery_warnings(root: Path, result: Result):
    if not (root / ".git").exists():
        return
    scopes = [*NAMED_SOURCES, *GOVERNED_DOC_DIRS, "openspec/changes", "scripts/documentation"]
    process = subprocess.run(
        ["git", "ls-files", "--others", "--ignored", "--exclude-standard", "--", *scopes],
        cwd=root, text=True, capture_output=True,
    )
    for raw in process.stdout.splitlines():
        relative = raw.replace("\\", "/")
        if _is_delivery_path(relative):
            result.warnings.append(f"ignored and untracked governed path: {relative}")


def _collect(root: Path, *, closure_change: str | None = None, delivery: bool = False) -> Result:
    root = root.resolve()
    result = Result()
    result.sources = governed_sources(root)
    for path in result.sources:
        _validate_document(path, root, result)
    _validate_architecture(root, result)
    _validate_agent_routing(root, result)
    closure_paths = None
    if closure_change:
        change = root / "openspec/changes" / closure_change
        if not change.is_dir():
            result.errors.append(f"openspec change not found: {closure_change}")
            closure_paths = set()
        else:
            validate_change_gate(change, result)
            closure_paths = {(change / "findings.md").resolve()} if (change / "findings.md").exists() else set()
    _validate_findings(result, root, closure_paths)
    if delivery:
        _delivery_warnings(root, result)
    return result


def validate(root: Path = DEFAULT_ROOT, *, delivery: bool = True) -> Result:
    return _collect(root, delivery=delivery)


def check_change(root: Path, change_name: str) -> Result:
    return _collect(root, closure_change=change_name)


def finding_inbox(result: Result, root: Path) -> list[Finding]:
    return sorted(
        (finding for finding in result.findings if _is_global_finding(finding, root) and finding.evidence_status == "observed" and finding.disposition == "pending"),
        key=lambda finding: (finding.last_verified_date, finding.id),
    )


def finding_inbox_report(result: Result, root: Path) -> str:
    lines = ["# Global Finding Inbox", "", "Unconfirmed global evidence (`observed + pending`), oldest verified first.", "", "| ID | Kind | Scope | Last verified date | Source |", "| --- | --- | --- | --- | --- |"]
    inbox = finding_inbox(result, root)
    if inbox:
        for finding in inbox:
            lines.append(f"| {finding.id} | {finding.kind} | {finding.scope} | {finding.last_verified_date} | `{_relative(finding.path, root)}` |")
    else:
        lines.append("| _None_ |  |  |  |  |")
    return "\n".join(lines) + "\n"


def _catalog_link(path: Path, root: Path) -> str:
    relative = _relative(path, root)
    href = relative[5:] if relative.startswith("docs/") else "../" + relative
    return f"[{relative}]({href})"


def active_changes(root: Path) -> list[Path]:
    changes = root / "openspec/changes"
    return sorted((path for path in changes.iterdir() if path.is_dir() and path.name != "archive"), key=lambda path: path.name) if changes.is_dir() else []


def source_fingerprint(result: Result, root: Path) -> str:
    digest = hashlib.sha256()
    sources = result.sources or governed_sources(root)
    for path in sources:
        digest.update(_relative(path, root).encode())
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    for path in active_changes(root):
        digest.update(b"active-change\0")
        digest.update(path.name.encode())
        digest.update(b"\0")
    return "sha256:" + digest.hexdigest()


def catalog(result: Result, root: Path) -> str:
    fingerprint = source_fingerprint(result, root)
    lines = [
        "<!-- GENERATED; DO NOT EDIT OR TRACK -->", "# Governed Documentation Catalog", "",
        "Generated navigation; linked source documents remain authoritative. Regenerate before each catalog-backed lookup.", "",
        "- Current system behavior: [ARCHITECTURE.md](ARCHITECTURE.md)",
        "- Usage and status meanings: [Documentation Evidence Governance](evidence-governance.md)",
        "- Regenerate: `uv run python scripts/documentation/catalog.py build`",
        "- Global Finding Inbox entries are unconfirmed evidence, not current facts or scheduled work.", "",
        f"Source fingerprint: `{fingerprint}`", "", "## Authority Entry Points", "",
        "| Need | Authority |", "| --- | --- |",
        "| Current behavior | [ARCHITECTURE.md](ARCHITECTURE.md) |",
        "| Stable contracts | [OpenSpec specs](../openspec/specs/) |",
        "| Intended work | [Active OpenSpec changes](../openspec/changes/) and the project issue tracker |",
        "| Governance and lookup workflow | [Documentation Evidence Governance](evidence-governance.md) |", "",
        "## Active OpenSpec Changes", "", "The repository can enumerate OpenSpec changes; external issues remain in the project issue tracker.", "",
        "| Change | Source |", "| --- | --- |",
    ]
    for path in active_changes(root):
        lines.append(f"| {path.name} | {_catalog_link(path, root)} |")
    lines += ["", "## Global Finding Inbox", "", "Unconfirmed global evidence (`observed + pending`), oldest verified first.", "", "| ID | Kind | Scope | Last verified date | Source |", "| --- | --- | --- | --- | --- |"]
    inbox = finding_inbox(result, root)
    if inbox:
        for finding in inbox:
            lines.append(f"| {finding.id} | {finding.kind} | {finding.scope} | {finding.last_verified_date} | {_catalog_link(finding.path, root)} |")
    else:
        lines.append("| _None_ |  |  |  |  |")
    lines += ["", "## Findings", "", "| ID | Kind | Scope | Evidence | Disposition | Source |", "| --- | --- | --- | --- | --- | --- |"]
    for finding in sorted(result.findings, key=lambda item: item.id):
        lines.append(f"| {finding.id} | {finding.kind} | {finding.scope} | {finding.evidence_status} | {finding.disposition} | {_catalog_link(finding.path, root)} |")
    for title, document_type in (("Decisions", "adr"), ("Known Issues", "known_issue"), ("Enhancements", "enhancement"), ("Validation Evidence", "validation_report")):
        lines += ["", f"## {title}", "", "| ID | Status | Source |", "| --- | --- | --- |"]
        for _, identity, status, path, _ in sorted((document for document in result.documents if document[0] == document_type), key=lambda item: item[1]):
            lines.append(f"| {identity} | {status} | {_catalog_link(path, root)} |")
    return "\n".join(lines) + "\n"


def print_diagnostics(result: Result):
    for warning in result.warnings:
        print("WARNING: " + warning, file=sys.stderr)
    for error in result.errors:
        print("ERROR: " + error, file=sys.stderr)
