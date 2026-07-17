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
- `context_files` 始终是显式硬检索边界；附件候选与普通候选共用唯一评分、postprocess、confidence 和回答上下文路径
- 每轮重检后刷新 postprocess/confidence，router 不消费旧信号
- `scope_mode` 是 Fallback 唯一权威的范围行为契约；在进入 Fallback 前保证 filter 只由可信确定性硬范围产生

**Non-Goals：**
- 不引入新的 LLM 调用类型（Level 1 已经会调 LLM，预算在内）
- 不做并行 fallback（顺序执行已确定）
- 不做附件全文总结；本项目能力边界仍是基于检索证据的 RAG 问答
- 除收紧精确管线 filter producer 这一必要前置条件外，不重新设计 Level 0 的字段与算法（Level 0 = pre-flight，其顺序与 query composition 由 intent-routing 和 terminology 提供）
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
    - 当前范围内候选分散或约束参数过紧
  策略:
    - filter: 保持硬 filename filter
    - boost: 降级为 none
    - none: 保持 none
    - candidate_k 增大 1.5x
    - same_root_cap 放宽 (允许更多同源)
    - 回答时强制注入"非精确匹配"声明

Level 3 (Insufficient): 明确告知
  触发条件:
    - Level 1+2 都试过仍不达标
    - 或预算超时
    - 或 no_docs (空召回直接到 Level 3, 不重试)
  输出:
    精确 filter: "未在你指定的文档范围内找到足够依据；本次没有搜索范围外知识库"
    精确 boost/none: "未在当前知识库中找到与当前查询匹配的足够依据"
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
    """只消费 scope_mode；不追溯来源，不处理 semantic entity filter。"""
    if query_plan.scope_mode == "filter":
        return query_plan  # planner 已承诺这是用户硬范围
    new_scope_mode = "none"  # boost -> none；none -> none
    return dataclasses.replace(
        query_plan,
        scope_mode=new_scope_mode,
        matched_files=(),
        route="global_hybrid",
    )

# 然后重新走一次 retrieve_candidate_pool, candidate_k 放大 1.5x
```

trace 记录 `level2_relaxations`（list，描述哪些约束被放宽）。

任何 `filter` 都不得移除组合 filename filter，也不得追加全库 reserve。Level 2 仍可放大 `candidate_k`、放宽 `same_root_cap`，其重检结果继续完整通过共享 postprocess/confidence。`boost → none` 必须原子更新 `scope_mode=none`、`matched_files=()` 与 `route=global_hybrid`。Fallback 不检查 filter 的来源，也不为 `PreciseQueryPlan` 新增 `scope_source`。

### 决策 6：Level 2 - 综合管线 scope relax

每个 retrieval branch 独立放宽：
- 按共享 `RetrievalScope.scope_mode` 执行同一规则：filter 保持、boost 降为 none、none 保持；clean-query baseline 使用同一轮结果重建但不改写其文本
- 继续使用 intent-routing 已解析的完整 comprehensive postprocess profile

`RetrievalScope.source` 保留为综合管线 trace/provenance，但它是非权威诊断字段，不参与 Level 2 路由或放宽决策。

Level 2 不在 graph 节点内替换 profile 组件。未来若要改变 merge/selection/budget 组合，必须注册并评测新的完整 profile，而不是临时修改单个策略。

trace 记录每个 sub_query 的放宽情况。

### 决策 7：Level 3 - 答案生成

不调用检索，直接生成解释性回答：

```python
def generate_level3_answer(query_plan, attempted_levels) -> str:
    if isinstance(query_plan, PreciseQueryPlan):
        attempts_str = " → ".join(f"Level {l}" for l in attempted_levels)
        if query_plan.scope_mode == "filter":
            return (
                "未在你指定的文档范围内找到足够依据；"
                "本次没有搜索该范围之外的知识库。"
                f"已尝试: {attempts_str}。"
            )
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

`prepare_rag_answer_messages` 增加 scope-aware Level 2 分支：

