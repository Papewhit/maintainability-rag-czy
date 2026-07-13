---
document_type: finding_ledger
change: agent-architecture-consumption
last_verified_commit: 4db940cad6afe6ab8ef7ed5ec567c29d0f1fc928
last_verified_date: 2026-07-13
---

# Change Findings

## AGENT-ARCH-F001

- Kind: design_ambiguity
- Primary scope: documentation
- Evidence status: confirmed
- Observation: The requirement and design specified oldest-first `last_verified_date` ordering but did not define the order of records with equal dates, even though inbox output must be deterministic.
- Inference: Different stable implementations could produce different equal-date output while each appeared to satisfy the written requirement.
- Decision: Sort by ascending `last_verified_date`, then by ascending Finding ID as the deterministic tie-break.
- Residual risk: none
- Evidence: Isolated agent review at commit `4db940cad6afe6ab8ef7ed5ec567c29d0f1fc928`; `scripts/validate_documentation.py` already uses the key `(last_verified_date, id)`.
- Disposition: change
- Disposition target: openspec/changes/agent-architecture-consumption/
- Resolution evidence: The change design, capability spec, task 2.2, governance procedure, and equal-date unit coverage now state or prove the Finding-ID tie-break.

## AGENT-ARCH-F002

- Kind: behavior_defect
- Primary scope: documentation.validation
- Evidence status: confirmed
- Observation: An active change ledger could avoid closure checks by omitting or misspelling `document_type: finding_ledger`.
- Inference: A malformed ledger could make the closure gate report success while governed findings remained undispositioned.
- Decision: Identify active change ledgers by their reserved path and require the `finding_ledger` document type and ledger metadata there.
- Residual risk: none
- Evidence: Independent validator review of `scripts/validate_documentation.py`; regression test `test_malformed_change_ledger_cannot_bypass_closure`.
- Disposition: change
- Disposition target: openspec/changes/agent-architecture-consumption/
- Resolution evidence: Path-based ledger validation and the closure-bypass regression test pass in `tests/unit/docs`.

## AGENT-ARCH-F003

- Kind: behavior_defect
- Primary scope: documentation.validation
- Evidence status: confirmed
- Observation: An invalidated Finding could satisfy validation without an Evidence section.
- Inference: Invalidation could become an unsupported assertion rather than an auditable conclusion.
- Decision: Require Evidence for every Finding, including invalidated Findings.
- Residual risk: none
- Evidence: Independent validator review; regression test `test_invalidated_finding_requires_evidence`.
- Disposition: change
- Disposition target: openspec/changes/agent-architecture-consumption/
- Resolution evidence: Finding validation now requires Evidence unconditionally and the regression test passes.

## AGENT-ARCH-F004

- Kind: evidence_gap
- Primary scope: documentation.finding-inbox
- Evidence status: confirmed
- Observation: A global `observed + pending` inbox entry could omit Observation or Evidence while still passing validation.
- Inference: The inbox could contain records that state neither what was seen nor why the record exists.
- Decision: Require Observation and Evidence for all Findings while keeping the remaining maximum vocabulary optional by lifecycle and template.
- Residual risk: none
- Evidence: Independent validator review; regression test `test_global_inbox_record_requires_observation_and_evidence`.
- Disposition: change
- Disposition target: openspec/changes/agent-architecture-consumption/
- Resolution evidence: The validator enforces both sections and the global inbox regression test passes.

## AGENT-ARCH-F005

- Kind: documentation_drift
- Primary scope: documentation.workflow
- Evidence status: confirmed
- Observation: The OpenSpec producer workflow required a closure validation run but did not give the `--closure-change` invocation.
- Inference: Agents could run only the general validator and miss the change-specific disposition gate.
- Decision: Put the exact closure command at the OpenSpec workflow's closure step.
- Residual risk: none
- Evidence: Independent routing review of `docs/evidence-governance.md`.
- Disposition: change
- Disposition target: openspec/changes/agent-architecture-consumption/
- Resolution evidence: The workflow now specifies `uv run python scripts/validate_documentation.py --closure-change <change-name> --strict-manifest`.

