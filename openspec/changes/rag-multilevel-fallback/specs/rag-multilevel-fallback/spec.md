## ADDED Requirements

### Requirement: 分级 Fallback 框架
RAG 管线 MUST 支持 0-3 共 4 个 fallback level。Level 0 SHALL 为预处理（每次必做），Level 1-3 SHALL 为按需触发的 fallback 阶段。各 level MUST 顺序执行（MUST NOT 并行），SHALL 由 Fallback Router 根据 confidence 信号决定路由。

#### Scenario: Level 0 始终执行
- **WHEN** 任何 RAG 请求进入管线
- **THEN** 依次执行意图/结构解析、成功结构 span 消费确认、terminology preflight、dense+BM25 query composition（分别由 `rag-intent-routing` 和 `rag-terminology-module` 提供）；terminology 消费结构处理后的实际检索文本而非 raw query；不提取 semantic entities，不依赖任何 fallback 信号

#### Scenario: Level 0 成功直接回答
- **WHEN** Level 0 完成后的检索结果通过 confidence gate（fallback_required=false）
- **THEN** 跳过 Level 1/2/3，直接生成回答；trace 字段 `fallback_level=0`、`fallback_path=[]`

#### Scenario: 顺序执行 Level 1 → Level 2
- **WHEN** Level 0 失败触发 Level 1，Level 1 后仍不达标
- **THEN** 进入 Level 2；不并行执行；trace 字段 `fallback_path=[1, 2]`

### Requirement: Fallback Router 规则
Fallback Router MUST 是纯规则函数（MUST NOT 调用 LLM），SHALL 接受 confidence 信号、query_plan、attempted_levels、remaining_budget 作为输入，MUST 输出 FallbackDecision（target_level、primary_signal、reason、budget_ms）。

#### Scenario: 空召回直接 Level 3
- **WHEN** confidence_reasons 包含 `no_docs`
- **THEN** target_level=3；不尝试 Level 1/2；reason 标明 "no_docs detected, retry unlikely to help"

#### Scenario: anchor_mismatch 触发 Level 1
- **WHEN** confidence_reasons 包含 `anchor_mismatch`
- **THEN** target_level=1；primary_signal="anchor_mismatch"；reason 标明 "query anchor not matching retrieved chunks"

#### Scenario: weak_margin_and_root 触发 Level 2
- **WHEN** confidence_reasons 包含 `weak_margin_and_root`
- **THEN** target_level=2；primary_signal="weak_margin_and_root"；reason 标明 "results scattered, need broader scope"

#### Scenario: low_score 触发改写
- **WHEN** confidence_reasons 包含 `low_score_and_margin`
- **THEN** target_level=1；不得使用 terminology 的 `entity_type_coverage` 推断实例级匹配或决定 scope relax

#### Scenario: 预算耗尽
- **WHEN** remaining_budget_ms < 当前 level 所需 minimum budget
- **THEN** target_level=3；reason="budget_exhausted"

#### Scenario: 已尝试 level 不重复
- **WHEN** attempted_levels=[1]，仍不达标进入下一轮 router
- **THEN** target_level=2（跳过 Level 1）；不会回 Level 1 重试

### Requirement: Level 1 - 精确管线 Query Rewrite
精确管线下 Level 1 SHALL 调用 LLM 选择 step_back / hyde / complex 策略，MUST 生成 rewritten_query。prompt 中 SHALL 注入原始 query、PreciseQueryPlan 的 anchors、doc_hints 和 scope 状态以提升 rewrite 聚焦度。

#### Scenario: step_back 策略
- **WHEN** Level 1 router LLM 选择 step_back
- **THEN** 生成抽象层的 step_back_question 和 step_back_answer；重新检索时使用 expanded_query；trace 中 `level1_strategy="step_back"`

#### Scenario: HyDE 策略
- **WHEN** Level 1 router LLM 选择 hyde
- **THEN** 生成 hypothetical_doc；用 hypothetical_doc 作为检索 query；trace 中 `level1_strategy="hyde"`

