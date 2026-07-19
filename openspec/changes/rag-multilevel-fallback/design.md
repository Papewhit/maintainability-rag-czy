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
- 每个 fallback level 有明确的触发信号与策略集；Level 1/2 有独立预算，Level 3 是总预算下的确定性终止步骤
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
    综合: 基于 final top-k 标注覆盖状态；0 < X < Y 时让现有回答模型只生成有来源证据维度的独立部分解答，不得跨未覆盖维度形成总体结论
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

新实现，针对每个被选中的失败分支使用一次合并的 LLM 调用同时做策略选择和重写。输入中的失败 branch 必须是 LLM sub-query；intent-routing 固定构造的 clean-query baseline 只提供 diagnostics，不得成为 rewrite/replace/decompose 目标。多个生成分支同时失败时，按 `priority` 升序、再按稳定 `branch_id` 排序，单轮最多选择 `RAG_FALLBACK_COMPREHENSIVE_REWRITE_WINDOW` 个（默认 2）。发生综合重试时 baseline 始终从 `ComprehensiveQueryPlan.clean_query` 原样重建：

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

窗口允许一次处理多个失败分支，因此综合 trace 使用列表契约：`level1_comprehensive_strategy: list[str]`、`level1_new_sub_queries: list[dict]`、`level1_sub_query_replaced: list[str]`；三个字段按选中分支的稳定顺序记录。

为满足通用 Level 1 trace 契约，综合分支还固定记录 `level1_strategy="comprehensive"`，并将 `level1_rewritten_query` 定义为 `list[str]`：按上述稳定分支顺序展平每个被接受的新 query。精确分支继续把 `level1_rewritten_query` 记录为单个字符串；消费者 MUST 根据 `level1_strategy` 解释该字段类型。

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

# 然后重新走一次 retrieve_candidate_pool；candidate_k 目标放大 1.5x，
# 并以既有 RAG_FALLBACK_EXPANDED_CANDIDATE_K 作为扩大量上限；
# 当该值低于上一轮 candidate_k 时保持上一轮值，不允许 Level 2 缩小候选池
```

trace 记录 `level2_relaxations`（list，描述哪些约束被放宽）。

任何 `filter` 都不得移除组合 filename filter，也不得追加全库 reserve。Level 2 将 `candidate_k` 目标放大 1.5x，并以既有 `RAG_FALLBACK_EXPANDED_CANDIDATE_K` 限制扩大量；有效值为上一轮已完成值与受限增长值中的较大者，因此配置上限低于上一轮值时保持而不缩小候选池。本轮 `same_root_cap` 临时增加 1；这些参数变化不写回全局配置。重检结果继续完整通过共享 postprocess/confidence。`boost → none` 必须原子更新 `scope_mode=none`、`matched_files=()` 与 `route=global_hybrid`。Fallback 不检查 filter 的来源，也不为 `PreciseQueryPlan` 新增 `scope_source`。

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
        # 综合管线: 仅从本轮 final top-k 判断覆盖与选择证据
        covered = [...]  # 成功的 sub_q
        missing = [...]  # 失败的 sub_q
        return f"已完成 {len(covered)}/{total} 个分析维度,...,未覆盖部分: {missing}"
```

`generate_level3_answer()` 本身是模板化输出，不调用 LLM。综合 coverage、维度证据和 baseline evidence MUST 只来自本轮 final top-k 实际表示的 branch；被 final selection 淘汰的 raw branch candidate 不得重新进入 Level 3。baseline-only 时显示 `0/Y`，并输出一条明确标注为“一般背景证据、不得计入分析覆盖率”的 baseline 摘录。若所有生成维度均由 final top-k 表示但整体 confidence 仍不足，输出 `Y/Y`，明确说明“全部维度已有相关证据，但整体置信度不足”，展示证据摘录并建议核对来源或补充更具判别力的查询条件，不得建议补充“未覆盖维度”。

当只有部分生成 sub-query 由 final top-k 表示（`0 < X < Y`）时，确定性模板列出 X/Y、每个已覆盖维度的证据摘录及既有 filename/page 来源、未覆盖维度，并约束现有回答模型：只基于这些摘录为已覆盖维度分别生成部分解答；明确整体证据不足；保留来源；不得回答未覆盖维度，也不得在缺少必要维度时做跨维度比较、汇总或总体建议。该模型调用属于现有回答交付，不是 `generate_level3_answer()` 新增的 LLM 调用。

`Y/Y` 但整体 confidence 不足时继续保持 evidence-only：模板只列带来源的证据摘录和低置信提示，不授权合成回答。baseline-only 与完全无证据也不授权部分解答。forced-preload 仍通过系统消息交付模板约束，optional-tool 仍通过 tool response 交付同一约束，再由现有 agent LLM 完成回答；两条路径不得维护第二套文案。

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