## AGENT-ARCH-F006

- Kind: evidence_gap
- Primary scope: documentation.catalog
- Evidence status: confirmed
- Observation: The catalog displayed OpenSpec Finding ledgers but its source fingerprint covered only Markdown under `docs/`.
- Inference: Ledger changes could leave the fingerprint unchanged, weakening freshness evidence.
- Decision: Include active OpenSpec Finding ledgers and active change names in the source fingerprint.
- Residual risk: none
- Evidence: Independent routing review; regression test `test_catalog_fingerprint_changes_when_openspec_ledger_changes`.
- Disposition: change
- Disposition target: openspec/changes/agent-architecture-consumption/
- Resolution evidence: Catalog fingerprint inputs now cover the displayed OpenSpec sources and the equal-length mutation regression test passes.

## AGENT-ARCH-F007

- Kind: documentation_drift
- Primary scope: documentation.catalog
- Evidence status: confirmed
- Observation: The lookup workflow covered intended work, but the generated catalog provided no navigation to active changes or the issue tracker.
- Inference: A human or agent relying on the catalog could fail to discover scheduled work.
- Decision: Add intended-work authority guidance and an active OpenSpec changes section to the catalog.
- Residual risk: none
- Evidence: Independent routing review; regression test `test_catalog_exposes_intended_work_and_active_changes`.
- Disposition: change
- Disposition target: openspec/changes/agent-architecture-consumption/
- Resolution evidence: Generated catalog output now lists active changes and points intended-work lookup to OpenSpec plus the project issue tracker.

## AGENT-ARCH-F008

- Kind: documentation_drift
- Primary scope: documentation.catalog
- Evidence status: confirmed
- Observation: A previously generated ignored catalog did not make its freshness requirement operationally clear.
- Inference: Consumers could treat stale navigation as current even though the catalog is not authoritative or tracked.
- Decision: Require regeneration before each catalog-backed lookup and state that rule in both governance and generated output.
- Residual risk: none
- Evidence: Independent routing review of the lookup workflow and generated catalog header.
- Disposition: change
- Disposition target: openspec/changes/agent-architecture-consumption/
- Resolution evidence: Governance and generated catalog output now contain the same regeneration instruction.

## AGENT-ARCH-F009

- Kind: behavior_defect
- Primary scope: documentation.finding-ledger
- Evidence status: confirmed
- Observation: AGENT-ARCH-F005 and AGENT-ARCH-F008 declared a `change` disposition but initially targeted the edited governance document instead of the owning OpenSpec change directory.
- Inference: The implementation fixes were complete, but the ledger itself could not pass its disposition-target contract.
- Decision: Point both records to this change and retain their resolution evidence as the concrete edited-document proof.
- Residual risk: none
- Evidence: Independent routing re-review and strict documentation validation of the change-local ledger.
- Disposition: closed_in_place
- Resolution evidence: Both invalid targets were replaced with `openspec/changes/agent-architecture-consumption/`; this record documents and closes the ledger-only correction.

## AGENT-ARCH-F010

- Kind: documentation_drift
- Primary scope: documentation.design
- Evidence status: confirmed
- Observation: Design decision 7 still described catalog regeneration only when the file was absent or potentially stale, while the implemented lookup workflow requires regeneration before every catalog-backed lookup.
- Inference: The change design and its implementation expressed different freshness contracts.
- Decision: Align the design with the deterministic before-each-lookup rule already adopted by governance and generated output.
- Residual risk: none
- Evidence: OpenSpec coherence verification comparing `design.md` with `docs/evidence-governance.md` and catalog generation output.
- Disposition: closed_in_place
- Resolution evidence: Design decision 7 now states that the ephemeral catalog is regenerated before each catalog-backed lookup.
