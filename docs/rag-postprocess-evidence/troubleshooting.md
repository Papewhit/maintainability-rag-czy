---
document_type: troubleshooting
status: current
scope: rag.postprocess
last_verified_commit: 8babe339cda636936c6c0af3c95a99e7c77c2f19
last_verified_date: 2026-07-12
---

# RAG 证据组织排障指南

先查看 `rag_trace.stage_errors`，再按阶段查看 `rag_trace.timings` 和候选计数。

| Trace 模式 | 常见原因 | 检查与处理 |
| --- | --- | --- |
| `rerank_skipped=true` | 模型加载或推理失败 | 检查 `rerank_error`、模型路径和 device；结果已回退到检索排序 |
| `auto_merge_applied=false` 且无错误 | 同 parent leaf 数未达到阈值 | 查看 parent ID 分布和 `AUTO_MERGE_THRESHOLD` |
| `auto_merge_skipped=true` | parent store 查询失败 | 查看 `auto_merge_error`；确认 parent store 与 Milvus 索引版本一致 |
| `step_chain_repaired_groups=[]` | 功能关闭、旧索引或候选不是不完整 parent | 检查开关、`chunk_level=1`、`list_group_id/list_order/list_complete`；旧索引需重建 |
| `step_chain_skipped=true` | 相邻 parent 的 Milvus query 失败 | 查看 filename/index_profile 作用域和 Milvus filter；当前结果保留 auto-merge 输出 |
| `structure_rerank_skipped=true` | 结构字段或排序逻辑异常 | 查看 `structure_rerank_error`；当前结果保留 step-chain 输出 |
| `entity_metadata_score_applied=false` | query 或 chunk 缺实体字段 | 查看 `term_matches`、`entity_types`、`term_match_count` |
| `fallback_required=true` | top score、margin、root share 或 anchor 信号不足 | 查看 `confidence_reasons`，不要只依据单一 score 调参 |

## 候选数检查

正常情况下：

```text
candidate_count_before_rerank
  >= rerank_output_count
  >= final_top_k_count
```

auto-merge 可能减少候选数，step-chain 可能增加候选数；因此结构重排前后的数量不要求单调。
若最终证据为空而检索候选非空，应优先查找 `stage_errors`，这通常表示违反了后处理降级契约。
