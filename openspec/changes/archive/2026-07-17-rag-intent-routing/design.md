## Context

当前 RAG 管线的入口路由 `plan_rag_turn()` 只做 session 级别的判断（是否有 context_files、是否检测到文档意图关键词），不分析 query 本身的语义结构。query 解析延迟到 `retrieve_documents()` 内部的规则版 QueryPlan（默认关闭），而且只能提取文档名/型号/章节这几类信号，对"综合分析"类查询完全无感。

下游所有阶段的输入都是同一种 `RetrievalRequest`：单个 `query` 字符串 + 可选 `context_files`。没有任何机制告诉检索/rerank/answer "这次查询是精确还是综合"。

融合方案设计文档（`docs/superpowers/specs/2026-05-20-rag-fusion-design.md`）曾提出：
- QueryPlan 识别文档名、页码、章节等结构定位信号
- 支持 filter / boost / global 三种 scope
- 对"沿用/改进/参考基本型方案"类问题，优先召回基本型产品文档（这是综合分析特征）
- 对参数问题提升表格 chunk 权重、对步骤问题提升 list group 权重（这是精确查找特征）

该文档同时预留了面向后续知识图谱的领域实体元数据，但当前上游没有实例级实体产出，当前检索也没有实例级消费契约。该二期构想不再作为本 change 的目标；terminology 产生的术语命中及类别 metadata 是独立、已实现的检索信号，不等同于 semantic entities。

精确和综合两种计划形态在单一 QueryPlan 结构下难以同时承载。

## Goals / Non-Goals

**Goals：**
- 用一次 LLM 调用完成意图分类和对应计划字段生成，承载 7:3 比例下的精确/综合两种产出形态。
- 让下游每个阶段都能根据 intent 调整自己的行为，而无需各自重新解析 query。
- LLM 调用失败时，整个 RAG 管线仍能正常工作（规则降级路径不阻塞）。
- 建立可重复跑的意图分类评测基线（intent accuracy / plan validity / sub-query quality）。

**Non-Goals：**
- 不做 LLM 微调。本 change 只提供可运行的 FAST_MODEL 评测路径，不声称真实模型已经达标；模型选择、few-shot 调整与激活结论由 `rag-intent-routing-activation` 基于真实评测决定。
- 不引入新的长期记忆层。意图解析只用本轮 query + 当前 context_files，不依赖历史会话。
- 不做意图分类的多分类细化（precise/comprehensive 二分即可，analysis_type 作为 comprehensive 内部子字段）。
- 不重写 `plan_rag_turn`。它继续通过 context_files 与既有通用文档检索关键词负责 session 级 FORCED_PRELOAD vs OPTIONAL_TOOL 路由；不得在此分类 precise/comprehensive、构造 QueryPlan 或编排 sub-query。intent 解析作为 RAG graph 内部第一节点独立存在。
- 不从 query 提取 product / equipment / component / parameter / maintenance_action 等 semantic entities，不在 QueryPlan 中预留 `EntityMatch`，也不为后续知识图谱保留隐式契约。
- 不把 terminology 结果写入 QueryPlan。terminology preflight 独立维护 `term_matches`、`normalized_query`、`sparse_expansion` 和 `protected_tokens`，其既有 chunk metadata 与 rerank 消费保持不变。

## Decisions

### 决策 1：意图解析下沉到 RAG graph 内部，而非提到 `plan_rag_turn`

`plan_rag_turn` 当前职责是通过 context_files 与既有通用文档检索关键词判断"本轮是否要走 RAG、context_files 是否需要预加载"。该确定性 session gate 不是 precise/comprehensive intent classifier。把 QueryPlan 或 sub-query 解析放进去会让它跨两层抽象（session 级 + retrieval intent），且 OPTIONAL_TOOL 模式下 Agent 决定调用 search_knowledge_base 时已经丢失了 `plan_rag_turn` 的解析结果。

下沉到 RAG graph 内部后，无论从 FORCED_PRELOAD 还是 OPTIONAL_TOOL 进入 `run_rag_graph()`，第一步都是 `intent_parse`，意图解析对调用方式透明。

### 决策 2：一次 LLM 调用合并意图分类 + 计划字段生成

