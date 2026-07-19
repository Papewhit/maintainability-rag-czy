## Context

`rag-intent-routing` 已实现 intent classifier、两种 QueryPlan、综合 fan-out、版本化 postprocess profile、公共 trace 和可重复评测 harness。当前生产默认仍为 `RAG_INTENT_CLASSIFIER_ENABLED=false`，确定性测试只能证明实现与评测契约可执行，不能证明 FAST_MODEL、发布 Milvus 语料、CrossEncoder 或回答/裁判模型达到上线质量与成本要求。

现有验证报告 `docs/validation/rag-intent-routing-evaluation.md` 因缺少真实模型与发布索引运行而保持 `partial`。本 change 是延后的发布激活边界：它不重写实现，只在具备外部环境后生成可比的真实证据、作出阈值决策、执行灰度并最终决定是否改变默认值。

## Goals / Non-Goals

**Goals:**

- 用同一发布候选源码、配置、数据集和发布语料执行可比的真实模型评测。
- 同时评估意图解析质量及 comprehensive postprocess 的质量/成本权衡。
- 在任何默认启用之前形成经评审的数值阈值、证据结论和回滚条件。
- 先通过显式环境配置灰度，再把代码默认值改为 true。
- 保留失败、部分或未执行评测的证据，不把“harness 可运行”误写为“生产可上线”。

**Non-Goals:**

- 不修改 intent-routing graph、QueryPlan、terminology、fan-out 或 postprocess 算法。
- 不实现 multilevel fallback 或统一 anchor 语法；这些由独立 change/known issue 持有。
- 不使用确定性替身、合成 trace 或开发语料设定生产激活阈值。
- 不在评测未通过时通过单独配置变更绕过 gate。

## Decisions

### 决策 1：实现完成与激活完成使用两个 change

`rag-intent-routing` 以“实现完成、默认关闭”归档；本 change 独立持有真实评测、阈值、灰度和默认启用。这样实现证据不会因外部发布环境暂不可用而长期悬置，同时激活责任仍有明确 OpenSpec owner。

替代方案是保留原 change 的两个未完成任务。该方案会把代码完成性与发布准备度混为一个状态，并阻塞稳定规格同步，因此不采用。

### 决策 2：真实评测必须绑定同一运行身份

所有 paired 结果必须共享：

- source commit 与版本化 source fingerprint；
- intent 数据集、filename registry 与发布语料/索引身份；
- embedding、Milvus、BM25、reranker、FAST_MODEL、answer/judge model 配置；
- 运行环境和资源采样方法。

`quality_first_v1` 与 `eval_no_crossencoder_v1` 只允许 profile 不同。runner 已有的配对一致性检查继续作为最低边界；执行记录还必须说明所有外部服务都是真实发布候选依赖，而非测试替身。

### 决策 3：阈值由首轮真实基线提出，评审后冻结

当前没有可信真实基线，因此不在 proposal 中预造数值。首轮有效运行先产生分布和候选阈值；评审后把阈值写入激活验证报告，再使用同一身份或明确记录的新发布候选重跑。阈值至少覆盖 intent accuracy、plan validity、sub-query quality、生成分支代表率、引用有效性、回答质量、P95 延迟、资源峰值、错误/降级率和预算耗尽率。

如果无法形成阈值、指标未达标或结果不可比，结论必须是 `partial` 或 `failed`，默认值保持 false。

### 决策 4：灰度使用显式开关，默认值最后改变

评测通过后，部署层先对受控流量显式设置 `RAG_INTENT_CLASSIFIER_ENABLED=true`。灰度至少经过 10% 起始阶段并按预先记录的阶段、观察窗口和停止条件扩大；代码默认仍为 false。只有灰度满足停止条件且无未处置回归时，才提交默认值变更。

这使关闭开关始终是即时回滚路径，也避免“为了灰度先改默认”造成未受控启用。

### 决策 5：激活证据使用新的验证报告

保留现有 `VAL-RAG-INTENT-001` partial 报告作为默认关闭实现的证据。本 change 生成独立的 activation validation 报告，记录真实运行身份、paired 原始输出位置、阈值、灰度观察和最终结论；通过时再更新 `docs/ARCHITECTURE.md` 的默认状态与验证绑定。

## Risks / Trade-offs

- **发布语料变化导致 A/B 不可比** → 固定 corpus/index fingerprint；任一身份变化都重跑两种 profile。
- **LLM 或外部服务漂移** → 记录精确模型/provider 配置、执行时间和请求参数；跨版本结果不得直接配对。
- **首轮基线参与阈值制定产生过拟合** → 将阈值制定与最终 gate 运行分开记录；最终结论使用冻结阈值。
- **灰度样本不足或流量偏置** → 预先记录 cohort、观察窗口和最低样本量；不足时保持默认关闭。
- **启用后延迟或成本恶化** → 保留 false 开关回滚，并把 P95、资源峰值、错误/降级和预算耗尽作为停止条件。
- **评测长期受外部条件阻塞** → change 保持 in-progress；不影响已实现 default-disabled capability，也不允许静默启用。

## Migration Plan

1. 固定发布候选提交、source/config/dataset/corpus fingerprints 和真实服务清单。
2. 运行真实 intent classifier 评测及两个 comprehensive profile 的 paired A/B。
3. 生成 activation validation 报告，提出、评审并冻结阈值；必要时按冻结阈值重跑。
4. 结论为 passed 后，以部署显式开关进行分阶段灰度；任一停止条件触发即回滚为 false。
5. 灰度通过后修改代码与示例配置默认值，更新契约测试和 `docs/ARCHITECTURE.md`。
6. 验证、同步规格并归档本 change。

## Open Questions

- 发布 Milvus corpus/index fingerprint 的权威生成方式与负责人。
- 灰度每个阶段的最低样本量、观察窗口和流量扩大比例。
- FAST_MODEL、answer model 与 judge model 的最终发布版本和稳定性窗口。
