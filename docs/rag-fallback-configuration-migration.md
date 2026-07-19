# RAG Fallback 配置迁移

本文档说明多层 fallback 引入后的环境变量迁移。当前功能仍默认关闭；迁移配置不会自动启用 fallback。

## 迁移结论

`RAG_FALLBACK_ENABLED` 在当前版本继续作为总开关，以保证已有部署在不修改配置时维持原行为。该变量将在 v2 移除；显式设置时运行时会输出 deprecation warning。

新的部署应使用毫秒预算，并显式配置各层开关：

```dotenv
RAG_FALLBACK_ENABLED=false
RAG_FALLBACK_TOTAL_BUDGET_MS=8000
RAG_FALLBACK_LEVEL1_BUDGET_MS=3000
RAG_FALLBACK_LEVEL2_BUDGET_MS=2500
RAG_FALLBACK_LEVEL1_ENABLED=true
RAG_FALLBACK_LEVEL2_ENABLED=true
RAG_FALLBACK_COMPREHENSIVE_REWRITE_WINDOW=2
```

总开关为 `false` 时，所有 fallback level 都跳过，系统继续使用 Level 0 已完成 postprocess 的 final top-k 生成常规回答。

## 配置迁移表

| 旧配置 | 新配置 | 迁移行为 |
| --- | --- | --- |
| `RAG_FALLBACK_ENABLED` | 当前保留；v2 移除 | 仍是总开关；显式设置时记录 deprecation warning |
| `RAG_FALLBACK_TIMEOUT_SECONDS=6` | `RAG_FALLBACK_TOTAL_BUDGET_MS=6000` | 仅当新变量未设置时，旧秒值乘 1000 映射为总预算 |
| 无 | `RAG_FALLBACK_LEVEL1_ENABLED=true` | 控制 Level 1；默认开启，但仍受总开关约束 |
| 无 | `RAG_FALLBACK_LEVEL2_ENABLED=true` | 控制 Level 2；默认开启，但仍受总开关约束 |
| 无 | `RAG_FALLBACK_LEVEL1_BUDGET_MS=3000` | Level 1 的正整数毫秒预算 |
| 无 | `RAG_FALLBACK_LEVEL2_BUDGET_MS=2500` | Level 2 的正整数毫秒预算 |
| 无 | `RAG_FALLBACK_COMPREHENSIVE_REWRITE_WINDOW=2` | 单轮综合失败分支的最大重写数量 |

如果旧秒值与新毫秒值同时设置，以 `RAG_FALLBACK_TOTAL_BUDGET_MS` 为准。非正预算值不属于本变更支持的配置域；本变更不为其定义钳制、拒绝、禁用或兼容行为。

## 分阶段启用

关闭 Level 1、保持 Level 2 时，router 会跳过查询重写并直接进入 scope relax：

```dotenv
RAG_FALLBACK_ENABLED=true
RAG_FALLBACK_LEVEL1_ENABLED=false
RAG_FALLBACK_LEVEL2_ENABLED=true
```

该路径会在 trace 中记录 `level1_skipped_by_config=true`。关闭两个 level 时，证据不足路径直接进入 Level 3；总开关关闭时则不会进入 Level 3 模板。
