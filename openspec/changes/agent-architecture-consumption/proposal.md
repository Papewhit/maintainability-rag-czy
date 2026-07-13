## Why

Repository agents can discover `AGENTS.md`, but the current instructions do not route them to the architecture and evidence-governance authorities or define executable workflows for consuming and producing governed knowledge. Without a clear entry point, terminology, and workflow boundary, agents can skip relevant context, treat unconfirmed Findings as facts, or create duplicate and weakly owned documentation.

## What Changes

- Add concise, task-triggered routing in `AGENTS.md` to the current architecture and evidence-governance authorities, with optional reading hints rather than rigid section checklists.
- Define Evidence, finding, Finding Record, typed document, disposition, work item, Global Finding Inbox, and catalog without using those terms interchangeably.
- Replace the declarative capture/disposition/consumption description with named OpenSpec and non-OpenSpec producer workflows, a human-and-agent governed-documentation lookup workflow, and a separate inbox-report operational procedure.
- Define `Architecture impact: yes/no` through a counterfactual misleading-document test and `New Finding: yes/no` through a cross-task decision-value test.
- Define typed-document granularity through an independent-lifecycle test so related evidence details do not create one document per observation.
- Add a read-only `--finding-inbox` validator query and a human-readable generated catalog with authority entry points, clickable source links, regeneration instructions, status context, and a `Global Finding Inbox` view.
- Enforce valid global Finding state combinations while preserving direct typed-document capture for sufficiently confirmed non-OpenSpec discoveries.
- Validate agent comprehension with isolated, context-free worktree scenarios and record reproducible validation evidence.

## Capabilities

### New Capabilities

- `agent-architecture-consumption`: Defines repository-agent discovery, architecture/evidence workflow selection, Finding Inbox consumption, completion judgments, deterministic artifact validation, and isolated behavioral acceptance testing.

### Modified Capabilities

None.

## Impact

- Root `AGENTS.md` repository instructions.
- `docs/evidence-governance.md` terminology and workflows, plus any navigation hints needed in `docs/ARCHITECTURE.md`.
- `scripts/validate_documentation.py`, its generated `docs/evidence-catalog.md`, and documentation-governance unit tests.
- New validation evidence under `docs/validation/` and temporary detached worktrees used only during behavioral verification.
- External scheduling may invoke the read-only inbox command, but scheduling frequency and work planning remain outside repository evidence documents.
