## ADDED Requirements

### Requirement: Typed Level 3 Delivery Contract
Level 3 MUST 以 typed contract 表达 delivery mode、coverage 计数、已覆盖/未覆盖维度、逐维度 evidence refs/excerpts、baseline evidence 和 constraints。业务逻辑、chat delivery 和 frontend MUST NOT 通过解析 `level3_answer` 自由文本推断这些状态；迁移期 `level3_answer` MUST 仅由 typed contract 确定性投影。

#### Scenario: 部分覆盖 typed delivery
- **WHEN** final top-k 表示 `0 < X < Y` 个生成维度
- **THEN** mode 为 `partial_synthesis`，contract 列出 X/Y、逐维度 evidence refs、未覆盖维度和禁止跨维度结论的 constraints

#### Scenario: 全覆盖低置信 typed delivery
- **WHEN** final top-k 表示全部 Y 个维度但 confidence 仍要求 Level 3
- **THEN** mode 为 `full_coverage_low_confidence`，contract 标明 Y/Y、证据 refs 和 evidence-only constraint，且不授权综合答案

#### Scenario: baseline-only 与无证据
- **WHEN** 没有生成维度被 final top-k 表示
- **THEN** 系统分别使用 `baseline_only` 或 `no_evidence`，不得把 baseline 计入 coverage

#### Scenario: precise 证据不足
- **WHEN** PreciseQueryPlan 进入 Level 3
- **THEN** mode 为 `precise_insufficient` 并保留既有 filter/boost/none 范围披露

### Requirement: Mode-specific Level 3 Answer Delivery
Chat delivery MUST 根据 typed mode 生成控制指令。只有 `partial_synthesis` MUST 要求现有 answer model 基于已覆盖维度证据组织独立、带来源的用户可读部分答案；full-coverage-low-confidence、baseline-only、no-evidence 与 precise-insufficient MUST 保持各自既有 evidence-only/insufficient 边界。系统 MUST NOT 增加新的 answer-model 调用。

#### Scenario: Partial synthesis 不复述内部模板
- **WHEN** mode 为 `partial_synthesis`
- **THEN** instruction 明确输入不是最终答案，模型 MUST NOT 输出“证据摘录”“回答约束”“交付约束”等内部标签，只回答已覆盖维度并声明整体不足

#### Scenario: Y/Y 保持 evidence-only
- **WHEN** mode 为 `full_coverage_low_confidence`
- **THEN** delivery 只展示带来源证据与低置信说明，不生成综合结论，也不将模型复述 evidence-only 内容误记为 partial synthesis failure

#### Scenario: 两条交付路径共用 typed contract
- **WHEN** Level 3 分别通过 forced-preload system message 与 optional-tool response 交付
- **THEN** 两条路径消费同一个 typed contract/renderer，不维护第二套 coverage 或来源文案

### Requirement: Level 3 Answer Evidence 精确绑定
Level 3 的 `answer_evidence_chunks` MUST 精确对应 typed delivery 实际引用的、来自本轮 final top-k 的去重文档；被 final selection 淘汰的 raw candidates 或未被任何 delivery evidence ref 使用的文档 MUST NOT 显示为 Level 3 最终来源。

#### Scenario: 同一文档覆盖多个维度
- **WHEN** 一个 final document 同时表示多个 sub-query 且被多个维度引用
- **THEN** typed contract MAY 在各维度引用同一 identity，但 `answer_evidence_chunks` 只包含一个去重文档

#### Scenario: 被淘汰 branch candidate 不得恢复
- **WHEN** raw branch candidate 没有进入 final top-k
- **THEN** 它不得进入 typed evidence refs、answer evidence、Level 3 兼容字符串或前端最终来源

#### Scenario: 兼容字符串等价
- **WHEN** 后端同时输出 typed delivery 与历史 `level3_answer`
- **THEN** 兼容字符串 MUST 由单一 renderer 生成，并与 typed mode、coverage、来源和 constraints 等价
