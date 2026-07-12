"""Validate governed documentation and generate the ignored evidence catalog."""
from __future__ import annotations

import argparse, fnmatch, hashlib, re, subprocess, sys
from dataclasses import dataclass, field
from pathlib import Path

DEFAULT_ROOT = Path(__file__).resolve().parents[1]
FINDING_ID = re.compile(r"^(?:FIND-\d{4}|[A-Z][A-Z0-9-]*-F\d{3})$")
TYPED_IDS = {"adr": re.compile(r"^ADR-\d{4}$"), "known_issue": re.compile(r"^KI-[A-Z0-9]+-\d{4}$"), "enhancement": re.compile(r"^ENH-[A-Z0-9]+-\d{4}$"), "validation_report": re.compile(r"^VAL-[A-Z0-9-]+-\d{3}$")}
KINDS = {"implementation_fact", "documentation_drift", "design_ambiguity", "behavior_defect", "system_limitation", "technical_debt", "evidence_gap", "evaluation_result", "delivery_risk"}
TOP_SCOPES = {"system", "documentation", "rag", "test", "evaluation", "delivery"}
EVIDENCE_STATES = {"observed", "confirmed", "invalidated"}
DISPOSITIONS = {"pending", "architecture", "adr", "known_issue", "enhancement", "validation", "change", "issue", "closed_in_place"}
TYPE_STATUS = {"adr": {"proposed", "accepted", "superseded", "rejected"}, "known_issue": {"open", "mitigated", "resolved", "invalidated"}, "enhancement": {"candidate", "planned", "delivered", "declined"}, "validation_report": {"passed", "failed", "partial", "historical", "superseded"}}
REQUIRED = {
 "adr": {"adr_id", "status", "scope", "decision_date", "last_verified_commit", "last_verified_time"},
 "known_issue": {"issue_id", "status", "scope", "severity", "first_confirmed", "last_verified_commit", "last_verified_time"},
 "enhancement": {"enhancement_id", "status", "scope", "motivation", "last_verified_commit", "last_verified_time"},
 "validation_report": {"validation_id", "status", "scope", "source_commit", "source_fingerprint", "executed_at"},
 "finding": {"id", "kind", "primary_scope", "evidence_status", "introduced_by", "disposition", "unresolved", "last_verified_commit", "last_verified_time"},
}
EXPECTED_DIR_TYPES = {"findings": {"finding"}, "architecture/decisions": {"adr"}, "known-issues": {"known_issue"}, "enhancements": {"enhancement"}, "validation": {"validation_report", "validation_guide"}}
TARGET_PREFIX = {"architecture": "docs/ARCHITECTURE.md", "adr": "docs/architecture/decisions/", "known_issue": "docs/known-issues/", "enhancement": "docs/enhancements/", "validation": "docs/validation/", "change": "openspec/changes/"}

@dataclass
class Finding:
 id: str; path: Path; kind: str=""; scope: str=""; evidence_status: str=""; disposition: str=""; target: str=""; evidence: str=""; resolution: str=""; unresolved: bool|None=None; residual_risk: str=""
@dataclass
class Result:
 errors: list[str]=field(default_factory=list); warnings: list[str]=field(default_factory=list); findings: list[Finding]=field(default_factory=list); documents: list[tuple[str,str,str,Path,list[str]]]=field(default_factory=list)

def _scalar(v: str):
 v=v.strip()
 if v in {"null","~",""}: return None
 if v.lower() in {"true","false"}: return v.lower()=="true"
 if v=="[]": return []
 if v.startswith("[") and v.endswith("]"): return [x.strip().strip("'\"") for x in v[1:-1].split(",") if x.strip()]
 return v.strip("'\"")

def frontmatter(text: str) -> dict:
 if not text.startswith("---\n"): return {}
 end=text.find("\n---\n",4)
 if end<0: return {}
 data={}; current=None
 for raw in text[4:end].splitlines():
  if raw.startswith("  - ") and current: data.setdefault(current,[]).append(_scalar(raw[4:])); continue
  m=re.match(r"^([A-Za-z_][\w-]*):\s*(.*)$",raw)
  if m: current,val=m.groups(); data[current]=[] if not val else _scalar(val)
 return data

