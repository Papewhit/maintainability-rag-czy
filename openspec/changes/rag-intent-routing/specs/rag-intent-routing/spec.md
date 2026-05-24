## ADDED Requirements

### Requirement: 意图分类入口
RAG 管线 SHALL 在执行检索之前先做意图分类，将查询归入 `precise_lookup` 或 `comprehensive_analysis` 二类之一。意图分类的实现 MAY 是 LLM 调用或规则降级路径，但管线对外暴露的行为 MUST 一致：所有下游节点 MUST 接受 `PreciseQueryPlan` 或 `ComprehensiveQueryPlan` 作为输入，不再接受裸 query 字符串。

#### Scenario: LLM 解析成功的精确查找
- **WHEN** 用户提交 query "XYZ123-A 主减速齿轮箱的拆卸步骤" 且 LLM 分类器可用
- **THEN** 意图节点输出 `PreciseQueryPlan`，包含 entities `[product_model=XYZ123-A, component=主减速齿轮箱, maintenance_action=拆卸]`、semantic_query "主减速齿轮箱拆卸步骤"、target_granularity `step_list`；trace 字段 `intent="precise_lookup"`、`intent_fallback_to_rules=false`

#### Scenario: LLM 解析成功的综合分析
- **WHEN** 用户提交 query "对比 XYZ123-A 和 XYZ456-B 的齿轮箱维修方案，分析改进方向"
- **THEN** 意图节点输出 `ComprehensiveQueryPlan`，包含 analysis_type `comparison`、sub_queries 列表（至少 2 个独立 sub_query，每个带自己的 domain 和 priority）、merge_strategy `hierarchical`；trace 字段 `intent="comprehensive_analysis"`、`sub_query_count >= 2`

#### Scenario: LLM 调用失败的规则降级
- **WHEN** LLM 调用超时、网络错误、或返回无法解析为目标 schema 的 JSON
- **THEN** 意图节点降级到规则路径，输出 `PreciseQueryPlan`（规则路径永不输出 ComprehensiveQueryPlan）；trace 字段 `intent_fallback_to_rules=true`、`intent_llm_error` 记录失败原因；不阻塞 RAG 流程

#### Scenario: 意图分类关闭
- **WHEN** 配置 `RAG_INTENT_CLASSIFIER_ENABLED=false`
- **THEN** 意图节点直接走规则降级路径，不发起 LLM 调用；行为与未启用 intent-routing 之前完全等价

### Requirement: 双 QueryPlan 数据结构
`PreciseQueryPlan` 和 `ComprehensiveQueryPlan` MUST 是两个独立的 frozen dataclass，共享 `EntityMatch` 字段。RAGState 中 SHALL 通过 union type 表达，下游节点 MUST 用 isinstance 或 match 语句分支。

#### Scenario: PreciseQueryPlan 字段完整性
- **WHEN** 意图分类产出 PreciseQueryPlan
- **THEN** 该实例必须包含 raw_query、semantic_query、entities (可空)、scope_mode (`filter`/`boost`/`none`)、matched_files (可空)、anchors (可空)、target_granularity、route 共 8 个字段；任意字段缺失视为非法状态，单元测试覆盖

#### Scenario: ComprehensiveQueryPlan 字段完整性
- **WHEN** 意图分类产出 ComprehensiveQueryPlan
- **THEN** 该实例必须包含 raw_query、analysis_type、entities、sub_queries (至少 1 个)、merge_strategy、coverage_domains 共 6 个字段；sub_queries 为空时视为非法状态（应降级到 PreciseQueryPlan）

#### Scenario: EntityMatch 规范化
- **WHEN** intent classifier 返回 entities
- **THEN** 每个 EntityMatch 必须有 type（枚举值之一）、value（原文）、normalized（规范化形式）、confidence（0-1）；terminology 模块上线前 normalized 直接采用 LLM 输出；terminology 上线后 normalized 必须通过术语表查找得到，未命中术语表的 entity 需降低 confidence（具体阈值待评测确定）

### Requirement: RAG graph 入口分支
`run_rag_graph()` MUST 以 `intent_parse` 节点为入口；从 `intent_parse` SHALL 引出条件边到 `retrieve_initial`（precise 路径）或 `decompose_and_fanout`（comprehensive 路径）。两条路径在 `assemble_context` 之前 MUST NOT 交汇。

#### Scenario: 精确路径连通性
- **WHEN** intent_parse 产出 PreciseQueryPlan
- **THEN** 状态机依次执行 `intent_parse → retrieve_initial → grade_documents → [rewrite/answer]`；与改造前现有路径行为兼容