替代方案是先分类，再按分类做第二次计划生成。合并调用可减少一次模型往返，并让 structured output 直接按 intent 约束对应字段集。

LLM 输出 schema：

```json
{
  "intent": "precise_lookup" | "comprehensive_analysis",
  // precise_lookup 字段：
  "scope_hint": "filter" | "boost" | "none",
  "anchors": ["第三章", "表2"],
  "target_granularity": "paragraph" | "table" | "step_list" | "figure",
  // comprehensive_analysis 字段：
  "analysis_type": "design_reuse" | "comparison" | "procedure_synthesis" | "general",
  "sub_queries": [{"query": "...", "domain": "...", "priority": 1-3}]
}
```

模型按 intent 输出对应的字段集，未使用的字段为空/省略。

`semantic_query` 不再由 LLM 直接生成。它由确定性的 query preparation 根据 raw query、已确认的结构 span 和解析结果构造；terminology normalization 在其后独立执行。

### 决策 3：PreciseQueryPlan 和 ComprehensiveQueryPlan 独立结构

替代方案是单一 QueryPlan 类带 optional 字段。但单一结构下 type checker 无法约束"comprehensive 必须有 sub_queries"，运行时也容易出现"precise 路径误用 sub_queries 字段"的 bug。

```python
@dataclass(frozen=True)
class PreciseQueryPlan:
    raw_query: str
    semantic_query: str
    clean_query: str
    doc_hints: list[str]
    scope_mode: Literal["filter", "boost", "none"]
    matched_files: list[tuple[str, float]]
    heading_hint: str | None
    anchors: list[str]
    model_numbers: list[str]
    intent_type: str | None
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
    clean_query: str
    analysis_type: Literal["design_reuse", "comparison",
                            "procedure_synthesis", "general"]
    sub_queries: list[SubQuery]
    coverage_domains: list[str]
    postprocess_profile: str = "quality_first_v1"
    retrieval_scope: RetrievalScope
```

两者通过 union type `QueryPlan = PreciseQueryPlan | ComprehensiveQueryPlan` 在 RAGState 中表达。

`ComprehensiveQueryPlan.clean_query` 由运行时 query preparation 确定性写入，不属于 LLM structured output。它是 comprehensive baseline branch 的源文本；该 branch 后续仍独立完成 semantic-query preparation 与 terminology preflight，不能把 `clean_query` 直接当作 normalization 结果。

`RetrievalScope` 是运行时确定性结构解析结果，不属于 LLM schema。它携带 `scope_mode`、`matched_files`、`doc_hints`、`anchors`、`heading_hint` 和来源，并由 baseline 与全部生成 sub-query 共享。共享的是 scope 语义而不是无条件硬过滤：普通 `《文档名》` 在 comprehensive 查询中默认解析为 boost，允许每个 branch 继续检索全局语料；只有“仅在/仅限/检索范围限定为”等明确封闭措辞或显式 `context_files` 才解析为 filter。Intent-routing 不根据局部召回动态放宽 filter；放宽属于 `rag-multilevel-fallback` Level 2。

这两个 plan 只表达检索编排，不承载 query semantic entities。现有 terminology preflight 在 graph 的独立状态中提供规范化和 sparse expansion；`entity_types` / `term_match_count` 仍是 terminology 产生的 chunk metadata，不是 QueryPlan 字段。

### 决策 4：兼容性 PreciseQueryPlan 路径

classifier 关闭以及 LLM 调用失败、超时或 schema 解析失败时，都输出 `PreciseQueryPlan`，但其内容必须由同一个兼容适配器按当前 QueryPlan 行为构造：

1. `QUERY_PLAN_ENABLED=false` 时，不运行新的关键词或 scope 规则；使用 raw query 作为 semantic/clean query，scope_mode=`none`，route=`global_hybrid`，其余兼容字段为空。
2. `QUERY_PLAN_ENABLED=true` 时，调用现有 `parse_query_plan()`，将 clean_query、doc_hints、matched_files、scope_mode、heading_hint、anchors、model_numbers、intent_type 和 route 无损映射到 PreciseQueryPlan。
3. 兼容路径永远不产出 ComprehensiveQueryPlan，也不使用综合关键词启发式改变路由。