def _fields(body: str) -> dict:
 return {k.lower().replace(" ","_"):v.strip().strip("`") for k,v in re.findall(r"^- ([A-Za-z ]+):\s*(.*)$",body,re.M)}

def _ledger_findings(path: Path,text: str) -> list[Finding]:
 matches=list(re.finditer(r"^## (?!Evidence Disposition Gate)([^\r\n]+)\s*$",text,re.M)); out=[]
 for i,m in enumerate(matches):
  f=_fields(text[m.end():matches[i+1].start() if i+1<len(matches) else len(text)])
  raw_unresolved=f.get("unresolved")
  unresolved=None if raw_unresolved is None else raw_unresolved.lower()=="true"
  out.append(Finding(m.group(1).strip(),path,f.get("kind",""),f.get("primary_scope",""),f.get("evidence_status",""),f.get("disposition",""),"" if f.get("disposition_target","") in {"null","None"} else f.get("disposition_target",""),f.get("evidence",""),f.get("resolution_evidence","") or f.get("invalidation_evidence",""),unresolved,f.get("residual_risk","")))
 return out

def _global_finding(path: Path,meta: dict,text: str) -> Finding:
 section=lambda name:(re.search(rf"^## {name}\s*$([\s\S]*?)(?=^## |\Z)",text,re.M).group(1).strip() if re.search(rf"^## {name}\s*$([\s\S]*?)(?=^## |\Z)",text,re.M) else "")
 return Finding(str(meta.get("id") or ""),path,str(meta.get("kind") or ""),str(meta.get("primary_scope") or ""),str(meta.get("evidence_status") or ""),str(meta.get("disposition") or ""),str(meta.get("disposition_target") or ""),section("Evidence"),section("Resolution Evidence") or section("Invalidation Evidence"),meta.get("unresolved"),section("Residual Risk"))

def _relative(path: Path,root: Path) -> str:
 try: return path.resolve().relative_to(root.resolve()).as_posix()
 except ValueError: return path.as_posix()

def _expected_type(path: Path,docs: Path):
 rel=_relative(path,docs)
 if rel.startswith("templates/") or path.name=="README.md": return False
 for prefix,typ in EXPECTED_DIR_TYPES.items():
  if rel.startswith(prefix+"/"): return typ
 return False

def _validate_links(path: Path,text: str,root: Path,result: Result):
 targets=re.findall(r"!?\[[^]]*\]\(([^)]+)\)",text)+re.findall(r"^\[[^]]+\]:\s*(\S+)",text,re.M)
 for raw in targets:
  target=raw.strip().strip("<>")
  if re.match(r"^[A-Za-z][A-Za-z0-9+.-]*://",target): continue
  filepart,_,fragment=target.partition("#")
  resolved=(path.parent/filepart).resolve() if filepart else path.resolve()
  try: resolved.relative_to(root.resolve())
  except ValueError: result.errors.append(f"{_relative(path,root)}: link escapes repository: {target}"); continue
  if not resolved.exists(): result.errors.append(f"{_relative(path,root)}: broken link {target}"); continue
  if fragment and resolved.is_file() and resolved.suffix.lower()==".md":
   anchors={re.sub(r"[^a-z0-9\- ]","",h.lower()).replace(" ","-") for h in re.findall(r"^#{1,6}\s+(.+)$",resolved.read_text(encoding="utf-8"),re.M)}
   if fragment.lower() not in anchors: result.errors.append(f"{_relative(path,root)}: missing anchor {target}")

