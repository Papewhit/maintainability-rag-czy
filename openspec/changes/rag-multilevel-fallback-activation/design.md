## Context

`rag-multilevel-fallback` 已实现四级路由、Level 1 rewrite、Level 2 scope/candidate relax、Level 3 证据不足交付、公共 trace 与前端步骤展示，生产默认仍为 `RAG_FALLBACK_ENABLED=false`。确定性测试、mock integration、非秘密 full-chain overlay 和窄范围人工 UX 只能证明实现路径与交付契约可执行，不能证明真实发布语料上的质量提升、路由比例、P95 或预算默认值合理。

当前缺少代表发布使用方式的可用语料、Milvus/BM25 索引、稳定 answer/judge model 和经评审 query set；这与 `rag-intent-routing-activation` 无法在实现 change 中完成真实激活证据的情况相同。本 change 是独立的发布激活边界：它不重写 fallback 实现，只在外部条件具备后产生可比证据、调优预算、执行灰度并决定是否改变默认值。

## Goals / Non-Goals

**Goals:**

- 用同一发布候选源码、配置、query set、语料/索引、模型和运行环境执行可比的真实 fallback 评测。
- 覆盖 precise/comprehensive、filter/boost/none、术语变体、部分/完整/无证据和预算耗尽等已支持场景。
- 分别判断 Level 0 命中、Level 1/2 增益、Level 3 合理性、来源约束、延迟、成本、资源与降级。
- 用首轮真实基线提出阈值，评审冻结后以独立 gate 数据作最终结论。
- 只有真实数据支持时才调整 total/Level 1/Level 2 budget；先显式配置灰度，最后才改变代码默认值。
- 与 intent-routing activation 共享可比的发布身份，但分别作出 intent 与 fallback gate 结论。

**Non-Goals:**

- 不修改 fallback router、rewrite、scope relax、Level 3 模板或 trace 契约。
- 不使用 mock、确定性替身、合成 trace、开发语料或窄范围 UX 证据设定生产阈值。
- 不因当前无法准备语料而猜测预算值、默认启用或增加保护性兼容行为。
- 不把 intent-routing gate 通过自动解释为 fallback gate 通过，反之亦然。

## Decisions

### 决策 1：实现完成与激活完成使用两个 change

`rag-multilevel-fallback` 以“实现完成、默认关闭”收束；本 change 持有原 tasks 10.3–10.5 的真实评测、指标和预算调优责任。这样当前 PR 的合并只声明 default-disabled implementation，不声明生产激活；外部环境门禁仍有明确 OpenSpec owner。

继续把三项任务留在实现 change 会让不可用的真实语料长期阻塞代码合并，并把实现正确性与发布质量混成一个状态，因此不采用。

### 决策 2：真实 gate 必须绑定完整运行身份

每次可用于阈值或激活的运行必须记录：

- source commit 与 versioned source fingerprint；
- runtime config 与 config fingerprint；
- query set、标注与 holdout 划分 fingerprint；
- 语料、Milvus collection/index profile、BM25 state 与 corpus/index fingerprint；
- intent/FAST、rewrite、answer、judge、embedding、reranker 模型身份；
- 运行设备、资源采样方式、执行时间与并发设置。

缺少任一必需身份、使用替身或使用非代表性开发语料时，报告只能是 `partial` 或 `failed`，不得据此调默认值。

### 决策 3：query set 按受支持失败模式分层并保留独立 gate

query set 至少覆盖：

- precise 初检成功、anchor/score 触发 Level 1、weak-margin/root 触发 Level 2、no-docs/预算触发 Level 3；
- filter/boost/none scope 及 `context_files` 硬范围；
- comprehensive 的 partial coverage、Y/Y low-confidence、baseline-only 与 no-evidence；
- 术语变体、常见非 filter 混淆与代表性文档范围；
- timeout、模型失败和检索降级。

首轮基线用于提出阈值；阈值冻结后必须使用预先隔离的 holdout 或明确记录的新发布候选执行最终 gate，避免同一结果自证通过。query set 的规模、分层比例和人工标注规则在真实语料可用后评审冻结，不在当前无语料条件下预造。

### 决策 4：质量、路由、延迟与可靠性共同组成 gate

报告至少包含：

