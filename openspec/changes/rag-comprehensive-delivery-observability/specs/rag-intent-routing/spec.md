## ADDED Requirements

### Requirement: Comprehensive 聚合进度事件
Comprehensive graph MUST 在分解/并行召回、分支 rerank、merge 和 shared postprocess 的主 node 边界产生有序 `rag_step`；并行 branch worker MUST NOT 直接产生无序用户事件。正常 comprehensive 请求即使不进入 fallback，也 MUST 向 stream frontend 展示检索进度。

#### Scenario: Comprehensive 正常路径事件完整
- **WHEN** ComprehensiveQueryPlan 完成正常分支检索并在 Level 0 结束
- **THEN** SSE 依序包含分解/并行检索、分支处理、证据合并和最终后处理事件，不依赖 fallback 事件证明检索发生

#### Scenario: 并行分支事件保持确定顺序
- **WHEN** 多个 branch worker 以不同顺序完成
- **THEN** frontend 只接收 node 汇总后的聚合事件，顺序不随 worker 完成时序变化

#### Scenario: 事件携带聚合计数
- **WHEN** comprehensive node 发出完成事件
- **THEN** detail 包含适用的计划/完成分支数、候选数或 final evidence 数，但不暴露内部 Prompt

### Requirement: Final 与 Answer Evidence 身份
公共 trace MUST 区分候选诊断集合、shared postprocess `final_evidence_chunks` 和实际进入 answer context/Level 3 delivery 的 `answer_evidence_chunks`。前端“最终来源片段”MUST 只展示 answer evidence；initial/expanded candidates MUST NOT 被合并后冒充最终来源。

#### Scenario: 普通回答展示最终消费证据
- **WHEN** final top-k 被格式化进正常 answer context
- **THEN** `answer_evidence_chunks` 与实际格式化文档 identity 一致，frontend 最终来源只展示该集合

#### Scenario: 候选被 final selection 淘汰
- **WHEN** initial 或 expanded candidate 未进入 final top-k
- **THEN** 它 MAY 出现在候选诊断区，但 MUST NOT 出现在最终来源片段

#### Scenario: 旧 trace 兼容
- **WHEN** 历史 trace 没有 answer evidence 字段
- **THEN** frontend MAY 回退到 `retrieved_chunks`，但 MUST NOT 回退到 initial/expanded 并集作为最终来源

### Requirement: Comprehensive 交付事件与证据可验证
Stream 最终 trace、历史消息和非流式响应 MUST 保持 comprehensive event 对应的最终 evidence identity、branch provenance 和 answer-consumed identity，使评测能够验证显示来源与回答输入一致。

#### Scenario: Stream 完成后的证据一致性
- **WHEN** comprehensive stream 完成并发送最终 trace
- **THEN** trace 中 answer evidence IDs 与前端来源 IDs 及后端格式化输入一致

#### Scenario: Level 3 后仍可识别实际证据
- **WHEN** comprehensive 请求进入 Level 3 且 graph 的返回 docs 为空
- **THEN** trace 仍通过 typed Level 3 refs 和 answer evidence IDs 标识实际进入交付模板的 final documents
