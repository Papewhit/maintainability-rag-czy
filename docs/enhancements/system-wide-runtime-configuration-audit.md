---
document_type: enhancement
enhancement_id: ENH-SYS-0001
status: candidate
scope: system.configuration
motivation: Establish an evidence-backed inventory of runtime settings, defaults, aliases, dependencies, storage identities, and observable effective state across the full application chain.
last_verified_commit: 5e49a4669f78dbaddf00ee97f1f76c7960bba419
last_verified_date: 2026-07-19
source_findings: []
related_issues:
  - KI-RAG-0004
  - KI-RAG-0006
  - KI-RAG-0009
  - KI-RAG-0010
  - KI-RAG-0011
  - KI-RAG-0014
  - KI-RAG-0017
---

# System-wide Runtime Configuration Audit

## Opportunity

Perform a systematic, evidence-backed inventory of configuration from document
upload through parsing, normalization, chunk emission, storage, retrieval,
reranking, confidence, fallback, answer delivery, frontend trace display, and
external telemetry. For each setting, record its owner, default, supported
domain, deprecated aliases, consumers, cross-setting prerequisites, storage or
cache identity impact, effective runtime value, and observable failure mode.

The need is supported by several independent runtime observations: table
retention depends on an index-profile capability not visible at upload time;
Milvus collection names and stored row profiles can disagree; BM25 profile
isolation remains manual; anchor consumers are independently switchable; a
Level 2 expansion ceiling can be lower than the initial candidate pool; and
deprecated fallback/rerank settings plus external tracing credentials produce
repeated runtime warnings; and a new collection name is not reachable from
the read path until another operation initializes its schema. An enabled intent
classifier with an explicit model can also remain ineffective when the selected
provider rejects the structured-output mode/prompt combination.

## Expected Value

- Make supported configuration combinations distinguishable from merely
  parseable combinations.
- Expose when one logical capability is split across unrelated switches or
  storage identities.
- Prevent environment drift between UI validation, E2E tests, evaluation, and
  production-like runs.
- Give traces and startup diagnostics enough effective-state evidence to make
  failures reproducible without disclosing secrets.
- Provide a factual basis for later decisions about validation, migration, or
  configuration consolidation.

## Non-Goals

This candidate does not change defaults, remove aliases, introduce a new
configuration abstraction, define a startup-failure policy, clean persistent
stores, or authorize modifications to `rag-multilevel-fallback`. It does not
turn the observed configuration problems into new contracts. Any such change
requires its own confirmed requirements and scheduled work item.

## Dependencies

- A complete environment-variable and config-loader inventory, including code
  paths that read environment state at import time.
- Redacted effective-configuration snapshots from UI validation, E2E,
  evaluation, and production-like startup paths.
- Storage inventories for Milvus collections/row profiles, ParentChunkStore,
  Redis namespaces, BM25 state, uploaded files, and parse metadata.
- A dependency map linking ingestion profiles, feature flags, budgets, legacy
  aliases, external telemetry, and frontend-visible trace fields.
- The related known issues must remain independently reproducible; this audit
  is not a substitute for resolving them.

## Planning Status

Candidate only. The inventory and evidence collection may be performed as
read-only investigation; any validation rules, migration behavior, or runtime
configuration redesign require a separately approved issue or OpenSpec change.
