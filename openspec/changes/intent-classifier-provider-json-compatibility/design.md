## Context

`IntentClassifier` 通过 LangChain `with_structured_output(IntentDecision)` 调用 OpenAI-compatible 模型。活动的百炼 Qwen provider 将该调用映射为 JSON-object response format，但要求任一请求消息显式包含 `JSON` 关键词；当前 prompt 只提到 schema，provider 因而在生成前返回 HTTP 400。异常被现有兼容路径捕获，用户请求仍成功，但分类器每次都降级到规则路径。

百炼官方契约同时要求调用方对返回 JSON 做 schema 校验。现有 Pydantic `IntentDecision` 与 `with_structured_output` 已承担这一职责，因此本 change 只修复 provider 消息前置条件，不引入第二套解析或 schema。

## Goals / Non-Goals

**Goals:**

- 让当前 JSON-object structured-output 请求满足百炼消息约束。
- 保持 `IntentDecision` 为唯一结构化输出 schema。
- 用确定性契约测试防止 prompt 再次丢失 JSON 要求。
- 用显式 opt-in 的真实 provider smoke 证明 schema-valid 模型成功，并与规则降级区分。
- 保持 feature flag、QueryPlan、timeout/capacity 和规则降级语义不变。

**Non-Goals:**

- 不改变 intent 分类标签、字段、few-shot 示例或路由算法。
- 不默认启用 intent classifier。
- 不在通用 OpenAI-compatible client 上无条件发送 Qwen 专属 thinking 参数。
- 不以替身测试代替真实 provider activation evidence。
- 不解决前端 intent 进度展示或 LangSmith root trace 分裂问题。

## Decisions

### 在 system prompt 中加入明确的 JSON 输出要求

提示词将明确要求“仅以符合既定 schema 的 JSON 对象输出”。这既满足百炼 JSON Mode 的关键词约束，也不会改变字段语义。相比手工构造 `response_format`，继续使用 `with_structured_output(IntentDecision)` 可以避免 LangChain schema 与手写请求漂移。

### 保持 provider-neutral 模型初始化

本 change 不向 `init_chat_model()` 无条件添加 `enable_thinking=false` 或其他 Qwen-only 参数，因为同一路径也可配置其他 OpenAI-compatible provider。reference evaluation 可在其冻结配置中选择非思考 Qwen；通用运行时只承担 schema 与消息兼容。

### 双层测试证据

普通 unit test 断言 structured wrapper 收到 `IntentDecision` 且 system message 包含 `JSON`。真实 smoke 仅在显式环境开关、凭据和模型身份齐备时运行，直接调用 `IntentClassifier` 并断言返回 schema-valid decision；缺少外部条件时跳过，不产生兼容性成功声明。

### 保留现有降级边界

provider、timeout、schema 或 capacity 失败继续由 `build_intent_parse_result()` 转为兼容 `PreciseQueryPlan`，并记录 `intent_fallback_to_rules=true` 与错误。修复成功只改变原本错误的 provider 请求能否到达 schema-valid 输出，不改变失败策略。

## Risks / Trade-offs

- **Prompt 文本修改可能轻微影响模型输出** → 只增加格式约束，不改变分类规则或示例，并运行现有 intent unit/eval 回归。
- **真实 provider smoke 受凭据、网络和模型漂移影响** → 默认跳过，显式运行时记录 provider/model/date，不进入普通确定性测试分母。
- **部分 provider 使用不同 structured-output 方法** → 继续委托 LangChain wrapper；本 change 只保证消息对 JSON-object provider 合法。
- **Qwen 思考模式可能产生非严格 JSON** → activation 配置单独冻结已验证的 model/mode；本 change 不污染通用 client 参数。

## Migration Plan

1. 更新 prompt 与 unit contract test。
2. 运行 intent classifier unit/eval 回归。
3. 在可用的活动百炼 Qwen 配置上显式运行 provider smoke。
4. smoke 成功后更新 KI-RAG-0017 和架构；失败则保持 known issue open 并保留默认关闭。
5. 显式关闭或回滚 prompt 变更即可恢复旧请求；feature defaults 始终不变。

## Open Questions

无。Qwen model/mode 的最终 reference identity 由后续 activation freeze 决定。
