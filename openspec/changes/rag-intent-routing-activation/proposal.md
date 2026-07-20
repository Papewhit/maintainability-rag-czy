## Why

Ragtenance 是学生简历项目与学校课题组合作项目的衍生成果，目标是形成高于 demo、可复现且有实证支撑的 RAG 系统，不承担严肃生产环境的 SLA、容量或灰度发布责任。

`rag-intent-routing` 已完成默认关闭的实现与确定性验证，但仍需要证明真实模型确实进入执行路径、两类 QueryPlan 能按预期生成，并且综合检索在可控语料上具有合理的质量与成本。真实业务文档不得外传，因此本 change 使用可公开复现的合成集作为主要覆盖，并用少量公开、获授权或可在受控环境内使用的真实文档补充生态有效性验证。

## What Changes

- 构建版本化合成文档集、query set、qrels、filename registry 与困难负例，覆盖 intent、scope、granularity、analysis type 和 trace 契约。
- 选取少量公开或获授权真实文档，执行相同模型、索引和 runner 下的补充评测；真实文档不进入可公开归档时，只保存脱敏结果与 fingerprint。
- 使用真实配置的 FAST_MODEL、embedding、Milvus/BM25、reranker 和 answer/judge model 执行混合评测；测试替身只用于 unit/contract tests。
- 成对比较 `quality_first_v1` 与 `eval_no_crossencoder_v1`，报告意图质量、检索/回答质量、延迟、调用量和错误/降级。
- 依据项目级、非生产的冻结门槛决定是否在 Ragtenance 的参考配置中默认启用 intent classifier，并保留显式关闭回滚路径。
- 不要求生产流量灰度、生产容量证明、发布语料或组织级上线审批。

## Capabilities

### New Capabilities

- `rag-intent-routing-activation`: 面向 Ragtenance 项目级展示与研究复现的合成集 + 部分真实文档评测、门槛、默认启用和回滚证据。

### Modified Capabilities

无。现有 `rag-intent-routing` 检索与降级契约保持不变。

## Impact

- 评测与证据：`tests/eval/rag/`、合成 corpus/query set、少量真实文档评测配置及新的 activation validation 报告。
- 运行配置：混合评测通过后可更新 `backend/rag/runtime_config.py` 与 `.env.example` 中的参考默认值。
- 当前系统文档：评测定位或默认状态改变后更新 `docs/ARCHITECTURE.md`。
- 外部依赖：可用模型凭据、本地或课题组 Milvus/BM25 环境、公开/获授权真实文档子集。
- 安全边界：不得把未授权真实文档、查询、答案或可还原内容写入公开仓库或对外评测包。
