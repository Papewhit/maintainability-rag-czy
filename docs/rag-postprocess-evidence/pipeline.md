---
document_type: behavior_evidence
status: current
scope: rag.postprocess
source_commit: 8babe339cda636936c6c0af3c95a99e7c77c2f19
source_fingerprint: sha256:41b32e61844e1c0a0b3c6011e38609e3033b321b26d07eba638fdb6a1e1423a7
executed_at: 2026-07-12T00:00:00+08:00
---

# RAG 证据后处理管线

检索候选进入固定的证据后处理顺序：

```text
rerank
  -> auto_merge
  -> step_chain_check
  -> structure_rerank
  -> top_k_truncate
  -> confidence_gate
```

`RERANK_CANDIDATE_POOL_SIZE` 默认是 20，控制 rerank 输出给后续阶段的候选数；最终
`top_k` 只在 structure rerank 完成后截断。旧 `RERANK_TOP_N` 仍能覆盖候选池，但会记录
弃用警告。

## 阶段职责

| 阶段 | 输入与输出 | 主要 trace |
| --- | --- | --- |
| rerank | 检索候选 → CrossEncoder/fusion 排序池 | `rerank_candidate_pool_size`、`rerank_output_count`、`rerank_ms` |
| auto_merge | 同 parent 的 leaf → parent 证据 | `auto_merge_applied`、`auto_merge_replaced_chunks`、`auto_merge_ms` |
| step_chain_check | 不完整 parent → 补充相邻 parent | `step_chain_repaired_groups`、`step_chain_completion_count`、`step_chain_ms` |
| structure_rerank | 证据池 → root 多样性排序池 | `structure_rerank_applied`、`structure_rerank_ms` |
| top_k_truncate | 排序池 → 最终证据 | `final_top_k_count` |
| confidence_gate | 最终证据 → fallback 信号 | `fallback_required`、`confidence_reasons`、`confidence_ms` |

step-chain 使用两跳读取。Milvus 仅索引 leaf：leaf 的 `list_order` 保留原始列表项序号，
`parent_list_order` 记录其所属的 1-based parent subgroup。修复阶段先按
`filename + index_profile + list_group_id + parent_list_order` 查询 leaf metadata，去重得到
`parent_chunk_id`，再由 ParentChunkStore 批量加载完整 parent。旧索引缺少
`parent_list_order` 时安全 no-op，启用该阶段前必须重建索引。

实体 metadata score 使用 query entity type 覆盖率和术语命中密度；只有 query 与 chunk
双方都带实体字段时才应用。旧索引缺字段时该分量为 0。

## 失败契约

每一阶段独立降级。异常会：

1. 在 `stage_errors` 追加 `{stage, error, severity, fallback_to}`；
2. 设置对应的 `<stage>_skipped=true` 和 `<stage>_error`；
3. 将上一阶段输出交给下一阶段，不清空已经得到的证据。

所有耗时都位于 `rag_trace.timings`。这些字段在成功、跳过和可恢复失败路径上保持稳定。
