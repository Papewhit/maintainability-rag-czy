---
document_type: enhancement
enhancement_id: ENH-DOC-0001
status: candidate
scope: documentation.catalog
motivation: Keep the generated evidence catalog consumable when many active changes contribute individual Finding rows.
last_verified_commit: cdeb4f4628ffb2e6586246c3e0633ea9e386cb40
last_verified_date: 2026-07-13
source_findings:
  - DOC-TOOL-F004
related_issues: []
---

# Scale Finding History Consumption in the Evidence Catalog

## Opportunity

The generated catalog currently renders one row for every Finding in every
active change ledger. Archiving removes those ledgers from active discovery,
but repositories with many concurrent or completed-yet-unarchived changes can
still produce a long, low-signal Findings table.

Future catalog design can evaluate source-level summaries, active/history
grouping, filters, pagination, or a dedicated drill-down view while preserving
authoritative source links and deterministic generation.

## Expected Value

- Keep the catalog useful as navigation rather than a dump of ledger history.
- Preserve direct access to individual Finding evidence when needed.
- Make active evidence and historical traceability distinguishable.

## Non-Goals

- Deleting or rewriting Finding ledgers to reduce row count.
- Treating the catalog as an authority or backlog.
- Scheduling implementation through this document.

## Dependencies

- Evidence catalog source and lifecycle semantics in
  `docs/evidence-governance.md`.
- Usage evidence after governance changes are routinely archived.

## Planning Status

Candidate only. Create an OpenSpec change or issue if catalog size or lookup
cost becomes material after normal archive hygiene.