#### Scenario: 综合路径连通性
- **WHEN** intent_parse 产出 ComprehensiveQueryPlan
- **THEN** 状态机执行 `intent_parse → decompose_and_fanout → merge_sub_query_results → assemble_context`；每个 sub_query 独立调用检索子图，merge_sub_query_results 按 merge_strategy 合并

### Requirement: 综合分析执行模式可切换
系统 SHALL 通过配置 `RAG_COMPREHENSIVE_MODE` 切换 `multi_turn`（默认，Agent 多轮工具调用）和 `parallel`（graph 内并发）两种模式。两种模式对外暴露的回答质量目标 MUST 一致，但延迟和成本特征不同。

#### Scenario: multi_turn 模式
- **WHEN** `RAG_COMPREHENSIVE_MODE=multi_turn` 且 intent 为 comprehensive_analysis
- **THEN** Agent 按 sub_queries 顺序逐个调用 search_knowledge_base 工具，每次工具调用可访问之前 sub_query 的结果；最大轮数受 `RAG_COMPREHENSIVE_MAX_TURNS` 限制

#### Scenario: parallel 模式
- **WHEN** `RAG_COMPREHENSIVE_MODE=parallel` 且 intent 为 comprehensive_analysis
- **THEN** 所有 sub_query 在同一次 graph 调用内并发执行，结果合并后一次性供 LLM 合成；不发生多轮工具调用

### Requirement: 意图解析 trace 字段
每次 RAG 请求的 rag_trace MUST 包含意图解析相关字段，用于评测、监控、debug。

#### Scenario: 解析成功 trace
- **WHEN** 意图分类正常完成
- **THEN** rag_trace 包含 `intent`（精确或综合）、`intent_confidence`（0-1）、`query_plan_type`（precise/comprehensive）、`intent_llm_model`、`intent_llm_ms`、`intent_fallback_to_rules=false`、`entity_count`、（comprehensive 时）`sub_query_count`、`analysis_type`

#### Scenario: 规则降级 trace
- **WHEN** LLM 调用失败触发规则降级
- **THEN** rag_trace 包含 `intent_fallback_to_rules=true`、`intent_llm_error`（失败原因字符串）、`intent_llm_ms`（即使失败也记录消耗的时间）、`intent="precise_lookup"`（规则降级永远是 precise）

### Requirement: 评测集与阈值
项目根目录下 MUST 存在意图分类评测集，包含至少 100 条标注样本（70% precise + 30% comprehensive），覆盖所有 entity 类型和 analysis_type。评测脚本 MUST 可重复运行，输出指标 MUST 达到既定阈值才允许将 `RAG_INTENT_CLASSIFIER_ENABLED` 默认值改为 true。

#### Scenario: 评测脚本可重复跑
- **WHEN** 运行 `pytest tests/test_intent_classifier_eval.py -m intent_eval`
- **THEN** 脚本读取 `tests/data/intent_eval/*.jsonl`，对每条样本调用当前 intent classifier，输出 intent accuracy / entity precision / entity recall / sub-query quality 四类指标，写入 `eval/intent/{date}_{model}.json`

#### Scenario: 阈值达标
- **WHEN** 评测完成后查看输出 JSON
- **THEN** 各项指标达到预设基线时视为达标；不达标时配置项 `RAG_INTENT_CLASSIFIER_ENABLED` 默认保持 false。具体阈值在标注完成后根据初评结果设定，不在此处硬编码

### Requirement: 与 plan_rag_turn 的职责边界
`plan_rag_turn()` MUST NOT 做 query 内容分析，SHALL 只做 session 级路由（FORCED_PRELOAD vs OPTIONAL_TOOL vs NO_RAG）。query 的意图分类和实体提取 MUST 全部由 RAG graph 内部的 `intent_parse` 节点承担。

#### Scenario: FORCED_PRELOAD 仍然走意图解析
- **WHEN** 请求带 context_files，`plan_rag_turn` 判定为 FORCED_PRELOAD
- **THEN** 进入 run_rag_graph 后仍先执行 intent_parse 节点；context_files 作为 PreciseQueryPlan 的硬约束（scope_mode=filter, matched_files 来自 context_files）

#### Scenario: OPTIONAL_TOOL 经工具调用进入
- **WHEN** Agent 调用 search_knowledge_base 工具
- **THEN** 工具内部调用 run_rag_graph 时也走 intent_parse 节点；Agent 不感知意图分类的存在，工具行为对外保持简单接口（输入 query 字符串）
