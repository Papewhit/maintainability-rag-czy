## Why

当前 RAG 链路对所有查询走同一条管线（global hybrid → rerank → answer），但船舶维修性设计场景中存在两类截然不同的查询：

- **精确查找（~70%）**：用户指向具体型号、设备、参数、步骤、章节。答案聚焦在 1-2 个特定 chunk，对精度敏感。
- **综合分析（~30%）**：用户要求跨文档对比、方案沿用、步骤综合。答案需要多源证据合并，对覆盖度敏感。

当前 QueryPlan 是基于正则和文件名匹配的规则引擎，默认关闭（`QUERY_PLAN_ENABLED=false`），只能在精确查找场景中"勉强可用"，对综合分析帮助为零。下游所有阶段（检索 scope、rerank 维度、回答风格、引用粒度）也无法区分两类查询。

## What Changes

引入 LLM 驱动的意图分类作为 RAG 管线的统一入口，并把 QueryPlan 拆成两种结构以适配两条管线：

1. **Intent + Entity Parser**：一次 LLM 调用同时输出意图分类、领域实体（产品型号、设备、组件、参数、维修动作）和扩展字段（精确查找的 scope_hint / 综合分析的 sub_queries + merge_strategy）。
2. **PreciseQueryPlan vs ComprehensiveQueryPlan**：两种数据结构对应两条管线，共享 EntityMatch 这一公共部分。
3. **Pipeline 分支**：`run_rag_graph` 的入口节点从 `retrieve_initial` 改为 `intent_parse`，按 intent 路由到 precise 子图或 comprehensive 子图。
4. **规则降级**：LLM 调用失败或超时时，规则引擎兜底（保留现有 `parse_query_plan` 逻辑作为 precise 路径的默认输入）。
5. **意图分类评测集**：人工标注 100-200 条样本，建立 intent accuracy / entity precision-recall / sub-query quality 三类指标，无需微调，目标使用现有 FAST_MODEL 直接达标。

## Capabilities

### New Capabilities
- `rag-intent-routing`: 意图分类入口、两种 QueryPlan 结构、管线分支与降级机制

### Modified Capabilities
<!-- 当前 openspec/specs/ 为空,无既有 spec 需修改。后续 rag-postprocess-evidence 等 change 会修改 rag-retrieval-pipeline 等 spec。 -->

## Impact

**代码影响：**
- `backend/rag/query_plan.py`：拆分 QueryPlan 为 PreciseQueryPlan / ComprehensiveQueryPlan 两种结构；新增 EntityMatch / SubQuery 数据类。
- `backend/rag/pipeline.py`：在 `build_rag_graph` 入口前增加 `intent_parse` 节点；新增 `retrieve_comprehensive` 和 `merge_sub_query_results` 节点。
- `backend/rag/utils.py`：`build_query_plan` 改为消费 intent 解析结果而非自己解析。
- `backend/chat/rag_execution.py`：`plan_rag_turn` 不再做 query 内容分析（intent 解析下沉到 RAG graph 内部），只保留 session 级路由（FORCED_PRELOAD vs OPTIONAL_TOOL）。
- `backend/rag/runtime_config.py`：新增 `intent_classifier_model` / `intent_classifier_temperature` / `comprehensive_mode` / `comprehensive_max_turns` 配置。
- `tests/`：新增 `test_intent_classifier.py` 验证 LLM 调用、规则降级、评测集准确率。

**接口影响：**
- 现有 `rag_trace` 增加字段：`intent`, `intent_confidence`, `query_plan_type`, `intent_llm_model`, `intent_llm_ms`, `intent_fallback_to_rules`。
- `/chat` 响应体 schema 无破坏性变更（trace 是扩展字段）。

**依赖：**
- 假设 `rag-terminology-module` 已提供术语规范化能力（intent parser 输出的 entities 需要术语表做归一化）。如果 terminology 未就绪，entities 字段以 LLM 原样输出落地，后置 normalize 待 terminology 上线后接入。
- 评测集落地依赖标注资源（10-20 小时人工标注）。
