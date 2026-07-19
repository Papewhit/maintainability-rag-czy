---
document_type: known_issue
issue_id: KI-RAG-0019
status: open
scope: rag.ingestion.structure-normalization
severity: high
first_confirmed: 2026-07-19
last_verified_commit: 5e49a4669f78dbaddf00ee97f1f76c7960bba419
last_verified_date: 2026-07-19
source_findings: []
---

# Three-level numeric section headings are treated as list items

## Observed Behavior

DeepDoc's adapter classifier recognizes a two-level heading such as `4.3 ...`
as `heading`, but classifies `4.3.2 ...` and `4.3.3 ...` as `list_item`.
The heading expression accepts only `number.number` followed by whitespace;
the later list expression then consumes the leading `4.` from a three-level
section number.

The list normalizer consequently grouped sibling sections `4.3.2` and `4.3.3`
as two items in `lg_p35_l1_s11`. Their shared parent contains both sections,
while both leaves retain only the higher-level section title
`4.3 基于规则的历史变更信息提取方法`. In the manual retrieval for
`配置管理系统出库如何触发`, the `4.3.2` title appeared in a separate rank-4
chunk combined with later formula/output text instead of enriching the rank-0
answer paragraph.

## Impact

Three-level headings do not enter the heading tree, do not establish their own
section path/title, and can cause sibling subsections to be grouped as a
maintenance-style list. Retrieval may return the right title and the right
answer sentence in different chunks, while auto-merge can produce a parent
spanning multiple sibling sections.

This is independent of the upstream cross-heading paragraph merge recorded in
[KI-RAG-0018](deepdoc-native-text-can-merge-paragraphs-across-section-headings.md):
fixing either defect alone does not restore the complete section contract.

## Evidence or Reproduction

Calling `backend.documents.parse_adapter.deepdoc.adapter._classify_block_type`
with the fixture headings returns:

```text
4.3   -> heading
4.3.2 -> list_item
4.3.3 -> list_item
```

Milvus leaf `SCM优化方案.pdf_lg11_sg0_leaf_0` records `list_marker=4.3.2`,
`list_level=1`, and `section_title=4.3 基于规则的历史变更信息提取方法`.
ParentChunkStore row `v4_full::SCM优化方案.pdf_lg11_sg0` records a two-item
list group containing both `4.3.2` and `4.3.3`.

## Workaround

When validating exact section retrieval, compare the visible heading with
`block_type`, `list_marker`, `section_title`, and parent text. Do not interpret
a dotted subsection number stored as a list marker as evidence that the source
contains a procedural or maintenance list.

## Resolution Criteria

- Supported multi-level numeric section forms are classified as headings before
  generic list-marker handling.
- `4.3.2`, `4.3.3`, and `4.3.4` create distinct heading-tree boundaries and
  section identities on the fixture page.
- They are not grouped into a shared ListGroup, while genuine numbered lists
  continue to be detected.
- Unit and real-parser integration regressions cover the ambiguous dotted-number
  grammar and downstream parent/leaf metadata.