```python
if turn_context.fallback_level == 2 and turn_context.scope_mode == "filter":
    instruction = (
        "未在用户指定的文档范围内找到精确匹配。"
        "以下证据仍全部来自该范围；本次没有搜索范围外知识库。"
    )
elif turn_context.fallback_level == 2:
    instruction = "未在优先文件中找到精确匹配，以下包含范围外相关参考。"
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

**风险 4：boost 放宽过度**

scope_mode 从 boost 降级到 none 后可能召回大量无关 chunk，反而稀释证据质量。filter 永不降级。

缓解：
- candidate_k 放大但仍受 max_candidate_k 上限保护
- structure_rerank 的 same_root_cap 仍工作，避免被同源 chunk 淹没
- Level 2 答案的 prompt 注入要求 LLM 明确标注"非精确匹配"，避免误导

**风险 5：不可信 filter 导致错误归因**

当前精确管线可因文件名匹配分数 ≥ 0.85 自动产生 filter，也允许 classifier 的 `scope_hint="filter"` 在匹配仅达到 boost 阈值时覆盖自动分级；classifier prompt 尚未定义 filter/boost/none 的语义。若不先收紧 producer，Level 1/2 会被锁在错误文件中，Level 3 还会错误声称这是用户指定范围。

缓解：
- filter 只由 `context_files`、确定性封闭范围措辞或确定性精确范围引用产生
- 文件名分数只确认文档身份/候选强度，不独立决定 hard scope
- classifier 不得把 boost/none 提升为 filter，也不得降级确定性 hard filter
- producer 单测先于 fallback graph 验收

**Trade-off：删除 `RAG_FALLBACK_ENABLED`**

直接删除会破坏现有用户的环境配置。

缓解：
- 保留 `RAG_FALLBACK_ENABLED` 作为总开关（=false 时所有 level 都跳过，使用 Level 0 的 final top-k 直接走现有回答流程）
- 新增 per-level 开关 `RAG_FALLBACK_LEVEL1_ENABLED` 等，默认 true
- 在 deprecation note 中说明 `RAG_FALLBACK_ENABLED` 在 v2 移除

## 依赖与衔接

- **依赖并收紧 `rag-intent-routing` 边界**：复用 query_plan 字段和 PreciseQueryPlan/ComprehensiveQueryPlan 类型；在 fallback 前完成可信 filter producer 的确定性约束
- **依赖 `rag-terminology-module`**：Level 0 已在结构解析后对实际检索文本做术语扩展并构造 dense/BM25 输入，本 change 不重复做，也不得在 Level 1/2 把 query 恢复为 raw query
- **依赖 `rag-postprocess-evidence`**：confidence gate 输出的 top score、margin、root share、anchor 和 sub-query coverage 信号。terminology 的 `entity_type_coverage` / `term_match_count` 可继续参与 rerank 与 trace，但不解释为实例级 entity coverage，也不用于本 change 的 scope-relax 路由。

本 change 必须在以上三个 change 至少部分上线后才能完整工作。可信 filter producer 是 Level 2 启用的硬前置条件；不得先上线“保留所有 filter”的 fallback，再以后补 producer。其他 fallback 骨架可以保持默认关闭并独立开发验证。

### 决策 11：context_files 与每轮证据生命周期

`context_files` 来自请求中的用户附件/显式文件选择，语义是硬检索域，而不是“额外保留附件 raw 内容”。附件已索引到与知识库相同的检索基础设施，因此每个既有检索分支以组合 filename filter 一次返回该范围内候选：

```text
query + context_files
  -> one filtered candidate retrieval per planned branch
  -> dedupe / rerank / postprocess / final top-k
  -> confidence
  -> fallback router
  -> answer or next fallback level
```

精确管线每轮只有一个检索分支。综合管线仍保留 intent-routing 规划的 clean-query baseline 与 LLM sub-query fan-out；附件只给这些既有分支增加相同 filter，不增加“附件检索”分支。

现有 `retrieve_initial` 在主检索之后调用 `retrieve_context_documents()`，逐文件直取已索引 leaf chunk 并在完整 postprocess 之后追加。该旁路并非原始文件字节，但没有经过相关性评分和 confidence，导致回答上下文与 router 评估的证据集合不同；本 change 删除该旁路。

Level 1/2 的每次重检都是一个新的完整证据生命周期。节点不得只替换 documents 后沿用旧 `rag_trace.confidence_reasons`；必须对新候选重新执行共享 postprocess，基于该轮 final top-k 重新计算 confidence，再回到 router。

环境默认值不阻碍实现：intent classifier 和 fallback 可以继续保持默认关闭，但 graph、typed plan 分支与测试按两者已显式启用的上线前提实现。关闭 `RAG_FALLBACK_ENABLED` 只保留现有兼容行为，不改变初检、postprocess 或回答上下文。

### 决策 12：filter producer 与下游契约边界

当前 `parse_query_plan()` 有两个不可信的 hard-filter producer：一是 `best_score >= DOC_SCOPE_MATCH_FILTER` 自动输出 filter；二是 `preferred_scope_mode` 优先覆盖自动分级，使 classifier 的 `scope_hint="filter"` 可以把仅达到 0.60 的文件匹配提升为 filter。字符串分数只表示标题与文件名的接近程度，不表示用户要求“只在该文件中检索”；现有 classifier prompt 也没有定义 filter/boost/none 的选择规则。

目标边界为：

```text
deterministic planner
  context_files                         -> filter
  explicit closed wording + resolved A -> filter
  resolved exact range form "《A》中"   -> filter
  ordinary document hint               -> boost
  no document preference               -> none

classifier scope_hint
  may advise boost vs none only
  cannot create or remove filter

fallback
  consumes scope_mode only
  filter -> filter
  boost  -> none
  none   -> none
```

因此先收紧 producer，再实现 Level 2。Fallback 不查看匹配分数、不查看 classifier hint，也不追溯 filter 的成因。一旦 planner 输出 filter，下游就把它当成用户硬范围。`PreciseQueryPlan` 不增加 `scope_source`；综合管线已有的 `RetrievalScope.source` 继续服务 trace/provenance，但不得进入 Level 2 行为判断。
