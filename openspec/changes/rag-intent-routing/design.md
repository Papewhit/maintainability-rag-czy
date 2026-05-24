## Context

当前 RAG 管线的入口路由 `plan_rag_turn()` 只做 session 级别的判断（是否有 context_files、是否检测到文档意图关键词），不分析 query 本身的语义结构。query 解析延迟到 `retrieve_documents()` 内部的规则版 QueryPlan（默认关闭），而且只能提取文档名/型号/章节这几类信号，对"综合分析"类查询完全无感。

下游所有阶段的输入都是同一种 `RetrievalRequest`：单个 `query` 字符串 + 可选 `context_files`。没有任何机制告诉检索/rerank/answer "这次查询是精确还是综合"。

融合方案设计文档（`docs/superpowers/specs/2026-05-20-rag-fusion-design.md`）明确要求：
- QueryPlan 需识别产品型号、设备名、组件名、维修动作、参数名、文档名、页码、章节
- 支持 filter / boost / global 三种 scope
- 对"沿用/改进/参考基本型方案"类问题，优先召回基本型产品文档（这是综合分析特征）
- 对参数问题提升表格 chunk 权重、对步骤问题提升 list group 权重（这是精确查找特征）

这些要求在单一 QueryPlan 结构下难以同时承载。

## Goals / Non-Goals

**Goals：**
- 用一次 LLM 调用同时完成意图分类和实体提取，承载 7:3 比例下的精确/综合两种产出形态。
- 让下游每个阶段都能根据 intent 调整自己的行为，而无需各自重新解析 query。
- LLM 调用失败时，整个 RAG 管线仍能正常工作（规则降级路径不阻塞）。
- 建立可重复跑的意图分类评测基线（intent accuracy / entity precision-recall / sub-query quality）。

**Non-Goals：**
- 不做 LLM 微调。所有目标基于现有 FAST_MODEL 开箱即用达成。如评测显示不达标，先升级到更大模型或加 few-shot 示例，而不是微调。
- 不引入新的长期记忆层。意图解析只用本轮 query + 当前 context_files，不依赖历史会话。
- 不做意图分类的多分类细化（precise/comprehensive 二分即可，analysis_type 作为 comprehensive 内部子字段）。
- 不重写 `plan_rag_turn`。它继续负责 session 级 FORCED_PRELOAD vs OPTIONAL_TOOL 路由；intent 解析作为 RAG graph 内部第一节点独立存在。

## Decisions

### 决策 1：意图解析下沉到 RAG graph 内部，而非提到 `plan_rag_turn`

`plan_rag_turn` 当前职责是判断"本轮是否要走 RAG、context_files 是否需要预加载"。把 intent 解析放进去会让它跨两层抽象（session 级 + query 级），且 OPTIONAL_TOOL 模式下 Agent 决定调用 search_knowledge_base 时已经丢失了 `plan_rag_turn` 的解析结果。

下沉到 RAG graph 内部后，无论从 FORCED_PRELOAD 还是 OPTIONAL_TOOL 进入 `run_rag_graph()`，第一步都是 `intent_parse`，意图解析对调用方式透明。

### 决策 2：一次 LLM 调用合并意图分类 + 实体提取

替代方案是两次调用（先分类，再按分类做不同的实体提取）。但 7:3 比例下，分类结果对实体提取的影响不大（两种意图需要的实体类型有大量交集），合并调用降低延迟约 200-400ms。

LLM 输出 schema：

```json
{
  "intent": "precise_lookup" | "comprehensive_analysis",
  "entities": [{"type": "...", "value": "...", "normalized": "..."}],
  // precise_lookup 字段：
  "semantic_query": "...",
  "scope_hint": "filter" | "boost" | "none",
  "anchors": ["第三章", "表2"],
  "target_granularity": "paragraph" | "table" | "step_list" | "figure",
  // comprehensive_analysis 字段：
  "analysis_type": "design_reuse" | "comparison" | "procedure_synthesis" | "general",
  "sub_queries": [{"query": "...", "domain": "...", "priority": 1-3}],
  "merge_strategy": "union" | "hierarchical"
}
```