#### Scenario: Level 1 预算超时
- **WHEN** rewrite LLM 调用超过 Level 1 budget
- **THEN** future 被取消；trace 中 `level1_timeout=true`；返回 router 重新决策（通常降到 Level 3）

### Requirement: Level 1 - 综合管线 Query Rewrite
综合管线下 Level 1 MUST 使用合并的 LLM 调用（router + rewriter 同一次调用）。输入 MUST 包含完整 ComprehensiveQueryPlan、失败的 LLM sub_query、失败信号、已成功的 sub_queries。输出 MUST 包含 strategy + new_sub_queries + reason。clean-query baseline MUST NOT 成为 Level 1 rewrite 目标；重新 fan-out 时 MUST 从 plan.clean_query 原样重建 baseline。

#### Scenario: baseline 失败不触发 rewrite
- **WHEN** clean-query baseline 失败但一个或多个 LLM sub-query 可继续处理
- **THEN** Level 1 只记录 baseline diagnostics，不把 baseline 传给 rewriter，不生成 baseline 替代项；后续 fan-out 仍从 plan.clean_query 构造同一 baseline

#### Scenario: generalize 策略
- **WHEN** 失败 sub_query 无召回，且其他 sub_query 多数成功
- **THEN** LLM 倾向输出 strategy="generalize"；new_sub_queries 包含 1 个更通用的 query 替换原 sub_query

#### Scenario: decompose 策略
- **WHEN** 失败 sub_query 范围过宽
- **THEN** LLM 倾向输出 strategy="decompose"；new_sub_queries 包含 2 个更细的 query

#### Scenario: 不重复已成功 sub_query
- **WHEN** LLM 生成 new_sub_queries
- **THEN** new_sub_queries 与 succeeded_sub_queries 内容不重复（通过 prompt 约束 + 后置校验）

### Requirement: Level 2 - Scope Relax
Level 2 MUST 是纯规则降级，MUST NOT 调用 LLM。scope_mode SHALL 按 `filter → boost → none` 链路降级；candidate_k SHALL 放大 1.5x；same_root_cap SHALL 放宽。Level 2 MUST NOT 创建、删除或调整 semantic entity filter。

#### Scenario: scope_mode 降级
- **WHEN** Level 2 触发，当前 scope_mode=filter
- **THEN** 新 query_plan 的 scope_mode=boost；trace 中 `level2_new_scope_mode="boost"`、`level2_relaxations=["scope_mode: filter -> boost"]`

#### Scenario: candidate_k 放大
- **WHEN** Level 2 触发
- **THEN** 检索的 candidate_k 从原值放大 1.5x；同时受 max_candidate_k 上限保护

#### Scenario: 综合管线 Level 2
- **WHEN** 综合管线触发 Level 2
- **THEN** 对每个 LLM sub_query 独立放宽结构 scope，clean-query baseline 使用同一轮放宽后的共享结构约束重建但文本仍等于 plan.clean_query；继续使用 intent-routing 解析出的完整 postprocess profile；不得在 Level 2 graph 节点内临时替换 merge/selection/budget 单个组件；trace 记录每个 retrieval branch 的放宽细节

### Requirement: Level 3 - Insufficient Evidence
Level 3 MUST NOT 调用检索，SHALL 使用模板化输出告知用户证据不足。精确管线和综合管线模板 MUST 不同。

#### Scenario: 精确管线 Level 3 输出
- **WHEN** 精确管线进入 Level 3
- **THEN** 回答以 "未在当前知识库中找到与当前查询及结构范围匹配的足够依据" 开头；附带 "已尝试: Level X → Level Y"；末尾给出建议（检查上传 / 调整问法 / 提供上下文文件）

#### Scenario: 综合管线 Level 3 输出
- **WHEN** 综合管线进入 Level 3 且有部分 sub_query 成功
- **THEN** 回答先给出 "已完成 X/Y 个分析维度"；列出已成功的 sub_query 对应的回答；明确标注 "未覆盖维度: [...]"；建议补充资料

