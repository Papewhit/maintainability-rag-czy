## ADDED Requirements

### Requirement: Fixed governed-source discovery
Documentation governance tooling SHALL discover only the named architecture and governance authorities, direct Markdown children of the governed typed-document and template directories, and active OpenSpec Finding ledgers. It SHALL NOT recursively scan unrelated documentation trees or expose a scan-scope switch.

#### Scenario: Historical document exists outside governed paths
- **WHEN** an unrelated historical or generated Markdown file exists elsewhere under `docs/`
- **THEN** validation and catalog discovery omit it without requiring a file-level exception

#### Scenario: Governed document exists in a typed destination
- **WHEN** a document is placed directly in a governed typed-document directory
- **THEN** the shared discovery result supplies it to validation and applicable catalog rendering

### Requirement: Structural delivery warnings
General documentation validation SHALL inspect ignored/untracked files only within the governed source paths and `scripts/documentation/`. Each matching path SHALL produce a delivery warning, and delivery warnings alone SHALL NOT cause a nonzero exit code.

#### Scenario: User keeps a governed detail local
- **WHEN** an ignored/untracked governed document exists and all tracked governance contracts are valid
- **THEN** validation identifies the path as a warning and exits successfully

#### Scenario: Unrelated ignored file exists
- **WHEN** an ignored/untracked document or script exists outside the structural delivery scope
- **THEN** validation emits no delivery warning for that file

### Requirement: Read-only general validation command
`scripts/documentation/validate.py` SHALL validate governed metadata, identities, links, lifecycle combinations, relationships, architecture boundaries, agent routing, templates, and delivery visibility without writing repository files.

#### Scenario: Maintainer runs general validation
- **WHEN** the validation command runs on a valid repository
- **THEN** it reports errors and warnings separately, returns success, and leaves the catalog and governed sources unchanged

### Requirement: Dedicated change-evidence command
`scripts/documentation/check_change.py <change-name>` SHALL validate the named active change's Evidence Disposition Gate and change-local Finding closure without serving catalog or inbox operations.

#### Scenario: Change contains pending evidence
- **WHEN** the named change contains an observed or pending change-local Finding
- **THEN** the change-evidence command fails and identifies the blocking Finding

#### Scenario: Change closure is complete
- **WHEN** every fixed gate item is checked and every Finding is dispositioned with required Evidence and targets
- **THEN** the change-evidence command succeeds without writing files

### Requirement: Cohesive catalog command
`scripts/documentation/catalog.py` SHALL expose `build` and `inbox` positional subcommands over the shared governed-source model. `build` SHALL write the fixed ignored catalog only when source validation succeeds; `inbox` SHALL print the shared Global Finding Inbox selection without writing files.

#### Scenario: Human builds the catalog
- **WHEN** the human runs `catalog.py build` against valid sources
- **THEN** the command writes `docs/evidence-catalog.md` and prints a concise summary containing document count, inbox count, and source fingerprint

#### Scenario: Automation queries the inbox
- **WHEN** automation runs `catalog.py inbox`
- **THEN** it receives the deterministic oldest-first inbox table and no repository file is created or changed

#### Scenario: Invalid source blocks catalog replacement
- **WHEN** governed-source validation reports an error
- **THEN** `catalog.py build` fails without replacing the existing catalog

### Requirement: Shared deterministic governance model
All three commands SHALL use one shared implementation for governed discovery, document parsing, validation, Finding Inbox selection, and catalog rendering. Catalog and inbox membership SHALL therefore be identical for the same source state.

#### Scenario: Same sources feed catalog and inbox
- **WHEN** catalog build and inbox query consume the same repository state
- **THEN** their Global Finding Inbox membership and ordering match exactly

### Requirement: Legacy tooling removal
The implementation SHALL remove the per-file documentation ignore baseline and the legacy multipurpose validator after current command references and tests migrate. It SHALL NOT modify `.gitignore`.

#### Scenario: Migration completes
- **WHEN** maintainers search current governance instructions and tooling tests
- **THEN** they find the three new command surfaces and no dependency on `documentation-ignore-baseline.txt` or `scripts/validate_documentation.py`
