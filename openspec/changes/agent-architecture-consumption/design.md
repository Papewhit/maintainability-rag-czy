## Context

Repository agents reliably discover root `AGENTS.md`, while the architecture and evidence-governance authorities are read only when explicitly routed. The current root instructions cover tests and review but do not route architecture-sensitive or evidence-sensitive work. `docs/evidence-governance.md` defines artifacts and fields, yet its capture/disposition/consumption description does not provide separate executable workflows for OpenSpec and non-OpenSpec work.

The two producer paths have different closure boundaries. OpenSpec changes have a durable Evidence Disposition Gate and archive lifecycle; non-OpenSpec tasks do not. Global Findings therefore need to remain a genuine inbox for uncertain evidence rather than being forced into a work item or typed destination during the originating task.

This change depends on the authorities and validator introduced by `documentation-evidence-governance`. It does not create another architecture or governance truth source.

## Goals / Non-Goals

**Goals:**

- Give capable agents a concise, automatically discoverable route to relevant architecture and governance context.
- Turn governance concepts into named producer and lookup workflows with explicit audiences, entry conditions, actions, outputs, and completion boundaries.
- Make unconfirmed global evidence discoverable without presenting it as fact, confirmed debt, or scheduled work.
- Preserve direct typed-document capture for sufficiently confirmed non-OpenSpec knowledge.
- Verify both deterministic repository behavior and independent agent comprehension.

**Non-Goals:**

- Creating a separate agent handbook that duplicates architecture or governance.
- Requiring every agent to read full authority documents for every task.
- Turning the Global Finding Inbox or generated catalog into a backlog.
- Storing scheduling cadence or implementation plans in evidence documents.
- Automatically editing, committing, or creating work items from periodic inbox reports.

## Decisions

### 1. Keep `AGENTS.md` as a thin router

Root `AGENTS.md` will name task triggers, link the two authorities, suggest useful starting sections, require scope re-evaluation when work expands, and require the two handoff judgments. Detailed terminology and workflow steps remain in `docs/evidence-governance.md`; current system facts remain in `docs/ARCHITECTURE.md`.

Reading guidance is a hint for capable agents. It suggests the evidence boundary, relevant architecture sections, feature status, and known limitations, with full-document reading when impact spans components or remains uncertain.

Alternative rejected: a dedicated agent guide. It would duplicate routing and workflow rules and create another drift surface.

### 2. Define precise terms before workflows

The governance document will distinguish:

- Evidence: reproducible support or disproof from code, tests, runtime, review, or evaluation.
- finding: a discovered knowledge proposition with cross-step value.
- Finding Record: an intermediate governed serialization in a change ledger or global file.
- typed document: a purpose-specific durable authority.
- disposition: the knowledge destination of a Finding Record.
- work item: an OpenSpec change or issue describing intended action.
- Global Finding Inbox: the generated subset of global `observed + pending` Finding Records.
- catalog: generated navigation, never an authority.

The fixed `New Finding` judgment refers to a material finding, not a particular serialization. This permits a confirmed non-OpenSpec discovery to go directly to a typed document.

### 3. Separate production, lookup, and reporting instructions

The governance authority will define three knowledge workflows:

1. **OpenSpec Producer Workflow**: read relevant authorities and inbox signals, capture material discoveries change-locally, collect Evidence, and disposition at the change gate before sync/archive.
2. **Non-OpenSpec Producer Workflow**: read triggered authorities, capture uncertain material evidence globally as `observed + pending`, and write sufficiently confirmed/classified knowledge directly to its typed destination.
3. **Governed Documentation Lookup Workflow**: used by humans and agents when locating current behavior, decisions, known problems, opportunities, or validation evidence. It starts with the authority table, explains when and how to regenerate the catalog, follows catalog links to source documents, and treats observed inbox entries as hypotheses requiring verification.

Periodic reporting is not a knowledge lifecycle workflow. A **Global Finding Inbox Report Procedure** under an Operational Procedures section defines the read-only command for human maintainers, scheduled automation, and investigation/design/review agents that need an inbox summary. It states who invokes it, when it is useful, and where its output is presented.

The prior capture, disposition, and consumption concepts remain useful operation names inside these workflows rather than a single lifecycle shared by every path.

### 4. Separate Finding materiality from typed-document granularity

A finding is material when losing it at task end could cause a future maintainer to misjudge current behavior, design boundaries, known risk, or evidence confidence. A new typed document additionally requires an independent lifecycle. Multiple symptoms or evidence details supporting one issue are consolidated into that issue instead of receiving separate documents.

This gives agents two simple reasoning tests without making templates universal.

### 5. Use distinct OpenSpec and global lifecycle enforcement