模型按 intent 输出对应的字段集，未使用的字段为空/省略。

### 决策 3：PreciseQueryPlan 和 ComprehensiveQueryPlan 独立结构

替代方案是单一 QueryPlan 类带 optional 字段。但单一结构下 type checker 无法约束"comprehensive 必须有 sub_queries"，运行时也容易出现"precise 路径误用 sub_queries 字段"的 bug。

```python
@dataclass(frozen=True)
class EntityMatch:
    type: Literal["product_model", "equipment", "component",
                  "parameter", "maintenance_action"]
    value: str           # 原文
    normalized: str      # 规范化形式
    confidence: float    # 0-1

@dataclass(frozen=True)
class PreciseQueryPlan:
    raw_query: str
    semantic_query: str
    entities: list[EntityMatch]
    scope_mode: Literal["filter", "boost", "none"]
    matched_files: list[tuple[str, float]]
    anchors: list[str]
    target_granularity: Literal["paragraph", "table", "step_list", "figure"]
    route: Literal["scoped_hybrid", "global_hybrid"] = "scoped_hybrid"

@dataclass(frozen=True)
class SubQuery:
    query: str
    domain: str
    priority: int                              # 1=高,2=中,3=低

@dataclass(frozen=True)
class ComprehensiveQueryPlan:
    raw_query: str
    analysis_type: Literal["design_reuse", "comparison",
                            "procedure_synthesis", "general"]
    entities: list[EntityMatch]
    sub_queries: list[SubQuery]
    merge_strategy: Literal["union", "weighted", "hierarchical"]
    coverage_domains: list[str]
```

两者通过 union type `QueryPlan = PreciseQueryPlan | ComprehensiveQueryPlan` 在 RAGState 中表达。

### 决策 4：规则降级路径

LLM 调用失败、超时或返回无法解析的 JSON 时，回退到规则引擎。规则降级永远输出 `PreciseQueryPlan`（不输出 ComprehensiveQueryPlan，因为综合分析的子查询拆解依赖 LLM 能力）。

降级算法：
1. 复用现有 `parse_query_plan()` 的正则和文件名匹配能力，输出 entities + anchors + scope_mode
2. 关键词启发判断 intent：
   - 强综合信号（对比/比较/分析/综合/方案/改进/评估/建议）→ 标记 `intent=comprehensive_analysis_rule_degraded`，但 sub_queries 为空
   - 默认 → `intent=precise_lookup`
3. trace 中标记 `intent_fallback_to_rules: true` 和 `intent_llm_error: <reason>`

综合分析降级后下游能感知到"sub_queries 为空"，可以选择当作单 query 走 precise 路径，或者直接进入 Level 3 fallback（无法拆解，告知用户）。

### 决策 5：模型选择优先级

意图分类优先使用配置项 `RAG_INTENT_CLASSIFIER_MODEL` 指定的模型；未配置时默认使用 FAST_MODEL。评测不达标时，按以下顺序尝试更大模型：
- 默认 → FAST_MODEL → GRADE_MODEL → MODEL

具体链待评测后确定（开箱即用目标为 FAST_MODEL 直接达标，不设硬回退逻辑）。

### 决策 6：综合分析的执行模式可降级

`RAG_COMPREHENSIVE_MODE` 配置：
- `multi_turn`（默认）：Agent 多轮工具调用，每个 sub_query 调一次 search_knowledge_base，可根据中间结果调整后续 sub_query
- `parallel`：所有 sub_query 在一次 RAG graph 调用内并发检索、合并、一次 LLM 合成

multi_turn 灵活但延迟高，适合资源充足场景；parallel 延迟低但失去中间调整能力，适合资源受限或对响应时间敏感的场景。

### 决策 7：评测集落地形态

`tests/data/intent_eval/` 下放：
- `precise_lookup.jsonl`（70 条，覆盖各实体组合）
- `comprehensive_analysis.jsonl`（30 条，覆盖各 analysis_type）
- 每条样本字段：`{query, expected_intent, expected_entities, expected_sub_queries?, expected_scope?, notes}`

