## Context

Ragtenance 的目标级别是“高于 demo 的学生/课题合作项目”：需要可复现数据、真实模型执行、自动指标、人工抽检和明确局限，但不需要生产 SLA、全量发布语料、流量灰度或容量认证。

`rag-intent-routing` 已实现 intent classifier、Precise/Comprehensive QueryPlan、综合 fan-out、版本化 postprocess profile、公共 trace 和评测 harness。当前默认仍为 `RAG_INTENT_CLASSIFIER_ENABLED=false`。已有 100 条合成 intent query 能验证解析契约，但缺少配套的完整合成 corpus，并且尚未用少量真实文档证明从解析到检索/回答的生态有效性。

前置 provider-compatibility change 已证明 JSON 请求/schema 可以成功，但没有证明当前 E2E 身份满足 activation 延迟预算。`INTENT-PROVIDER-F001` 记录了 `qwen3.6-plus + 5s` 在 LangSmith run `019f82cb-b723-7852-8bed-b62b25c6a721` 中超时并降级；一次 `qwen-flash + 5s` 成功只能作为 development 候选。正常 gate 必须在同一冻结身份下取得非 fallback `model_success`，并分别记录冷启动总耗时、模型调用耗时和 warm-run 分布。`INTENT-PROVIDER-F002` / KI-RAG-0021 还表明外层线程 timeout 不会取消已开始的 provider 调用，因此可靠性判断必须包含 timeout 后的 capacity/slot 恢复。

## Goals / Non-Goals

**Goals:**

- 用版本化合成集系统覆盖 intent、scope、granularity、analysis type、filename collision、困难负例和 trace。
- 用少量公开、获授权或留在受控环境内的真实文档补充格式、语言和检索行为验证。
- 使用真实配置模型和基础设施运行端到端评测，区分 synthetic 与 real-subset 指标。
- 在同一运行身份下比较两个 comprehensive profile。
- 以预先记录的项目级门槛决定 Ragtenance 参考配置是否默认启用，并保留关闭路径。

**Non-Goals:**

- 不声明生产可上线、生产容量、SLA 或企业数据代表性。
- 不要求生产流量灰度、最低流量比例或长期监控窗口。
- 不修改 intent-routing graph、QueryPlan、terminology、fan-out 或 postprocess 算法。
- 不允许 mock/替身结果单独支撑默认启用；它们只证明测试契约。
- 不要求真实文档或可还原内容进入公开仓库。

## Decisions

### 决策 1：混合证据代替生产发布证据

主要覆盖由完全虚构且可公开复现的合成 corpus 提供；少量真实文档用于验证格式噪声、自然措辞和真实解析/检索差异。二者分别报告并共同形成项目级结论。合成集负责边界覆盖，真实子集负责生态有效性，不能用一个总平均值隐藏任一分层失败。

### 决策 2：真实执行边界与替身测试分开

activation run 使用实际配置的 FAST_MODEL、embedding、Milvus/BM25、reranker 和 answer/judge model。unit tests 可以使用替身，但报告必须标记 `contract-only`；默认启用结论至少需要一次真实模型 + 真实索引的混合集运行。

FAST_MODEL 的 `model_success` 必须来自 gate 所冻结的确切 provider/model/timeout 身份。放宽 timeout 的兼容性 smoke、规则 fallback 或另一个候选模型的成功均不得替代。计时口径必须区分模型对象冷构造、单次 provider invoke 和 intent node 端到端耗时。

### 决策 3：保留轻量运行身份

最终报告绑定 source commit/fingerprint、runtime config、dataset/corpus/index fingerprints、模型身份、执行时间与设备。`quality_first_v1` 和 `eval_no_crossencoder_v1` 只允许 profile 不同。这里的身份绑定服务于复现与简历/研究答辩，不上升为生产供应链认证。

### 决策 4：门槛在最终运行前冻结

允许先用 development split 调试 generator、runner 和候选阈值；随后冻结 synthetic gate split、real-subset 清单与项目级门槛，再执行最终运行。无需大规模独立生产 holdout，但不得在看到最终结果后静默修改样本或阈值。

强制边界至少包括 scope 正确、引用来自检索结果、paired identity 一致、默认关闭兼容路径无回归。数值指标包括 intent accuracy、plan validity、sub-query quality、生成分支代表率、引用有效性、回答质量、P95 和错误/降级率。

### 决策 5：以本地/展示 rehearsal 代替生产灰度

评测通过后，在干净索引和固定配置下执行一次端到端 rehearsal：显式开启 classifier，运行预定 synthetic + real smoke cases，检查 trace、回答、关闭开关回滚和演示路径。通过后可修改 Ragtenance 参考默认值；不要求生产 cohort 或流量阶段。

### 决策 6：证据声明与项目定位匹配

activation validation 报告可结论为 `passed|partial|failed`。`passed` 表示达到 Ragtenance 项目级门槛，不表示生产 readiness。报告必须明确 synthetic/real 样本规模、限制和不可外推范围。

## Risks / Trade-offs

- **合成模板过于规律** → 使用事实图、困难负例、反事实孪生、多种文档结构和措辞人工抽检。
- **真实子集太小** → 分层单独报告，不对未覆盖业务域作外推，并记录样本规模限制。
- **真实文档泄漏** → 优先公开/获授权材料；受控材料只在原环境执行并导出脱敏指标。
- **模型漂移** → 记录模型/provider 与执行日期；关键版本变化后重跑 gate。
- **先看结果再调门槛** → 冻结 gate split、清单和阈值，变更必须形成新版本。
- **项目级 passed 被误读为生产可用** → 验证报告与架构显式标注非生产定位。

## Migration Plan

1. 冻结 Ragtenance 项目定位、数据使用规则和混合证据边界。
2. 建设合成 corpus/query/qrels，并选定公开或获授权真实文档子集。
3. 用 development split 调通真实模型与索引 runner，提出项目级门槛。
4. 冻结 gate split、真实子集、配置和门槛，执行 intent 与 paired A/B。
5. 生成 activation validation 报告并执行本地/展示 rehearsal。
6. 通过后修改参考默认值、回滚测试和架构；否则保持默认关闭并记录限制。

## Open Questions

- 少量真实文档采用公开材料、课题组授权材料，还是两者兼有。
- synthetic/real-subset 的最低样本规模与格式分布。
- 项目级门槛的具体数值及人工抽检比例。