def _validate_document(path: Path,root: Path,result: Result):
 text=path.read_text(encoding="utf-8"); meta=frontmatter(text); docs=root/"docs"; expected=_expected_type(path,docs) if path.is_relative_to(docs) else False; typ=str(meta.get("document_type") or "")
 if expected and typ not in expected: result.errors.append(f"{_relative(path,root)}: expected document_type in {sorted(expected)!r}, got {typ!r}")
 if typ in REQUIRED and "templates" not in path.relative_to(root).parts:
  missing=[k for k in REQUIRED[typ] if meta.get(k) in {None,"",()}]
  if missing: result.errors.append(f"{_relative(path,root)}: missing/empty metadata {', '.join(sorted(missing))}")
 if typ=="finding" and "templates" not in path.parts: result.findings.append(_global_finding(path,meta,text))
 if typ=="finding_ledger" and "templates" not in path.parts: result.findings.extend(_ledger_findings(path,text))
 identity=str(meta.get({"adr":"adr_id","known_issue":"issue_id","enhancement":"enhancement_id","validation_report":"validation_id"}.get(typ,"") ) or "")
 if typ in TYPED_IDS and "templates" not in path.parts:
  status=str(meta.get("status") or ""); sources=list(meta.get("source_findings") or [])
  result.documents.append((typ,identity,status,path,sources))
  if not TYPED_IDS[typ].match(identity): result.errors.append(f"{_relative(path,root)}: invalid {typ} ID {identity!r}")
  if status not in TYPE_STATUS[typ]: result.errors.append(f"{_relative(path,root)}: invalid {typ} status {status!r}")
 if typ=="validation_report" and "templates" not in path.parts:
  if not re.fullmatch(r"[0-9a-f]{40}",str(meta.get("source_commit") or "")): result.errors.append(f"{_relative(path,root)}: source_commit must be 40 lowercase hex")
  if not re.fullmatch(r"sha256:[0-9a-f]{64}",str(meta.get("source_fingerprint") or "")): result.errors.append(f"{_relative(path,root)}: invalid source_fingerprint")
  if not re.match(r"^\d{4}-\d{2}-\d{2}T",str(meta.get("executed_at") or "")): result.errors.append(f"{_relative(path,root)}: invalid executed_at")
  commit=str(meta.get("source_commit") or "")
  if (root/".git").exists() and subprocess.run(["git","cat-file","-e",f"{commit}^{{commit}}"],cwd=root,capture_output=True).returncode!=0: result.errors.append(f"{_relative(path,root)}: source_commit does not exist")
 _validate_links(path,text,root,result)

def _validate_architecture(root: Path,result: Result):
 path=root/"docs/ARCHITECTURE.md"; text=path.read_text(encoding="utf-8")
 for raw in re.findall(r"`((?:(?:backend|frontend|tests|scripts|openspec|docs)/[^`*]+|(?:pyproject\.toml|\.gitignore)))`",text):
  clean=raw.rstrip(".,;:")
  if not (root/clean).exists(): result.errors.append(f"docs/ARCHITECTURE.md: missing repository path {clean}")
 matrix_match=re.search(r"^## Feature Status Matrix\s*$([\s\S]*?)(?=^## |\Z)",text,re.M)
 active=text if not matrix_match else text[:matrix_match.start()]+text[matrix_match.end():]
 for planned in ("rag-intent-routing","rag-multilevel-fallback"):
  if planned in active: result.errors.append(f"docs/ARCHITECTURE.md: planned change {planned} appears in active flow")

def _target_ok(f: Finding,root: Path,doc_sources: dict[str,list[str]]) -> bool:
 if f.disposition=="closed_in_place": return not f.target and bool(f.resolution)
 if f.disposition=="issue": return bool(re.match(r"^https://",f.target))
 prefix=TARGET_PREFIX.get(f.disposition)
 if not prefix or not f.target.startswith(prefix): return False
 target=root/f.target
 if f.disposition=="change": return target.is_dir()
 if not target.is_file(): return False
 if f.disposition!="architecture" and f.id not in doc_sources.get(f.target,[]): return False
 return True

