## Context

The repository has an ignored `docs/` tree with selectively tracked files, an ignored `scripts/` tree with existing tracked exceptions, and OpenSpec artifacts that remain normally visible to Git. `docs/ARCHITECTURE.md` is intended to describe the current system but still names removed modules and omits the active parse-adapter, normalization, maintainability chunking, terminology, parent/leaf storage, and shared postprocess contracts. Evidence documents also mix observations, inferences, resolved decisions, open debt, validation results, and future work.

The verified implementation baseline is commit `8babe339cda636936c6c0af3c95a99e7c77c2f19`, with pre-existing working-tree changes in `backend/infra/vector_store/milvus_client.py` and `docs/rag-postprocess-evidence/implementation-notes.md` preserved as user work. The architecture update must distinguish baseline evidence from any relevant uncommitted state.

The governance model must work both inside and outside OpenSpec. It must support typed long-lived documents without forcing every ADR, known issue, enhancement, or validation report into one universal Finding template.

## Goals / Non-Goals

**Goals:**

- Make `docs/ARCHITECTURE.md` the only current-system overview and bind its claims to reproducible code evidence.
- Separate discovery capture, durable disposition, and typed consumption.
- Define one maximum Finding record vocabulary, split between metadata and body concepts, while keeping purpose-specific document templates independent.
- Make undispositioned Findings and ambiguous planned/current statements mechanically detectable.
- Prevent ignored documentation and validator files from silently disappearing from the proposed PR manifest.
- Preserve historical evidence with explicit status and supersession metadata instead of unsupported deletion or content rewriting.

**Non-Goals:**

- Turning the evidence catalog into a backlog or authoritative source.
- Tracking implementation progress in Finding states.
- Persisting unimplemented suggestions extracted from historical generated documents.
- Implementing `rag-intent-routing` or `rag-multilevel-fallback`.
- Changing `.gitignore` before the explicit end-of-change tracking discussion.
- Requiring every OpenSpec change to create `findings.md` when it has no new findings.

## Decisions

### 1. Separate capture, disposition, and consumption

A Finding is a discovery record, not a universal document type. Findings are captured either in a conditional `openspec/changes/<change>/findings.md` ledger or as one file per Finding under `docs/findings/` when no change is involved. Long-lived consumers use purpose-specific documents: architecture, ADRs, known issues, enhancements, validation reports, OpenSpec changes, or issues.

Alternative rejected: storing every artifact as a Finding. It makes ADR and validation structures unnatural, treats ideas as evidence, and produces an undifferentiated consumption surface.

### 2. Use one Finding record vocabulary without schema inheritance

The maximum Finding record vocabulary has two explicit parts. Metadata contains identity, kind, scope, evidence state, provenance, disposition, target, and commit/date verification binding. Body concepts contain Observation, Inference, Decision, Residual Risk, Evidence, and Disposition narrative. Narrative concepts are not duplicated into frontmatter.

The global Finding template and change ledger are two serializations of this record vocabulary. ADR, known-issue, enhancement, and validation templates are independent typed contracts rather than Finding subsets or subclasses. They may reuse common field semantics, but their required fields and bodies come only from their own template. An enhancement may originate from an idea and therefore does not require `source_findings`.

Finding `kind` describes discovery nature, not destination: `implementation_fact`, `documentation_drift`, `design_ambiguity`, `behavior_defect`, `system_limitation`, `technical_debt`, `evidence_gap`, `evaluation_result`, or `delivery_risk`.

Scopes use controlled dotted names. Valid top-level scopes are `system`, `documentation`, `rag`, `test`, `evaluation`, and `delivery`; child scopes are extensible. Multiple scopes are permitted only with one `primary_scope`.

### 3. Keep Finding evidence state minimal

`evidence_status` is `observed`, `confirmed`, or `invalidated`. Work planning and resolution do not belong in Finding state. `disposition` is independent and is one of `pending`, `architecture`, `adr`, `known_issue`, `enhancement`, `validation`, `change`, `issue`, or `closed_in_place`.

`observed` or `pending` blocks the Evidence Disposition Gate. `confirmed` requires a non-pending target or justified in-place closure. `invalidated` requires invalidation evidence and `closed_in_place`.

