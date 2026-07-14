## Context

当前 fallback 实现见 `backend/rag/pipeline.py`：
- `grade_documents_node`（线 310-403）：检查 `fallback_required` 信号 + LLM grader 评估文档相关性
- `rewrite_question_node`（线 406-526）：用 router LLM 选 step_back / hyde / complex 策略，生成 expanded_query
- `retrieve_expanded`（线 668-886）：用 expanded query 重新检索

整体路径只有"扩展查询 → 重检"一种 fallback。`RAG_FALLBACK_ENABLED=false` 默认关闭，事实上未投产。

confidence gate（`backend/rag/confidence.py`）已经输出了多维信号：
- top_margin（top1 与 top2 score 差距）
- top_score
- dominant_root_share（top-N 中主导 root 的得分占比）
- dominant_root_support
- anchor_match（query anchor 与 chunk anchor 是否匹配）
- query_anchors

但这些信号目前只汇总成单一 boolean `fallback_required`，下游没有差异化使用。

讨论确定的分级框架：
- Level 0：每次必做的顺序预处理（意图/结构解析、结构清洗、术语扩展、dense+BM25 query composition）
- Level 1：Query Rewrite（"问题描述不准"）
- Level 2：Scope Relax（"搜索约束太紧"）
- Level 3：明确告知证据不足
- 顺序执行，预算控制，意图区分

## Goals / Non-Goals

**Goals：**
- 每个 fallback level 有明确的触发信号、策略集、预算
- Router 是纯规则（无 LLM），逻辑可单测、可解释
- Level 1 内部按 plan_type 路由（精确 vs 综合）
- 整体预算可控，不会因 fallback 让单次 RAG 失控
- trace 完整记录 fallback 决策路径，便于前端"思考过程"展示

**Non-Goals：**
- 不引入新的 LLM 调用类型（Level 1 已经会调 LLM，预算在内）
- 不做并行 fallback（顺序执行已确定）
- 不在本 change 重新设计 Level 0 的字段与算法（Level 0 = pre-flight，其顺序与 query composition 由 intent-routing 和 terminology 提供）
- 不在本 change 修改 confidence gate 算法（只消费它的信号）

## Decisions

### 决策 1：分级框架与触发信号映射

```
Level 0 (Pre-flight): 每次必做
  ├─ Intent / 结构解析 (rag-intent-routing)
  ├─ 确认 scope/anchor 消费并构造 semantic query
  ├─ Terminology preflight (rag-terminology-module)
  `─ normalized query -> dense; sparse expansion -> BM25

Level 1 (Query Rewrite): 由 LLM 改写 query
  触发信号:
    - anchor_mismatch
    - low_score_and_margin
    - sub_query_coverage < threshold (comprehensive)
  策略:
    精确: step_back / hyde / complex (LLM router 选择)
    综合: generalize / specialize / replace / decompose (LLM router + rewriter 合并调用)

Level 2 (Scope Relax): 放宽搜索约束
  触发信号:
    - weak_margin_and_root
    - scope_mode == filter 但 matched_files 召回不相关
  策略:
    - scope_mode 降级: filter → boost → none
    - candidate_k 增大 1.5x
    - same_root_cap 放宽 (允许更多同源)
    - 回答时强制注入"非精确匹配"声明

Level 3 (Insufficient): 明确告知
  触发条件:
    - Level 1+2 都试过仍不达标
    - 或预算超时
    - 或 no_docs (空召回直接到 Level 3, 不重试)
  输出:
    精确: "未在当前知识库中找到与当前查询及结构范围匹配的足够依据,已尝试 [尝试过的 level]"
    综合: 部分覆盖回答 + 未覆盖维度的明确标注
```

### 决策 2：Fallback Router 实现

纯规则 Python 函数，无 LLM：

```python
@dataclass(frozen=True)
class FallbackDecision:
    target_level: Literal[0, 1, 2, 3]   # 0=不需 fallback,直接答
    primary_signal: str                  # 主导信号
    contributing_signals: list[str]
    reason: str
    budget_ms: int                       # 分配给本 level 的预算

def route_fallback(
    confidence: dict,
    query_plan: PreciseQueryPlan | ComprehensiveQueryPlan,
    attempted_levels: list[int],
    remaining_budget_ms: float,
) -> FallbackDecision:
    reasons = confidence.get("confidence_reasons", [])
    if not reasons:
        return FallbackDecision(target_level=0, ...)

    # 空召回直接 Level 3
    if "no_docs" in reasons:
        return FallbackDecision(target_level=3, primary_signal="no_docs", ...)

    # 预算耗尽直接 Level 3
    if remaining_budget_ms < MINIMUM_LEVEL1_BUDGET_MS:
        return FallbackDecision(target_level=3, primary_signal="budget_exhausted", ...)

    # 已尝试过的 level 不重复
    if 1 in attempted_levels and 2 not in attempted_levels:
        return FallbackDecision(target_level=2, ...)
    if 2 in attempted_levels:
        return FallbackDecision(target_level=3, ...)

    # 首次决策: 根据主导信号选 Level 1 or Level 2
    if "anchor_mismatch" in reasons:
        return FallbackDecision(target_level=1, primary_signal="anchor_mismatch", ...)
    if "weak_margin_and_root" in reasons:
        return FallbackDecision(target_level=2, primary_signal="weak_margin_and_root", ...)
    if "low_score_and_margin" in reasons:
        return FallbackDecision(target_level=1, primary_signal="low_score_and_margin", ...)

    return FallbackDecision(target_level=1, ...)   # 默认 Level 1