评测脚本 `tests/test_intent_classifier_eval.py` 用 pytest 标记 `@pytest.mark.intent_eval`，CI 不默认跑（成本高），但本地和发版前必跑。指标输出到 `eval/intent/{date}_{model}.json`。

阈值目标（待初评后根据实际基线修正）：
- Intent Accuracy（目标 > 正面率基线）
- Entity Precision / Recall
- Sub-query Quality（人工 1-5 分均值）

具体数值在标注完成后根据模型初评结果设定。不达标时，升级模型而非微调。

## Risks / Trade-offs

**风险 1：LLM 输出不稳定**

即使用结构化输出约束，LLM 偶尔会输出格式错误的 JSON 或不在 schema 内的 enum 值。

缓解：
- 用 langchain 的 `with_structured_output(Schema)` 强约束（已在现有 grader 中使用，行为可控）
- LLM 输出无法解析时直接降级到规则路径，不重试（重试只会放大延迟）
- trace 字段 `intent_llm_parse_error` 记录失败次数，超过阈值（如周内 5% 调用失败）触发监控告警

**风险 2：FAST_MODEL 精度不够**

7:3 比例下，精确查找的 70% 容错较低（用户期望快速准确），如果 intent 误判为 comprehensive，会触发 sub_query 拆解，延迟和成本都翻倍。

缓解：
- 评测集中精确查找样本占 70%，确保模型在大头场景上达标
- 评测不达标时升级模型（默认 → GRADE_MODEL → MODEL），不微调
- 引入 `intent_confidence` 字段，置信度低于阈值时偏向 precise（保守选择）

**风险 3：综合分析的 sub_query 质量取决于 LLM**

LLM 拆解 sub_queries 可能不合理（重复、遗漏关键维度、子查询太宽泛）。

缓解：
- few-shot 示例覆盖典型 analysis_type
- sub_query 质量评测分（人工评判）作为硬指标
- multi_turn 模式下，Agent 可以在执行过程中发现拆解不合理并补救（parallel 模式无此能力，作为已知限制）

**风险 4：成本翻倍**

每次 RAG 都多调一次 LLM（intent classifier）。按 FAST_MODEL 估算单次 ~200-400ms + token 成本。

缓解：
- 配置项 `RAG_INTENT_CLASSIFIER_ENABLED` 允许关闭（关闭时全部走规则降级路径，等价于现有行为）
- 后续优化方向：对精确查找可考虑 short-ttl query 缓存（收益待验证，v1 不实现）

**Trade-off：意图二分 vs 多分类**

选择二分（精确/综合）而非细分（factoid/data_query/procedure/comparison/...）。细分能让下游做更精细的路由，但二分对 LLM 要求低、评测集容易构造、下游分支简单。细分留作未来扩展（通过 `analysis_type` 子字段表达）。

**Trade-off：意图解析放在 RAG graph 入口 vs `plan_rag_turn`**

放在 RAG graph 入口让 OPTIONAL_TOOL 的 search_knowledge_base 工具调用也能受益，但代价是 FORCED_PRELOAD 和 OPTIONAL_TOOL 各走一遍意图解析（无缓存复用）。考虑到 OPTIONAL_TOOL 占比超过 50%，下沉到 graph 内部的收益更大。

## 依赖与衔接

- **依赖 `rag-terminology-module`**：entities 字段的 normalized 形式由术语表提供。terminology 未就绪前，normalized 直接采用 LLM 输出（可能不规范），完成后回填正确规范化。
- **被 `rag-multilevel-fallback` 依赖**：fallback 的 Level 1 rewrite router 需要 ComprehensiveQueryPlan 作为输入；Level 2 scope relax 需要 PreciseQueryPlan 的 scope_mode 字段。
- **被 `rag-postprocess-evidence` 依赖**：EvidenceBuilder 需要 intent 来决定是否启用 step_chain_check（precise 才启用）。

实施时 intent-routing 可以先用 LLM 原样输出的 entities 跑通，待 terminology 上线后接入规范化。
