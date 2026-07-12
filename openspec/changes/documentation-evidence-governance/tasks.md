## 1. Verified Architecture Baseline

- [x] 1.1 Inventory active ingestion, retrieval, postprocess, storage, codec, trace, evaluation, and runtime-default implementation paths at the verification commit.
- [x] 1.2 Rebuild `docs/ARCHITECTURE.md` in English as the single current-system overview with required flows, contracts, status matrix, limitations, navigation, and verification commands.
- [x] 1.3 Correct maintainer-facing code documentation that contradicts the active parse-adapter/normalizer/chunker pipeline.
- [x] 1.4 Mark `docs/knowledge-and-architecture.md` superseded and `docs/document-preprocessing-insights.md` historical without refreshing the generated historical body or persisting its unimplemented suggestions.

## 2. Evidence Governance Model

- [x] 2.1 Create the governance authority document defining ownership, capture/disposition/consumption layers, Finding vocabulary, kinds, scopes, evidence states, dispositions, linking, and catalog semantics.
- [x] 2.2 Create purpose-specific templates for global Findings, change Finding ledgers, ADRs, known issues, enhancements, and validation reports using appropriate metadata subsets.
- [x] 2.3 Create `docs/findings/README.md` and the global one-Finding-per-file conventions without a hand-maintained register.
- [x] 2.4 Define the mandatory Evidence Disposition Gate and conditional `findings.md` behavior for OpenSpec changes.

## 3. Evidence Migration

- [x] 3.1 Disposition every entry in `docs/rag-postprocess-evidence/design-ambiguities.md`, separating long-lived decisions from open known issues, enhancements, and closed change-local findings.
- [x] 3.2 Bind RAG postprocess implementation, pipeline, troubleshooting, and evaluation documents to explicit status, provenance, commit, source fingerprint, and supersession metadata as applicable.
- [x] 3.3 Add durable ADRs for resolved cross-change storage/postprocess decisions and trace their source Findings or archived designs.
- [x] 3.4 Add typed known-issue/enhancement documents for unresolved entity schema, historical migration, metadata mapping, and observability items without copying work schedules into evidence documents.
- [x] 3.5 Add navigation from archived terminology/chunker designs to durable decisions and current architecture while preserving archived change history.

## 4. Documentation Validator

- [x] 4.1 Implement `scripts/validate_documentation.py` with code-path, metadata, ID uniqueness, internal-link, relationship-target, planned/current, Finding-gate, validation fingerprint, and ignored-file manifest checks.
- [x] 4.2 Generate `docs/evidence-catalog.md` by default and print the grouped catalog to the console with a source fingerprint and generated/non-authoritative notice.
- [x] 4.3 Add unit tests under the repository test taxonomy for valid fixtures and each required failure mode.
- [x] 4.4 Add change acceptance validation proving the Evidence Disposition Gate blocks unconfirmed, pending, or ambiguous Findings and permits explicit no-Finding closure.

## 5. Verification and Independent Review

- [x] 5.1 Run focused ingestion, retrieval, postprocess, codec, governance-validator, and OpenSpec tests and record reproducible validation evidence.
- [x] 5.2 Use an independent sub-agent to review whether `docs/ARCHITECTURE.md` accurately reflects the current implementation and disposition all findings.
- [x] 5.3 Use an independent sub-agent to review whether evidence governance distinguishes fact, inference, decision, and unresolved questions and disposition all findings.
- [x] 5.4 Use an independent sub-agent to review validator path coverage and disposition all findings.
- [x] 5.5 Run `openspec-verify-change` and resolve all critical findings before final assessment.

## 6. Evidence Disposition Gate

- [x] 6.1 Confirm every new Finding is classified.
- [x] 6.2 Confirm code, test, review, runtime, or invalidation evidence is linked.
- [x] 6.3 Confirm every confirmed Finding has a durable disposition or justified in-place closure.
- [x] 6.4 Confirm every unresolved matter has a durable typed document.
- [x] 6.5 Confirm follow-up work is represented by an OpenSpec change or issue rather than evidence-document scheduling.
- [x] 6.6 Confirm architecture impact is applied.
- [x] 6.7 Confirm no undispositioned design ambiguity remains and complete the approved ignored/tracked PR manifest.