Change-local Findings may remain `observed + pending` during implementation but must pass the OpenSpec Evidence Disposition Gate. Global Finding Records use three stable combinations:

```text
observed + pending
  -> confirmed + governed non-pending disposition
  -> invalidated + closed_in_place
```

A global record that reaches either terminal evidence state remains at its path for traceability. A non-OpenSpec discovery already supported by sufficient evidence can skip the intermediate record and update a typed destination directly.

### 6. Define architecture impact with a counterfactual test

`Architecture impact: yes` means leaving the architecture overview unchanged after the task would materially mislead readers about the current system or its explicit current/default-disabled/planned boundary. The relevant cases include component responsibilities, cross-module flows, storage or metadata contracts, runtime defaults, feature state, degradation, trace, and evaluation contracts. A lagging verification commit alone does not decide impact; agents inspect task-relevant code.

`New Finding: yes` means the task produced a material finding. Both values are included in user-facing handoff with a concise rationale and target path when applicable.

### 7. Make catalog consumption human-readable

`docs/evidence-governance.md` will contain the authoritative `Finding and Using Governed Documentation` instructions. Humans and agents use the authority table first, regenerate the catalog with `uv run python scripts/validate_documentation.py` when it is absent or potentially stale, and follow catalog links to authoritative sources.

The generated `docs/evidence-catalog.md` will identify itself as navigation, link to `docs/ARCHITECTURE.md` and evidence governance, show the regeneration command, explain the unconfirmed nature of Global Finding Inbox entries, preserve source fingerprint and governed status, and use clickable relative Markdown links for source documents. The generated file is self-explanatory enough for a human who opens it directly while leaving detailed semantics in the tracked governance authority.

### 8. Share one generated inbox query

`scripts/validate_documentation.py --finding-inbox` will derive the global inbox directly from source documents, output a stable oldest-first table, return success for an empty inbox, and avoid writing catalog or report files. Normal catalog generation will use the same selector for a `Global Finding Inbox` section.

This command is the common interface for manual reporting, task-time investigation, and external periodic reporting. Its CLI help gives a concise usage description; detailed audience and timing guidance lives in the governance Operational Procedures section. Scheduling configuration and cadence stay outside repository evidence.

### 9. Validate comprehension in isolated worktrees

Static tests can prove links, schemas, selection, ordering, and state combinations, but the objective also requires evidence that independent agents choose the intended route. Acceptance will create clean detached worktrees at the tested commit and launch agents without inherited conversation context. Prompts contain only realistic business scenarios. Some scenarios are read-only routing exercises; others permit disposable edits whose diffs reveal chosen artifacts.

The evaluation rubric covers authority selection, workflow selection, destination choice, `Architecture impact`, `New Finding`, and whether observed evidence is promoted incorrectly. Agents do not commit or push. Worktrees are removed through Git worktree commands after evidence capture.

Alternative rejected: evaluating agents in the implementation worktree or with this discussion context, which would leak both state and expected answers.

## Risks / Trade-offs

- [Hints may be interpreted inconsistently] → Back them with named workflows, precise terms, scenario validation, and authority links rather than rigid reading quotas.
- [Global inbox records may age without action] → Make them visible in task-time consumption and read-only periodic reports sorted by verification date.
- [Observed evidence may be mistaken for current fact] → Give the inbox an exact definition and include this distinction in behavioral acceptance.
- [State validation may reject migrated historical shapes] → Scope the strict three-combination rule to governed global Finding Records and add fixture coverage before enabling it repository-wide.
- [Behavior tests are model-dependent] → Bind prompts, rubric, commit, and scenario fingerprint; report results as validation evidence rather than deterministic unit-test truth.
- [Temporary worktrees can be left behind after interrupted tests] → Use predictable workspace-local paths, inspect registration before removal, and clean through `git worktree remove`/`prune` with verified targets.

## Migration Plan

1. Restructure governance terminology and workflows without changing typed authority ownership.
2. Add root agent routing and optional architecture-reading hints.
3. Implement the global lifecycle validator, shared inbox selector, CLI output, human-readable catalog navigation, and inbox group.
4. Add deterministic tests for routing links, workflow anchors, catalog instructions/links, state combinations, selection, ordering, empty output, and no-write behavior.
5. Run isolated agent scenarios at the implementation commit and publish reproducible validation evidence.
6. Run OpenSpec verification and the Evidence Disposition Gate.

Rollback removes the new routing and query behavior and restores the previous governance layout. Generated catalog output can be regenerated. Temporary validation worktrees contain no authoritative state and are removed after evidence capture.

## Open Questions

None. Periodic scheduling cadence is an external operational choice made when the read-only automation is created.
