# RAG 后处理设计模糊地带与实现决策

## 1. confidence gate 与 top-k 的先后顺序

- 模糊点：proposal 的概述出现过 `confidence_gate -> top_k_truncate`，delta spec 和 design 的
  决策图则要求 `top_k_truncate -> confidence_gate`。
- 假设：confidence 应评估最终实际提供给回答生成的证据，而不是更大的中间候选池。
- 解决：以 delta spec 和 design 决策为准，先截断最终 top-k，再执行 confidence gate；E2E
  明确验证 confidence 收到最终 3 条证据。

## 2. `list_order` 的层级与基数

- 模糊点：规格把 `list_order=1` 当列表头，但现有 chunker 只给 leaf 写 0-based
  `list_item_index`，parent 没有顺序。
- 假设：step-chain 的修复对象应是 parent subgroup，而不是单个 leaf item。
- 解决：parent 写入 1-based `sg_idx + 1`；leaf 继续保留 0-based item order；step-chain
  只消费 `chunk_level=1`/root，避免混用两种语义。旧索引需重建，功能默认关闭。

## 3. `list_group_id` 的唯一性

- 模糊点：设计示例只按 `list_group_id + list_order` 查询，但实际 group ID 会在不同文件中
  重复，也可能跨 index profile 重复。
- 假设：相邻步骤必须来自同一文件和同一索引 profile。
- 解决：Milvus query 额外约束 `filename`，并在 metadata 可用时约束
  `index_profile`；测试覆盖 filter 表达式。

## 4. 候选池大小与 CrossEncoder 成本

- 模糊点：风险说明推断 pool 从 5 增到 20 会令 CrossEncoder 约慢 4 倍，但现有实现用
  `RERANK_INPUT_K_CPU/GPU` 独立控制模型输入，candidate pool 控制排序输出数。
- 假设：保留现有 input cap 是兼容性要求；不应让输出预算隐式改写设备预算。
- 解决：候选池与最终 top-k 解耦，但不改变 input cap 语义；cache key 加入 entity types；
  评测明确记录模型无关限制，默认选择 20，生产发布前仍需跑真实 GPU/gold dataset。

## 5. entity metadata 缺失时的旧行为

- 模糊点：设计称 metadata 分量是占位，但当前代码已有 anchor/section/page 的通用
  metadata score。
- 假设：“无 entity 信号时行为兼容”优先于删除现有通用排序信号。
- 解决：新增纯 `_metadata_score(doc, query_entities)`，无 entity 时返回 0；score fusion 在
  entity 存在时使用实体分数，否则继续使用原通用 metadata score。`applied` 只有在 fusion
  开启且 metadata 权重大于 0 时才为 true。

## 6. `RagTraceMeta` 的真实类型

- 模糊点：tasks 指向不存在的 `RagTraceMeta`，仓库实际 API 模型为
  `backend.contracts.schemas.RagTrace`，内部契约为 `RetrievalMeta/RagTrace` TypedDict。
- 假设：新增同义 wrapper 会制造第二套 trace schema。
- 解决：直接更新三处真实契约，不新增 alias/wrapper；新增 schema 测试验证序列化不会丢字段。

## 7. 阶段失败后的执行方式

- 模糊点：“用上一阶段输出作为最终结果”没有说明是否立即退出，还是继续执行后续安全阶段。
- 假设：后处理阶段相互独立；某阶段失败不应阻止后续纯算法阶段继续改善已有证据。
- 解决：每个阶段局部捕获异常，将上一阶段输出传给下一阶段，同时记录
  `stage_errors`、`<stage>_skipped`、`<stage>_error` 和耗时。最终不会因单个后处理异常清空证据。

## 8. 性能验收的环境边界

- 模糊点：任务要求 P50/P95，但没有规定必须使用生产模型、GPU 或 Milvus 数据集。
- 假设：本 change 必须提供可重复的 CI 评测，同时诚实区分微基准与生产性能。
- 解决：CI 使用无模型确定性 reranker 比较 5/10/20，并将数据固化；报告不宣称生产延迟
  达标，明确把真实 GPU 和 125 条 gold dataset 复跑列为发布步骤。