#### Scenario: 只有 baseline 有证据
- **WHEN** 所有 LLM sub_query 都未形成可用证据，但 clean-query baseline 有可用候选
- **THEN** baseline 证据不得增加已完成分析维度，Level 3 标明 "已完成 0/Y 个分析维度"；MAY 在明确标为一般背景证据的区域引用 baseline 候选，不得据此宣称综合分析 coverage 已满足

#### Scenario: 完全无证据
- **WHEN** baseline 与所有 sub_query（综合）或整个 query（精确）都无任何召回
- **THEN** 回答只包含"证据不足"声明 + 建议；不附带任何 chunk 引用

### Requirement: Level 2 触发时的 Prompt 注入
当 fallback_level=2 时，`prepare_rag_answer_messages` MUST 追加 "非精确匹配" 声明指令到 RAG prompt 之后。

#### Scenario: 注入声明
- **WHEN** RagTurnContext.fallback_level == 2
- **THEN** 系统消息追加：要求 LLM 在回答开头说明 "未找到精确匹配，以下是相关参考"；对每个引用标注是否完全匹配；建议用户补充信息

#### Scenario: 其他 level 无注入
- **WHEN** fallback_level 为 0/1/3
- **THEN** 不注入此声明；使用各 level 自己的 prompt 处理逻辑

### Requirement: 预算控制
每次 RAG 请求 MUST 有整体预算 `RAG_FALLBACK_TOTAL_BUDGET_MS`（默认 8000ms）。每个 fallback level MUST 有自己的预算上限。预算耗尽时 SHALL 直接降到 Level 3。

#### Scenario: 整体预算检查
- **WHEN** 进入 Level N 前
- **THEN** 计算 `remaining = total_budget - elapsed_since_turn_start`；如 remaining < level_N_budget，跳过本 level 直接 Level 3

#### Scenario: Level 内超时
- **WHEN** Level 1 LLM 调用超过 LEVEL1_BUDGET_MS
- **THEN** future 取消；trace 中 `level1_timeout=true`；下一轮 router 倾向 Level 3

### Requirement: Fallback Trace 完整性
rag_trace MUST 完整记录 fallback 决策路径和每个 level 的执行细节，供调试和"思考过程"前端展示使用。

#### Scenario: 主路径 trace
- **WHEN** 任意 RAG 请求完成
- **THEN** rag_trace 包含 `fallback_level`（最终落到的 level）、`fallback_path`（实际走过的 level 序列）、`fallback_decisions`（每次 router 决策的列表）、`fallback_total_ms`

#### Scenario: 各 level 详情
- **WHEN** Level 1/2/3 任意触发
- **THEN** 对应字段填充：`level1_strategy` / `level1_ms` / `level1_rewritten_query` / `level2_relaxations` / `level2_ms` / `level3_reason` / `level3_ms`

#### Scenario: emit_rag_step 事件
- **WHEN** 进入或离开任何 fallback level
- **THEN** 通过 `emit_rag_step` 发送步骤事件（icon, label, detail, level, signal）；前端可折叠为思考过程展示

### Requirement: 与现有 RAG_FALLBACK_ENABLED 配置兼容
系统 MUST 保留 `RAG_FALLBACK_ENABLED` 作为总开关。SHALL 新增 per-level 开关 `RAG_FALLBACK_LEVEL1_ENABLED` / `RAG_FALLBACK_LEVEL2_ENABLED`。

#### Scenario: 总开关关闭
- **WHEN** `RAG_FALLBACK_ENABLED=false`
- **THEN** 所有 fallback level 跳过；Level 0 成功直接回答；Level 0 失败也不尝试 Level 1/2，直接 Level 3 模板化输出

#### Scenario: per-level 关闭
- **WHEN** `RAG_FALLBACK_LEVEL1_ENABLED=false` 但 `RAG_FALLBACK_LEVEL2_ENABLED=true`
- **THEN** router 跳过 Level 1，触发条件下直接进 Level 2；trace 记录 `level1_skipped_by_config`

#### Scenario: deprecation 警告
- **WHEN** 启动时检测到 `RAG_FALLBACK_ENABLED` 仍然显式设置
- **THEN** 日志输出 deprecation 警告，提示 v2 将移除此配置；推荐使用 per-level 开关
