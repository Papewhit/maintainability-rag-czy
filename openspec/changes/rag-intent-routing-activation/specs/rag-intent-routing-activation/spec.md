## ADDED Requirements

### Requirement: 真实发布候选评测身份
intent-routing 激活评测 MUST 使用真实 FAST_MODEL、发布候选 Milvus 语料与检索基础设施，以及配置的 answer/judge model。每次 gate 运行 MUST 记录 source commit、版本化 source fingerprint、配置 fingerprint、数据集 fingerprint、发布 corpus/index fingerprint、模型身份、执行时间和运行环境；确定性替身、合成 trace 或开发语料 MUST NOT 作为默认启用证据。

#### Scenario: 评测身份完整
- **WHEN** 维护者启动 intent-routing 激活 gate
- **THEN** runner 或验证记录包含全部源码、配置、数据集、语料/索引、模型和环境身份，且外部模型、embedding、reranker 与 Milvus 均为声明的真实发布候选依赖

#### Scenario: 身份不完整或使用替身
- **WHEN** 任一必需 fingerprint/模型身份缺失，或运行使用测试替身、合成 trace、非发布语料
- **THEN** 结果只能记录为 `partial` 或 `failed`，不得用于设置激活阈值或允许默认启用

### Requirement: paired 质量与成本评测
系统 MUST 在相同运行身份下成对执行 `quality_first_v1` 与 `eval_no_crossencoder_v1`。除 effective comprehensive postprocess profile 外，两次运行的查询、分支 fan-out、检索配置、模型、语料和资源环境 MUST 相同。报告 MUST 同时给出意图解析质量、检索/回答质量、延迟、调用量、资源和降级指标。

#### Scenario: 有效 paired A/B
- **WHEN** 两个 profile 以相同 case ids、source/config/dataset/corpus fingerprints 和外部依赖执行
- **THEN** 报告比较 intent accuracy、plan validity、sub-query quality、生成分支代表率、引用有效性、回答质量、embedding/search calls、rerank pairs、P50/P95、CPU/GPU 峰值、错误/降级率和预算耗尽率

#### Scenario: paired 身份不一致
- **WHEN** 两个 profile 的 case ids 或任一受控 fingerprint、模型、语料、检索配置不一致
- **THEN** runner MUST 拒绝 paired 结论，验证报告不得声称 profile 质量或成本差异

### Requirement: 阈值与默认关闭 gate
默认启用决策 MUST 使用已评审并冻结的数值阈值。阈值 MUST 在首轮可信真实基线后写入 activation validation 报告，并 MUST 覆盖核心质量、延迟、资源与可靠性指标。评测未执行、证据不完整、阈值未冻结或任一强制阈值未达标时，`RAG_INTENT_CLASSIFIER_ENABLED` 的代码默认值 MUST 保持 false。

#### Scenario: gate 未通过
- **WHEN** 激活报告状态为 `partial`/`failed`，阈值尚未冻结，或强制指标未达到阈值
- **THEN** 不得修改 intent classifier 的代码默认值，评测 profile 也不得自动成为生产默认替代品

#### Scenario: gate 通过
- **WHEN** 同一发布候选的真实评测满足全部冻结阈值且 activation validation 报告状态为 `passed`
- **THEN** change MAY 进入显式配置灰度阶段，但代码默认值仍保持 false，直到灰度 gate 通过

### Requirement: 受控灰度与回滚
默认值变更前 MUST 通过部署显式设置 `RAG_INTENT_CLASSIFIER_ENABLED=true` 进行受控灰度。灰度计划 MUST 预先记录 cohort、至少 10% 的起始流量、后续阶段、每阶段观察窗口、最低样本量和停止条件。任一停止条件触发时 MUST 将灰度 cohort 回滚为 false。

#### Scenario: 灰度逐步扩大
- **WHEN** activation evaluation 已 passed 且当前灰度阶段满足预定质量、P95、错误/降级、资源和预算条件
- **THEN** 部署 MAY 按计划扩大下一阶段流量，并保留未进入 cohort 的默认关闭行为

#### Scenario: 灰度回滚
- **WHEN** 任一阶段触发预定停止条件或出现未处置的正确性回归
- **THEN** 部署 MUST 将显式开关恢复为 false，停止扩大流量，记录证据且不得修改代码默认值

### Requirement: 默认启用与证据更新
只有真实评测 gate 与灰度 gate 均通过后，系统 SHALL 将 `RAG_INTENT_CLASSIFIER_ENABLED` 的代码默认值改为 true。该变更 MUST 同步更新环境示例、默认值契约测试、activation validation 报告和 `docs/ARCHITECTURE.md`；关闭开关 MUST 继续作为回滚路径。

#### Scenario: 默认启用提交
- **WHEN** 真实评测和灰度均通过且所有残余风险已有 durable disposition
- **THEN** 默认值、环境示例、测试和当前架构在同一受验证 change 中更新，架构状态从 implemented/default-disabled 改为 default-enabled

#### Scenario: 启用后紧急关闭
- **WHEN** 默认启用后发生达到回滚条件的质量、延迟、资源或错误回归
- **THEN** 运维方可显式设置 `RAG_INTENT_CLASSIFIER_ENABLED=false` 恢复兼容 PreciseQueryPlan 路径，并将回归记录到 governed evidence/work item