classifier 关闭不是运行时失败：trace 记录 classifier disabled 和 compatibility source，不记录 `intent_llm_error`，也不标记失败降级。classifier 已启用但 LLM 失败时，trace 记录 `intent_fallback_to_rules=true`、失败原因和已消耗时间。

该设计允许 `intent_parse` 始终作为 graph 入口，同时把默认关闭状态下的 semantic query、filters、route 和检索结果保持在现有兼容边界内。

### 决策 5：结构 span 所有权与 hybrid query composition

`raw_query` 是不可变审计输入。query preparation 必须先确认结构片段是否已被实际消费，再构造检索文本：

1. `clean_query` 是确定性结构清洗结果。文档提示只有成功解析为 `matched_files + scope_mode` 后才可删除；章节、附录等已识别 anchor 只有写入 `anchors` 后才可删除。
2. 未匹配到文件的 `《...》` 文档提示、未被结构解析器消费的文本和其中术语必须保留，不能因为外观像结构提示就丢弃。
3. `semantic_query` 是进入 terminology 前的最终检索基底；它可在 `clean_query` 基础上继续删除已经成功转成 scope 的型号等冗余 token，但不得删除没有对应结构约束的内容。
4. intent LLM 只给出 intent、结构提示和目标粒度，不生成 terminology canonical 值，不负责 query normalization。
5. comprehensive 成功解析文档提示后，消费 span 的同时必须把 scope 保存到 `ComprehensiveQueryPlan.retrieval_scope`；不得只删除文档名而丢弃约束。普通文档提示默认 boost，明确封闭措辞或 context_files 才 filter。

terminology preflight 在结构解析之后执行，输入必须是 `semantic_query`；comprehensive 路径由 `clean_query` 构造的 baseline branch 与每个实际 sub-query 都必须独立执行相同 preflight。其输出按固定职责消费：

```text
semantic_query / sub_query.query
  -> terminology preflight
       -> term_matches + protected_tokens
       -> normalized_query -> dense embedding
       `-> sparse_expansion -> BM25 sparse embedding
  -> Milvus dense+sparse hybrid search -> RRF
