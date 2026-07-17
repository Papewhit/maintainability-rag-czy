## Why

`rag-intent-routing` 已完成默认关闭的实现与确定性验证，但当前环境没有 FAST_MODEL 凭据、发布 Milvus 语料或回答/裁判模型，无法完成真实质量与成本评测。将发布评测和默认启用留在实现 change 内会混淆“功能已实现”与“已具备上线证据”，因此需要独立的激活 change 持有外部评测、阈值决策和上线责任。

## What Changes

- 在同一发布候选提交、配置、数据集和 source fingerprint 下，执行 FAST_MODEL 与发布 Milvus 的真实 intent-routing 评测。
- 成对比较 `quality_first_v1` 与 `eval_no_crossencoder_v1`，覆盖意图准确率、计划有效性、生成分支代表率、引用有效性、回答质量、延迟、资源消耗及错误/降级率。
- 由评测结果提出并评审激活阈值；评测未通过或证据不完整时保持 `RAG_INTENT_CLASSIFIER_ENABLED=false`。
- 仅在评测通过后，通过受控灰度验证运行指标，再将默认值改为 true，并更新当前架构与发布证据。
- 不改变已实现的 intent-routing graph、QueryPlan、fan-out、postprocess profile 或默认关闭兼容路径。

## Capabilities

### New Capabilities

- `rag-intent-routing-activation`: 真实模型与发布索引评测、激活阈值、灰度观察、默认启用和回滚门槛。

### Modified Capabilities

无。现有 `rag-intent-routing` 契约已经规定只有评测达标后才允许默认启用；本 change 实现该激活门槛，不修改其检索契约。

## Impact

- 评测与证据：`tests/eval/rag/`、`eval/intent/`、`docs/validation/rag-intent-routing-evaluation.md` 或后继验证报告。
- 运行配置：评测通过后更新 `backend/rag/runtime_config.py`、`.env.example` 中的 intent classifier 默认值。
- 当前系统文档：激活状态改变后更新 `docs/ARCHITECTURE.md` 的默认状态和验证绑定。
- 外部依赖：FAST_MODEL 与 judge/answer model 凭据、代表发布配置的 Milvus 语料、可控 CPU/GPU 运行环境及灰度流量指标。
- 发布安全：任何门槛失败、证据不可比或灰度指标恶化都阻止默认启用，并保留关闭开关作为回滚路径。
