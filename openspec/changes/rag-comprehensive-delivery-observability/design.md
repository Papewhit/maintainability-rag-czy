## Context

真实 E2E 中，qwen-flash 将单点定义问题误判为 comprehensive。综合 graph 执行了分解、三分支并行召回、分支 rerank、merge 和 shared postprocess，但这些正常阶段没有 `rag_step`，前端只显示后续 fallback。前端 `traceChunks()` 又优先拼接 initial/expanded 候选，可能把已淘汰片段标为“来源片段”。

该 run 的结构化 Level 3 输入包含 2 个 sub-query，final 5 docs 每个都表示 baseline、sub_query_0 和 sub_query_1，因此是 `Y/Y` 全覆盖、不是 partial；它因 `weak_margin_and_root + low_score_and_margin` 经 Level 2 后 `levels_exhausted` 进入 Level 3。稳定 spec 对 Y/Y low-confidence 要求 evidence-only，因此本 change 不借该误判 case 放宽生成边界，而是修复事件、证据身份和交付表示。

## Goals / Non-Goals

**Goals:**

- intent parse 完成后显式展示最终采用的精确/综合执行路线，包括安全降级后的实际路线。
- comprehensive 正常路径产生有序、聚合级、用户可理解的进度事件。
- trace 和 UI 区分 candidates、final top-k 与 answer-consumed evidence。
- Level 3 使用 typed delivery contract 表达 mode、coverage、证据与约束。
- partial synthesis 与三类 evidence-only 模式在两条 chat delivery path 中一致。
- 保留历史 trace/API 的可读兼容。

**Non-Goals:**

- 不改变 `weak_margin_and_root`、`low_score_and_margin` 或其他 confidence 公式/阈值。
- 不改变 fallback routing order、budget 或 Level 1/2 策略。
- 不因本次误判 comprehensive 的单点查询允许 Y/Y low-confidence 生成综合答案。
- 不增加新的 retrieval 或 answer-model 调用。

## Decisions

### 决策 1：只在 graph node 边界发送聚合事件

`intent_parse` 在 typed plan 已确定后发送一次最终路线事件；精确路线进入 `retrieve_initial`，综合路线进入 `decompose_and_fanout`。forced/automatic classifier 降级时事件必须显示实际执行路线，并仅用通用降级说明，不公开 provider 错误或原始模型输出。

在 decompose/fanout、branch rerank、merge 和 shared postprocess 的主执行边界发送开始/完成事件；并行 branch worker 不直接写 SSE，以避免线程完成顺序造成 UI 乱序。事件 detail 携带计划/完成分支数、候选/最终数和策略，但不泄露内部 Prompt 或完整查询内容。

### 决策 2：建立三层证据身份

Trace 明确保留：candidate/initial/expanded 诊断集合、`final_evidence_chunks`（shared postprocess final top-k）和 `answer_evidence_chunks`（实际序列化进 answer context 或 Level 3 delivery 的子集）。每个集合通过稳定 candidate identity/chunk_id 对齐。

前端“最终来源片段”只读取 `answer_evidence_chunks`，旧 trace 缺少该字段时才回退 `retrieved_chunks`；initial/expanded 只能显示在明确标注的候选诊断区。不得把集合并集命名为来源。

### 决策 3：Level 3 typed delivery 是权威，字符串是兼容投影

新增 typed contract：`mode`、`covered_count/total_count`、covered dimensions、uncovered dimensions、逐维度 evidence refs/excerpts、baseline evidence、constraints。支持 `partial_synthesis | full_coverage_low_confidence | baseline_only | no_evidence | precise_insufficient`。

`level3_answer` 在迁移期保留为由 typed contract 确定性渲染的兼容字段，但业务分支、answer prompt 和前端不得再解析该字符串推断 mode 或 coverage。

### 决策 4：按 mode 生成不同 delivery instruction

`partial_synthesis` instruction 明确输入是证据与约束而非可复制的最终答案，要求现有 answer model 为每个已覆盖维度生成独立、带来源的用户可读部分答案，并禁止输出内部标签、回答未覆盖维度或形成跨维度结论。

`full_coverage_low_confidence`、`baseline_only` 和 `no_evidence` 保持 evidence-only。它们使用确定性、用户可读投影，不授权综合生成；因此真实模型复述证据本身不构成 partial-delivery 缺陷。precise insufficient 保持既有范围披露。

### 决策 5：Level 3 answer evidence 必须来自 final top-k 实际消费

逐维度证据仍只从进入 Level 3 前的 final docs 选择；选择函数同时返回 evidence ref，不只返回文本。`answer_evidence_chunks` 精确等于被 typed delivery 引用的去重文档，不包含只存在于 raw branch candidates 的条目。

### 决策 6：兼容性按 producer/consumer 双向迁移

后端先同时写 typed field 与旧 `level3_answer`，API schema接受两者；frontend 优先 typed/final fields并为旧历史 trace保留 fallback。待历史兼容窗口结束后，另行决定是否移除旧字段，本 change 不做 breaking removal。

## Risks / Trade-offs

- **事件过多造成 UI 噪声** → 只发 node 聚合事件，不发每个 branch worker 细节。
- **answer evidence 子集与 final top-k 不同增加理解成本** → 以清晰字段名和稳定 IDs 显式表达包含关系，并在 UI 分区。
- **typed contract 与兼容字符串漂移** → 只允许单一确定性 renderer 生成旧字段，并做等价性测试。
- **partial 模式仍依赖 answer model 遵循指令** → 加真实模型 E2E；不满足时阻断 activation，而不是把内部模板当作成功答案。
- **Y/Y evidence-only 体验仍偏保守** → 保持稳定安全边界；任何授权综合生成的调整需要独立 evidence 和 spec change。

## Migration Plan

1. 增加 typed Level 3 与 final/answer evidence 字段，同时保留旧字段。
2. 在 comprehensive node 边界添加事件并完成 backend/SSE tests。
3. 切换 chat delivery 到 typed mode-specific instruction。
4. 前端优先展示 answer evidence，候选集合移入诊断区；旧 trace 使用兼容 fallback。
5. 用 partial、Y/Y、baseline-only、no-evidence 和 precise cases 执行两条 delivery path E2E。

## Open Questions

- 已决：候选诊断区随现有默认折叠的思考过程显示，并与“最终来源片段”使用独立标题和数据选择器；本 change 不增加第二层折叠控件。
