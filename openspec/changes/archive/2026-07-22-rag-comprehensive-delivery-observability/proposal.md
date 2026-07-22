## Why

真实 comprehensive E2E 暴露出三项相互关联的交付缺口：正常分支检索阶段没有前端事件，“来源片段”优先展示 initial/expanded 候选而非最终证据，Level 3 又把覆盖数据、内部约束和用户文案混为一个字符串。用户因此只能看到 fallback、无法确认最终答案实际使用的证据，并可能收到内部模板的原样复述。

## What Changes

- 在 `intent_parse` 完成后显式发送最终精确/综合执行路线的 `rag_step`，安全降级时展示实际采用的路线而不是请求路线。
- 为 comprehensive 的分解、并行召回、分支 rerank、merge 和 shared postprocess 增加有序的聚合级 `rag_step` 事件，不从并行 worker 直接发出乱序事件。
- 明确区分候选证据、final top-k 和真正进入 Level 3 交付的 evidence；前端“最终来源片段”只展示回答实际消费的集合，候选片段另作诊断展示。
- 将 Level 3 交付拆成 typed mode、覆盖维度、未覆盖维度、逐维度证据与 delivery constraints；不再让一个 `level3_answer` 字符串同时充当状态、控制指令和最终文案。
- 对 forced-preload、optional-tool、stream/non-stream、历史 trace 与前端渲染增加一致性测试。

## Capabilities

### New Capabilities

无。

### Modified Capabilities

- `rag-intent-routing`: 补充 intent 最终路线、comprehensive 正常执行阶段的公共事件及 final evidence/trace 展示契约。
- `rag-multilevel-fallback`: 将 Level 3 覆盖与交付改为 typed contract，并保持 partial 与 evidence-only 的既有生成边界。

## Impact

- Comprehensive graph 与 trace：`backend/rag/pipeline.py`、`backend/rag/types.py`、`backend/rag/trace.py`。
- Level 3 delivery：`backend/rag/level3_answer.py`、`backend/chat/fallback_delivery.py`、`backend/chat/rag_execution.py`、`backend/rag/formatting.py`。
- API schema 与前端：`backend/contracts/schemas.py`、`frontend/script.js`、`frontend/index.html`。
- 测试：comprehensive event order、final evidence identity、四类 Level 3 mode、两种 delivery path、SSE 和 frontend source rendering。
