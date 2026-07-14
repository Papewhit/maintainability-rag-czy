## MODIFIED Requirements

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
- **THEN** 记录 branch-scoped stage error；保留其他分支及该分支失败前仍可用的候选；不得因单分支失败清空 global candidate pool

#### Scenario: precise 完整管线执行
- **WHEN** precise 检索返回 candidate_k 个候选 chunk
- **THEN** 依次执行既有 6 个阶段；最终输出 top_k 个 chunk；rag_trace 中每个阶段的耗时字段（rerank_ms / auto_merge_ms / step_chain_ms / structure_rerank_ms / confidence_ms）填充

#### Scenario: 任意共享阶段失败的降级
- **WHEN** precise 或 comprehensive 的某个共享后处理阶段抛异常
- **THEN** 在 stage_errors 中记录 stage 名和原因；用上一阶段输出继续后续安全阶段；trace 中标记 `<stage>_skipped=true`；不得清空已经合并的可用证据

### Requirement: rerank 候选池解耦
Precise 路径继续以 `RERANK_CANDIDATE_POOL_SIZE` 控制单 query rerank 输出。Comprehensive 路径 MUST 将该值解释为跨 clean-query baseline 与全部 sub-query 共享的全局 rerank 输出候选预算，并由 effective postprocess profile 的 budget policy 分配；CrossEncoder pair budget 由当前 device tier 的 `RERANK_INPUT_K_CPU/GPU` 解析，未配置时回退到输出候选预算。最终 top_k 仍只在全局 structure rerank 后截断。

#### Scenario: comprehensive 不复制候选池预算
- **WHEN** RERANK_CANDIDATE_POOL_SIZE=20 且有 4 个 sub-query
- **THEN** baseline + 4 个生成分支合计的 rerank 输出候选预算为 20，而不是每个分支 20；pair budget 按 device-tier input cap 独立计算；trace 记录 `sub_query_count=4`、`retrieval_branch_count=5`，并分别记录每个分支及总量的 allocated/used output budget 和 pair budget

#### Scenario: budget 不足安全降级
- **WHEN** 某分支未获得 CrossEncoder 配额
- **THEN** 该分支使用 Milvus local rank 继续进入 multi_query_merge；后处理标记局部 rerank budget exhaustion，但不把它视为无召回

#### Scenario: precise 标准配置
- **WHEN** precise 路径下 RERANK_CANDIDATE_POOL_SIZE=20，candidate_count=50，top_k=5
- **THEN** rerank 输出 20 个 chunk；auto_merge / step_chain_check / structure_rerank 在 20 个候选上工作；最终输出 5 个

#### Scenario: precise 候选不足
- **WHEN** precise 路径 candidate_count=10 < RERANK_CANDIDATE_POOL_SIZE
- **THEN** rerank 输出全部 10 个候选；其余阶段在 10 个上工作；最终输出 min(10, top_k)

#### Scenario: RERANK_TOP_N 兼容
- **WHEN** 部署方设置 RERANK_TOP_N=15（旧配置）
- **THEN** precise 路径等价于 RERANK_CANDIDATE_POOL_SIZE=15；comprehensive 路径将 15 解释为全局共享 budget；deprecation 警告输出到日志

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
