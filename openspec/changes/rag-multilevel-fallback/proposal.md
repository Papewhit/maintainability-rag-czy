## Why

当前 fallback 机制（位于 `backend/rag/pipeline.py` 的 `grade_documents_node` → `rewrite_question_node` → `retrieve_expanded`）有几个明确的问题：

1. **默认关闭**：`RAG_FALLBACK_ENABLED=false`。线上几乎没人启用，导致 confidence gate 的 `fallback_required` 信号是死信号。
2. **单层 fallback**：不论触发原因，处理方式都是"rewrite → re-retrieve"一种。没有针对不同失败模式的差异化策略。
3. **触发信号粗糙**：依赖 LLM grader 判断 binary "relevant/not relevant"，与 confidence gate 的多维信号（top_margin / dominant_root_share / anchor_match）脱节。
4. **缺乏预算控制**：当前仅有一个 `RAG_FALLBACK_TIMEOUT_SECONDS=6.0` 整体超时；没有按 level 分配预算。
5. **不区分意图**：fallback 对精确查找和综合分析使用同一套逻辑。但两类查询的失败模式和合理应对完全不同。
6. **术语增强不是预处理而是 fallback 时才做**：当前 rewrite 才用 LLM 改写 query，但术语规范化和同义扩展应该是每次必做的预处理（Level 0），不是 fallback 才补救。

设计文档（融合方案 4.10 + 4.12）要求 fallback 支持"识别证据不足、返回'未在当前知识库中找到足够依据'"，但没有给出多级 fallback 的具体形态。讨论中确定的设计：

- **Level 0**：始终做的预处理（意图分类 + 术语增强）
- **Level 1**：Query Rewrite（信号指向"问题描述不准"）
- **Level 2**：Scope Relax（信号指向"搜索约束太紧"）
- **Level 3**：明确告知证据不足

## What Changes

把 fallback 从"单层 LLM-grader 驱动"重构为"信号驱动的分级策略"：

1. **Pre-flight 阶段独立**：意图分类、确定性结构清洗与 terminology 的 normalized_query / sparse_expansion 从 fallback 路径中剥离，移到 Level 0 预处理（每次必做）。Level 0 按“意图/结构解析 → 结构 span 消费确认 → terminology preflight → dense+BM25 query composition”顺序执行；fallback 不提取 semantic entities。

2. **信号到 Level 的映射**：confidence gate 产出的多维信号（top_margin、dominant_root_share、anchor_match、sub_query_coverage）通过一个 Fallback Router 映射到目标 level。Router 是纯规则（无 LLM 调用）。terminology 的 `entity_type_coverage` 是粗粒度 rerank trace，不作为实例级 coverage 路由信号。

3. **Level 1 - Query Rewrite**：当信号指向"问题描述不准"时触发。
   - 精确管线：step_back / HyDE / complex 三种策略（保留现有 router 逻辑）
   - 综合管线：失败的 LLM sub_query 按 priority 升序、再按稳定 branch_id 选择；单轮最多处理 `RAG_FALLBACK_COMPREHENSIVE_REWRITE_WINDOW` 个（默认 2）。每个被选中的失败分支以完整 plan 上下文为输入，让 LLM 选择 generalize / specialize / replace / decompose 策略并生成新 sub_query；intent-routing 固定的 clean-query baseline 不是 rewrite 目标，重试时按 plan.clean_query 原样重建

4. **Level 2 - Scope Relax**：当信号指向"搜索约束太紧"时触发。
   - `filter` 表示可信的用户硬范围，始终保持 filter
   - `boost` 表示文件软偏好，可降级为 none；`none` 保持 none
   - candidate_k 增大 1.5x，并复用 `RAG_FALLBACK_EXPANDED_CANDIDATE_K` 作为上限
   - same_root_cap 在本轮临时增加 1
   - 答案生成时强制注入"非精确匹配"声明

5. **Level 3 - Insufficient Evidence**：所有上一级都无效或预算耗尽时触发。
   - 精确管线：明确告知"未找到与当前查询及结构范围匹配的足够依据"，附带尝试过的 level
   - 综合管线：基于本轮 final top-k 标注已覆盖与未覆盖维度；当 `0 < X < Y` 时，现有回答模型只为有来源证据的已覆盖维度生成彼此独立的部分解答，禁止回答未覆盖维度或形成跨维度总体结论；`Y/Y` 低置信场景仍只交付 evidence excerpts

6. **预算控制**：
   - `RAG_FALLBACK_TOTAL_BUDGET_MS`（默认 8000）整体上限
   - `RAG_FALLBACK_LEVEL1_BUDGET_MS`（默认 3000）
   - `RAG_FALLBACK_LEVEL2_BUDGET_MS`（默认 2500）
   - Level 1/2 入口检查各自预算；Level 3 是只受总预算约束的确定性终止步骤，不设独立预算配置

7. **意图区分**：fallback router 接收 query_plan_type 参数（precise / comprehensive），路由到不同实现。

8. **顺序执行**：Level 1 → Level 2 顺序，不并行。前级失败再走后级。

9. **Trace 完整性**：每次 fallback 尝试都记录 level、原因、策略、耗时、是否成功；前端可折叠为"思考过程"展示。

