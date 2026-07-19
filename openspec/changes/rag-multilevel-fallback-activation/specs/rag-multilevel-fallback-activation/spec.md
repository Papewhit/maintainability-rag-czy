## ADDED Requirements

### Requirement: 真实 Fallback 评测身份
multilevel fallback 激活 gate MUST 使用代表发布候选的真实语料、Milvus/BM25 索引、检索基础设施和配置的 intent/rewrite/answer/judge/embedding/reranker 模型。每次 gate 运行 MUST 记录 source commit、versioned source fingerprint、config fingerprint、query-set/标注/holdout fingerprint、corpus/index fingerprint、模型身份、执行时间和运行环境；替身、合成 trace、非代表性开发语料或窄范围 UX 结果 MUST NOT 作为默认启用或预算调优证据。

#### Scenario: 运行身份完整
- **WHEN** 维护者启动 fallback activation gate
- **THEN** runner 或验证报告包含全部源码、配置、query set、语料/索引、模型与环境身份，且外部依赖为声明的真实发布候选

#### Scenario: 身份缺失或使用替身
- **WHEN** 任一必需 fingerprint/模型身份缺失，或运行使用测试替身、合成 trace、非代表性语料
- **THEN** 结果只能记录为 `partial` 或 `failed`，MUST NOT 用于冻结阈值、调整默认预算或启用 fallback

### Requirement: 分层 Query Set 与独立 Gate
activation query set MUST 覆盖已支持的 precise/comprehensive 路径、Level 0/1/2/3 触发原因、filter/boost/none scope、术语变体、综合覆盖状态及 timeout/degradation。首轮可信基线 MAY 用于提出阈值，但最终 gate MUST 使用预先隔离的 holdout 或明确记录的新发布候选；MUST NOT 使用同一未隔离结果同时制定并证明阈值。

#### Scenario: 失败模式覆盖完整
- **WHEN** query set 进入评审
- **THEN** 清单包含 precise 初检/改写/放宽/证据不足、comprehensive partial/Y-Y/baseline-only/no-evidence、硬范围/软偏好/无范围、术语变体及 timeout/degradation，并记录每类预期路由和回答边界

#### Scenario: 最终 gate 与阈值制定隔离
- **WHEN** 首轮基线已用于提出数值阈值或预算候选
- **THEN** 最终结论使用冻结阈值及独立 holdout/发布候选数据；同一未隔离样本不得自证通过

### Requirement: 质量、路由、延迟与可靠性 Gate
activation 报告 MUST 同时评估 Level 0 命中率、Level 0/1/2/3 路由比例、Level 1/2 质量增益、Level 3 触发合理性与来源约束、P50/P95、调用量、资源峰值、timeout、budget exhaustion、错误和降级率。任何硬范围越界、未覆盖维度作答、错误来源披露或默认关闭兼容回归 SHALL 阻断激活，不得由平均质量或延迟指标抵消。

#### Scenario: 指标集合完整
- **WHEN** activation 报告给出 gate 结论
- **THEN** 报告包含所有质量、路由、来源、延迟、调用、资源和可靠性指标，以及按 query-set 分层的失败明细

#### Scenario: 强制正确性边界失败
- **WHEN** 任一 case 越出 filter、回答未覆盖维度、丢失必要来源、错误声明检索范围或破坏 fallback-disabled 兼容路径
- **THEN** activation gate MUST NOT 标记为 passed，即使平均质量、P95 或其他比例达到阈值

### Requirement: 数据驱动预算调优
`RAG_FALLBACK_TOTAL_BUDGET_MS`、`RAG_FALLBACK_LEVEL1_BUDGET_MS` 与 `RAG_FALLBACK_LEVEL2_BUDGET_MS` 的默认值 MUST 仅依据真实分层 gate 的质量、路由、P95、timeout 和 budget-exhaustion 证据调整。预算候选 MUST 在阈值制定数据上提出并通过独立 gate 验证；没有满足全部冻结阈值的候选时 SHALL 保留实现 change 的默认值。

#### Scenario: 预算候选通过独立验证
- **WHEN** 基线结果提出新的 total/Level 1/Level 2 budget 候选
- **THEN** 候选以独立 gate 数据重新执行全部强制质量、路由、延迟和可靠性检查，通过后才 MAY 修改默认值

#### Scenario: 无可信预算证据
- **WHEN** 真实语料/索引不可用、证据不完整或所有预算候选未满足冻结阈值
- **THEN** 默认预算保持不变，报告状态为 `partial` 或 `failed`；MUST NOT 用主观估计或替身结果调参

### Requirement: Intent-Routing 协同激活
comprehensive fallback 的发布 gate MUST 与 `rag-intent-routing-activation` 使用可比的 source/config/corpus/model identity，并 MUST 要求 intent-routing gate 对相应发布候选有效。intent-routing 与 fallback SHALL 分别记录阈值和结论；任一 gate 未通过时 MUST NOT 默认启用完整 comprehensive fallback 链路。

#### Scenario: 两个 Gate 身份一致且分别通过
- **WHEN** comprehensive fallback 申请进入灰度
- **THEN** fallback 报告引用同一发布候选的有效 intent-routing activation evidence，并分别证明 intent 与 fallback 阈值通过

#### Scenario: Intent Gate 未通过
- **WHEN** intent-routing evidence 为 partial/failed、身份不一致或发布候选已变化
- **THEN** precise fallback 证据 MAY 保留，但完整 comprehensive fallback MUST NOT 宣称 activation passed 或进入默认启用

### Requirement: 显式灰度、默认启用与回滚
真实 gate 通过后，系统 MUST 先以部署显式配置对受控 cohort 启用所需 intent、confidence 与 fallback 开关，代码默认值仍保持关闭。灰度计划 MUST 预先记录阶段、观察窗口、最低样本量、停止条件和回滚动作。只有全部灰度阶段通过且无未处置正确性回归时，change MAY 修改 fallback 开关或预算默认值，并 MUST 同步环境示例、契约测试、activation validation 报告和 `docs/ARCHITECTURE.md`。

#### Scenario: Gate 未通过或语料尚不可用
- **WHEN** 真实评测未执行、证据不完整、阈值未冻结或任一强制阈值未达标
- **THEN** `RAG_FALLBACK_ENABLED` 及相关生产默认保持关闭/原值，本实现 change 的合并 MUST NOT 被解释为激活

#### Scenario: 灰度停止并回滚
- **WHEN** 任一灰度阶段触发正确性、质量、P95、资源、错误、降级或预算停止条件
- **THEN** 部署 MUST 恢复关闭配置、停止扩大 cohort、记录 governed evidence，且不得提交默认启用

#### Scenario: 默认值变更
- **WHEN** 真实 gate 与全部灰度阶段均通过，且残余风险已有 durable disposition
- **THEN** 默认开关/预算、环境示例、契约测试、activation 报告和当前架构在同一受验证 change 中更新，关闭开关继续作为回滚路径
