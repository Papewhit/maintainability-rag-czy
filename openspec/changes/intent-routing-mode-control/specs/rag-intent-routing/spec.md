## ADDED Requirements

### Requirement: 请求级 Intent Routing Mode
系统 MUST 通过单一 thin resolver 将请求级 `force_comprehensive` 与现有 `RAG_INTENT_CLASSIFIER_ENABLED` 配置解析为 `forced_comprehensive | auto_classifier | precise_only`。用户显式选择 MUST 优先于环境自动分类开关；frontend、chat policy、tool 和 graph MUST NOT 各自重新推导有效模式。

#### Scenario: 用户显式强制 comprehensive
- **WHEN** chat 请求携带 `force_comprehensive=true`
- **THEN** resolver 输出 `forced_comprehensive`，不受 `RAG_INTENT_CLASSIFIER_ENABLED` true/false 影响

#### Scenario: 未勾选且自动 classifier 开启
- **WHEN** `force_comprehensive=false` 且 `RAG_INTENT_CLASSIFIER_ENABLED=true`
- **THEN** resolver 输出 `auto_classifier`

#### Scenario: 未勾选且自动 classifier 关闭
- **WHEN** `force_comprehensive=false` 且 `RAG_INTENT_CLASSIFIER_ENABLED=false` 或未设置
- **THEN** resolver 输出 `precise_only`

### Requirement: 三态 Intent Producer 行为
`precise_only` MUST NOT 调用 intent LLM，并 MUST 复用现有 precise compatibility planner；`auto_classifier` MUST 保持现有 classifier 与失败降级语义；`forced_comprehensive` MUST 使用当前模型和唯一 `IntentDecision` schema 固定 comprehensive intent 并生成 analysis_type/sub_queries，MUST NOT 新增第二套 QueryPlan、schema 或 graph。

#### Scenario: precise-only 不调用模型
- **WHEN** 有效模式为 `precise_only`
- **THEN** intent 节点不调用 intent LLM，并输出兼容 PreciseQueryPlan

#### Scenario: forced comprehensive 成功
- **WHEN** 有效模式为 `forced_comprehensive` 且当前 intent 模型返回 schema-valid comprehensive decision
- **THEN** runtime 通过现有确定性 query preparation 构造 ComprehensiveQueryPlan 并进入现有 comprehensive graph

#### Scenario: forced comprehensive 无法生成合法计划
- **WHEN** 模型未配置、超时、返回非法 schema 或返回 precise decision
- **THEN** 系统安全降级为现有 PreciseQueryPlan，记录 requested/effective mode 与错误，且 MUST NOT 声称 forced comprehensive 成功

### Requirement: Chat 与 RAG 入口一致传递
ChatRequest MUST 以默认 false 的可选字段承载用户选择。同步/流式、forced-preload/optional-tool、附件/无附件与 regenerate MUST 把同一请求值传至 intent routing；用户强制 comprehensive MUST 选择 forced-preload 以保证 RAG 执行。

#### Scenario: 强制 comprehensive 绕过 optional agent 决策
- **WHEN** 用户勾选 comprehensive 且问题不含现有 document-intent marker
- **THEN** chat policy 仍为 `FORCED_PRELOAD`，reason 为 `user_forced_comprehensive`，RAG 收到 `force_comprehensive=true`

#### Scenario: optional-tool 传递未勾选状态
- **WHEN** 未勾选请求经 optional agent 调用 knowledge tool
- **THEN** tool 使用当前 turn 的 false override，intent node 再依据服务器环境开关解析 auto 或 precise

#### Scenario: regenerate 复用原请求模式
- **WHEN** 用户重新生成一条当时以 forced comprehensive 发送的回答
- **THEN** regenerate 请求继续携带原 user message 的 true 值，不读取 composer 当前 checkbox

#### Scenario: 旧客户端兼容
- **WHEN** ChatRequest 未携带新字段
- **THEN** 后端按 false 处理，并保持现有环境开关所定义的默认行为

### Requirement: Intent Mode 可观测性
公共 trace MUST 记录 requested/effective routing mode、mode source、classifier 是否调用以及 forced comprehensive 是否成功。模式 trace MUST 在 API、stream 最终 trace 与历史消息中保持一致，不得仅存在于内部 state。

#### Scenario: 用户强制成功的 trace
- **WHEN** forced comprehensive 成功产生 ComprehensiveQueryPlan
- **THEN** trace 标明 source=user、requested/effective=`forced_comprehensive`、classifier invoked=true 且 forced success=true

#### Scenario: 环境 precise-only 的 trace
- **WHEN** 用户未勾选且 classifier 环境开关关闭
- **THEN** trace 标明 source=environment、effective=`precise_only` 且 classifier invoked=false

#### Scenario: forced 模式降级 trace
- **WHEN** forced comprehensive 无法产生合法 comprehensive plan
- **THEN** trace 保留 requested=`forced_comprehensive`、effective precise degradation 和具体错误