10. **配置兼容**：保留 `RAG_FALLBACK_ENABLED` 作为总开关（=false 时所有 level 跳过直接回答）。新增 per-level 开关（`RAG_FALLBACK_LEVEL1_ENABLED` / `RAG_FALLBACK_LEVEL2_ENABLED`）。现有部署环境不修改配置时行为不破坏。

11. **统一证据路径**：`context_files` 只表示每个既有检索分支的硬范围，不是额外候选来源或额外检索分支。精确管线每轮执行一次组合 filename-filtered retrieval；综合管线保留 baseline/sub-query fan-out，但每个分支携带相同硬范围。初检和每轮 Level 1/2 重检都必须让同一候选集完整经过去重、rerank、postprocess、final top-k 和 confidence；router 只消费本轮新产生的 confidence。删除附件逐文件直取 chunk 后追加到回答上下文的旁路。

12. **可信 filter 前置条件**：先收紧精确管线的 filter 产生条件。只有 `context_files`、确定性解析出的明确封闭范围措辞，以及可被确定性识别为范围选择的精确文档引用（如解析成功的“《A》中……”）可以产生 filter。单个 hard-scope 文档提示必须唯一解析到一个文件；若同一提示匹配多个文件则只产生 boost。`中` 只有作为范围标记时才产生 filter，`《A》中心思想`、`《A》中文翻译` 等常见词组混淆仍是普通文档提示。文件名字符串匹配分数本身不得把 boost 提升为 filter；classifier 的 `scope_hint` 也不得单独完成该提升。

13. **scope_mode 是行为契约**：Fallback 只消费 `scope_mode`。`filter` 不可放宽，`boost` 可放宽为 none，`none` 只调整候选参数。综合管线保留 `RetrievalScope.source` 用于 trace/provenance，但它是非权威诊断字段；不为精确管线新增 `scope_source`。

## Capabilities

### New Capabilities
- `rag-multilevel-fallback`: 分级 fallback 框架、信号-Level 映射、预算控制、意图区分

### Modified Capabilities
- `rag-intent-routing`：收紧精确 planner 的 filter producer；明确 `scope_mode` 为下游权威行为契约，综合 `RetrievalScope.source` 仅保留诊断用途；修正稳定 spec 中“Level 2 可放宽 filter”的旧约定

## Impact

**代码影响：**
- `backend/rag/pipeline.py`：
  - 重构 `grade_documents_node`：不再调 LLM grader，改为消费 confidence gate 的多维信号
  - 重构 `rewrite_question_node`：拆分为 `level1_query_rewrite_node`（按 plan_type 分支）
  - 新增 `level2_scope_relax_node`
  - 新增 `level3_insufficient_evidence_node`
  - graph 结构调整：condition edge 根据 fallback router 输出路由到 Level 1/2/3
  - 删除 `retrieve_initial` 中 `retrieve_context_documents()` 的附件直取补充；`context_files` 仅通过主检索 filename filter 生效
- `backend/rag/query_plan.py`、`backend/rag/intent.py`：收紧精确管线 filter producer；字符串相似度和 classifier hint 不得单独产生硬范围
- `backend/rag/fallback_router.py`（新文件）：信号到 level 的映射规则
- `backend/rag/runtime_config.py`：新增多个 budget 配置
- `RAG_FALLBACK_COMPREHENSIVE_REWRITE_WINDOW` 控制单轮综合失败分支改写数量（默认 2）；旧 `RAG_FALLBACK_EXPANDED_CANDIDATE_K` 作为 Level 2 candidate_k 上限继续复用
- `backend/chat/rag_execution.py`：Level 2 触发时在 prompt 中注入"非精确匹配"声明
- 现有 `RAG_FALLBACK_TIMEOUT_SECONDS` 映射到 `RAG_FALLBACK_TOTAL_BUDGET_MS`（乘 1000）
- `tests/test_fallback_router.py`、`tests/test_multilevel_fallback.py`

**接口影响：**
- rag_trace 字段：`fallback_level`（0/1/2/3）、`fallback_signals`（触发的 confidence reasons）、`fallback_path`（实际走过的 level 序列）、`level1_strategy`、`level1_rewritten_query`、`level2_relaxations`、`level3_reason`、各级 ms 字段；综合 Level 1 使用 `level1_strategy="comprehensive"` 和按稳定分支顺序排列的 rewritten-query 列表
- emit_rag_step 在 fallback 各阶段发送步骤事件，前端折叠为"思考过程"

**依赖：**
- 依赖 `rag-intent-routing`：fallback router 需要 query_plan_type 输入
- 依赖 `rag-terminology-module`：Level 0 在结构解析之后使用 terminology preflight，并以同一结构处理后的 query 基底生成 dense normalization 与 BM25 expansion
- 依赖 `rag-postprocess-evidence`：confidence gate 输出的 top score、margin、root share、anchor 和 sub-query coverage 信号

**风险：**
- 重构现有 fallback 逻辑可能引入回归（虽然现有默认关闭，但仍要保证关闭时行为不变）
- 多 level 的 trace 字段较多，可能让前端展示复杂；需要明确的折叠策略
- 附件很多时单次硬范围检索的 filter 与候选池会变大，但不应退化为“全库检索 + 每附件检索”的重复调用
- 若可信 filter 前置条件未先完成，错误的 classifier hint 会把 Level 1/2 锁在错误文件内，并导致 Level 3 将系统误判归因于用户指定范围
