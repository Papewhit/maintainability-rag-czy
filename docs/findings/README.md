---
document_type: finding_collection
status: current
scope: documentation
last_verified_commit: 8babe339cda636936c6c0af3c95a99e7c77c2f19
last_verified_date: 2026-07-12
---

# Global Findings

This directory is the durable inbox for material findings discovered outside
OpenSpec whose evidence or typed destination is not yet sufficiently known.
Use one file per Finding, a stable `FIND-NNNN` ID, and
`docs/templates/finding.md`.

Global records use one of three stable combinations:

- `observed + pending`: appears in the generated Global Finding Inbox;
- `confirmed + non-pending disposition`: linked to its durable destination;
- `invalidated + closed_in_place`: retained with invalidation evidence.

If a non-OpenSpec discovery is already confirmed and clearly classified,
create or update its typed document directly. Closed and invalidated Finding
files remain at their stable paths. Do not hand-maintain an index; generate
`docs/evidence-catalog.md` or query `--finding-inbox` through the documentation
validator. The inbox is unconfirmed evidence, not a backlog.