def _validate_findings(result: Result,root: Path,closure_paths: set[Path]|None=None):
 seen={}; doc_sources={_relative(p,root):src for _,_,_,p,src in result.documents}; typed_seen={}
 for typ,identity,_,path,_ in result.documents:
  key=(typ,identity)
  if key in typed_seen: result.errors.append(f"duplicate {typ} ID {identity}: {_relative(typed_seen[key],root)} and {_relative(path,root)}")
  typed_seen[key]=path
 for f in result.findings:
  if not FINDING_ID.match(f.id): result.errors.append(f"{_relative(f.path,root)}: invalid Finding ID {f.id!r}")
  if f.id in seen: result.errors.append(f"duplicate Finding ID {f.id}: {_relative(seen[f.id],root)} and {_relative(f.path,root)}")
  seen[f.id]=f.path
  if f.kind not in KINDS: result.errors.append(f"{f.id}: invalid kind {f.kind!r}")
  if f.scope.split(".",1)[0] not in TOP_SCOPES: result.errors.append(f"{f.id}: invalid scope {f.scope!r}")
  if f.evidence_status not in EVIDENCE_STATES: result.errors.append(f"{f.id}: invalid evidence status {f.evidence_status!r}")
  if f.disposition not in DISPOSITIONS: result.errors.append(f"{f.id}: invalid disposition {f.disposition!r}")
  if f.evidence_status=="confirmed" and not f.evidence: result.errors.append(f"{f.id}: confirmed Finding lacks Evidence")
  if f.unresolved is None: result.errors.append(f"{f.id}: Unresolved must be explicitly true or false")
  if f.residual_risk and f.residual_risk.lower() not in {"none","n/a"} and f.unresolved is not True: result.errors.append(f"{f.id}: non-empty Residual risk requires Unresolved: true")
  if f.evidence_status=="invalidated" and (f.disposition!="closed_in_place" or not f.resolution): result.errors.append(f"{f.id}: invalidation requires evidence and closed_in_place")
  if f.unresolved and f.disposition not in {"pending","known_issue","enhancement","change","issue"}: result.errors.append(f"{f.id}: unresolved Finding has non-durable disposition")
  if f.disposition not in {"pending"} and not _target_ok(f,root,doc_sources): result.errors.append(f"{f.id}: invalid/missing disposition target or backlink")
  if closure_paths and f.path.resolve() in closure_paths and (f.evidence_status=="observed" or f.disposition=="pending"): result.errors.append(f"{f.id}: blocks closure ({f.evidence_status}/{f.disposition})")

def validate_change_gate(change_dir: Path,result: Result):
 tasks=change_dir/"tasks.md"; ledger=change_dir/"findings.md"; text=tasks.read_text(encoding="utf-8") if tasks.exists() else ""; label=change_dir.as_posix()
 m=re.search(r"^## (?:\d+\. )?Evidence Disposition Gate\s*$([\s\S]*?)(?=^## |\Z)",text,re.M)
 if not m:
  result.errors.append(f"{label}: missing Evidence Disposition Gate")
  if not ledger.exists(): result.errors.append(f"{label}: no ledger or checked No new findings declaration")
  return
 body=m.group(1); checks=re.findall(r"^- \[([ xX])\]\s+(.+)$",body,re.M)
 if not checks or any(mark==" " for mark,_ in checks): result.errors.append(f"{label}: Evidence Disposition Gate has unchecked or missing checklist items")
 required=("classified","evidence","durable disposition","durable typed","openspec change or issue","architecture impact","design ambiguity")
 items=[item.lower() for _,item in checks]
 missing=[term for term in required if not any(term in item for item in items)]
 if len(checks)<len(required): missing.append("seven distinct checklist items")
 if missing: result.errors.append(f"{label}: Evidence Disposition Gate missing fixed items: {', '.join(missing)}")
 ledger_findings=_ledger_findings(ledger,ledger.read_text(encoding="utf-8")) if ledger.exists() else []
 if ledger.exists() and not ledger_findings: result.errors.append(f"{label}: empty findings ledger")
 if not ledger.exists() and not any(mark.lower()=="x" and "No new findings" in item for mark,item in checks): result.errors.append(f"{label}: no ledger or checked No new findings declaration")

