---
document_type: governance
status: current
scope: documentation
last_verified_commit: 8babe339cda636936c6c0af3c95a99e7c77c2f19
last_verified_date: 2026-07-12
---

# Documentation Evidence Governance

## Purpose and Authority

This governance records what is known and why. Evidence is not a backlog: Findings and validation capture knowledge; OpenSpec changes and issues capture intended work.

| Information | Authority |
| --- | --- |
| Current behavior | `docs/ARCHITECTURE.md` |
| Stable contract | `openspec/specs/<capability>/spec.md` |
| Long-lived decision | `docs/architecture/decisions/ADR-*.md` |
| Confirmed unresolved problem | `docs/known-issues/*.md` |
| Non-defect future opportunity | `docs/enhancements/*.md` |
| Change-local discovery/trade-off | change `design.md` and conditional `findings.md` |
| Reproducible test/evaluation evidence | `docs/validation/*.md` or change evidence |
| Work schedule | OpenSpec change or issue |

## Capture, Disposition, Consumption

1. **Capture** a material observation in its originating change, validation, review, or global Finding.
2. **Disposition** it by confirming or invalidating evidence and selecting a durable target.
3. **Consume** the typed authority appropriate to the question; use the generated catalog only to discover and trace it.

A Finding is a discovery protocol that supports the consolidation of temporary findings. ADRs, known issues, enhancements, and validation reports have purpose-specific templates. An enhancement may originate as an idea and need no source Finding.

## Finding Capture

Use `openspec/changes/<change>/findings.md` for change-related findings. Outside OpenSpec workflow, use one file per Finding in `docs/findings/`. Do not record casual ideas, ordinary task progress, or schedules.

Record a Finding when it may change design/acceptance, become a limitation/debt/enhancement, needs evidence to close, or must be dispositioned before change closure.

### Finding Record Vocabulary

This is the maximum vocabulary for a Finding record, not a frontmatter schema and not a base schema inherited by other document types. It has two representations:

- **Metadata** exists for identity, indexing, relationships, and verification.
- **Body sections** hold the knowledge narrative. They are not duplicated into frontmatter.

Global and change-local Finding templates select different serializations of this same record vocabulary. ADR, known-issue, enhancement, and validation templates are independent typed contracts; they may reuse common field meanings such as `scope` or `last_verified_date`, but they do not inherit the Finding vocabulary.

Finding metadata:

```yaml
id:                 # stable identity
kind:               # discovery nature
primary_scope:      # governed top-level or dotted scope
scopes:             # optional additional scopes
evidence_status:    # observed | confirmed | invalidated
introduced_by:      # origin
disposition:        # durable route
disposition_target: # target identity/path
last_verified_commit:
last_verified_date: # YYYY-MM-DD
```

Finding body sections are `Observation`, `Inference`, `Decision`, `Residual Risk`, `Evidence`, and `Disposition`. `Observation` and `Evidence` are required; the other sections are completed when applicable. A change ledger expresses the same body concepts as labeled list items under each Finding heading, not as ledger frontmatter.

Kinds: `implementation_fact`, `documentation_drift`, `design_ambiguity`, `behavior_defect`, `system_limitation`, `technical_debt`, `evidence_gap`, `evaluation_result`, `delivery_risk`.

Top-level scopes: `system`, `documentation`, `rag`, `test`, `evaluation`, `delivery`. Dotted children are extensible. Multiple scopes require one `primary_scope`.

### Evidence State and Disposition

- `observed`: recorded, not sufficiently verified;
- `confirmed`: supported by reviewed evidence;
- `invalidated`: disproved by later evidence.

Disposition values: `pending`, `architecture`, `adr`, `known_issue`, `enhancement`, `validation`, `change`, `issue`, `closed_in_place`.

Finding state never tracks planned/completed work. That lifecycle belongs to the target. `observed` or `pending` blocks closure. `confirmed` requires evidence and a target, or explicit resolution evidence for `closed_in_place`. `invalidated` requires invalidation evidence and `closed_in_place`. A Finding with residual risk routes to `known_issue`, `enhancement`, `change`, or `issue`; `closed_in_place` asserts that no durable follow-on risk remains. Identity, provenance, and original Observation remain stable while later evidence may refine inference and disposition.

### Target and Backlink Contract

Targets are repository-relative paths, except external issue targets which use a stable issue URL:

| Disposition | Target format |
| --- | --- |
| `architecture` | `docs/ARCHITECTURE.md` |
| `adr` | `docs/architecture/decisions/ADR-*.md` |
| `known_issue` | `docs/known-issues/*.md` |
| `enhancement` | `docs/enhancements/*.md` |
| `validation` | `docs/validation/*.md` or typed change evidence |
| `change` | `openspec/changes/<change>/` |
| `issue` | stable issue URL |
| `closed_in_place` | null target plus `resolution_evidence` or `invalidation_evidence` |

Typed targets backlink through `source_findings`. Architecture dispositions are traced through the Finding and architecture verification commit.

## Typed Documents and Catalog

Templates under `docs/templates/` define different metadata/body requirements for global Findings, change ledgers, ADRs, known issues, enhancements, and validation reports. `source_findings` is optional unless a document claims to disposition a Finding.

Typed status vocabularies are:

- ADR: `proposed | accepted | superseded | rejected`.
- known issue: `open | mitigated | resolved | invalidated`.
- enhancement: `candidate | planned | delivered | declined`; only a linked change/issue justifies `planned`.
- validation: `passed | failed | partial | historical | superseded`.

The catalog groups by typed document and always displays its governed status so consumers can distinguish accepted decisions, open issues, candidate ideas, and historical evidence.

`scripts/validate_documentation.py` scans governed sources, prints a grouped catalog, and writes `docs/evidence-catalog.md`. The catalog is generated, ignored, non-authoritative, and never a place for scheduling or manual edits.

## OpenSpec Evidence Disposition Gate

Every change created or materially updated after governance adoption, and every legacy change presented for completion/archive, must include this phase. Archived changes are not retrofitted unless reopened.

```markdown
## Evidence Disposition Gate

- [ ] New findings classified, or `No new findings` recorded
- [ ] Code, test, review, runtime, or invalidation evidence linked
- [ ] Every confirmed Finding has a durable disposition or evidenced in-place closure
- [ ] Unresolved matters have durable typed documents
- [ ] Follow-up work has an OpenSpec change or issue where required
- [ ] ARCHITECTURE impact assessed
- [ ] No undispositioned design ambiguity remains
```

Create `findings.md` only when Findings exist. With none, the completed gate must contain the literal `No new findings`; missing ledger alone proves nothing.

Before completion/archive the validator rejects observed or pending Findings, missing targets/evidence, invalidated Findings without invalidation evidence, undispositioned ambiguity, and changes with neither a ledger nor explicit no-Finding declaration.

## Historical Documents, Validation, and Delivery

Do not delete old documents without evidence. Use `status`, `superseded_by`, and verification metadata. For automatically generated historical documents, add only an invalidation/status notice and current authority link; do not refresh the body or persist its speculative suggestions.

Validation/evaluation reports require `source_commit`, `source_fingerprint`, `executed_at`, and result status, and must distinguish substitutes from real infrastructure.

The validator reports ignored governance files absent from the tracked PR manifest. It never edits `.gitignore`, stages, or force-adds files; tracking remains an explicit repository decision.