当 Level 2 前后均为 `scope_mode=none` 时，声明为：“未在当前知识库中找到精确匹配，以下是扩大候选池及放宽结构限制后得到的相关参考；本轮没有改变文档检索范围。”不得套用“优先文件”或“范围外”措辞。

注入位置：forced-preload 在原 RAG 上下文 prompt 之后追加；optional-tool 把同一声明附在 tool response 的检索结果之前。

### 决策 9：预算分配与超时

```
RAG_FALLBACK_TOTAL_BUDGET_MS    = 8000   # 整体上限
RAG_FALLBACK_LEVEL1_BUDGET_MS   = 3000
RAG_FALLBACK_LEVEL2_BUDGET_MS   = 2500

进入 Level 1/2 前检查: remaining_budget = total_budget - elapsed_since_turn_start
  if remaining_budget < level_N_budget:
      跳过本 level, 直接进入 Level 3

Level 3 不设独立预算配置或入口阈值；它是不调用检索、模板生成不调用 LLM 的确定性终止步骤，只受整体预算约束。
```

复用 `_get_fallback_executor` 和 `_await_with_deadline` 基础设施。

本 change 的受支持配置域只包含正整数毫秒值。零值和负值属于 unsupported configuration；本 change 不为其增加钳制、拒绝、禁用或兼容解释。

### 决策 10：意图与 plan_type 区分

fallback router 接收 query_plan 实例，按 isinstance 路由：

```python
match query_plan:
    case PreciseQueryPlan():
        return _precise_fallback_path(decision, query_plan)
    case ComprehensiveQueryPlan():
        return _comprehensive_fallback_path(decision, query_plan)
```

Level 3 输出也按 plan_type 不同：精确管线给"未找到"；综合管线报告 final top-k 所证明的覆盖状态，且仅在 `0 < X < Y` 时授权现有回答模型为已覆盖维度生成受来源约束的独立部分解答。

## Risks / Trade-offs

**风险 1：多 level fallback 累计延迟**

最坏的有界重试部分：Level 1 (3s) → Level 2 (2.5s) = 5.5s 额外延迟；Level 3 是总预算下的确定性模板终止步骤。加上原始检索仍可能接近整体预算边界。

缓解：
- 整体预算 8s 硬性限制
- Level 1/2 入口检查各自预算，所有 fallback 共享整体预算
- 以 P95 5-7s 作为待真实评测验证的目标范围；tasks 10.3-10.5 完成前不声称已有实测结论

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
- candidate_k 目标放大且受 max_candidate_k 扩大量上限保护；上限不得反向缩小上一轮候选池
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

新一轮只有在 retrieval、postprocess、final top-k 和 confidence 全部完成后才可原子提交 plan 与 evidence state。若 complete round 超时或失败，返回 router 的 query plan、final documents 和 branch identities 全部回退到上一轮已完成快照；尤其 comprehensive decompose 改变 sub-query 索引后，不得用新 plan 解释旧 final documents。

环境默认值不阻碍实现：intent classifier 和 fallback 可以继续保持默认关闭，但 graph、typed plan 分支与测试按两者已显式启用的上线前提实现。关闭 `RAG_FALLBACK_ENABLED` 只保留现有兼容行为，不改变初检、postprocess 或回答上下文。

### 决策 12：filter producer 与下游契约边界

当前 `parse_query_plan()` 有两个不可信的 hard-filter producer：一是 `best_score >= DOC_SCOPE_MATCH_FILTER` 自动输出 filter；二是 `preferred_scope_mode` 优先覆盖自动分级，使 classifier 的 `scope_hint="filter"` 可以把仅达到 0.60 的文件匹配提升为 filter。字符串分数只表示标题与文件名的接近程度，不表示用户要求“只在该文件中检索”；现有 classifier prompt 也没有定义 filter/boost/none 的选择规则。

目标边界为：

```text
deterministic planner
  context_files                         -> filter
  explicit closed wording + uniquely resolved A -> filter
  uniquely resolved exact range form "《A》中"   -> filter
  one hard hint resolving multiple files        -> boost
  lexical compounds after title (中心/中文/中英文/中外/中长期/中短期/中间/中部) -> boost
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

唯一解析按每个 hard-scope 文档提示单独判断：一个提示只有一个达到 routable threshold 的文件时才贡献 hard filter；一个提示命中多个文件时，该提示降为普通 boost。多个彼此独立且各自唯一解析的 hard-scope 提示可以共同形成组合 filter。`《A》中说明步骤` 的 `中` 是范围标记；`《A》中心思想`、`《A》中文翻译`、`《A》中英文术语`、`《A》中外方案`、`《A》中长期计划`、`《A》中短期计划`、`《A》中间章节`、`《A》中部结构` 中的 `中` 属于后续词组，不是范围标记。
