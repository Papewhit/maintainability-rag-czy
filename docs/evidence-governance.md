---
document_type: governance
status: current
scope: documentation
last_verified_commit: 2748ab5639454dcd2f7bd12e75783de16c9731b2
last_verified_date: 2026-07-13
---

# Documentation Evidence Governance

## Purpose

This governance explains where durable knowledge belongs, how findings move
from discovery to an authority, and how humans and agents find that knowledge.
Evidence documents record what is known and why. OpenSpec changes and issues
record intended work.

## Terminology

- **Evidence**: reproducible support or disproof from code, tests, runtime
  behavior, review, or evaluation. Evidence supports a statement; it is not a
  work item.
- **finding**: a knowledge proposition discovered during work that may have
  value beyond the current step.
- **Finding Record**: the governed intermediate representation of a material
  finding in a change `findings.md` ledger or a file under `docs/findings/`.
- **typed document**: a purpose-specific durable authority such as an ADR,
  known issue, enhancement, validation report, or the architecture overview.
- **disposition**: the knowledge destination of a Finding Record. It does not
  state that implementation work is complete.
- **work item**: an OpenSpec change or issue that records intended action.
- **Global Finding Inbox**: the generated view of Finding Records under
  `docs/findings/` with `evidence_status: observed` and
  `disposition: pending`. Its entries are unconfirmed evidence.
- **catalog**: generated navigation across governed sources. It is not an
  authority; linked source documents remain authoritative.

## Authority Routing

| Information needed | Authority |
| --- | --- |
| Current behavior | `docs/ARCHITECTURE.md` |
| Stable contract | `openspec/specs/<capability>/spec.md` |
| Long-lived decision | `docs/architecture/decisions/ADR-*.md` |
| Confirmed unresolved problem | `docs/known-issues/*.md` |
| Non-defect future opportunity | `docs/enhancements/*.md` |
| Change-local discovery/trade-off | change `design.md` and conditional `findings.md` |
| Reproducible test/evaluation evidence | `docs/validation/*.md` or change evidence |
| Intended work | OpenSpec change or issue |

## Decision Tests

### Material Finding Test

A finding is material when losing it at task end could cause a future
maintainer to misjudge current behavior, a design boundary, known risk, or
evidence confidence. Ordinary task progress and implementation details already
made clear by code and tests do not require a Finding Record.

Example: three reproducible symptoms that expose one storage-contract defect
are material evidence for that defect. They are not necessarily three separate
findings.

### Typed Document Granularity Test

Create a new typed document only when the subject has an independently
confirmable, acceptable, resolvable, deliverable, rejectable, or supersedable
lifecycle. Add related details without an independent lifecycle to the
existing coherent typed document.

Example: additional reproduction paths for an existing known issue belong in
that issue's Evidence section rather than in new known-issue files.

### Architecture Impact Test

Architecture impact is `yes` when leaving `docs/ARCHITECTURE.md` unchanged
after the task would materially mislead readers about the current system or
its explicit current, default-disabled, or planned boundary. Inspect relevant
code; a verification commit that differs from HEAD is not sufficient by
itself.

Common impacts include component responsibilities, cross-module flow, storage
or metadata contracts, runtime defaults, feature state, degradation, trace,
and evaluation contracts. A refactor that preserves a documented contract
normally has no architecture impact.

## OpenSpec Producer Workflow

**Audience:** humans or agents proposing, implementing, reviewing, verifying,
syncing, or archiving an OpenSpec change.

**Enter when:** the task is conducted through an OpenSpec change.

1. Read the change artifacts and the authorities relevant to its scope.
2. Query or inspect relevant Global Finding Inbox entries when they may affect
   design, acceptance, review, or verification. Treat them as hypotheses.
3. Record each material finding produced by the change in the conditional
   change-local `findings.md` ledger, initially as `observed + pending` when
   confirmation or destination is not yet known.
4. Link code, test, review, runtime, evaluation, or invalidation Evidence.
5. At the Evidence Disposition Gate, confirm or invalidate every change-local
   Finding Record and route confirmed knowledge to a typed document or justify
   `closed_in_place`.
6. Assess architecture impact and complete every fixed gate item before
   completion, sync, or archive.

**Durable outputs:** the change ledger when findings exist, typed destination
documents, validation evidence, and the completed gate. With no findings, the
gate records the literal `No new findings` without an empty ledger.

