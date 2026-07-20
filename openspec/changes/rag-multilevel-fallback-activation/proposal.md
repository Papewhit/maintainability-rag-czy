## Why

Ragtenance 是高于 demo 的学生简历/课题合作衍生项目，不承担严肃生产 SLA、容量或流量灰度责任。`rag-multilevel-fallback` 已完成默认关闭实现、确定性回归和窄范围 UX 验证，但仍需要在可控且可复现的文档集上证明 Level 0–3 路由、scope 边界、partial/no-evidence 交付和预算行为具有项目级可信度。

真实业务文档不得外传，因此本 change 采用合成集覆盖全部失败模式，并使用少量公开、获授权或受控使用的真实文档补充自然噪声和真实解析/检索验证。

## What Changes

- 构建分层 synthetic corpus/query set，覆盖 precise/comprehensive、Level 0/1/2/3、filter/boost/none、术语变体、partial/Y-Y/baseline-only/no-evidence、timeout/degradation。
- 选取少量真实文档执行相同 runner 下的补充评测，synthetic 与 real-subset 指标分别报告。
- 用实际配置的 intent/rewrite/answer/judge/embedding/reranker 与 Milvus/BM25 运行端到端混合评测。
- 对比 fallback-disabled、仅 Level 1、仅 Level 2 与完整链路，并验证硬范围、未覆盖禁止回答、来源披露和关闭兼容路径。
- 根据混合数据提出适合本地展示/研究复现的 budget 候选；不声称生产容量调优。
- 评测通过后以固定本地 rehearsal 代替生产流量灰度，再决定是否修改 Ragtenance 参考默认值。

## Capabilities

### New Capabilities

- `rag-multilevel-fallback-activation`: 面向 Ragtenance 项目级展示与研究复现的合成集 + 部分真实文档评测、轻量预算调优、默认启用和回滚门槛。

### Modified Capabilities

无。现有 fallback 路由与交付契约保持不变。

## Impact

- 评测与证据：合成 corpus/query/qrels、少量真实文档子集、runner 与 governed activation validation 报告。
- 运行配置：通过后可调整 Ragtenance 参考 budget 或 `RAG_FALLBACK_ENABLED` 默认值。
- 当前系统文档：项目定位、评测边界或默认状态改变时更新 `docs/ARCHITECTURE.md`。
- 协同边界：comprehensive fallback 仍依赖同一身份下有效的 intent-routing 项目级评测。
- 安全边界：未授权真实文档及可还原 query/answer/citation 不得进入公开仓库或对外交接包。
