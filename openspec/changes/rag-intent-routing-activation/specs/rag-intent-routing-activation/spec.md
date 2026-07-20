## ADDED Requirements

### Requirement: Ragtenance 混合评测身份
intent-routing activation MUST 使用版本化合成 corpus/query set 与少量公开、获授权或受控使用的真实文档共同评测。activation run MUST 使用实际配置的 FAST_MODEL、embedding、Milvus/BM25、reranker 与 answer/judge model，并记录 source commit/fingerprint、config、dataset/corpus/index fingerprints、模型身份、执行时间和设备。测试替身 MAY 用于 contract tests，但 MUST NOT 单独支持默认启用结论。

#### Scenario: 混合身份完整
- **WHEN** 维护者启动 Ragtenance intent-routing activation gate
- **THEN** 报告分别标识 synthetic 与 real-subset case，绑定完整运行身份，并说明真实文档的授权或受控执行方式

#### Scenario: 只有替身或只有合成解析测试
- **WHEN** 没有真实模型/索引运行，或真实文档子集未执行
- **THEN** 报告 MUST 为 `partial`，MUST NOT 据此改变参考默认值

### Requirement: Intent 与 paired profile 评测
系统 MUST 评测 precise/comprehensive intent、plan validity、scope、granularity、analysis type 和 sub-query quality，并 MUST 在相同 case/source/config/dataset/corpus identity 下成对执行 `quality_first_v1` 与 `eval_no_crossencoder_v1`。synthetic 与 real-subset 指标 MUST 分别报告。

#### Scenario: 有效混合评测
- **WHEN** synthetic gate set 与 real-subset 均完成
- **THEN** 报告包含 intent accuracy、plan validity、sub-query quality、分支代表率、引用有效性、回答质量、P50/P95、调用量及错误/降级率，并给出逐分层结论

#### Scenario: paired 身份不一致
- **WHEN** 两个 profile 的 case ids 或受控 fingerprints 不一致
- **THEN** runner MUST 拒绝 paired 结论

### Requirement: 项目级 Gate
默认启用决策 MUST 使用最终运行前已记录的项目级门槛和冻结数据版本。门槛 MUST 包含 scope/引用/兼容路径等强制正确性检查，以及核心质量、延迟和可靠性指标。门槛 MAY 根据 development baseline 提出，但 MUST NOT 在看到最终 gate 结果后静默修改。

#### Scenario: Gate 未通过
- **WHEN** 任一强制边界失败、真实子集未执行、证据不可比或冻结数值门槛未达到
- **THEN** `RAG_INTENT_CLASSIFIER_ENABLED` 的参考默认值 MUST 保持 false，报告为 `partial` 或 `failed`

#### Scenario: Gate 通过
- **WHEN** synthetic 与 real-subset 分层均满足冻结门槛
- **THEN** 报告 MAY 标记为 Ragtenance 项目级 `passed`，但 MUST 明确不代表生产 readiness

### Requirement: 本地 Rehearsal 与回滚
默认值变更前 MUST 在干净索引和固定配置下执行一次显式开启的端到端 rehearsal，覆盖 synthetic cases、real smoke cases、trace 可见性和关闭开关回滚。不要求生产流量灰度。

#### Scenario: Rehearsal 通过
- **WHEN** 固定 case 清单执行成功且显式关闭恢复兼容 PreciseQueryPlan 路径
- **THEN** change MAY 修改 Ragtenance 参考默认值

#### Scenario: Rehearsal 失败
- **WHEN** 发生正确性回归、不可接受错误或关闭回滚失败
- **THEN** 参考默认值 MUST 保持 false，并记录失败证据

### Requirement: 默认启用与证据更新
混合 gate 与 rehearsal 均通过后，系统 MAY 将 Ragtenance 参考配置中的 `RAG_INTENT_CLASSIFIER_ENABLED` 默认值改为 true。该变更 MUST 同步更新环境示例、默认值/关闭回滚测试、activation validation 报告和 `docs/ARCHITECTURE.md`；显式 false MUST 继续受支持。

#### Scenario: 项目级默认启用
- **WHEN** 混合 gate 和 rehearsal 均 passed
- **THEN** 默认值与证据在同一 change 中更新，报告明确样本规模、真实子集来源、限制和非生产定位
