## Why

Ragtenance documentation mixes current implementation facts, historical snapshots, design decisions, open ambiguities, validation evidence, and future work, while the current architecture overview has drifted from the active ingestion and retrieval pipelines. A durable evidence-governance contract is needed now so architecture updates and OpenSpec closure decisions remain traceable to code, tests, reviews, and reproducible validation.

## What Changes

- Rebuild `docs/ARCHITECTURE.md` as the single English-language current-system map, verified against a named commit and explicitly separating default-enabled, implemented-but-default-disabled, and planned capabilities.
- Mark superseded or historical generated architecture material without creating competing current-system descriptions.
- Introduce two Finding serializations backed by one Finding record vocabulary, plus independent purpose-specific contracts for ADRs, known issues, enhancements, and validation reports.
- Add a global one-Finding-per-file intake under `docs/findings/` and conditional per-change `findings.md` ledgers.
- Define evidence confirmation, durable disposition, source/target linking, and an explicit OpenSpec Evidence Disposition Gate.
- Migrate RAG postprocess evidence and archived terminology/chunker decisions so resolved decisions, open issues, enhancements, and reproducible evidence no longer share ambiguous ownership.
- Add a validator under `scripts/` that checks paths, metadata, IDs, internal links, planned/current language boundaries, Finding disposition, validation fingerprints, and ignored-file PR omissions; it also generates an ignored `docs/evidence-catalog.md` and prints the catalog to the console.
- Preserve `.gitignore` until a separate end-of-change tracking discussion determines how the validator is tracked and its generated catalog remains ignored.

## Capabilities

### New Capabilities

- `documentation-evidence-governance`: Defines authoritative documentation ownership, typed evidence artifacts, Finding capture and disposition, catalog generation, validation rules, and the OpenSpec closure gate.
- `current-architecture-documentation`: Defines the required content, status boundaries, evidence binding, and automated verification contract for the single current-system architecture map.

### Modified Capabilities

None.

## Impact

- Documentation under `docs/`, including architecture, RAG postprocess evidence, historical generated documents, ADRs, known issues, enhancements, Findings, and validation reports.
- OpenSpec artifacts and templates for evidence disposition during change completion and archive readiness.
- A new documentation validator under ignored `scripts/`, plus unit and acceptance coverage under the repository test taxonomy.
- Repository delivery policy: ignored documentation and scripts must be surfaced in a PR manifest check; final tracking changes require explicit user agreement and are outside this proposal's automatic authority.
