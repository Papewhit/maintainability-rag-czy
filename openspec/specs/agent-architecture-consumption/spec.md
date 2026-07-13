# Agent Architecture Consumption Specification

## Purpose

Define how repository agents discover, consume, produce, query, and hand off architecture and governed evidence.

## Requirements

### Requirement: Task-triggered authority routing
Root `AGENTS.md` SHALL route repository agents to `docs/ARCHITECTURE.md` for architecture-sensitive work and to `docs/evidence-governance.md` for design, OpenSpec, review, governed documentation, limitations, debt, enhancement, and validation-evidence work. The routing SHALL provide optional navigation hints and SHALL require re-evaluation when task scope expands.

#### Scenario: Local task reveals a cross-module contract impact
- **WHEN** an agent begins with a local task and later discovers a storage, metadata, runtime-default, degradation, trace, evaluation, or cross-module flow impact
- **THEN** it applies the architecture routing at discovery time and assesses the architecture impact before completion

### Requirement: Unambiguous governance vocabulary
Evidence governance SHALL distinctly define Evidence, finding, Finding Record, typed document, disposition, work item, Global Finding Inbox, and catalog. `Global Finding Inbox` SHALL mean the generated view of global Finding Records under `docs/findings/` whose `evidence_status` is `observed` and whose `disposition` is `pending`.

#### Scenario: Agent encounters an inbox entry
- **WHEN** an agent reads a Global Finding Inbox entry
- **THEN** it treats the entry as unconfirmed evidence to investigate rather than current fact, confirmed problem, or scheduled work

### Requirement: Named producer and lookup workflows
Evidence governance SHALL define separate, executable OpenSpec producer, non-OpenSpec producer, and governed-documentation lookup workflows. Each workflow SHALL state its audience, entry conditions, ordered actions, durable outputs, and completion boundary. Periodic inbox reporting SHALL be documented separately as an operational procedure.

#### Scenario: OpenSpec implementation produces a material finding
- **WHEN** implementation, review, evaluation, or verification within an OpenSpec change produces a material finding
- **THEN** the agent records it in the change-local `findings.md` and dispositions it through the change Evidence Disposition Gate

#### Scenario: Non-OpenSpec work produces uncertain durable evidence
- **WHEN** non-OpenSpec work produces a material finding that is not sufficiently confirmed or classified
- **THEN** the agent records a global `observed + pending` Finding Record for later task-time or periodic consumption

#### Scenario: Non-OpenSpec discovery is already confirmed and classified
- **WHEN** non-OpenSpec work produces sufficiently confirmed knowledge with a clear typed destination
- **THEN** the agent creates or updates that typed document directly

#### Scenario: Human looks for prior governed knowledge
- **WHEN** a human needs to locate current behavior, a decision, known problem, opportunity, or validation result
- **THEN** the lookup workflow directs them from the authority table through the generated catalog to the authoritative source document

### Requirement: Materiality and document-granularity decisions
The non-OpenSpec and OpenSpec producer workflows SHALL use cross-task decision value to determine whether a finding is material. A new typed document SHALL require an independently confirmable, acceptable, resolvable, deliverable, rejectable, or supersedable lifecycle; related details without an independent lifecycle SHALL be consolidated into an existing coherent typed document.

#### Scenario: Several symptoms support one known problem
- **WHEN** multiple observations are evidence for the same independently resolvable problem
- **THEN** they are consolidated as evidence in one known-issue document rather than emitted as one document per observation

### Requirement: Valid global Finding lifecycle
A global Finding Record SHALL use exactly one of these stable combinations: `observed + pending`, `confirmed + non-pending disposition`, or `invalidated + closed_in_place`. A previously observed global record SHALL remain at its stable path after confirmation or invalidation and SHALL link its durable destination when applicable.

#### Scenario: Global inbox evidence is confirmed
- **WHEN** later task-time investigation confirms an `observed + pending` global Finding
- **THEN** its evidence state becomes `confirmed`, it receives a governed non-pending disposition, and it leaves the generated inbox view while remaining in Finding history

#### Scenario: Global inbox evidence is disproved
- **WHEN** later evidence disproves an `observed + pending` global Finding
- **THEN** it becomes `invalidated + closed_in_place` with invalidation evidence

### Requirement: Completion judgments
Agents SHALL present `Architecture impact: yes/no` and `New Finding: yes/no` in task handoff. Architecture impact SHALL use the test of whether leaving `docs/ARCHITECTURE.md` unchanged would materially mislead readers about the current system or explicit planning boundary. New Finding SHALL indicate whether the task produced a material finding, independent of whether its durable representation is a Finding Record or a typed document.

#### Scenario: Confirmed defect is written directly as a known issue
- **WHEN** a non-OpenSpec task confirms a material defect and records it directly in a known-issue document
- **THEN** its handoff reports `New Finding: yes` and identifies the typed destination

### Requirement: Read-only Finding Inbox query
`scripts/documentation/catalog.py inbox` SHALL be the single repository query for the Global Finding Inbox. It SHALL print only matching global records, sorted by `last_verified_date` from oldest to newest and then by Finding ID in ascending order when dates are equal, with ID, kind, scope, date, and source path. An empty inbox SHALL succeed without modifying files.

#### Scenario: Agent queries the inbox
- **WHEN** an agent runs `scripts/documentation/catalog.py inbox`
- **THEN** it receives the current generated summary without document mutation or a second generated report artifact

### Requirement: Generated catalog inbox view
The catalog produced by `scripts/documentation/catalog.py build` SHALL be human-readable navigation containing authority entry points, a regeneration command, a link to evidence-governance usage and status semantics, governed statuses, source fingerprint, clickable relative source links, and a `Global Finding Inbox` group derived from the same selector as the `inbox` subcommand. It SHALL identify inbox entries as unconfirmed evidence.

#### Scenario: Catalog and console query are regenerated
- **WHEN** catalog build and inbox query consume the same governed source state
- **THEN** the catalog inbox membership matches the standalone Finding Inbox query

#### Scenario: Human opens the generated catalog directly
- **WHEN** a human opens `docs/evidence-catalog.md` without prior workflow context
- **THEN** the header explains its navigation role, current-behavior authority, explicit build command, governance reference, and inbox evidence boundary

### Requirement: Isolated agent comprehension validation
Acceptance SHALL include independent agent scenarios executed in clean detached worktrees at the implementation commit without inherited discussion context. Scenario prompts SHALL state business tasks rather than expected governance actions, and evaluation SHALL assess authority routing, workflow selection, artifact destination, completion judgments, and treatment of observed evidence. Results SHALL bind the tested commit and scenario fingerprint in `docs/validation/`.

#### Scenario: Independent agents interpret repository guidance
- **WHEN** the acceptance suite runs routing and operation scenarios in separate temporary worktrees
- **THEN** each agent's response and worktree diff can be evaluated without contamination from another agent or the design discussion

### Requirement: Periodic inbox reporting boundary
Evidence governance SHALL document a Global Finding Inbox Report Procedure for human maintainers, scheduled automation, and investigation/design/review agents. The procedure SHALL define when the read-only query is useful and SHALL present its list without changing Finding state, refreshing verification dates, creating work items, or committing repository changes. Scheduling cadence SHALL remain outside governed evidence documents.

#### Scenario: Scheduled inbox report runs
- **WHEN** an external scheduler invokes the Finding Inbox query
- **THEN** it presents the current sorted list and leaves the repository unchanged
