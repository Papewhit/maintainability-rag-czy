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
- **THEN** Level 1 的新候选 MUST 完整经过共享 postprocess 和 confidence 后再进入 router；若仍不达标才进入 Level 2；不并行执行；trace 字段 `fallback_path=[1, 2]`

### Requirement: 附件硬范围与统一证据路径
当请求包含 `context_files` 时，系统 MUST 将其解释为用户显式选择的硬检索范围。所有初检及 Level 1/2 重检的每个既有检索分支 MUST 使用覆盖全部 `context_files` 的组合 filename filter，MUST NOT 因附件而新增无过滤的全库分支、附件专用分支，也 MUST NOT 逐附件直取 chunk 后追加到最终上下文。全部候选 MUST 平等进入同一去重、rerank、postprocess、final top-k 和 confidence 流程。

#### Scenario: 多附件只形成一次检索范围
- **WHEN** 请求包含一个或多个 `context_files`
- **THEN** 精确管线的单个检索分支使用一个组合 filename filter 返回候选；附件数量不得直接产生逐文件语义检索或逐文件直取补充调用

#### Scenario: 综合管线不因附件增加分支
- **WHEN** 综合管线请求包含一个或多个 `context_files`
- **THEN** baseline 与既有 LLM sub-query 分支数量仍由 intent-routing plan 决定；每个分支携带相同组合 filename filter，附件不得产生额外 retrieval branch

#### Scenario: 附件候选统一评分
- **WHEN** 带 `context_files` 的检索返回候选
- **THEN** 所有候选在进入回答上下文前经过共享 postprocess；confidence MUST 基于同一 final top-k 计算；不得在 confidence 之后追加未评分附件 chunk

#### Scenario: Fallback 重检刷新信号
- **WHEN** Level 1 或 Level 2 完成一次重检
- **THEN** 系统 MUST 使用该轮新候选重新执行完整 postprocess 和 confidence，再将新信号交给 Fallback Router；MUST NOT 复用上一轮 confidence

#### Scenario: Fallback 完整轮超时保持上一轮原子证据状态
- **WHEN** Level 1/2 已构造新 plan 或 scope，但完整 retrieval/postprocess/final top-k 轮在完成前超时或失败
- **THEN** 返回 router 的 query plan、final documents 与 branch identities MUST 全部来自上一轮已完成状态；MUST NOT 把新 plan 与旧 final documents 组合，也不得按新索引解释旧 branch identity

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

#### Scenario: 多个生成分支同时失败
- **WHEN** 多个 LLM sub_query 在同一轮失败
- **THEN** Level 1 MUST 按 priority 升序、再按稳定 branch_id 选择失败分支；单轮最多重写 `RAG_FALLBACK_COMPREHENSIVE_REWRITE_WINDOW` 个，默认窗口为 2；窗口外失败分支保持原样；`level1_comprehensive_strategy`、`level1_new_sub_queries` 与 `level1_sub_query_replaced` MUST 使用按该稳定顺序记录的列表

#### Scenario: 综合 Level 1 通用 trace
- **WHEN** 综合管线完成 Level 1 rewrite
- **THEN** trace MUST 记录 `level1_strategy="comprehensive"`；`level1_rewritten_query` MUST 是按 priority、稳定 branch_id 和每个分支输出顺序展平的 query 字符串列表；精确管线的同名字段继续是单个字符串

### Requirement: 可信 Filter 产生契约
在启用多级 Fallback 前，精确管线 planner MUST 将 `filter` 收紧为可信的用户硬范围。只有确定性信号 SHALL 产生 filter：请求中的 `context_files`、解析成功且每个文档提示唯一匹配一个文件的明确封闭范围措辞（例如“仅在/只基于《A》”），以及解析成功、每个文档提示唯一匹配一个文件且能表达范围选择的精确文档引用（例如“《A》中……”）。文件名字符串匹配分数本身 MUST NOT 产生 filter。classifier 的 `scope_hint` MUST NOT 单独将 boost/none 提升为 filter，也 MUST NOT 将确定性 hard filter 降级。没有确定性 hard-filter 信号时，classifier 只 MAY 在 boost 与 none 之间提供提示。

#### Scenario: context_files 产生 filter
- **WHEN** 请求包含 `context_files`
- **THEN** planner 输出 scope_mode=filter，matched_files 精确等于去重后的 context_files；classifier hint 不得覆盖该结果

#### Scenario: 明确封闭措辞产生 filter
- **WHEN** 查询包含解析成功且未被否定的“仅在/只基于《A》”等封闭范围措辞，并解析到唯一可用文件
- **THEN** planner 输出 scope_mode=filter，并消费已确认归属 scope 的文档 span