**Complete when:** the change closure validator passes and no observed,
pending, or undispositioned change-local Finding remains.

## Non-OpenSpec Producer Workflow

**Audience:** humans or agents performing repository work outside an OpenSpec
change.

**Enter when:** the task produces a finding that passes the Material Finding
Test.

1. Collect reproducible Evidence and check existing authorities for the same
   subject.
2. If the knowledge is sufficiently confirmed and has a clear destination,
   create or update the coherent typed document directly. A separate Finding
   Record is optional when no discovery trail is needed.
3. If confirmation or destination is not yet known, create one global Finding
   file from `docs/templates/finding.md` with `observed + pending`.
4. If a pre-existing global Finding is confirmed, give it a non-pending
   governed disposition and backlink from the typed destination. If disproved,
   use `invalidated + closed_in_place` with invalidation Evidence.
5. Assess architecture impact and report `Architecture impact: yes/no` and
   `New Finding: yes/no` in the task handoff, including destination paths when
   applicable.

**Durable outputs:** a typed destination for confirmed/classified knowledge or
a global inbox record for unconfirmed/unclassified evidence.

**Complete when:** the current task evidence and chosen representation are
written and valid. Global `observed + pending` is an allowed inbox state and
does not assert a confirmed problem or planned action.

## Finding and Using Governed Documentation

**Audience:** humans and agents locating current behavior, decisions, known
problems, opportunities, validation results, or unconfirmed evidence.

**Enter when:** prior governed knowledge could answer a question, inform a
design or review, or prevent duplicate discovery.

1. Start with the Authority Routing table and open the source appropriate to
   the question. Current behavior starts at `docs/ARCHITECTURE.md`.
2. When `docs/evidence-catalog.md` is absent or potentially stale, regenerate
   and validate it:

   ```powershell
   uv run python scripts/validate_documentation.py
   ```

3. Open `docs/evidence-catalog.md`, choose the relevant governed group, and
   follow its clickable source link. The linked document, not the catalog, is
   the authority.
4. For investigation, design, OpenSpec, or review work, inspect relevant
   Global Finding Inbox entries when useful. Verify an observed entry against
   current Evidence before using it as a fact or requirement.
5. If lookup produces a new material finding, enter the applicable producer
   workflow.

**Durable outputs:** none for lookup alone. Any new knowledge is handled by a
producer workflow.

**Complete when:** the question has been answered from an authority or the
search has transitioned into a producer workflow.

## Finding Record Contract

Use `openspec/changes/<change>/findings.md` for change-related findings.
Outside OpenSpec, use one file per global Finding under `docs/findings/` only
when evidence or destination remains uncertain.

### Finding Record Vocabulary

The vocabulary has two representations and is not a base schema inherited by
other document types.

- **Metadata** supports identity, indexing, relationships, and verification.
- **Body sections** hold the knowledge narrative and are not duplicated into
  frontmatter.

Global files and change ledgers are two serializations of this vocabulary.
ADRs, known issues, enhancements, and validation reports have independent
typed contracts, though common fields such as `scope` and
`last_verified_date` keep the same meaning.

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

Finding body concepts are `Observation`, `Inference`, `Decision`,
`Residual Risk`, `Evidence`, and `Disposition`. `Observation` and `Evidence`
are required; complete the others when applicable. A change ledger expresses
them as labeled items beneath each Finding heading.

Kinds: `implementation_fact`, `documentation_drift`, `design_ambiguity`,
`behavior_defect`, `system_limitation`, `technical_debt`, `evidence_gap`,
`evaluation_result`, or `delivery_risk`.

Top-level scopes: `system`, `documentation`, `rag`, `test`, `evaluation`, and
`delivery`. Dotted child scopes are extensible. Multiple scopes require one
`primary_scope`.

### Evidence State, Disposition, and Global Lifecycle

- `observed`: recorded but not sufficiently verified;
- `confirmed`: supported by reviewed Evidence;
- `invalidated`: disproved by later Evidence.

Disposition values: `pending`, `architecture`, `adr`, `known_issue`,
`enhancement`, `validation`, `change`, `issue`, or `closed_in_place`.

Global Finding Records have exactly three stable combinations:

