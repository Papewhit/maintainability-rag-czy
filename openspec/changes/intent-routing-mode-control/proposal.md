## Why

真实 FAST_MODEL 在现阶段既存在延迟差异，也可能把单点事实查询误判为综合分析。默认关闭 classifier 虽能保持 precise 兼容路径，却无法让用户在不依赖自动分类准确率的情况下显式进入已实现的 comprehensive 链路，因此需要一个请求级、可回滚且尽量不侵入现有实现的临时控制面。

## What Changes

- 在 chat 请求中增加逐请求的“为我启用综合查询”选择；显式选择时解析为 `forced_comprehensive`。
- 增加一个纯 thin resolver，把用户选择与现有 `RAG_INTENT_CLASSIFIER_ENABLED` 合成为 `forced_comprehensive | auto_classifier | precise_only` 三种有效模式。
- `forced_comprehensive` 只固定 intent 选择，继续复用现有模型、`IntentDecision`、`ComprehensiveQueryPlan`、query preparation 和 comprehensive graph；不建立第二套 planner 或检索链路。
- 未显式选择时，现有环境开关为 true 则运行 `auto_classifier`，为 false 则运行不调用 intent LLM 的 `precise_only`。
- 在 forced-preload 与 optional-tool 两条入口、同步与流式 API、重新生成和 trace 中传递同一个请求级模式，避免各层重新推导。
- 保持默认值和未携带新字段的客户端兼容；不在本 change 调整 classifier Prompt、confidence signals、fallback 算法或参考默认开关。

## Capabilities

### New Capabilities

无。

### Modified Capabilities

- `rag-intent-routing`: 增加请求级 intent routing mode 解析、显式 comprehensive 选择、默认兼容行为和公共 trace 契约。

## Impact

- API：`backend/contracts/schemas.py`、`backend/routers/chat.py`。
- Chat 入口与请求上下文：`backend/chat/agent.py`、`backend/chat/rag_execution.py`、`backend/chat/tools.py`。
- Intent routing：`backend/rag/intent.py`、`backend/rag/pipeline.py`、`backend/rag/runtime_config.py`。
- 前端：composer 控件、请求 payload、重新生成状态及模式展示。
- 测试：resolver unit tests、API/stream wire tests、forced/auto/precise graph tests、前端交互测试和默认关闭兼容回归。
