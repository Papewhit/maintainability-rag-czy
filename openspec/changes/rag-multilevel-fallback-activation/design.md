## Context

Ragtenance 的目标是形成可演示、可复现、有混合数据证据的学生/课题项目，而不是生产服务。`rag-multilevel-fallback` 已实现四级路由、Level 1 rewrite、Level 2 scope/candidate relax、Level 3 证据不足交付、公共 trace 与前端步骤展示，当前仍为 `RAG_FALLBACK_ENABLED=false`。

已有确定性测试和 M8.5 UX 证明路径可执行，但缺少覆盖所有失败模式的完整 corpus/query/qrels，也缺少少量真实文档上的自然语言与解析噪声验证。本 change 使用“系统合成覆盖 + 真实子集抽检”形成项目级 activation 证据。

## Goals / Non-Goals

**Goals:**

- 以合成集完整覆盖 precise/comprehensive、Level 0–3、scope、coverage、来源、timeout 和 degradation。
- 以少量公开、获授权或受控真实文档验证自然措辞、结构噪声与真实索引行为。
- 使用真实配置模型和基础设施运行，分别报告 synthetic/real-subset 指标。
- 评估 Level 1/2 是否相对上一轮改善，以及 Level 3 是否在该拒答时拒答。
- 依据混合结果选择本地/展示参考 budget，并保留关闭回滚。
- 与 intent-routing activation 共享身份，但分别作出结论。

**Non-Goals:**

- 不声明生产 SLA、容量、全域代表性或企业上线 readiness。
- 不要求生产流量灰度、cohort、长期观察窗口或最低线上样本量。
- 不修改 fallback router、rewrite、scope relax、Level 3 模板或 trace 契约。
- 不允许 mock/替身结果单独支撑默认启用。
- 不要求真实受限文档进入仓库。

## Decisions

### 决策 1：合成覆盖与真实抽检共同组成 Gate

合成集承担难以从小规模真实材料稳定获得的边界覆盖，包括 filter trap、反事实孪生、partial/no-evidence 和受控故障。真实子集承担格式、语言、解析和检索生态验证。最终报告分别给出两层结果；hard gate 在任一适用分层失败都不能被平均分抵消。

### 决策 2：分层 Query Set 使用允许路由与硬边界

query set 至少覆盖：

- precise 的 Level 0 成功、Level 1 改写、Level 2 放宽、Level 3 无证据；
- filter/boost/none 与 `context_files`；
- comprehensive partial、Y/Y low-confidence、baseline-only、no-evidence；
- 术语变体、相似文件、冲突事实和无答案；
- timeout、budget exhaustion、模型失败和检索降级。

容易受 embedding/model 分数波动影响的 case 可以标注 `allowed_levels`，但 filter 不越界、未覆盖禁止回答、来源不伪造、scope 变化披露和关闭兼容路径仍是确定性 hard gates。

### 决策 3：轻量冻结而非生产级 Holdout

development split 用于调试 generator、标注和 budget 候选；随后冻结 synthetic gate split、real-subset 清单、配置和项目级门槛并执行最终运行。无需大规模独立发布 holdout，但变更 gate 数据、阈值或模型必须产生新版本并重跑。

### 决策 4：质量、路由、延迟与可靠性共同报告

报告至少包含 Level 0 命中率、Level 0/1/2/3 分布、Level 1/2 改善率、Level 3 合理性、来源/覆盖合规率、P50/P95、调用量、timeout、budget exhaustion、错误与降级率。CPU/GPU/内存峰值可作为诊断，不作为生产容量认证。

### 决策 5：Budget 只表示 Ragtenance 参考配置

total/Level 1/Level 2 budget 候选可由 development mixed set 提出，再用冻结 gate 验证。候选必须同时满足 hard gates、质量和可接受的本地演示延迟。通过后修改的是 Ragtenance 参考默认值，不作生产容量外推；若无候选通过则保留实现默认值。

### 决策 6：Intent 协同但结论独立

comprehensive fallback 使用与 `rag-intent-routing-activation` 可比的 source/config/corpus/model identity，并引用该项目级 gate。intent 未通过时，precise fallback 证据可保留，但完整 comprehensive fallback 不得标记 passed。

### 决策 7：固定 Rehearsal 代替流量灰度

混合 gate 通过后，在干净索引中显式启用 intent、confidence 和 fallback，运行固定 synthetic + real smoke 清单，检查 Level 展示、回答边界、trace 与关闭回滚。通过后可改变参考开关/budget；不要求线上 cohort。

### 决策 8：Passed 是项目级结论

activation validation 报告记录运行身份、数据版本、阈值、budget、rehearsal 与 `passed|partial|failed`。`passed` 只表示满足 Ragtenance 项目级展示/研究复现门槛，不表示生产 readiness。

## Risks / Trade-offs

- **合成 case 被模板线索轻易识别** → 多生成器模板、事实图、最小差异对、反事实孪生和人工抽检。
- **真实子集太小** → 单独报告规模和限制，不外推到未覆盖领域。
- **真实文档泄漏** → 优先公开/授权材料；受控材料只输出脱敏结果和 fingerprint。
- **Level 平均增益掩盖安全失败** → hard gates 独立判定。
- **budget 适配单台机器** → 记录硬件和模型身份，明确只作参考配置。
- **项目级 passed 被误读** → 架构与验证报告明确非生产定位。

## Migration Plan

1. 冻结 Ragtenance 项目定位、混合证据和数据使用规则。
2. 构建分层 synthetic corpus/query/qrels，并选择真实文档子集。
3. 在 development split 上调通真实模型链路并提出项目级门槛/budget 候选。
4. 冻结 gate 数据、真实子集、配置和门槛后执行完整评测。
5. 生成 activation validation 报告并执行固定本地 rehearsal。
6. 通过后修改参考默认值/budget、测试和架构；否则保持关闭/原值。

## Open Questions

- 真实子集的公开/授权来源、规模与格式分布。
- synthetic/real 的分层比例和人工抽检比例。
- 项目级延迟、质量和错误率门槛。