```

完整单测覆盖每条规则。

### 决策 3：Level 1 - 精确管线 rewrite

复用现有 `rewrite_question_node` 的 step_back / hyde / complex 逻辑，但：
- 入口检查预算：超预算直接降 Level 3
- 移除 LLM grader（grader 决策已被 fallback router 替代）
- prompt 改写：把原始 query、PreciseQueryPlan 的 anchors、doc_hints 和 scope 状态注入 rewrite prompt，让 LLM 更聚焦
- trace 记录 `level1_strategy` 和 `level1_ms`

### 决策 4：Level 1 - 综合管线 rewrite

新实现，使用合并的 LLM 调用同时做策略选择和重写。输入中的失败 branch 必须是 LLM sub-query；intent-routing 固定构造的 clean-query baseline 只提供 diagnostics，不得成为 rewrite/replace/decompose 目标。发生综合重试时 baseline 始终从 `ComprehensiveQueryPlan.clean_query` 原样重建：

```
System:
你是综合分析查询的修复器。一个 sub_query 召回不足,需要修复。
基于完整 plan 和失败信号,选择策略并生成新的 sub_query。

策略:
- generalize: 抽象到更通用层
- specialize: 生成假设性具体内容辅助检索
- replace: 换一个不同角度的提问
- decompose: 拆成 2 个更细的 sub_query

输出 JSON:
{
  "strategy": "...",
  "new_sub_queries": [{"query": "...", "domain": "...", "priority": ...}],
  "reason": "..."
}

User input:
{
  "original_plan": <完整 ComprehensiveQueryPlan>,
  "failed_sub_query": <失败的 sub_q>,
  "failure_signal": {
    "candidate_count": ...,
    "top_score": ...,
    "anchors_matched": [...]
  },
  "succeeded_sub_queries": [...]   ← 防止生成重复
}
```

输出可能是 1 个 sub_query（generalize/specialize/replace）或 2 个（decompose）。

### 决策 5：Level 2 - 精确管线 scope relax

无 LLM 调用，纯规则降级：

```python
def relax_scope(query_plan: PreciseQueryPlan) -> PreciseQueryPlan:
    """降级结构化 scope；不处理 semantic entity filter。"""
    new_scope_mode = SCOPE_DOWNGRADE[query_plan.scope_mode]  # filter→boost→none
    return dataclasses.replace(
        query_plan,
        scope_mode=new_scope_mode,
    )

# 然后重新走一次 retrieve_candidate_pool, candidate_k 放大 1.5x
```

trace 记录 `level2_relaxations`（list，描述哪些约束被放宽）。

### 决策 6：Level 2 - 综合管线 scope relax

每个 retrieval branch 独立放宽：
- 对 LLM sub-query 放宽该分支的结构 scope；clean-query baseline 使用同一轮已放宽的共享结构约束重新构造，但不改写其文本
- 继续使用 intent-routing 已解析的完整 comprehensive postprocess profile

Level 2 不在 graph 节点内替换 profile 组件。未来若要改变 merge/selection/budget 组合，必须注册并评测新的完整 profile，而不是临时修改单个策略。

trace 记录每个 sub_query 的放宽情况。

### 决策 7：Level 3 - 答案生成

不调用检索，直接生成解释性回答：

```python
def generate_level3_answer(query_plan, attempted_levels) -> str:
    if isinstance(query_plan, PreciseQueryPlan):
        attempts_str = " → ".join(f"Level {l}" for l in attempted_levels)
        return (
            f"未在当前知识库中找到与“{query_plan.raw_query}”及当前结构范围匹配的足够依据。"
            f"已尝试: {attempts_str}。"
            f"建议: 检查相关文档是否已上传 / 调整问法 / 提供更多上下文文件。"
        )
    else:
        # 综合管线: 用已成功的 sub_query 结果生成部分回答
        covered = [...]  # 成功的 sub_q
        missing = [...]  # 失败的 sub_q
        return f"已完成 {len(covered)}/{total} 个分析维度,...,未覆盖部分: {missing}"