| Evidence status | Disposition | Meaning |
| --- | --- | --- |
| `observed` | `pending` | Unconfirmed Global Finding Inbox entry |
| `confirmed` | any governed non-pending value | Confirmed and knowledge-dispositioned |
| `invalidated` | `closed_in_place` | Disproved and retained as history |

Change-local records may remain `observed + pending` during work, but that
combination blocks their Evidence Disposition Gate. `confirmed` requires
Evidence and a valid target or evidenced in-place closure. `invalidated`
requires invalidation Evidence and `closed_in_place`. A Finding with residual
risk routes to a known issue, enhancement, change, or issue.

### Target and Backlink Contract

Targets are repository-relative paths except external issue targets, which use
a stable issue URL:

| Disposition | Target format |
| --- | --- |
| `architecture` | `docs/ARCHITECTURE.md` |
| `adr` | `docs/architecture/decisions/ADR-*.md` |
| `known_issue` | `docs/known-issues/*.md` |
| `enhancement` | `docs/enhancements/*.md` |
| `validation` | `docs/validation/*.md` or typed change evidence |
| `change` | `openspec/changes/<change>/` |
| `issue` | stable issue URL |
| `closed_in_place` | null target plus resolution or invalidation Evidence |

Typed targets backlink through `source_findings`. Architecture dispositions
are traced through the Finding and architecture verification commit.

## Typed Documents and Catalog

Templates under `docs/templates/` define independent metadata and body
requirements for global Findings, change ledgers, ADRs, known issues,
enhancements, and validation reports. `source_findings` is optional unless a
document claims to disposition a Finding Record.

Typed status vocabularies are:

- ADR: `proposed | accepted | superseded | rejected`;
- known issue: `open | mitigated | resolved | invalidated`;
- enhancement: `candidate | planned | delivered | declined`; only a linked
  change or issue justifies `planned`;
- validation: `passed | failed | partial | historical | superseded`.

`scripts/validate_documentation.py` validates governed sources, prints a
grouped catalog, and writes `docs/evidence-catalog.md`. The generated catalog
is ignored and non-authoritative. It provides authority entry points,
governed statuses, clickable source links, source fingerprint, regeneration
instructions, and the Global Finding Inbox view.

## Operational Procedures

### Global Finding Inbox Report Procedure

**Used by:** human maintainers, scheduled automation, and humans or agents
performing investigation, design, OpenSpec, or review work.

**Use when:** an inbox summary is needed without regenerating the full catalog,
including periodic visibility checks.

Run:

```powershell
uv run python scripts/validate_documentation.py --finding-inbox
```

The command lists only global `observed + pending` records, oldest verified
first, with ID, kind, scope, verification date, and source path. An empty list
is a successful result. Present the output as a report; the procedure does not
change Finding state, refresh verification dates, create work items, or commit
repository changes. Scheduling cadence belongs to the external scheduler.

## OpenSpec Evidence Disposition Gate

Every change created or materially updated after governance adoption, and
every legacy change presented for completion or archive, completes this phase.
Historical archived changes are not retrofitted unless reopened.

```markdown
## Evidence Disposition Gate

- [ ] New findings classified, or `No new findings` recorded
- [ ] Code, test, review, runtime, or invalidation evidence linked
- [ ] Every confirmed Finding has a durable disposition or evidenced in-place closure
- [ ] Residual risks have durable typed destinations
- [ ] Planned work has an OpenSpec change or issue owner where required
- [ ] ARCHITECTURE impact assessed
- [ ] No undispositioned design ambiguity remains
```

Create `findings.md` only when Findings exist. With none, the completed gate
contains the literal `No new findings`; missing ledger alone proves nothing.

Before completion or archive, the validator rejects observed or pending
change-local Findings, missing targets or Evidence, invalidated Findings
without invalidation Evidence, undispositioned ambiguity, and changes with
neither a ledger nor an explicit no-Finding declaration.

## Historical Documents, Validation, and Delivery

Do not delete old documents without Evidence. Use `status`, `superseded_by`,
and verification metadata. For automatically generated historical documents,
add only an invalidation/status notice and current-authority link; do not
refresh the body or persist its speculative suggestions.

Validation and evaluation reports require `source_commit`,
`source_fingerprint`, `executed_at`, and result status, and distinguish
substitutes from real infrastructure.

The validator reports ignored governance files absent from the tracked PR
manifest. It never edits `.gitignore`, stages, or force-adds files; tracking
remains an explicit repository decision.
