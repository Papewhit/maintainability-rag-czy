## MODIFIED Requirements

### Requirement: Evidence catalog generation
The dedicated catalog command SHALL derive a grouped evidence catalog from the fixed governed source set. Its `build` subcommand SHALL write `docs/evidence-catalog.md` and print a concise build summary. The generated catalog SHALL be non-authoritative and excluded from version tracking.

#### Scenario: Catalog is regenerated
- **WHEN** a maintainer runs `scripts/documentation/catalog.py build` against valid governed sources
- **THEN** `docs/evidence-catalog.md` contains grouped navigation for Findings, ADRs, known issues, enhancements, and validation reports with a source fingerprint, while the console receives a concise summary

### Requirement: Ignored-file delivery manifest
General documentation validation SHALL identify ignored and untracked files only within the fixed governed source paths and `scripts/documentation/`. It SHALL report each path as a delivery warning, SHALL NOT fail solely because of those warnings, and SHALL NOT modify `.gitignore` or stage files automatically.

#### Scenario: Governed artifact is intentionally local
- **WHEN** a governance-relevant script or authority document is ignored and untracked while governed sources are otherwise valid
- **THEN** validation reports its path as a non-blocking delivery warning and exits successfully
