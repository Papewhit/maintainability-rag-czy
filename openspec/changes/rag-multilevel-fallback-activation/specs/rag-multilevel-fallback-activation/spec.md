## ADDED Requirements

### Requirement: Ragtenance 混合 Fallback 评测身份
fallback activation MUST 使用版本化合成 corpus/query set 与少量公开、获授权或受控使用的真实文档共同评测。activation run MUST 使用实际配置的 intent/rewrite/answer/judge/embedding/reranker、Milvus 与 BM25，并记录 source/config/dataset/corpus/index fingerprints、模型身份、执行时间和设备。测试替身 MAY 用于 contract tests，但 MUST NOT 单独支持默认启用或参考 budget 变更。

#### Scenario: 混合运行完整
- **WHEN** 维护者启动 Ragtenance fallback activation gate
- **THEN** 报告分别标识 synthetic 与 real-subset case，绑定完整运行身份，并说明真实材料的授权或受控执行方式

#### Scenario: 缺少真实执行层
- **WHEN** 只有 mock/替身、只有 synthetic contract tests，或真实文档子集未执行
- **THEN** 报告 MUST 为 `partial`，参考开关与 budget MUST 保持原值

### Requirement: 分层 Query Set
query set MUST 覆盖 precise/comprehensive、Level 0/1/2/3、filter/boost/none、术语变体、partial/Y-Y/baseline-only/no-evidence 以及 timeout/degradation。数据 MUST 划分 development 与冻结 gate 版本；阈值、budget 或 gate 数据的后续修改 MUST 产生新版本。

#### Scenario: 失败模式覆盖完整
- **WHEN** synthetic gate set 进入评审
- **THEN** 每类 case 记录 expected/allowed levels、scope、覆盖维度、允许回答、forbidden claims、来源要求与判分规则

#### Scenario: 真实子集补充验证
- **WHEN** real-subset 进入 gate
- **THEN** 它覆盖至少若干常见真实格式或结构，并具有人工 query/qrels 与使用依据；报告不对未覆盖领域外推

### Requirement: 质量与强制正确性 Gate
报告 MUST 分别计算 synthetic 与 real-subset 的 Level 分布、Level 1/2 改善、Level 3 合理性、来源/覆盖合规、P50/P95、调用量、timeout、budget exhaustion、错误和降级。任何 filter 越界、未覆盖维度作答、伪造来源、错误 scope 披露或 fallback-disabled 兼容回归 SHALL 阻断项目级 passed。

#### Scenario: 强制边界失败
- **WHEN** 任一适用 case 违反 hard gate
- **THEN** activation MUST NOT 标记为 passed，即使平均指标达到门槛

#### Scenario: 分层指标通过
- **WHEN** synthetic 与 real-subset 分别满足冻结门槛且无 hard-gate 失败
- **THEN** 报告 MAY 给出 Ragtenance 项目级 passed，并 MUST 声明非生产定位与样本限制

### Requirement: 项目级 Budget 调优
`RAG_FALLBACK_TOTAL_BUDGET_MS`、Level 1 和 Level 2 budget MAY 依据 development mixed set 提出候选，但候选 MUST 在冻结 gate 上重新验证 hard gates、质量、P95、timeout 和 budget exhaustion。通过后的值只表示 Ragtenance 参考配置，不表示生产容量结论。

#### Scenario: Budget 候选通过
- **WHEN** 候选在冻结 synthetic 与 real-subset gate 上均达到项目级门槛
- **THEN** change MAY 修改参考 budget，并记录机器、模型和数据身份

#### Scenario: 无候选通过
- **WHEN** 所有候选失败或证据不完整
- **THEN** 默认 budget MUST 保持不变

### Requirement: Confidence Signal 分层 Gate
activation evidence MUST 按单一 confidence reason 与 reason 组合分别计算特异性并执行消融。`weak_margin_and_root` MUST NOT 作为独立启用条件，除非它在冻结 gate 上满足项目门槛；未通过时，候选配置 MUST 停用或收紧该 reason。`low_score_and_margin` MUST 独立评估，系统 MUST NOT 仅凭它与低特异性 reason 共现就停用或放宽该信号。

#### Scenario: weak-margin 独立特异性不足
- **WHEN** 冻结 gate 或消融证据显示 `weak_margin_and_root` 会反复拒绝直接相关、相互佐证的 final evidence
- **THEN** activation candidate 停用或收紧该独立 trigger，并重新运行适用 gate

#### Scenario: 两个 reasons 共现
- **WHEN** `weak_margin_and_root` 与 `low_score_and_margin` 在同一失败 case 中共现
- **THEN** 报告记录该 case 不能单独归因，并使用单信号样本或消融分别决定两个 reasons 的 activation 状态

### Requirement: Intent-Routing 协同
comprehensive fallback gate MUST 引用可比身份下有效的 `rag-intent-routing-activation` 项目级证据。intent 与 fallback MUST 分别报告结论；intent gate 未通过时，完整 comprehensive fallback MUST NOT 标记 passed。

#### Scenario: 两个 Gate 分别通过
- **WHEN** comprehensive fallback 申请默认启用
- **THEN** fallback 报告引用同一 source/config/corpus/model identity 下的 intent passed evidence

### Requirement: 本地 Rehearsal、默认启用与回滚
混合 gate 通过后，系统 MUST 在干净索引和固定配置下显式启用所需 intent、confidence 与 fallback 开关，运行固定 synthetic + real smoke rehearsal，并验证 trace、回答边界和显式关闭回滚。不要求生产流量灰度。gate 与 rehearsal 均通过后，change MAY 修改 Ragtenance 参考开关或 budget，并 MUST 同步环境示例、契约测试、activation report 与 `docs/ARCHITECTURE.md`。

#### Scenario: Rehearsal 失败
- **WHEN** rehearsal 发生 hard-gate 回归、不可接受错误或关闭回滚失败
- **THEN** 参考开关与 budget MUST 保持原值

#### Scenario: 项目级默认启用
- **WHEN** 混合 gate 与 rehearsal 均通过
- **THEN** 参考配置 MAY 默认启用 fallback，显式关闭 MUST 继续受支持，报告 MUST 明确非生产 readiness