#### Scenario: 精确文档范围引用产生 filter
- **WHEN** 查询使用可被确定性解析为范围选择的精确文档引用（例如“《A》中……”），且文档引用解析成功
- **THEN** planner 输出 scope_mode=filter；文件匹配分数仅用于确认引用对应的文件，不单独决定硬范围语义

#### Scenario: 单个 hard-scope 提示匹配多个文件时仅 boost
- **WHEN** 一个明确封闭或精确范围文档提示同时匹配多个达到 routable threshold 的文件
- **THEN** 该提示视为未唯一解析，MUST NOT 产生 filter；最多形成包含这些匹配文件的 boost；多个彼此独立且各自唯一解析的 hard-scope 提示 MAY 共同形成组合 filter

#### Scenario: 文档名后的常见中词组不是范围标记
- **WHEN** 已解析文档提示后紧接“中心思想”“中文翻译”“中英文术语”“中外方案”“中长期计划”“中短期计划”“中间章节”或“中部结构”等常见词组
- **THEN** 其中的“中” MUST NOT 被解释为“《A》中……”范围标记；该文档提示最多产生 boost，相关词组文本保留在 semantic query

#### Scenario: 高字符串匹配分数本身不是硬范围
- **WHEN** 文档标题与文件名匹配分数大于等于 DOC_SCOPE_MATCH_FILTER，但查询没有 context_files、封闭范围措辞或精确范围引用
- **THEN** planner MUST NOT 仅凭分数输出 filter；MAY 输出 boost

#### Scenario: classifier 不得提升为 filter
- **WHEN** 确定性解析仅得到 boost 或 none，而 classifier 输出 scope_hint=filter
- **THEN** 最终 scope_mode MUST NOT 为 filter；planner 保持确定性 hard-boundary 判断，并将 classifier hint 限制在非硬范围行为内

#### Scenario: Fallback 不追溯 filter 来源
- **WHEN** planner 已输出 scope_mode=filter
- **THEN** Fallback MUST 将其视为不可放宽的硬约束，不得根据 filename score、classifier hint 或 provenance 重新解释；PreciseQueryPlan MUST NOT 为此新增 scope_source

#### Scenario: 综合 source 仅用于诊断
- **WHEN** ComprehensiveQueryPlan.RetrievalScope 包含 source
- **THEN** source MAY 保留在 trace/provenance 中，但 MUST NOT 参与 Level 2 路由或决定 filter 是否可放宽；scope_mode 是下游唯一范围行为契约

### Requirement: Level 2 - Scope Relax
Level 2 MUST 是纯规则降级，MUST NOT 调用 LLM。Fallback MUST 只消费 `scope_mode` 作为权威行为契约：`filter` SHALL 保持 filter，`boost` SHALL 降级为 none，`none` SHALL 保持 none。candidate_k SHALL 以 1.5x 为增长目标、且 SHALL 复用 `RAG_FALLBACK_EXPANDED_CANDIDATE_K` 作为扩大量上限；该上限 MUST NOT 使有效 candidate_k 低于上一轮已完成值。same_root_cap SHALL 在本轮临时增加 1。Level 2 MUST NOT 创建、删除或调整 semantic entity filter。

#### Scenario: filter 硬范围保持不变
- **WHEN** Level 2 触发且当前 scope_mode=filter
- **THEN** scope_mode、filename filter 和 matched_files MUST 保持不变；Level 2 MAY 放大 candidate_k 或放宽 same_root_cap，但 MUST NOT 检索范围外内容；trace 记录 `scope_mode: filter preserved`

#### Scenario: boost 软偏好降级
- **WHEN** Level 2 触发且当前 scope_mode=boost
- **THEN** PreciseQueryPlan MUST 原子更新为 scope_mode=none、matched_files=()、route=global_hybrid；ComprehensiveQueryPlan 的 retrieval_scope MUST 原子更新为 scope_mode=none、matched_files=()；trace 记录 `scope_mode: boost -> none`

#### Scenario: none 仅放宽参数
- **WHEN** Level 2 触发且当前 scope_mode=none
- **THEN** scope_mode 保持 none；PreciseQueryPlan 保持 route=global_hybrid 且 matched_files 为空；只放大 candidate_k、放宽 same_root_cap 等候选参数

#### Scenario: candidate_k 放大
- **WHEN** Level 2 触发
- **THEN** 检索的 candidate_k 以原值的 1.5x 为增长目标，同时受既有 `RAG_FALLBACK_EXPANDED_CANDIDATE_K` 扩大量上限保护；有效值 MUST NOT 小于上一轮已完成值

