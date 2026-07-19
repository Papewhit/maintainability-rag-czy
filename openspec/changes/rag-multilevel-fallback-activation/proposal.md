## Why

`rag-multilevel-fallback` 已完成默认关闭的实现、确定性回归和窄范围 UX 验证，但当前无法准备可用于发布判断的真实语料、Milvus/BM25 索引、answer/judge model 与代表性 query set。与 intent router 启用相同，继续把真实评测和默认调优留在实现 change 中会混淆“代码可合并”与“已有上线证据”，因此需要独立的 activation/evaluation change 持有这些外部环境门禁。

## What Changes

- 固定发布候选源码、配置、query set、真实语料/索引、模型和运行环境身份，再执行 multilevel fallback 的真实端到端评测。
- 覆盖精确未匹配、综合分析部分/完整覆盖、术语变体、filter/boost/none scope 与 Level 3 输出边界，验证 Level 0/1/2/3 路由及回答质量。
- 采集 Level 0 命中率、Level 1/2 质量提升、Level 3 触发合理性、来源约束、P50/P95、调用量、资源、超时和降级指标。
- 基于首轮可信真实基线提出并评审阈值；阈值冻结后执行最终 gate，证据不足或不达标时保持 `RAG_FALLBACK_ENABLED=false`。
- 仅根据真实评测数据调整 total/Level 1/Level 2 budget 默认值；不得用确定性替身、开发语料或主观估计调参。
- 评测通过后先以显式配置与 intent-routing activation 协同灰度，再决定是否改变 fallback 默认值，并保留关闭开关作为回滚路径。
- 将原 `rag-multilevel-fallback` tasks 10.3–10.5 迁移到本 change；原 change 只证明默认关闭实现完成，不作生产激活声明。

## Capabilities

### New Capabilities

- `rag-multilevel-fallback-activation`: 真实语料/索引评测、质量与延迟阈值、数据驱动预算调优、协同灰度、默认启用和回滚门槛。

### Modified Capabilities

无。现有 `rag-multilevel-fallback` 契约继续定义默认关闭实现行为；本 change 只持有激活证据和发布门禁。

## Impact

- 评测与证据：`tests/eval/rag/`、`tests/e2e/`、评测数据集/runner，以及新的 governed activation validation 报告。
- 运行配置：评测通过后才可能调整 `RAG_FALLBACK_TOTAL_BUDGET_MS`、Level 1/2 budget 或 `RAG_FALLBACK_ENABLED` 默认值，并同步 `.env.example` 与契约测试。
- 当前系统文档：迁移后 `docs/ARCHITECTURE.md` 指向本 activation change；激活状态改变时再次更新 feature status 与证据绑定。
- 外部依赖：代表性真实语料、发布 Milvus collection/index profile、BM25 state、FAST/answer/judge model、embedding/reranker 与可控资源环境。
- 协同边界：综合路径的发布评测依赖 `rag-intent-routing-activation` 的真实 intent classifier 与发布索引身份；任一 gate 未通过都不得静默启用 fallback。
