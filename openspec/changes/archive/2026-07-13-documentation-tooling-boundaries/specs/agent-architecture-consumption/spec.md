## MODIFIED Requirements

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
