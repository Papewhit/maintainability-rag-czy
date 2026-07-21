## ADDED Requirements

### Requirement: Provider-compatible structured intent output
当 intent classifier 使用 structured output 时，系统 MUST 保持 `IntentDecision` 为唯一输出 schema，并 MUST 满足所配置 provider 对 JSON Mode 的请求前置条件。对于要求消息声明 JSON 输出的 provider，请求消息 MUST 明确包含 JSON 输出要求；系统 MUST NOT 通过另一套手写 schema 或宽松 JSON 解析绕过 `IntentDecision` 校验。

#### Scenario: JSON-object provider 成功分类
- **WHEN** classifier 使用要求消息包含 JSON 关键词的 OpenAI-compatible provider，并通过 `with_structured_output(IntentDecision)` 发起调用
- **THEN** system message 明确要求 JSON 输出，返回内容通过 `IntentDecision` 校验，且成功 trace 标记 `intent_fallback_to_rules=false`

#### Scenario: Provider 或 schema 仍然失败
- **WHEN** provider 拒绝请求、调用超时或返回内容不能通过 `IntentDecision` 校验
- **THEN** 系统保持既有兼容降级语义，输出 `PreciseQueryPlan` 并记录 `intent_fallback_to_rules=true` 与具体错误

#### Scenario: 确定性测试与真实 provider 证据分离
- **WHEN** 测试仅使用 structured-output 替身而未调用真实配置 provider
- **THEN** 测试只证明 prompt/schema/降级契约，不得声明真实 provider compatibility 或 activation `model_success`