Alternative rejected: `planned` and `resolved` Finding states. They duplicate the lifecycle owned by an issue, OpenSpec change, known issue, or enhancement.

### 4. Generate, do not curate, the evidence catalog

The validator scans the typed sources and writes `docs/evidence-catalog.md` while also printing it to the console. The catalog groups Findings, decisions, known issues, enhancements, and validation evidence for consumption. It is derived, ignored, and not authoritative.

Alternative rejected: a hand-maintained tracked register, which creates a second drift-prone source of truth.

### 5. Use conditional change ledgers and a mandatory gate

An OpenSpec change creates `findings.md` when implementation, validation, evaluation, or review produces Findings. If it produces none, its tasks record `No new findings` in the mandatory Evidence Disposition Gate. Absence alone never proves that no Findings exist.

The gate checks classification, linked code/test/review/runtime evidence, durable disposition, residual-risk durability, work ownership through a disposition target, architecture impact, and remaining design ambiguity.

### 6. Preserve typed authority boundaries

- Current behavior: `docs/ARCHITECTURE.md`.
- Stable behavior contracts: `openspec/specs/<capability>/spec.md`.
- Long-lived decisions: `docs/architecture/decisions/ADR-*.md`.
- Confirmed unresolved problems: `docs/known-issues/*.md`.
- Non-defect future opportunities: `docs/enhancements/*.md`.
- Change-local discovery and trade-offs: change design and Findings ledger.
- Reproducible test/evaluation evidence: `docs/validation/*.md`.
- Work scheduling: OpenSpec changes or issues.

`docs/knowledge-and-architecture.md` becomes superseded by the architecture overview. `docs/document-preprocessing-insights.md` is an automatically generated historical document: only status, supersession, and verification metadata are added; its body is not refreshed and its unimplemented suggestions are not persisted.

### 7. Validate semantics conservatively

The validator checks deterministic structure: referenced paths, required metadata, ID uniqueness, internal links, typed relationship targets, Finding gate rules, validation commit/fingerprint bindings, and ignored-file manifest coverage. Planned/current language checks use explicit status regions and prohibited normative/current phrasing rather than attempting unrestricted natural-language truth detection.

### 8. Defer Git tracking policy to the closeout discussion

The validator is implemented under `scripts/` as requested. Architecture and new/updated authority documents may be force-added within the already approved first three documentation categories. No `.gitignore` change and no forced tracking of the validator occurs until the user reviews a concrete final list. The validator must nevertheless report ignored relevant files so they cannot be silently omitted.

## Risks / Trade-offs

- [Semantic planned/current checks can produce false positives] → Restrict checks to declared status sections and explicit phrases; document escape/annotation behavior.
- [A generated ignored catalog may be stale locally] → Regenerate it on every validator run and label it generated with source fingerprint.
- [Distributed typed documents make discovery harder] → Generate grouped catalog views and enforce bidirectional identifiers where a Finding has a durable target.
- [Historical evidence may still contain stale prose] → Add prominent machine-readable and visible historical/superseded status without rewriting its body.
- [Ignored validator may be implemented but absent from the final PR] → Emit an ignored-file manifest failure and hold a mandatory tracking discussion before closeout.
- [Working-tree changes may blur verification claims] → Record commit plus dirty-path disclosure and avoid overwriting unrelated user edits.

## Migration Plan

1. Capture code/document drift in this change's `findings.md`.
2. Create typed governance templates and authority documentation.
3. Rebuild the architecture overview from verified code paths and runtime defaults.
4. Mark competing/generated architecture documents superseded or historical with minimal metadata changes.
5. Disposition every entry in RAG postprocess design ambiguities into ADR, known issue, enhancement, validation, or closed-in-place history; add source links to archived terminology/chunker decisions without rewriting archived artifacts as current facts.
6. Implement the validator and tests, generate the ignored catalog, and run architecture/evidence acceptance validation.
7. Run independent reviews and OpenSpec verification.
8. Present the exact ignored/tracked file list and discuss `.gitignore` before staging or committing.

Rollback is documentation-only: revert tracked governance artifacts and architecture updates. Generated catalog output can be deleted and regenerated. No production data migration is performed.

## Open Questions

- Final `.gitignore` rules and tracking treatment for `scripts/validate_documentation.py` and generated `docs/evidence-catalog.md` remain intentionally open until closeout.
