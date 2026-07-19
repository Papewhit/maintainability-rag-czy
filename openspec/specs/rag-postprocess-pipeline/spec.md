# rag-postprocess-pipeline

## Purpose

RAG 检索后处理管线：定义候选重排、父块合并、步骤链补齐、结构重排、结果截断、置信度门控及其可观测性契约。
## Requirements
### Requirement: 后处理管线顺序
Precise 路径 MUST 保持 `rerank → auto_merge → step_chain_check → structure_rerank → top_k_truncate → confidence_gate`。Comprehensive 路径 MUST 对 clean-query baseline 与全部 LLM sub-query 扩展为 `branch-local rerank → multi_query_merge → auto_merge → step_chain_check → structure_rerank → branch-aware top_k_truncate → comprehensive confidence_gate`。每个共享结构阶段 MUST 在 merge 后只执行一次；任一可恢复阶段失败时继续使用前一阶段可用输出。

#### Scenario: precise 顺序不变
- **WHEN** QueryPlan 为 PreciseQueryPlan
- **THEN** 使用既有 shared-postprocess-v1 顺序与 trace 契约，不创建 multi-query merge 阶段

#### Scenario: comprehensive 先局部相关性再全局结构处理
- **WHEN** QueryPlan 为 ComprehensiveQueryPlan
- **THEN** clean-query baseline 与每个生成分支先产生 query-local rerank pool；multi_query_merge 去重融合 branch provenance 后，auto_merge、step-chain、structure rerank、最终截断和 confidence 各执行一次；baseline 不占生成分支 reservation 席位

#### Scenario: comprehensive 分支失败
- **WHEN** 一个分支的 retrieve 或 local rerank 失败
- **THEN** 记录 branch-scoped error；保留其他分支及该分支失败前仍可用的候选；不得因单分支失败清空 global candidate pool；retrieve 通过 `retrieval_mode="failed"`/stage_errors 返回失败或 local rerank 通过 meta 返回 error 时，即使没有抛异常也必须进入相同的分支降级诊断与 comprehensive confidence 输入

#### Scenario: precise 完整管线执行
- **WHEN** precise 检索返回 candidate_k 个候选 chunk
- **THEN** 依次执行既有 6 个阶段；最终输出 top_k 个 chunk；rag_trace 中每个阶段的耗时字段（rerank_ms / auto_merge_ms / step_chain_ms / structure_rerank_ms / confidence_ms）填充

#### Scenario: 任意共享阶段失败的降级
- **WHEN** precise 或 comprehensive 的某个共享后处理阶段抛异常
- **THEN** 在 stage_errors 中记录 stage 名和原因；用上一阶段输出继续后续安全阶段；trace 中标记 `<stage>_skipped=true`；不得清空已经合并的可用证据；multi_query_merge 失败时还必须保留 branch union，并按 candidate identity 将所有重复项的已知 branch provenance 求并集后写回每个保留副本，同时记录 error、branch/merged/unique/deduplicated 候选计数，使后续去重式 branch-aware selection 与 confidence 仍能识别全部成功分支

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
Precise 路径继续以 `RERANK_CANDIDATE_POOL_SIZE` 控制单 query rerank 输出。Comprehensive 路径 MUST 将该值解释为跨 clean-query baseline 与全部 sub-query 共享的全局 rerank 输出候选预算，并由 effective postprocess profile 的 budget policy 分配；CrossEncoder pair budget 由当前 device tier 的 `RERANK_INPUT_K_CPU/GPU` 解析，未配置时回退到输出候选预算。最终 top_k 仍只在全局 structure rerank 后截断。

#### Scenario: comprehensive 不复制候选池预算
- **WHEN** RERANK_CANDIDATE_POOL_SIZE=20 且有 4 个 sub-query
- **THEN** baseline + 4 个生成分支合计的 rerank 输出候选预算为 20，而不是每个分支 20；pair budget 按 device-tier input cap 独立计算；trace 记录 `sub_query_count=4`、`retrieval_branch_count=5`，并分别记录每个分支及总量的 allocated/used output budget 和 pair budget

#### Scenario: budget 不足安全降级
- **WHEN** 某分支未获得 CrossEncoder 配额
- **THEN** 该分支使用 Milvus local rank 继续进入 multi_query_merge；后处理标记局部 rerank budget exhaustion，但不把它视为无召回

#### Scenario: pair 配额小于 output 配额
- **WHEN** 某分支获得的 CrossEncoder pair 配额小于其 output candidate 配额
- **THEN** 已配对候选按 CrossEncoder local rank 排在前面，剩余 output 配额由未配对候选按 Milvus local rank 补齐；不得因 pair cap 较小而静默缩小该分支的 merge pool

#### Scenario: precise 标准配置
- **WHEN** precise 路径下 RERANK_CANDIDATE_POOL_SIZE=20，candidate_count=50，top_k=5
- **THEN** rerank 输出 20 个 chunk；auto_merge / step_chain_check / structure_rerank 在 20 个候选上工作；最终输出 5 个

