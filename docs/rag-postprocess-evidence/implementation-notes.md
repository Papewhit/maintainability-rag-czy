# RAG 后处理证据链实施记录

## PR 摘要

本变更修复了 `auto_merge` 死代码，并将 rerank 候选预算与最终 `top_k` 解耦。

修复前的代码证据：

- `backend/rag/context.py` 定义 `auto_merge_documents()`。
- `backend/rag/utils.py` 定义 `_auto_merge_documents()` 包装入口。
- 修复前 `_finish_retrieval_pipeline()` 的成功路径只执行 `rerank -> structure_rerank -> confidence_gate`，没有调用 `_auto_merge_documents()`。

修复后，成功路径使用独立候选池执行
`rerank -> auto_merge -> step_chain_check -> structure_rerank -> top_k -> confidence`。

## M1 + M2 验证

- 修复前基线：独立 worktree `06faa1c` 上 `33 passed`，原始记录见
  `docs/rag-postprocess-evidence/baseline-regression.xml`。
- 新增红测最初结果：`4 failed`，分别证明候选池配置、输出量函数和 auto-merge 接线尚不存在。
- 早期 M1+M2 聚焦测试为 `40 passed`；最终全套验证见本文“最终验证”。
- M6 最终候选池评测覆盖 `10 / 15 / 20`，同时比较延迟和证据覆盖。唯一权威数值表见
  `docs/rag-postprocess-evidence/evaluation.md`，避免不同运行批次的微基准表互相冲突。

## M3 验证

`step_chain_check` 默认关闭。启用后只处理带 `list_group_id`、明确
`list_complete=false` 且 `list_order > 1` 的候选；按 `±lookback` 生成有界订单集合，
通过一次 Milvus query/组拉取相邻 parent，并按稳定候选标识去重。

这里按 OpenSpec 场景采用 parent subgroup 的 1-based 边界语义：`list_order=1` 被视为列表头，
不触发修复。chunker 现在给 root 写入 `sg_idx + 1`；leaf 继续保留 0-based
`list_item_index`，step-chain 只消费 root，因此两种字段语义不会混用。Milvus 相邻查询同时
约束 `filename` 和可用的 `index_profile`，避免跨文档或跨 profile 拼接。旧 profile 缺字段时
保持 no-op；开关仍默认关闭，需重建索引后再启用。

## M4 验证

实体 metadata 分量复用现有 score-fusion：query entity type 覆盖率占 70%，
`term_match_count / 5` 的封顶密度占 30%。实体来自已有 terminology preflight 的
`term_matches`，也兼容未来 intent routing 的 `query_entities`。没有 query entities 或旧 chunk
没有 `entity_types` 时，实体分数为 0，并保留原有通用 metadata 分量行为。

rerank cache key 加入排序后的 query entity types，避免术语表启用前后的缓存结果交叉复用。
trace 记录是否实际应用实体分量，以及候选中的最大 type coverage 和 match density。

## M5 验证

项目不存在设计稿所称的 `RagTraceMeta` 类；实际 API 契约是
`backend.contracts.schemas.RagTrace`，内部静态契约是 `RetrievalMeta/RagTrace` TypedDict。
本阶段同时更新三处真实契约，并保留现有类名以避免无意义 wrapper。

后处理每个阶段现在独立捕获异常，记录 `stage_errors`、`<stage>_skipped` 和错误字段，
并把上一阶段输出继续向下传递。完整测试结果以最终验证记录为准。

## 最终验证

- unit：`481 passed`
- integration（排除 slow）：`15 passed, 1 skipped, 5 deselected`
- eval + regression：`68 passed, 10 subtests passed`
- 完整后处理 E2E：`1 passed`
- 前端契约脚本：`15 checks passed`
- backend compileall、OpenSpec strict validation、`git diff --check`：通过
