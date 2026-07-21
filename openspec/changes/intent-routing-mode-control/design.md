## Context

当前 intent routing 只有 `RAG_INTENT_CLASSIFIER_ENABLED` 布尔入口：开启时由 LLM 同时选择 intent 并生成计划提示，关闭或失败时进入 precise 兼容路径。真实 `qwen-flash` 能满足当前时延预算，但已把“根据知识库，统一源图是什么”这一单点定义问题以 confidence 1.0 误判为 comprehensive，并拆成两个高度重叠的 sub-query。Prompt 调优和准确率 gate 尚未完成，用户却需要一种显式、可控的方式分别验证 precise 与 comprehensive 下游链路。

该能力跨越 frontend、ChatRequest、chat execution policy、optional-tool ContextVar 与 RAGState，但必须保持为薄控制面：模式只决定现有 intent producer 的入口，不复制 QueryPlan、query preparation、retrieval 或 fallback 实现。

## Goals / Non-Goals

**Goals:**

- 提供 `forced_comprehensive | auto_classifier | precise_only` 三态请求级模式。
- 让用户显式选择 comprehensive 时稳定触发 RAG，而不依赖 agent 是否决定调用工具。
- 复用现有环境开关、模型、schema、planner 和 graph。
- 同步/流式、forced-preload/optional-tool 和 regenerate 使用同一模式值。
- 让 trace 明确区分用户强制、环境自动与默认 precise。

**Non-Goals:**

- 不调优 classifier Prompt、阈值、模型或 sub-query quality。
- 不新增第二套 ComprehensiveQueryPlan、手写 JSON schema 或检索 graph。
- 不修改 confidence、fallback、rerank 或 postprocess 行为。
- 不把临时用户控制宣称为 classifier activation evidence。

## Decisions

### 决策 1：复用现有环境开关，只增加纯模式 resolver

请求仅增加 `force_comprehensive: bool = false`。intent routing 内部的纯 resolver 按以下优先级产生枚举值：用户 true → `forced_comprehensive`；否则 `RAG_INTENT_CLASSIFIER_ENABLED=true` → `auto_classifier`；其余 → `precise_only`。不新增含义重叠的环境变量，也不让 frontend 发送 `auto_classifier` 或 `precise_only` 等服务器策略值。

替代方案是把三态直接做成环境变量或 API enum；前者无法表达逐请求用户意图，后者允许客户端覆盖服务器是否启用自动 classifier 的治理边界，均不采用。

### 决策 2：请求只传 override，模式在 intent routing 边界解析一次

ChatRequest、RagTurnRequest/RagTurnContext 和 optional-tool ContextVar 只传递 `force_comprehensive`。`intent_parse_node` 入口的 thin wrapper 使用当前 runtime config 解析有效模式，并把它传给现有 intent builder。下游只消费既有 typed QueryPlan，不感知 UI checkbox。

该方式避免 chat policy、tool 和 graph 分别根据环境变量推导不同结果。trace 同时保留 requested/effective/source，便于证明实际路径。

### 决策 3：forced comprehensive 固定分类，不复制计划生成

`forced_comprehensive` 继续调用当前配置的 intent 模型和 `IntentDecision` schema，但向同一 classifier 增加明确的 forced-intent 约束：输出必须为合法 comprehensive decision，包含 analysis_type 和 sub_queries。现有确定性 runtime 继续构造 clean_query、retrieval_scope、postprocess profile 和 ComprehensiveQueryPlan。

如果模型/配置不可用、超时、schema 无效或仍返回 precise，系统沿用安全的 precise compatibility fallback，同时在 trace 中记录 requested forced mode、effective precise degradation 和错误；不得静默声称用户选择已生效。该 change 不增加重试或第二模型调用。

替代方案是手写默认 `general + [raw_query]` 计划，但它会制造无有效分解的伪 comprehensive 证据，因此不采用。

### 决策 4：显式 comprehensive 强制 forced-preload

用户勾选时，`plan_rag_turn()` 选择 `FORCED_PRELOAD`，reason 为 `user_forced_comprehensive`。这样即使问题没有文档关键词，也会直接执行 RAG，而不是把控制权交给 optional agent。未勾选时保留现有 context-files、document-intent 与 optional-tool policy。

### 决策 5：模式是逐请求状态，regenerate 必须复用原值

前端每个 user message 保存当次 `forceComprehensive`，请求 payload 使用该值，regenerate 从原消息恢复，而不是读取 composer 当前状态。历史 API 若不能恢复该字段，旧消息默认 false；不回填或猜测历史模式。

### 决策 6：保持 wire 与默认兼容

新字段可选且默认 false。旧客户端、未设置环境变量和默认关闭配置继续走 precise compatibility path。现有 `RAG_INTENT_CLASSIFIER_ENABLED=true` 的环境在用户未勾选时仍保持当前 auto classifier 行为。

## Risks / Trade-offs

- **用户强制 comprehensive 仍依赖模型生成 sub-query** → 强制的只是分类选择；保留 schema 校验、明确降级 trace，并由后续 Change 1 评估 sub-query quality。
- **跨 forced-preload/optional-tool 传值可能分叉** → 只传 request override，在 intent node 单点解析；为两条路径和同步/流式分别增加契约测试。
- **UI 看似保证但模型可能失败** → trace 和最终 UI 状态区分 requested/effective；失败不伪装 comprehensive success。
- **临时 workaround 演变为第二套架构** → 禁止新增 planner/graph/schema，后续可保留显式用户选择，但自动默认仍由 activation gate 决定。

## Migration Plan

1. 增加默认 false 的 API/frontend 字段和纯 resolver，不改变默认运行结果。
2. 贯通同步、流式、forced-preload、optional-tool 与 regenerate，并增加 trace。
3. 在 classifier disabled 下验证 unchecked=precise、checked=forced comprehensive；在 enabled 下验证 unchecked=auto。
4. 保持参考默认关闭；需要回滚时隐藏 checkbox 并停止发送字段，后端默认兼容路径仍有效。

## Open Questions

- 前端 checkbox 是否在成功发送后复位属于交互细节；无论视觉状态如何，每次请求都必须携带并记录自己的布尔值。