#### Scenario: precise 候选不足
- **WHEN** precise 路径 candidate_count=10 < RERANK_CANDIDATE_POOL_SIZE
- **THEN** rerank 输出全部 10 个候选；其余阶段在 10 个上工作；最终输出 min(10, top_k)

#### Scenario: RERANK_TOP_N 兼容
- **WHEN** 部署方设置 RERANK_TOP_N=15（旧配置）
- **THEN** precise 路径等价于 RERANK_CANDIDATE_POOL_SIZE=15；comprehensive 路径将 15 解释为全局共享 budget；deprecation 警告输出到日志

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

#### Scenario: 同一 group 多个不连续截断点
- **WHEN** top-K 中同一 filename / index_profile / list_group_id 同时包含 list_order=2 和 list_order=6 的不完整 parent，且 lookback=2
- **THEN** step_chain_check MUST 累积两个 order，并通过一次 Milvus 查询获取邻域并集 1、3、4、5、7、8；MUST NOT 只修复第一个 order；trace 中该 group 只记录一次

#### Scenario: 关闭状态
- **WHEN** `STEP_CHAIN_CHECK_ENABLED=false`
- **THEN** 阶段完全跳过；trace 中 `step_chain_check_enabled=false`

### Requirement: entity 信号融入 score fusion
当 `RERANK_SCORE_FUSION_ENABLED=true`、terminology preflight 输出 query `term_matches`，且 chunk 携带 terminology 扫描产生的 `entity_types` / `term_match_count` metadata 时，rerank score fusion 的 metadata 分量 MUST 使用这些术语信号计算。QueryPlan 或 intent classifier MUST NOT 作为 query semantic entities 的生产者；实现中的 `query_entities`、`entity_types`、`entity_type_coverage` 等既有字段名 SHALL 视为 terminology 历史命名，不得解释为实例级实体匹配。

#### Scenario: terminology 类型命中加分
- **WHEN** `RERANK_SCORE_FUSION_ENABLED=true`，query term_matches 的类型为 `[product_model, component]`，某 chunk 的 entity_types 为 `[product_model, component, maintenance_action]`
- **THEN** metadata score 大于 0；该 chunk 的 final_score 在 metadata 分量上获得加权；trace 中现有 `entity_type_coverage = 1.0` 表示两种 query 术语类别均被覆盖，不表示 canonical/value 实例完全匹配

#### Scenario: term_match_count 表示 chunk 术语密度
- **WHEN** chunk 的 `term_match_count=3`
- **THEN** metadata score MAY 将其作为封顶的 chunk-wide 术语密度信号；MUST NOT 将其解释为当前 query 的三个术语都在 chunk 中精确命中，也 MUST NOT 据此生成实例级 entity coverage

#### Scenario: score fusion 关闭
- **WHEN** `RERANK_SCORE_FUSION_ENABLED=false`，即使 query 和 chunk 都带 terminology metadata
- **THEN** terminology metadata 分量不参与最终分数；trace 中 `entity_metadata_score_applied=false`

#### Scenario: 无 terminology 信号降级
- **WHEN** query term_matches 为空，或 chunk 的 entity_types 为空
- **THEN** terminology metadata score 为 0；与 terminology 未上线时的行为等价；trace 中 `entity_metadata_score_applied=false`

#### Scenario: intent parser 不提供 metadata fusion 信号
- **WHEN** intent classifier 产出 PreciseQueryPlan 或 ComprehensiveQueryPlan
- **THEN** 两种 plan 均不含 entities；postprocess MUST NOT 从 intent result 合成 query_entities，terminology preflight 仍是 query 侧术语信号的唯一生产者

#### Scenario: 数据缺失不报错
- **WHEN** chunk metadata 不含 entity_types 字段（旧 schema）
- **THEN** 视为空列表处理；不抛异常

#### Scenario: Milvus metadata 编解码边界
- **WHEN** 正常 ingestion 或 terminology rescan 将 entity_types 写入 Milvus
- **THEN** 两条写入路径 MUST 使用相同的 JSON string wire format；hybrid、split dense/sparse、dense fallback 三条检索路径 MUST 将其解码为 list[str] 后再交给后处理管线

#### Scenario: 历史 list 表示兼容
- **WHEN** 旧 collection 的 dynamic field 返回 list[str]，或新记录返回 JSON string array
- **THEN** 两种表示 MUST 规范化为等价的去重 list[str]，并产生相同 metadata fusion 分数和 rerank cache signature

#### Scenario: 非法 entity_types 安全降级
- **WHEN** Milvus 返回非法 JSON、非数组 JSON 或不支持的 entity_types 类型
- **THEN** 视为空列表处理；MUST NOT 按字符串字符参与术语类别覆盖率计算，MUST NOT 阻断检索

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