#### Scenario: candidate_k 上限低于上一轮值
- **WHEN** Level 2 触发且既有 `RAG_FALLBACK_EXPANDED_CANDIDATE_K` 小于上一轮已完成的 candidate_k
- **THEN** 本轮 MUST 保持上一轮 candidate_k，MUST NOT 将配置上限解释为缩小候选池；trace MUST 记录保持后的有效值

#### Scenario: 综合管线 Level 2
- **WHEN** 综合管线触发 Level 2
- **THEN** 对每个 LLM sub_query 独立放宽结构 scope，clean-query baseline 使用同一轮放宽后的共享结构约束重建但文本仍等于 plan.clean_query；继续使用 intent-routing 解析出的完整 postprocess profile；不得在 Level 2 graph 节点内临时替换 merge/selection/budget 单个组件；trace 记录每个 retrieval branch 的放宽细节

### Requirement: Level 3 - Insufficient Evidence
Level 3 MUST NOT 调用检索，`generate_level3_answer()` MUST NOT 调用 LLM，SHALL 使用模板化输出告知用户证据不足。精确管线和综合管线模板 MUST 不同。综合 coverage、维度证据摘录和 baseline evidence MUST 只消费本轮 final top-k 及其实际表示的 branch identity，MUST NOT 从被 final selection 淘汰的 raw branch candidates 恢复证据。forced-preload MUST 通过系统消息交付该模板约束；optional-tool MUST 在 tool response 中交付同一模板约束，再由现有 agent LLM 完成回答。

#### Scenario: 精确管线 Level 3 输出
- **WHEN** 精确管线以 scope_mode=boost 或 none 进入 Level 3
- **THEN** 回答以 "未在当前知识库中找到与当前查询及结构范围匹配的足够依据" 开头；附带 "已尝试: Level X → Level Y"；末尾给出建议（检查上传 / 调整问法 / 提供上下文文件）

#### Scenario: 精确管线 filter 范围内证据不足
- **WHEN** 精确管线以 scope_mode=filter 进入 Level 3
- **THEN** 回答 MUST 明确说明“未在你指定的文档范围内找到足够依据；本次没有搜索该范围之外的知识库”；MUST NOT 声称整个知识库没有答案

#### Scenario: 综合 Level 3 部分覆盖生成受限部分解答
- **WHEN** 本轮 final top-k 表示 X 个生成维度且 `0 < X < Y`
- **THEN** 确定性模板 MUST 标明 `X/Y`、列出每个已覆盖维度的证据摘录及其既有 filename/page 来源，并明确列出未覆盖维度；forced-preload 与 optional-tool 的同一模板约束 MUST 要求现有回答模型只基于这些摘录为已覆盖维度分别生成部分解答、保留来源并声明整体证据不足；MUST NOT 回答未覆盖维度，也 MUST NOT 在缺少必要维度时生成跨维度比较、汇总或总体建议；`generate_level3_answer()` 本身仍 MUST NOT 调用 LLM

#### Scenario: 综合 Level 3 只消费最终证据
- **WHEN** raw branch candidates 包含某生成维度，但该维度没有进入本轮 final top-k 的 represented branch identities
- **THEN** 该维度 MUST 计为未覆盖，且其 raw candidate MUST NOT 出现在 Level 3 coverage、证据摘录、baseline evidence 或 trace 中

#### Scenario: 只有 baseline 有证据
- **WHEN** 所有 LLM sub_query 都未形成可用证据，但 clean-query baseline 有可用候选
- **THEN** baseline 证据不得增加已完成分析维度，Level 3 标明 "已完成 0/Y 个分析维度"；回答 MUST 输出一条明确标注为“一般背景证据、不得计入分析覆盖率”的 baseline 证据摘录，并 MUST 明确约束现有回答模型只展示该背景证据、不得生成分析解答；不得据此宣称综合分析 coverage 已满足

#### Scenario: 全维度有最终证据但整体置信度不足
- **WHEN** 本轮 final top-k 表示全部 Y 个生成维度，但整体 confidence 仍要求进入 Level 3
- **THEN** 回答 MUST 标明 `Y/Y`，说明“全部维度已有相关证据，但整体置信度不足”，列出各维度及其既有 filename/page 来源的证据摘录并明确不是生成答案；`未覆盖维度` MUST 为空，建议 MUST 改为核对证据来源或补充更具判别力的查询条件，不得要求补充未覆盖维度；该场景 MUST NOT 授权现有回答模型生成综合解答

#### Scenario: 完全无证据
- **WHEN** 本轮 final top-k 不表示 baseline 或任何生成维度（综合），或精确管线的 final top-k 为空
- **THEN** 回答只包含"证据不足"声明 + 建议；不附带任何 chunk 引用

