## ADDED Requirements

### Requirement: 后处理管线顺序
RAG 检索的后处理阶段 MUST 按固定顺序执行：rerank → auto_merge → step_chain_check → structure_rerank → top_k_truncate → confidence_gate。每个阶段的输入 MUST 是上一阶段的输出，输出 SHALL 可被独立测试。

#### Scenario: 完整管线执行
- **WHEN** 检索返回 candidate_k 个候选 chunk
- **THEN** 依次执行 6 个阶段；最终输出 top_k 个 chunk；rag_trace 中每个阶段的耗时字段（rerank_ms / auto_merge_ms / step_chain_ms / structure_rerank_ms / confidence_ms）填充

#### Scenario: 任意阶段失败的降级
- **WHEN** 某个后处理阶段抛异常
- **THEN** 在 stage_errors 中记录 stage 名和原因；用上一阶段的输出作为最终结果（不阻断流程）；trace 中标记 `<stage>_skipped=true`

### Requirement: auto_merge 真实接入
auto_merge MUST 在 rerank 之后、structure_rerank 之前真实调用 `auto_merge_documents()`。trace 字段 `auto_merge_applied` 和 `auto_merge_replaced_chunks` MUST 反映真实执行结果，MUST NOT 被 hardcoded 为 false。

#### Scenario: 多个 leaf 来自同一 parent
- **WHEN** rerank 输出中存在 ≥ AUTO_MERGE_THRESHOLD（默认 2）个 chunk 共享同一 parent_chunk_id
- **THEN** auto_merge 将这些 leaf 合并为对应的 parent chunk；trace 中 `auto_merge_applied=true`、`auto_merge_replaced_chunks` 反映合并数量

#### Scenario: 无可合并候选
- **WHEN** rerank 输出中所有 chunk 来自不同 parent，或共享 parent 的数量未达阈值
- **THEN** auto_merge 不合并任何 chunk；trace 中 `auto_merge_applied=false`、`auto_merge_replaced_chunks=0`；不阻断流程

#### Scenario: auto_merge 关闭
- **WHEN** `AUTO_MERGE_ENABLED=false`
- **THEN** auto_merge 阶段直接跳过；trace 中 `auto_merge_enabled=false`、`auto_merge_applied=false`

### Requirement: rerank 候选池解耦
rerank 输出量 MUST 由 `RERANK_CANDIDATE_POOL_SIZE` 控制（默认 20），SHALL 与最终 top_k 解耦。最终 top_k 截断 MUST 在 structure_rerank 之后进行。

#### Scenario: 标准配置
- **WHEN** RERANK_CANDIDATE_POOL_SIZE=20，candidate_count=50，top_k=5
- **THEN** rerank 输出 20 个 chunk；auto_merge / step_chain_check / structure_rerank 在 20 个候选上工作；最终输出 5 个

#### Scenario: 候选不足
- **WHEN** candidate_count=10 < RERANK_CANDIDATE_POOL_SIZE
- **THEN** rerank 输出全部 10 个候选；其余阶段在 10 个上工作；最终输出 min(10, top_k)

#### Scenario: RERANK_TOP_N 兼容
- **WHEN** 部署方设置 RERANK_TOP_N=15（旧配置）
- **THEN** 等价于 RERANK_CANDIDATE_POOL_SIZE=15，rerank 输出 15 个；deprecation 警告输出到日志

### Requirement: step_chain_check 步骤链完整性检查
当配置 `STEP_CHAIN_CHECK_ENABLED=true` 且 chunk 携带 list_group_id 等列表 metadata 时，后处理管线 MUST 检测 top-K parent chunk 的步骤链完整性，SHALL 必要时拉取相邻 parent 补齐。

#### Scenario: 检测到截断
- **WHEN** top-3 chunk 中包含一个 list_complete=false 且 list_order=2 的 chunk
- **THEN** step_chain_check 通过 Milvus 查询同 list_group_id 且 parent_list_order=1/3 的 leaf metadata，去重得到 parent_chunk_id，再从 ParentChunkStore 批量加载相邻 parent；将未在结果中的 parent 追加到候选列表；trace 中 `step_chain_repaired_groups` 包含该 list_group_id

