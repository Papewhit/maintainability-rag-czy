## 1. Milestone M1：数据结构与降级路径骨架

- [ ] 1.1 定义 `EntityMatch`、`SubQuery`、`PreciseQueryPlan`、`ComprehensiveQueryPlan` 数据类（`backend/rag/query_plan.py`），保留现有 `QueryPlan` 类作为规则降级输出，并标注 deprecation
- [ ] 1.2 实现规则降级路径 `_rule_fallback_intent(query, context_files)`：复用 `parse_query_plan` 的正则匹配，加关键词启发分类，永远输出 PreciseQueryPlan
- [ ] 1.3 新增 `RAGState` 字段 `intent_result: IntentParseResult | None`、`query_plan_type: Literal["precise", "comprehensive"]`
- [ ] 1.4 单元测试覆盖：规则降级在 LLM 缺失时的兜底行为、各 entity 类型的正则识别、综合分析关键词触发

**验收**：所有数据结构编译通过；规则降级路径在断开 LLM 的环境下能产出合法 PreciseQueryPlan；trace 字段 `intent_fallback_to_rules` 在降级时为 true。

## 2. Milestone M2：LLM 意图解析器接入

- [ ] 2.1 实现 `IntentClassifier` 类（新文件 `backend/rag/intent.py`）：封装 LLM 调用、structured output schema、超时控制
- [ ] 2.2 设计 prompt 模板（system + 3-5 个 few-shot 示例覆盖两种意图）
- [ ] 2.3 接入 langchain `with_structured_output`，定义 Pydantic schema 约束 LLM 输出
- [ ] 2.4 添加 `RAG_INTENT_CLASSIFIER_ENABLED`（默认 false）、`RAG_INTENT_CLASSIFIER_MODEL`、`RAG_INTENT_CLASSIFIER_TIMEOUT_SECONDS` 配置（`backend/rag/runtime_config.py`）
- [ ] 2.5 LLM 调用失败/超时/解析错误时自动降级到 M1 的规则路径，trace 记录 `intent_llm_error` 和 `intent_llm_ms`
- [ ] 2.6 集成测试：mock LLM 返回各种 schema 的 JSON，验证产出的 QueryPlan 结构正确

**验收**：`RAG_INTENT_CLASSIFIER_ENABLED=true` 时全链路能产出 PreciseQueryPlan 或 ComprehensiveQueryPlan；LLM 调用失败时降级到规则路径且不阻塞。

## 3. Milestone M3：RAG graph 入口集成

- [ ] 3.1 在 `backend/rag/pipeline.py` 增加 `intent_parse_node`，作为 graph 的新入口节点
- [ ] 3.2 添加条件边：`intent_parse → retrieve_initial`（precise 路径）或 `intent_parse → decompose_and_fanout`（comprehensive 路径）
- [ ] 3.3 修改 `retrieve_initial` 接受 PreciseQueryPlan 作为输入而非 raw query
- [ ] 3.4 实现 `decompose_and_fanout` 节点：comprehensive 路径下并发或顺序执行每个 sub_query 的检索
- [ ] 3.5 实现 `merge_sub_query_results` 节点：按 ComprehensiveQueryPlan.merge_strategy 合并多 sub_query 结果
- [ ] 3.6 `plan_rag_turn` 不变，但 trace 增加 `query_plan_type` 字段反映 intent 解析结果

**验收**：完整 RAG 流程在 precise 和 comprehensive 两条路径下都能产出回答；现有测试 `tests/test_rag_pipeline.py` 全绿。

## 4. Milestone M4：综合分析执行模式

- [ ] 4.1 实现 multi_turn 模式：Agent 通过工具循环调用 search_knowledge_base，每次传入一个 sub_query；search_knowledge_base 工具增加 sub_query 参数支持
- [ ] 4.2 实现 parallel 模式：所有 sub_query 在 graph 内并发检索，统一合并后一次 LLM 合成
- [ ] 4.3 配置项 `RAG_COMPREHENSIVE_MODE`（multi_turn / parallel）、`RAG_COMPREHENSIVE_MAX_TURNS`（默认 4）
- [ ] 4.4 parallel 模式下的 ThreadPoolExecutor 复用现有 `_get_fallback_executor`
- [ ] 4.5 trace 增加 `comprehensive_execution_mode`、`sub_query_count`、`sub_query_results`（每个 sub_query 的命中数和延迟）

**验收**：两种模式都能跑通 comprehensive 测试用例；parallel 模式延迟显著低于 multi_turn；trace 完整。

## 5. Milestone M5：意图分类评测集

- [ ] 5.1 设计评测样本 schema：`{query, expected_intent, expected_entities, expected_sub_queries?, expected_scope?, notes}`
- [ ] 5.2 标注样本：100-200 条，70% precise + 30% comprehensive，覆盖所有 entity 类型和 analysis_type
- [ ] 5.3 评测脚本 `tests/test_intent_classifier_eval.py`：跑当前模型，输出 intent accuracy / entity precision-recall / sub-query 5 分制评分（人工部分用 LLM-as-judge）
- [ ] 5.4 评测结果落地到 `eval/intent/{date}_{model}.json`（不进 git，gitignore 覆盖）
- [ ] 5.5 在 `docs/` 下记录评测方法和指标定义；阈值在标注完成后根据初评结果设定

**验收**：评测脚本可重复跑；FAST_MODEL 评测结果达标（阈值由初评基线确定）；不达标时模型升级路径在 design.md 中记录。

## 6. Milestone M6：上线开关与监控

- [ ] 6.1 默认 `RAG_INTENT_CLASSIFIER_ENABLED=false`，开关由部署方控制
- [ ] 6.2 监控指标：intent classifier 调用 P50/P95 延迟、LLM 失败率、规则降级率、各 intent 占比
- [ ] 6.3 灰度策略文档：先 10% 流量启用，观察延迟和准确率，逐步全量
- [ ] 6.4 关闭开关时全部走规则降级路径，与现有行为完全等价（无回归）
- [ ] 6.5 完成评测后将默认值改为 true，作为单独的小 change 上线

**验收**：在 `RAG_INTENT_CLASSIFIER_ENABLED=false` 状态下，所有现有测试通过、行为与改造前一致；监控字段在 rag_trace 中齐全。