### Requirement: Level 2 触发时的 Prompt 注入
当 fallback_level=2 时，`prepare_rag_answer_messages` MUST 根据 Level 2 前后的 scope_mode 追加准确的“非精确匹配”声明指令到 RAG prompt 之后。

#### Scenario: 注入声明
- **WHEN** RagTurnContext.fallback_level == 2 且 scope_mode 从 boost 降为 none
- **THEN** 系统消息要求 LLM 说明“未在优先文件中找到精确匹配，以下包含范围外相关参考”；对每个引用标注是否完全匹配；建议用户补充信息

#### Scenario: filter 域内放宽声明
- **WHEN** RagTurnContext.fallback_level == 2 且 scope_mode=filter 保持不变
- **THEN** 系统消息要求 LLM 说明“未在指定文档范围内找到精确匹配，以下是该范围内的相关参考；本次没有搜索范围外知识库”；不得声称扩大了文档范围

#### Scenario: none 域内候选放宽声明
- **WHEN** RagTurnContext.fallback_level == 2 且 scope_mode 从 none 保持 none
- **THEN** 声明“未在当前知识库中找到精确匹配，以下是扩大候选池及放宽结构限制后得到的相关参考；本轮没有改变文档检索范围”；不得声称存在优先文件或检索了范围外内容

#### Scenario: optional-tool 交付声明
- **WHEN** Level 2 或 Level 3 经 `search_knowledge_base` optional-tool 路径完成
- **THEN** tool response MUST 在检索内容之前携带与 forced-preload 相同的 scope-aware 声明或 Level 3 模板约束，再由现有 agent LLM 完成回答；不得新增第二套文案

#### Scenario: 其他 level 无注入
- **WHEN** fallback_level 为 0/1/3
- **THEN** 不注入此声明；使用各 level 自己的 prompt 处理逻辑

### Requirement: 预算控制
每次 RAG 请求 MUST 有整体预算 `RAG_FALLBACK_TOTAL_BUDGET_MS`（默认 8000ms）。Level 1 与 Level 2 MUST 各有自己的预算上限。Level 3 MUST 是只受整体预算约束的确定性终止步骤，MUST NOT 新增独立预算配置或入口阈值。预算不足以进入 Level 1/2 时 SHALL 直接降到 Level 3。受支持的预算配置值 MUST 为正整数毫秒；非正值属于 unsupported configuration，本 change MUST NOT 为其新增钳制、拒绝、禁用或兼容语义。

#### Scenario: 整体预算检查
- **WHEN** 准备进入 Level 1 或 Level 2
- **THEN** 计算 `remaining = total_budget - elapsed_since_turn_start`；如 remaining 小于该 level 的预算，跳过该 level 直接进入无独立预算检查的 Level 3

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
- **THEN** 对应字段填充：`level1_strategy` / `level1_ms` / `level1_rewritten_query` / `level2_relaxations` / `level2_ms` / `level3_reason` / `level3_ms`；精确 Level 1 的 `level1_rewritten_query` 是字符串，综合 Level 1 的 `level1_strategy` 固定为 `comprehensive` 且 `level1_rewritten_query` 是稳定排序的字符串列表

#### Scenario: emit_rag_step 事件
- **WHEN** 进入或离开任何 fallback level
- **THEN** 通过 `emit_rag_step` 发送步骤事件（icon, label, detail, level, signal）；前端可折叠为思考过程展示

### Requirement: 与现有 RAG_FALLBACK_ENABLED 配置兼容
系统 MUST 保留 `RAG_FALLBACK_ENABLED` 作为总开关。SHALL 新增 per-level 开关 `RAG_FALLBACK_LEVEL1_ENABLED` / `RAG_FALLBACK_LEVEL2_ENABLED`。

#### Scenario: 总开关关闭
- **WHEN** `RAG_FALLBACK_ENABLED=false`
- **THEN** 所有 fallback level 跳过；无论 confidence 是否请求 fallback，都使用 Level 0 已完成 postprocess 的 final top-k 按现有常规回答流程直接回答；不得进入 Level 3 模板化输出；trace 保留原始 confidence 信号并记录 `fallback_disabled=true`

#### Scenario: per-level 关闭
- **WHEN** `RAG_FALLBACK_LEVEL1_ENABLED=false` 但 `RAG_FALLBACK_LEVEL2_ENABLED=true`
- **THEN** router 跳过 Level 1，触发条件下直接进 Level 2；trace 记录 `level1_skipped_by_config`

#### Scenario: deprecation 警告
- **WHEN** 启动时检测到 `RAG_FALLBACK_ENABLED` 仍然显式设置
- **THEN** 日志输出 deprecation 警告，提示 v2 将移除此配置；推荐使用 per-level 开关
