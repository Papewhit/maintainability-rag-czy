---
document_type: enhancement
enhancement_id: ENH-RAG-0007
status: candidate
scope: rag.query-preparation.scope
motivation: Decide whether and how deterministic closed-scope control wording should be removed from precise retrieval text after it establishes a hard filter.
last_verified_commit: 837102015297282e972e33c6b4db128b2e7f3938
last_verified_date: 2026-07-19
source_findings:
  - RAG-MF-F031
related_issues: []
---

# RAG Closed-scope Prefix Consumption

## Opportunity

Precise query preparation currently consumes a resolved document span and an
owned `中` range suffix, but retains preceding closed-scope wording such as
`只基于` or `仅在`. The wording has already established `scope_mode=filter`, so
retaining it may add non-content tokens to dense and sparse retrieval text.

The current change contract defines which signals may create a hard filter and
prohibits deleting text without a structural owner, but it does not define the
owner or cleanup boundary for the prefix itself. Removing only the nearest
prefix is one possible interpretation, not an existing required behavior.

## Decision Background

A future specification must decide the cleanup unit for at least:

- one prefix and one resolved document, such as `只基于《A》说明步骤`;
- prefix-plus-range forms such as `仅在《A》中说明步骤`;
- multiple independently resolved hard hints such as
  `只基于《A》和只基于《B》说明步骤`;
- punctuation and conjunctions between structural scope wording and the
  remaining content query;
- negated or unresolved wording, which must remain retrieval text unless a
  different structural owner is explicitly defined.

## Non-Goals

This document does not authorize deleting all closed-scope-looking text,
changing filter production, adding a compatibility cleanup branch, or choosing
one of the ownership interpretations without an OpenSpec decision and failing
regressions.

## Planning Status

Candidate only. Before implementation, confirm whether the prefix should be
owned by the scope span and define exact multi-document, conjunction,
punctuation, negation, and unresolved-hint scenarios in an OpenSpec change.