```

无术语命中时，`normalized_query` 和 `sparse_expansion` 必须等于本次 preflight 的输入，而不是 `raw_query`。terminology 未加载或失败时，dense 和 BM25 也都使用该输入。当前实现先构造 `query_plan.semantic_query`，随后用基于 raw query 的 terminology 结果覆盖它；该组合缺陷必须在本 change 中修复。

该顺序确保文档名中的领域词在成功限域后只作为 scope 消费，不再以 terminology 形式重复进入 dense/BM25；如果文档名未解析成功，则它仍留在检索文本中并可正常命中 terminology。

Precise 路径进入既有 HyDE/step-back fallback 时，只替换该次检索使用的 `semantic_query`，必须继承初始 `PreciseQueryPlan` 的 matched_files、scope_mode、anchors、heading_hint 等确定性结构约束，并保留原始 raw_query 作为审计输入。扩展文本仍独立执行 terminology preflight；Level 1 query expansion 不得隐式把 filter/boost 改为 global，scope relax 仍只属于 fallback Level 2。

### 决策 6：模型选择优先级

意图分类优先使用配置项 `RAG_INTENT_CLASSIFIER_MODEL` 指定的模型；未配置时默认使用 FAST_MODEL。评测不达标时，按以下顺序尝试更大模型：
- 默认 → FAST_MODEL → GRADE_MODEL → MODEL

具体链待评测后确定（开箱即用目标为 FAST_MODEL 直接达标，不设硬回退逻辑）。

### 决策 7：综合分析只采用 graph 内并行检索

ComprehensiveQueryPlan 在运行时固定构造一个 `branch_id="baseline"`、`branch_kind="baseline"` 的检索分支，其源文本是确定性 `clean_query`；它与受 fanout 上限约束的 LLM sub-query 在同一次 `run_rag_graph()` 调用内并行检索。graph 在 embedding/Milvus 调用前按 priority 数字升序保留 sub-query，同 priority 保持 LLM 原始顺序；默认最多保留 4 个，可由 `RAG_COMPREHENSIVE_MAX_SUB_QUERIES` 调整，但运行时硬上限为 8。截断后的 effective QueryPlan 写回 graph state，使 rerank、merge、reservation 和 confidence 只消费实际执行分支。每个 branch 使用自己的 query 文本执行 terminology preflight，同时继承 plan 的同一 `retrieval_scope`，不得自行放宽 filter。随后由 effective `ComprehensivePostprocessPolicy` 完成 branch rerank、merge 和共享后处理。baseline 不是 LLM 输出、不是 coverage domain，也不写回 `sub_queries`。`requested_sub_query_count` 记录 LLM 请求项总数，`sub_query_count` 只统计实际执行的生成项，真实执行量记为 `retrieval_branch_count = sub_query_count + 1`。Chat Agent 只接收 graph 的最终检索结果，不读取 QueryPlan、不逐个调用 branch，也不参与检索决策。现有 `search_knowledge_base(query)` 单次工具接口和每轮一次调用限制保持不变。

本 change 不提供 `multi_turn` / `parallel` 模式开关，也不设计根据中间检索结果动态增加、删除或调整 sub-query 的循环。结果驱动的 multi-turn 检索仅作为候选 enhancement 记录；若未来计划上线，必须通过独立 OpenSpec change 明确状态、预算和停止条件，并以 A/B 实验验证质量收益相对于延迟与成本的影响。

对已经生成但检索效果不佳的 sub-query 进行 rewrite、replace 或 decompose，属于 `rag-multilevel-fallback` 的 Level 1 策略。本 change 只负责初始意图解析、sub-query 生成、并行检索和结果合并。

### 决策 8：综合并行结果采用 branch-local relevance + global shared postprocess

不能让每个 sub-query 完整执行现有后处理后再 union。这样会让 branch top-k 提前截断、重复执行 auto_merge/step-chain、把不可比的跨 query 原始分数混合，并使 confidence 只能描述局部分支。

v1 采用以下固定边界：

```text
baseline(clean_query) + 每个 LLM sub-query 并行：
  query preparation
  -> dense + BM25 hybrid retrieval / Milvus RRF
  -> branch-local rerank（相对于该 branch query，使用该 branch term_matches）
  -> branch candidate pool + branch diagnostics

merge_sub_query_results：
  priority-weighted RRF over local ranks
  -> chunk_id 去重并合并 branch provenance
  -> auto_merge（全局一次）
  -> step_chain_check（全局一次）
  -> structure_rerank + branch diversity（全局一次）
  -> branch-aware top_k（全局一次）
  -> comprehensive confidence gate（全局一次）
```

跨 query 不平均 dense、BM25 或 CrossEncoder 原始 score；这些 score 只在各自 branch 内产生 local rank。merge 使用 local rank 的 priority-weighted RRF。baseline 使用固定中性 effective priority `2`，LLM sub-query 使用其 schema priority。重复 chunk 只保留一份，并携带 `matched_branch_ids`、`per_branch_local_rank`、`per_branch_rerank_score`、`best_local_rank`、`multi_query_rrf_score`、`baseline_matched` 和仅对生成分支计数的 `coverage_count`。leaf 被 auto_merge 替换为 parent 时，上述 provenance 必须求并集并保留可追溯的最佳 local rank；parent 的 `multi_query_rrf_score` 继承 contributing leaves 的最大值，以保留已有排名信号而不因 parent 聚合重复累加。

branch diagnostics 记录 baseline 与每个 sub-query 的 branch_kind、candidate_count、top score/rank、耗时、错误以及共享 retrieval_scope 的 mode/source/matched_files，顶层 trace 同样记录该 scope，供 API/history、评测和后续 fallback Level 1 验证 boost/filter 实际语义并定位失败的生成分支；baseline 失败只记录诊断，不作为 Level 1 rewrite 目标。branch diagnostics 不是独立 confidence gate。最终 confidence 只在共享 top-k 后执行，并可消费生成 sub-query representation 与 `baseline_matched` 信号。

最终选择采用静态 branch reservation，不建立证据账本，也不触发 multi-turn。reservation 只作用于成功的 LLM sub-query：当 `top_k >= successful_generated_branch_count` 时，每个成功生成分支至少保留一个候选，剩余位置按全局排序填充；当成功生成分支数超过 top_k 时，按 SubQuery.priority、稳定 branch id 和 global rank 决定保留顺序。baseline 不占 reservation 席位，只能凭合并后的 global rank 进入剩余位置，因此不会稀释已规划的 coverage domain。

### 决策 9：后处理使用版本化策略 profile，而非散落开关

LLM 不选择 merge/postprocess 算法。运行时通过具名 profile 解析一个完整、可验证的策略组合：

```python
@dataclass(frozen=True)
class ComprehensivePostprocessPolicy:
    profile_id: str
    branch_rerank: BranchRerankStrategy
    cross_query_merge: CrossQueryMergeStrategy
    final_selection: FinalSelectionStrategy
    budget_allocation: BudgetAllocationStrategy
    shared_postprocess_version: str