def _manifest(root: Path,result: Result):
 baseline_path=root/"docs/documentation-ignore-baseline.txt"
 baseline=[line.strip() for line in baseline_path.read_text(encoding="utf-8").splitlines() if line.strip() and not line.startswith("#")] if baseline_path.exists() else []
 proc=subprocess.run(["git","ls-files","--others","--ignored","--exclude-standard","docs","scripts"],cwd=root,text=True,capture_output=True)
 for rel in proc.stdout.splitlines():
  rel=rel.replace("\\","/")
  if rel=="docs/evidence-catalog.md" or "/__pycache__/" in rel or rel.endswith(".pyc") or any(fnmatch.fnmatch(rel,pattern) for pattern in baseline): continue
  result.warnings.append(f"tracking decision required: {rel}")

def catalog(result: Result,root: Path) -> str:
 docs=root/"docs"; h=hashlib.sha256()
 for p in sorted(x for x in docs.rglob("*.md") if x.name!="evidence-catalog.md"):
  h.update(_relative(p,root).encode()); h.update(b"\0"); h.update(p.read_bytes()); h.update(b"\0")
 lines=["<!-- GENERATED; DO NOT EDIT OR TRACK -->","# Evidence Catalog","",f"Source fingerprint: `sha256:{h.hexdigest()}`",""]
 lines += ["## Findings","","| ID | Kind | Scope | Evidence | Disposition | Source |","| --- | --- | --- | --- | --- | --- |"]
 for f in sorted(result.findings,key=lambda x:x.id): lines.append(f"| {f.id} | {f.kind} | {f.scope} | {f.evidence_status} | {f.disposition} | `{_relative(f.path,root)}` |")
 for title,kind in (("Decisions","adr"),("Known Issues","known_issue"),("Enhancements","enhancement"),("Validation Evidence","validation_report")):
  lines += ["",f"## {title}","","| ID | Status | Source |","| --- | --- | --- |"]
  for _,identity,status,path,_ in sorted(d for d in result.documents if d[0]==kind): lines.append(f"| {identity} | {status} | `{_relative(path,root)}` |")
 return "\n".join(lines)+"\n"

def validate(root: Path=DEFAULT_ROOT,*,closure_change: str|None=None,manifest: bool=True) -> Result:
 root=root.resolve(); docs=root/"docs"; result=Result()
 for path in sorted(docs.rglob("*.md")):
  if path.name!="evidence-catalog.md": _validate_document(path,root,result)
 for path in sorted((root/"openspec/changes").glob("*/findings.md")): _validate_document(path,root,result)
 _validate_architecture(root,result)
 closure_paths=None
 if closure_change:
  change=root/"openspec/changes"/closure_change; validate_change_gate(change,result); closure_paths={(change/"findings.md").resolve()} if (change/"findings.md").exists() else set()
 _validate_findings(result,root,closure_paths)
 if manifest and (root/".git").exists(): _manifest(root,result)
 return result

def main() -> int:
 ap=argparse.ArgumentParser(); ap.add_argument("--closure-change"); ap.add_argument("--strict-manifest",action="store_true"); ap.add_argument("--no-catalog",action="store_true"); args=ap.parse_args()
 root=DEFAULT_ROOT; result=validate(root,closure_change=args.closure_change); output=catalog(result,root)
 if not args.no_catalog: (root/"docs/evidence-catalog.md").write_text(output,encoding="utf-8")
 print(output,end="")
 for w in result.warnings: print("WARNING: "+w,file=sys.stderr)
 for e in result.errors: print("ERROR: "+e,file=sys.stderr)
 return 1 if result.errors or (args.strict_manifest and result.warnings) else 0
if __name__=="__main__": raise SystemExit(main())
