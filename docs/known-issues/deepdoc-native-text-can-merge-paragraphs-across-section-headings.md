---
document_type: known_issue
issue_id: KI-RAG-0018
status: open
scope: rag.ingestion.parse-order
severity: high
first_confirmed: 2026-07-19
last_verified_commit: 5e49a4669f78dbaddf00ee97f1f76c7960bba419
last_verified_date: 2026-07-19
source_findings: []
---

# DeepDoc native-text parsing can merge paragraphs across a section heading

## Observed Behavior

Page 35 of `SCM优化方案.pdf` has the visual and native-text order:

1. the final paragraph of the preceding subsection;
2. heading `4.3.2 出库动作触发与目标软件配置项识别`;
3. the first paragraph describing the software outbound trigger;
4. the remaining formula and explanatory paragraphs.

The indexed block `b_60` instead contains the preceding subsection's final
paragraph immediately followed by the first `4.3.2` paragraph. The intervening
heading is absent from that block and appears later in a different indexed
block. The resulting leaf ranked at position 0 for the manual query
`配置管理系统出库如何触发`, so the exact answer-bearing paragraph was delivered
with unrelated context from the preceding subsection.

This run used `parse_path=native_text`, not OCR. The persisted parse metadata
reported no warnings, so the defect is not explained by OCR recognition quality
or by a surfaced parse warning.

## Impact

Section boundaries and reading order can be corrupted before chunking. Exact
answer text may remain retrievable, but it can be attached to the wrong context,
section title, and parent. This degrades reranking, answer grounding, citation
clarity, and any structural filter or confidence signal that relies on section
identity.

The downstream chunker preserves the combined normalized block as one root and
leaf; it cannot recover the missing boundary from the text it receives.

## Evidence or Reproduction

- Source fixture:
  `tests/fixtures/documents/SCM优化方案.pdf`, PDF page 35 (printed page 29),
  section `4.3.2`.
- Visual rendering and `pdfplumber` native text extraction both place the
  `4.3.2` heading between the two paragraphs in the correct order.
- Milvus leaf `SCM优化方案.pdf_b_60_leaf_0` and ParentChunkStore root
  `v4_full::SCM优化方案.pdf_root_b_60` contain the cross-heading paragraph
  merge and retain section title `4.3 基于规则的历史变更信息提取方法`.
- Persisted metadata reports `parse_engine=deepdoc`, `parse_path=native_text`,
  76 pages, zero parse warnings, and a 169074 ms parse duration.
- `parsed_to_chunks()` creates one root per non-grouped normalized block and
  carries its text unchanged, locating this corruption upstream of ordinary
  leaf splitting. The exact DeepDoc merge/layout subroutine responsible has not
  yet been isolated.

## Workaround

For high-value exact answers, inspect the rendered source page and adjacent
ranked chunks rather than assuming one retrieved leaf respects the visible
section boundary. Treat a chunk containing text from both sides of a missing
heading as structurally unreliable even when its answer sentence is correct.

## Resolution Criteria

- Native-text parsing preserves the visible order and boundary around `4.3.2`
  on the identified page.
- The preceding subsection paragraph and the first `4.3.2` paragraph are never
  emitted in the same ParsedBlock, normalized block, parent, or leaf.
- A parser/chunker integration regression verifies the heading and both
  neighboring paragraphs, not only final text presence.
- Parse diagnostics surface a boundary/order degradation if the source cannot
  be reconstructed reliably.