```

策略通过 protocol/registry 组合，graph 只依赖 policy 接口，不按 profile_id 写 if/else。v1 只注册生产 profile：

```text
quality_first_v1
  branch_rerank       = local_cross_encoder_with_term_fusion
  cross_query_merge   = priority_weighted_rrf
  final_selection     = branch_reservation_then_global_rank
  budget_allocation   = global_shared_priority_budget
  shared_postprocess  = shared-postprocess-v1
```

`RAG_COMPREHENSIVE_POSTPROCESS_PROFILE` 默认 `quality_first_v1`。未知 profile 必须降级到该默认值并记录结构化配置 warning 与 effective profile；不得部分接受一个非法组合。未来增加便宜 profile 时，必须以新的版本化 registry entry 整体加入并提供组合契约测试，避免独立环境开关形成未经验证的笛卡尔积。

`RERANK_CANDIDATE_POOL_SIZE` 在 comprehensive 路径是 baseline 与全部生成分支共享的全局 rerank 输出候选预算，不按 branch 复制，并复用 precise 的 effective pool 规则：未配置/`<=0` 回退到 `top_k*4`，过小的正值提升到 final `top_k`，最后受实际候选总数限制。CrossEncoder pair budget 独立解析：当前 device tier 的 `RERANK_INPUT_K_CPU/GPU` 大于 0 时作为全局 pair cap，否则回退到全局输出候选预算。预算先给每个可执行 branch 最小配额，剩余按 effective priority 分配；baseline 的 effective priority 固定为 `2`。预算不足覆盖所有分支时，未获 CrossEncoder 配额但拥有 output 配额的分支在该配额内保留 Milvus local rank，并在 trace 标记 `branch_rerank_budget_exhausted=true`；pair 配额小于 output 配额时，CrossEncoder local rank 在前，未配对尾部按 Milvus local rank 补足 output 配额。output 配额为 0 的分支不向 merge 传入候选。成功、部分 pair、无 pair、rerank 异常和 no-CrossEncoder 消融路径都必须执行相同 output quota，使实际 merge pool 与 trace used budget 一致。

### 决策 10：综合后处理成本必须评测后才能上线

`quality_first_v1` 明确是质量优先基线，不假定其成本可接受。本 change 实现可重复的评测 harness、指标与 source-binding 契约；真实 FAST_MODEL / release Milvus 的上线评测由后继 `rag-intent-routing-activation` change 执行。上线评测必须至少记录：LLM requested/executed/truncated sub-query count、包含 baseline 的 retrieval branch count、baseline 独立命中/最终入选率、dense/sparse embedding 调用数、hybrid search 调用数、rerank pair 总量、各分支与合并候选数、merge/postprocess 耗时、端到端 P50/P95、CPU/GPU 峰值与错误/降级率，并绑定质量指标（生成分支代表率、引用有效性、回答质量）。错误/降级率同时消费顶层 stage_errors、branch_errors 与 branch diagnostics 的 error，避免保留候选的 branch-local rerank 降级被误报为成功。paired run 使用 version 2 source fingerprint：对排序后的固定证据文件以及全部 `backend/rag/**/*.py`、`backend/infra/**/*.py`、`backend/shared/**/*.py` 求哈希，确保 trace identity、terminology preflight、embedding/vector retrieval 等传递依赖变化都会使对照失配，而不是只绑定 graph 入口文件。

评测必须包含至少一个消融对照：保留相同 parallel retrieval 和 weighted-RRF merge，但关闭 branch CrossEncoder，只使用 Milvus local rank。该对照可作为 eval-only profile，不得在没有独立质量证据时成为生产默认。默认开启 intent classifier/comprehensive 路径前，必须由 `rag-intent-routing-activation` 形成质量增益相对于延迟和资源成本的评测结论；阈值在真实基线运行后确定，不在本设计中伪造固定数值。

### 决策 11：评测集落地形态

`tests/eval/data/intent_routing/` 下放：
- `precise_lookup.jsonl`（70 条，覆盖结构限域与目标粒度组合）
- `comprehensive_analysis.jsonl`（30 条，覆盖各 analysis_type）
- 每条样本字段：`{query, expected_intent, expected_sub_queries?, expected_scope?, expected_granularity?, notes}`

评测脚本 `tests/eval/rag/test_intent_classifier_eval.py` 用 pytest 标记 `@pytest.mark.eval`，CI 不默认跑需要真实模型的部分；真实模型与发布索引运行由 `rag-intent-routing-activation` 在发版 gate 执行。指标输出到 `eval/intent/{date}_{model}.json`。

阈值目标（待初评后根据实际基线修正）：
- Intent Accuracy（目标 > 正面率基线）
- Plan Validity（schema、字段集与 scope/target_granularity 约束）
- Sub-query Quality（人工 1-5 分均值）

具体数值在标注完成后根据模型初评结果设定。不达标时，升级模型而非微调。

### 决策 12：以 validation-only 配置验证 anchor 工作流，不改变结构清洗规则

成功解析的 anchor 已从自由文本转换为结构化约束，因此继续按决策 5 从 semantic query 移除。不能仅依据 `HEADING_LEXICAL_ENABLED` 的状态推断 anchor 是否在整条链路被消费：heading lexical 直接以 anchor 重排已有候选，confidence anchor gate 用它判断结果匹配，现有 fallback 又可能根据 `anchor_mismatch` 发起补偿检索。反过来，任何单个开关启用也不能证明整条能力完整。

本 change 增加 `.env.rag-intent-routing-workflow.example`，仅供受控工作流验证时成组开启：

```text
RAG_INTENT_CLASSIFIER_ENABLED=true
QUERY_PLAN_ENABLED=true
HEADING_LEXICAL_ENABLED=true
CONFIDENCE_GATE_ENABLED=true
ENABLE_ANCHOR_GATE=true
RAG_FALLBACK_ENABLED=true
```

该文件不改变运行时默认值，不是生产推荐配置。只有在真实 FAST_MODEL / release Milvus 上完成 paired A/B、成本评测及 fallback 行为验证后，才可通过 `rag-intent-routing-activation` 讨论升级。多个独立开关缺少统一 capability configuration 约束是根因，但统一 profile、启动时约束或隐式联动均不在本 change 重新设计；由 `docs/known-issues/anchor-capability-configuration.md` 持续治理。

验证期间还必须区分两个已确认问题面：

- extraction mismatch：query preparation、confidence 与 chunk heading normalizer 支持的 anchor 类型和规范化规则并不一致，且 LLM additional anchors 可引入前两者未共享的 surface form。
- fallback contract gap：当前 precise confidence 会从 raw query 重提取 anchor，rewrite 输出可能把已消费 anchor 写回 semantic query；未来 Level 2 放宽 scope 后尚无不变量保证仍有 anchor 消费者；comprehensive shared postprocess 虽可产出 fallback 信号，但 graph 尚未接入 precise 的 grade/rewrite fallback 子图。

这两类发现不通过“把 anchor 留在 semantic query”绕过，而作为统一 capability/anchor contract 的退出条件记录。

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
- 记录 `intent_confidence` 供评测与灰度观测；v1 不在缺少真实基线时伪造阈值或改写模型 intent，后续若引入低置信度保守路由必须通过独立 change 和评测确定阈值

**风险 3：综合分析的 sub_query 质量取决于 LLM**

LLM 拆解 sub_queries 可能不合理（重复、遗漏关键维度、子查询太宽泛）。

缓解：
- few-shot 示例覆盖典型 analysis_type
- sub_query 质量评测分（人工评判）作为硬指标
- 本 change 不做结果驱动的动态补救；失败或低质量 sub-query 在 trace 中可观测，后续由 `rag-multilevel-fallback` Level 1 负责调整
- multi-turn 作为候选 enhancement 保留，但只有独立设计和 A/B 证据才能支持上线决策

**风险 4：综合并行后处理放大成本**

baseline 与每个 sub-query 都需要 dense/BM25 embedding、Milvus hybrid search 和 query-local relevance 计算；baseline 因此固定增加一个 retrieval branch，若错误地为每个分支复制完整 rerank pool，成本还会随 sub-query 数近似线性放大并可能产生 GPU 排队。

缓解：
- rerank output candidate budget 与 CrossEncoder pair budget 分开计算，但都跨分支共享
- 只对候选的来源 sub-query 做 relevance 计算，不做所有 candidate × all sub-query 笛卡尔积
- branch-local 失败保留 Milvus rank，不因 rerank 配额耗尽丢失候选
- 上线 gate 同时比较 `quality_first_v1` 与 no-CrossEncoder 消融结果
- trace 必须可按 sub-query_count 分桶观察延迟和资源成本
- trace 与评测必须同时按 retrieval_branch_count 统计，不能把 baseline 成本隐藏在 sub_query_count 之外

**风险 5：结构清洗与术语扩展重复或丢词**

结构解析和 terminology 若都直接消费 raw query，会让已转成 scope 的文档名再次进入 dense/BM25；若结构解析仅按外观删除，又会在文件匹配失败时丢失重要词。

缓解：
- query preparation 记录并只删除已成功消费的结构 span
- terminology 始终消费结构处理后的 semantic query，不得覆盖回 raw query
- 组合测试同时断言 scope、dense input、BM25 input 和 term_matches，而不是分别测试两个模块

**风险 6：意图分类调用成本**

每次 RAG 都多调一次 LLM（intent classifier）。按 FAST_MODEL 估算单次 ~200-400ms + token 成本。

缓解：
- 配置项 `RAG_INTENT_CLASSIFIER_ENABLED` 允许关闭；关闭时走兼容性 PreciseQueryPlan 路径，不调用 LLM，也不启用新的规则行为
- 后续优化方向：对精确查找可考虑 short-ttl query 缓存（收益待验证，v1 不实现）

**Trade-off：意图二分 vs 多分类**

选择二分（精确/综合）而非细分（factoid/data_query/procedure/comparison/...）。细分能让下游做更精细的路由，但二分对 LLM 要求低、评测集容易构造、下游分支简单。细分留作未来扩展（通过 `analysis_type` 子字段表达）。

**Trade-off：意图解析放在 RAG graph 入口 vs `plan_rag_turn`**

放在 RAG graph 入口让 OPTIONAL_TOOL 的 search_knowledge_base 工具调用也能受益，但代价是 FORCED_PRELOAD 和 OPTIONAL_TOOL 各走一遍意图解析（无缓存复用）。考虑到 OPTIONAL_TOOL 占比超过 50%，下沉到 graph 内部的收益更大。

## 依赖与衔接

- **与 `rag-terminology-module` 顺序衔接**：intent/结构解析先确定 semantic query，terminology preflight 再提供术语规范化、sparse expansion 和术语 metadata；intent classifier 不读取或输出 entities，QueryPlan 不拥有 terminology 字段。当前 `term_match_count` 与 `entity_types` 的可选 rerank fusion 行为保持不变。
- **被 `rag-multilevel-fallback` 依赖**：fallback 的 Level 1 rewrite router 需要 ComprehensiveQueryPlan 作为输入；Level 2 scope relax 需要读取 PreciseQueryPlan.scope_mode 或 ComprehensiveQueryPlan.retrieval_scope.scope_mode。intent-routing 内部不执行该放宽。
- **修改 `rag-postprocess-pipeline`**：precise 保持 shared-postprocess-v1；comprehensive 以 clean-query baseline + LLM sub-query 构成 retrieval branches，在 branch-local rerank 后插入 multi-query merge，再复用一次 auto-merge / step-chain / structure-rerank / top-k / confidence，并增加全局预算与 branch provenance 契约。