- Level 0 命中率及 Level 0/1/2/3 路由比例；
- Level 1/2 相对上一完成轮的回答质量与证据质量改善比例；
- Level 3 触发合理性、覆盖判定、未覆盖禁止回答和来源保留合规率；
- P50/P95、embedding/search/rerank/LLM 调用量、CPU/GPU/内存峰值；
- timeout、budget exhaustion、模型/检索失败与降级率；
- filter 不越界、boost→none 披露和默认关闭兼容路径的正确性。

任一强制正确性边界失败都阻断激活。数值阈值由首轮可信基线提出并经评审冻结；当前不复用示例比例作为既成发布阈值。

### 决策 5：预算调优必须来自冻结 gate 证据

`RAG_FALLBACK_TOTAL_BUDGET_MS`、Level 1 和 Level 2 budget 只能依据真实分层结果、P95、成功增益和 timeout/budget-exhaustion 分布调整。调参候选先在 baseline 数据上提出，再用独立 gate 验证；不得只为了降低延迟而破坏质量/正确性 gate，也不得把零或负值纳入受支持配置。

如果没有一个候选同时满足冻结阈值，默认预算保持实现 change 的值，activation 结论为 `partial` 或 `failed`。

### 决策 6：与 intent-routing activation 协同但不合并结论

comprehensive fallback 的发布 gate 依赖真实 intent classifier、发布语料和相同的 source/config/corpus identity，因此应复用 `rag-intent-routing-activation` 已固定的身份和有效结果。若 intent-routing gate 未通过，comprehensive activation 不得宣称通过；precise fallback 的独立证据可以保留，但不能据此默认启用完整能力。

两个 change 分别记录阈值和结论，避免一个 gate 的平均指标掩盖另一个组件的失败。

### 决策 7：显式开关灰度，默认值最后改变

真实 gate 通过后，部署层先对受控 cohort 显式启用 intent routing、confidence gate 与 fallback 所需开关，代码默认仍保持 false。灰度计划必须预先记录 cohort、阶段、观察窗口、最低样本量、停止条件和回滚动作。只有全部阶段满足冻结阈值且无未处置正确性回归，才允许提交 fallback 默认值或 budget 默认值变更。

### 决策 8：激活证据使用独立 governed validation report

本 change 新建 activation validation 报告，绑定运行身份、query set/holdout、原始结果位置、阈值、预算候选、灰度观察与 `passed|partial|failed` 结论。现有 `VAL-RAG-FALLBACK-001` 继续只证明窄范围 M8.5 UX，不升级为生产质量证据。

## Risks / Trade-offs

- **真实语料长期不可用** → change 保持 in-progress；实现可保持 default-disabled 合并，但不得静默激活。
- **与 intent activation 身份不一致** → 要求共享 source/config/corpus fingerprints；不一致结果不得联合解释。
- **首轮基线过拟合阈值** → 阈值制定与最终 holdout gate 分离。
- **LLM/provider 漂移** → 记录精确模型与执行时间；身份变化后重新运行受影响 gate。
- **Level 1/2 平均增益掩盖 scope 越界或 Level 3 幻觉** → 正确性边界作为独立强制 gate，不允许用均值抵消。
- **预算降低改善 P95 但增加 Level 3/timeout** → 质量、路由比例与延迟联合评审；不满足全部阈值则保留原默认。
- **灰度样本不足或流量偏置** → 预先冻结最低样本量和 cohort；不足时保持默认关闭。

## Migration Plan

1. 从 `rag-multilevel-fallback` 移交 M10.3–M10.5，并在架构中把真实评测/调优 owner 指向本 change。
2. 真实语料可用后固定发布候选、完整运行身份、分层 query set 和 holdout。
3. 运行首轮真实基线，提出并评审质量、路由、延迟、资源与可靠性阈值及预算候选。
4. 使用冻结阈值与独立 gate 数据重跑，生成 activation validation 报告。
5. passed 后以显式配置协同 intent-routing activation 进行分阶段灰度；任一停止条件触发即恢复关闭配置。
6. 灰度通过后才修改默认开关/预算、同步测试与 `docs/ARCHITECTURE.md`；否则保持 default-disabled。
7. 验证、同步规格并归档本 change。

## Open Questions

- 发布 corpus/index fingerprint 的权威生成方式与负责人。
- query set 的最低规模、各失败模式比例、标注复核人与 holdout 比例。
- answer/judge model 的最终版本、稳定性窗口和人工复核抽样规则。
- 灰度 cohort、最低样本量、观察窗口和阶段扩大量。
