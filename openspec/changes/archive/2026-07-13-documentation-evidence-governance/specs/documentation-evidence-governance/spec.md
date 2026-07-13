## ADDED Requirements

### Requirement: Typed evidence ownership
The repository SHALL assign current behavior, stable contracts, long-lived decisions, confirmed unresolved problems, non-defect future opportunities, change-local discoveries, reproducible validation evidence, and work scheduling to distinct authoritative locations. A Finding SHALL be a discovery record and SHALL NOT be the mandatory template for every typed document.

#### Scenario: Consumer selects an authority
- **WHEN** a maintainer needs current behavior, a design rationale, an unresolved problem, a future opportunity, validation evidence, or a work plan
- **THEN** the governance documentation directs the maintainer to the architecture overview, ADRs, known issues, enhancements, validation reports, or OpenSpec/issues respectively

### Requirement: Finding capture paths
The repository SHALL support conditional change-local Finding ledgers and a global `docs/findings/` directory containing one file per non-change Finding. Closed global Findings SHALL remain at their stable paths.

#### Scenario: Finding occurs outside OpenSpec
- **WHEN** a confirmed discovery does not naturally belong to an OpenSpec change or an already typed durable document
- **THEN** it is assigned a unique ID and stored as an independent file under `docs/findings/`

#### Scenario: Change produces no findings
- **WHEN** an OpenSpec change produces no new Findings
- **THEN** its Evidence Disposition Gate explicitly records `No new findings` without requiring an empty `findings.md`

### Requirement: Finding evidence and disposition
A Finding SHALL use `observed`, `confirmed`, or `invalidated` as its evidence state and SHALL separately record one of the governed disposition values. Findings SHALL NOT use planning or implementation completion states.

#### Scenario: Confirmed finding is dispositioned
- **WHEN** a Finding is confirmed
- **THEN** it has a non-pending disposition target or a justified `closed_in_place` disposition with evidence

#### Scenario: Finding is invalidated
- **WHEN** later evidence disproves a Finding
- **THEN** the Finding records invalidation evidence and uses `closed_in_place`

### Requirement: Purpose-specific templates
The repository SHALL define one Finding record vocabulary with metadata and body concepts, and SHALL provide separate templates for global Findings, change Finding ledgers, ADRs, known issues, enhancements, and validation reports. Finding narrative concepts SHALL NOT be duplicated in frontmatter. Typed non-Finding documents SHALL have independent contracts rather than inherit a Finding schema. Enhancements SHALL be permitted without a source Finding.

#### Scenario: ADR is created from a finding
- **WHEN** a confirmed Finding results in a long-lived design decision
- **THEN** the ADR uses the ADR template and links the source Finding without reproducing a mandatory six-section Finding body

#### Scenario: Enhancement originates as an idea
- **WHEN** a future opportunity is not based on confirmed evidence
- **THEN** an enhancement document can be created without a `source_findings` value

### Requirement: Typed targets and residual risk
The repository SHALL define machine-valid target formats, typed artifact status vocabularies, and backlink rules. A Finding with residual risk SHALL route to a known issue, enhancement, change, or issue and SHALL NOT close in place. It SHALL NOT use a separate `unresolved` or `follow_up` field.

#### Scenario: Finding routes to an ADR
- **WHEN** a Finding uses `disposition: adr`
- **THEN** its repository-relative ADR target exists and the ADR backlinks through `source_findings`

#### Scenario: Finding retains residual risk
- **WHEN** a Finding records substantive Residual Risk
- **THEN** its disposition is `known_issue`, `enhancement`, `change`, or `issue`

### Requirement: Evidence catalog generation
The documentation validator SHALL derive a grouped evidence catalog from source documents, print it to the console, and write it to `docs/evidence-catalog.md`. The generated catalog SHALL be non-authoritative and excluded from version tracking.

#### Scenario: Catalog is regenerated
- **WHEN** the validator runs successfully
- **THEN** console output and `docs/evidence-catalog.md` contain grouped navigation for Findings, ADRs, known issues, enhancements, and validation reports with a source fingerprint

### Requirement: OpenSpec Evidence Disposition Gate
Every change created or materially updated after governance adoption, plus every legacy change presented for completion/archive, SHALL explicitly complete an Evidence Disposition Gate. The gate SHALL reject unchecked items, unconfirmed or pending Findings, and undispositioned design ambiguity. Historical archived changes are not retrofitted unless reopened.

#### Scenario: Change has pending finding
- **WHEN** a change contains a Finding with `evidence_status: observed` or `disposition: pending`
- **THEN** the governance validator reports the change as not ready to complete or archive

#### Scenario: Change has no new findings
- **WHEN** the change has no Finding ledger
- **THEN** the validator requires an explicit `No new findings` declaration in its Evidence Disposition Gate

### Requirement: Ignored-file delivery manifest
The validator SHALL identify relevant ignored documentation and script files that are absent from the version-tracked change manifest. It SHALL NOT modify `.gitignore` or stage files automatically.

#### Scenario: Validator is ignored and untracked
- **WHEN** a new governance-relevant script or authority document is ignored and untracked
- **THEN** validation reports its path as a required tracking decision rather than silently succeeding

### Requirement: Documentation integrity validation
The validator SHALL check required typed metadata, unique Finding identifiers, internal links, relationship targets, documented code-path existence, planned/current boundaries, validation commit and source fingerprints, and change Finding disposition.

#### Scenario: Planned content is stated as current
- **WHEN** a planned-status section uses governed current-system language or is included in the active architecture flow
- **THEN** validation fails with the responsible file and section

#### Scenario: Validation evidence lacks reproducibility binding
- **WHEN** a validation or evaluation report lacks a source commit or source fingerprint
- **THEN** validation fails and identifies the missing binding
