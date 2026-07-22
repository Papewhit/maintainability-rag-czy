## Why

当前活动的百炼 OpenAI-compatible Qwen 端点会拒绝 intent classifier 的 JSON-object structured-output 请求，因为请求消息没有包含 provider 要求的 `JSON` 关键词。运行时随后静默降级到规则路径，使启用开关无法产生真实模型分类，也阻断 intent-routing activation 的 `model_success` 前置证据。

## What Changes

- 使 intent classifier 的结构化输出提示满足百炼 JSON Mode 的消息约束，同时保持现有 `IntentDecision` schema、QueryPlan 语义和规则降级行为不变。
- 增加 provider compatibility 契约测试，证明 structured-output 调用携带明确的 JSON 输出要求并继续使用唯一的 Pydantic schema。
- 增加可选的真实模型 smoke，区分 schema-valid 模型成功与规则降级；没有凭据时不得把替身结果声明为真实 provider 证据。
- 更新已知问题、当前架构和验证证据，使 provider 兼容状态与实际实现一致。

## Capabilities

### New Capabilities

无。

### Modified Capabilities

- `rag-intent-routing`: intent classifier 的 structured-output 请求必须满足所配置 provider 的 JSON Mode 前置条件，并通过 schema-valid 成功与明确降级证据区分兼容和失败路径。

## Impact

- 运行时：`backend/rag/intent.py` 的 classifier system prompt；默认关闭开关与 QueryPlan 契约不变。
- 测试：intent classifier unit/contract tests，以及由环境变量显式启用的真实 provider smoke。
- 文档：`KI-RAG-0017`、`docs/ARCHITECTURE.md` 和 change-local evidence disposition。
- 外部依赖：真实 smoke 需要现有百炼 API 凭据、base URL 和 Qwen model identity；凭据不得进入报告或 fingerprint。