```

这是模板化输出，不调 LLM。`backend/chat/rag_execution.py` 的 prompt 注入逻辑识别 Level 3 并强制使用此输出。

### 决策 8：Level 2 触发时的 prompt 注入

`prepare_rag_answer_messages` 增加 Level 2 分支：

```python
if turn_context.fallback_level == 2:
    instruction = (
        "检索系统在精确范围内未找到充分证据,已放宽搜索范围。"
        "当前提供的证据来源于扩大后的范围。"
        "生成回答时必须:"
        "1. 开头明确说明: 未找到与原始 query 及结构范围完全匹配的证据,以下是相关参考"
        "2. 引用每个来源时,标注它是否完全匹配原始约束"
        "3. 不要把放宽后的内容当作直接答案,要把它定位为参考方案"
        "4. 如有可能,建议用户补充信息或上传相关文档以获得精确答案"
    )
```

注入位置：在原 RAG 上下文 prompt 之后追加。

### 决策 9：预算分配与超时

```
RAG_FALLBACK_TOTAL_BUDGET_MS    = 8000   # 整体上限
RAG_FALLBACK_LEVEL1_BUDGET_MS   = 3000
RAG_FALLBACK_LEVEL2_BUDGET_MS   = 2500
RAG_FALLBACK_LEVEL3_BUDGET_MS   = 100    # Level 3 几乎零成本

进入 level N 前检查: remaining_budget = total_budget - elapsed_since_turn_start
  if remaining_budget < level_N_budget:
      跳过本 level, 直接进入 Level 3
```

复用 `_get_fallback_executor` 和 `_await_with_deadline` 基础设施。

### 决策 10：意图与 plan_type 区分

fallback router 接收 query_plan 实例，按 isinstance 路由：

```python
match query_plan:
    case PreciseQueryPlan():
        return _precise_fallback_path(decision, query_plan)
    case ComprehensiveQueryPlan():
        return _comprehensive_fallback_path(decision, query_plan)
```

Level 3 输出也按 plan_type 不同：精确管线给"未找到"，综合管线给"部分覆盖"。

## Risks / Trade-offs

**风险 1：多 level fallback 累计延迟**

最坏情况：Level 1 (3s) → Level 2 (2.5s) → Level 3 (0.1s) = ~5.6s 额外延迟。加上原始检索可能超 10s。

缓解：
- 整体预算 8s 硬性限制
- 各 level 入口检查预算
- 实测 P95 落在 5-7s 范围内（多数查询 Level 0 直接成功）

**风险 2：fallback router 规则维护性**

规则随时间累加可能变得难维护。

缓解：
- 每条规则单测覆盖
- 规则定义放在独立文件 `backend/rag/fallback_router.py`
- 重大规则变更需要在 trace 中体现（router_version）

**风险 3：意图分类失败时的 fallback 路径**

intent classifier 降级到规则路径时，可能产出错误的 query_plan_type（如把综合分析判成精确）。fallback router 按错误的 plan_type 路由会更糟。

缓解：
- intent classifier 规则降级永远输出 PreciseQueryPlan（保守选择）
- comprehensive 路径的 fallback 失败时进入 Level 3 而非循环重试
- intent_fallback_to_rules=true 时记录到 fallback trace，便于事后分析

**风险 4：Level 2 放宽过度**

scope_mode 降级到 none 后召回大量无关 chunk，反而稀释证据质量。

缓解：
- candidate_k 放大但仍受 max_candidate_k 上限保护
- structure_rerank 的 same_root_cap 仍工作，避免被同源 chunk 淹没
- Level 2 答案的 prompt 注入要求 LLM 明确标注"非精确匹配"，避免误导

**Trade-off：删除 `RAG_FALLBACK_ENABLED`**

直接删除会破坏现有用户的环境配置。

缓解：
- 保留 `RAG_FALLBACK_ENABLED` 作为总开关（=false 时所有 level 都跳过，直接走 Level 3）
- 新增 per-level 开关 `RAG_FALLBACK_LEVEL1_ENABLED` 等，默认 true
- 在 deprecation note 中说明 `RAG_FALLBACK_ENABLED` 在 v2 移除

## 依赖与衔接

- **依赖 `rag-intent-routing`**：query_plan 字段、PreciseQueryPlan/ComprehensiveQueryPlan 类型
- **依赖 `rag-terminology-module`**：Level 0 已在结构解析后对实际检索文本做术语扩展并构造 dense/BM25 输入，本 change 不重复做，也不得在 Level 1/2 把 query 恢复为 raw query
- **依赖 `rag-postprocess-evidence`**：confidence gate 输出的 top score、margin、root share、anchor 和 sub-query coverage 信号。terminology 的 `entity_type_coverage` / `term_match_count` 可继续参与 rerank 与 trace，但不解释为实例级 entity coverage，也不用于本 change 的 scope-relax 路由。

本 change 必须在以上三个 change 至少部分上线后才能完整工作。可以早期上线"骨架版"：Level 1 沿用现有 rewrite 逻辑（不区分 plan_type），Level 2 仅做 scope_mode 降级，Level 3 模板输出。完整能力随依赖 change 推进而启用。