#### Scenario: leaf 与 parent 序号语义隔离
- **WHEN** 一个 leaf 的原始列表项 list_order 与其所属 parent subgroup 序号不同
- **THEN** leaf 的 `list_order` MUST 保留原始列表项序号，`parent_list_order` MUST 记录 1-based parent subgroup 序号；相邻 parent 查询 MUST 使用 `parent_list_order`，MUST NOT 将两种序号混用

#### Scenario: Milvus 只存 leaf
- **WHEN** 正常 ingestion 将 parent 写入 ParentChunkStore、将 leaf 写入 Milvus
- **THEN** 相邻查询 MUST 在 Milvus 使用 chunk_level=3 定位 parent_chunk_id，MUST NOT 查询不存在的 chunk_level=1 Milvus 记录；完整 parent 内容 MUST 从 ParentChunkStore 获取

#### Scenario: 完整步骤无操作
- **WHEN** top-K 中所有 chunk 的 list_complete=true 或 list_order=1
- **THEN** step_chain_check 不触发任何 Milvus query；trace 中 `step_chain_completion_count=0`

#### Scenario: 缺失 list_group_id 降级
- **WHEN** chunk 未携带 list_group_id（如来自旧 profile）
- **THEN** step_chain_check 对这些 chunk 跳过；trace 中 `step_chain_check_enabled=true` 但 `step_chain_repaired_groups=[]`

#### Scenario: leaf 缺失 parent_list_order 降级
- **WHEN** 旧索引中的 leaf 未携带 parent_list_order
- **THEN** Milvus 定位结果为空并安全降级，不解析 chunk_id 猜测 parent 序号；重新启用 step_chain 前需要重建索引

#### Scenario: lookback 窗口限制
- **WHEN** STEP_CHAIN_ADJACENT_LOOKBACK=2
- **THEN** 对 list_order=5 的 chunk，最多拉取 list_order 3、4、6、7 的相邻 parent；不无限扩散

#### Scenario: 关闭状态
- **WHEN** `STEP_CHAIN_CHECK_ENABLED=false`
- **THEN** 阶段完全跳过；trace 中 `step_chain_check_enabled=false`

### Requirement: entity 信号融入 score fusion
当 query 携带 query_entities（来自 intent classifier 或 terminology preflight）且 chunk 携带 entity_types / term_match_count metadata 时，rerank score fusion 的 metadata 分量 MUST 使用 entity 信号计算。

#### Scenario: entity 命中加分
- **WHEN** query_entities = [{type: product_model, ...}, {type: component, ...}]，某 chunk 的 entity_types = [product_model, component, maintenance_action]
- **THEN** _metadata_score(doc, query_entities) > 0；该 chunk 的 final_score 在 metadata 分量上获得加权；trace 中 `entity_type_coverage = 1.0`（query 中两种类型都被覆盖）

#### Scenario: 无 entity 信号降级
- **WHEN** query_entities 为空 或 chunk 的 entity_types 为空
- **THEN** _metadata_score = 0；与 terminology 未上线时的行为等价；trace 中 `entity_metadata_score_applied=false`

#### Scenario: 数据缺失不报错
- **WHEN** chunk metadata 不含 entity_types 字段（旧 schema）
- **THEN** 视为空列表处理；不抛异常

### Requirement: 后处理 trace 字段完整性
rag_trace MUST 包含每个后处理阶段的详细字段，供调试和评测使用。

#### Scenario: 字段集
- **WHEN** 后处理管线完整执行
- **THEN** rag_trace 至少包含：
  - `rerank_candidate_pool_size`, `rerank_output_count`, `rerank_ms`
  - `auto_merge_enabled`, `auto_merge_applied`, `auto_merge_replaced_chunks`, `auto_merge_ms`
  - `step_chain_check_enabled`, `step_chain_repaired_groups` (list), `step_chain_completion_count`, `step_chain_ms`
  - `structure_rerank_applied`, `structure_rerank_ms`
  - `entity_metadata_score_applied`, `entity_type_coverage` (可选)
  - `confidence_gate_enabled`, `fallback_required`, `confidence_reasons`, `confidence_ms`

#### Scenario: 失败时 trace 字段
- **WHEN** 后处理某阶段失败
- **THEN** 该阶段的 ms 字段记录失败前耗时；stage_errors 列表中追加 `{stage, error, severity}`；其他字段尽量保留可用值
