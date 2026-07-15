## Why

当前 RAG 链路对所有查询走同一条管线（global hybrid → rerank → answer），但实际查询存在两类截然不同的检索需求：

- **精确查找（~70%）**：用户指向具体文档、章节、表格、步骤或其他结构位置。答案聚焦在 1-2 个特定 chunk，对精度敏感。
- **综合分析（~30%）**：用户要求跨文档对比、归纳或多维分析。答案需要多源证据合并，对覆盖度敏感。

当前 QueryPlan 是基于正则和文件名匹配的规则引擎，默认关闭（`QUERY_PLAN_ENABLED=false`），只能在精确查找场景中"勉强可用"，对综合分析帮助为零。下游所有阶段（检索 scope、rerank 维度、回答风格、引用粒度）也无法区分两类查询。

## What Changes

引入 LLM 驱动的意图分类作为 RAG 管线的统一入口，并把 QueryPlan 拆成两种结构以适配两条管线：

1. **Intent Parser**：一次 LLM 调用输出意图分类及对应的计划提示（精确查找的 scope_hint / anchors / target_granularity，综合分析的 sub_queries）；不提取或生成 semantic entities，不负责 terminology normalization，也不选择运行时后处理算法。
2. **PreciseQueryPlan vs ComprehensiveQueryPlan**：两种数据结构对应两条管线；PreciseQueryPlan 保留现有 QueryPlan 的检索字段，支持无损兼容映射；ComprehensiveQueryPlan 额外保存确定性生成的 `clean_query` 和 typed `retrieval_scope`。后者把已解析的 scope 语义共享给 baseline 与全部 sub-query：普通文档提示默认 boost，只有明确封闭措辞或 `context_files` 才 filter。两种 plan 都不携带 `EntityMatch` 或 `entities`。
3. **确定性 Query Preparation**：先解析并确认结构 span 的消费归属，再生成 clean/semantic query；只有成功转成 scope 或 anchor 的 span 才可从检索文本移除。terminology 随后基于该检索文本生成 dense normalization 与 BM25 expansion，禁止再用 raw query 覆盖清洗结果。
4. **Pipeline 分支**：`run_rag_graph` 的入口节点从 `retrieve_initial` 改为 `intent_parse`，按 intent 路由到 precise 子图或 comprehensive 子图；comprehensive 子图把 `clean_query` baseline 与全部 LLM sub-query 一起组成固定 fan-out，在单次 graph 调用内并行检索，先做 branch-local rerank，再合并候选并只执行一次共享结构后处理。baseline 是召回安全网，不新增 coverage domain，也不占用生成分支的最终保留席位。
5. **兼容降级**：classifier 关闭或 LLM 调用失败时，按现有 `QUERY_PLAN_ENABLED` 语义构造兼容性 PreciseQueryPlan；关闭 QueryPlan 时保持 raw query + global route，启用时无损映射现有 `parse_query_plan()` 结果。Query preparation 修复只改变已启用 QueryPlan 与 terminology 组合时 raw query 覆盖 semantic query 的缺陷。
6. **意图分类评测集**：人工标注 100-200 条样本，建立 intent accuracy / plan validity / sub-query quality 指标，无需微调，目标使用现有 FAST_MODEL 直接达标。
7. **可组合后处理策略与成本 gate**：综合路径通过一个具名、版本化的 postprocess profile 组合 branch rerank、跨 query fusion、最终选择和共享预算策略；v1 采用质量优先组合。上线前必须评测随 sub-query 数增长的 embedding、hybrid search、rerank pair、延迟和资源成本，并与更便宜的消融方案比较。
8. **Anchor 工作流验证配置**：提供独立 validation-only env 示例，成组开启 intent routing / QueryPlan、heading lexical、confidence anchor gate 与现有 fallback；不修改默认值、不把 anchor 留在 semantic query，也不把该组合称为生产推荐。多开关缺少统一 capability 约束、各阶段 extraction mismatch 与 fallback contract gap 进入已知问题治理。

## Capabilities

### New Capabilities
- `rag-intent-routing`: 意图分类入口、两种 QueryPlan 结构、管线分支与降级机制

### Modified Capabilities
- `rag-terminology-module`：query preflight 改为消费结构解析后的检索文本；无术语命中时保持该检索文本，不能回退成 raw query；输出继续分别进入 dense 与 BM25。
- `rag-postprocess-pipeline`：将 query 侧 metadata fusion 信号限定为 terminology preflight 的术语命中，删除未来 intent entities 作为信号源的规定；保留既有 `entity_types` / `term_match_count` 运行时行为。

## Impact

**代码影响：**
- `backend/rag/query_plan.py`：拆分 QueryPlan 为 PreciseQueryPlan / ComprehensiveQueryPlan 两种结构；新增 SubQuery、RetrievalScope 与运行时 ComprehensiveRetrievalBranch 数据类，不新增 EntityMatch；ComprehensiveQueryPlan 保存确定性 `clean_query` 和共享 retrieval_scope，结构解析输出可验证的 consumed spans，未成功解析的文档提示不得从检索文本删除。
- `backend/rag/pipeline.py`：在 `build_rag_graph` 入口前增加 `intent_parse` 节点；在结构解析后执行 query preparation；新增 graph 内并行 fan-out 的 `retrieve_comprehensive` 和确定性合并的 `merge_sub_query_results` 节点。
- `backend/rag/utils.py`：`build_query_plan` 改为消费 intent 解析结果；dense 使用 terminology-normalized semantic query，BM25 使用基于同一 semantic query 的 sparse expansion，禁止 terminology preflight 用 raw query 覆盖 semantic query。
- `backend/rag/comprehensive_postprocess.py`（新文件）：定义 typed strategy protocols、`ComprehensivePostprocessPolicy`、具名 profile registry、预算分配、priority-weighted RRF merge 和 branch-aware final selection；graph 节点不得散落 profile-specific 分支。
- `backend/chat/rag_execution.py`：`plan_rag_turn` 保留既有 session 级 RAG 触发规则（context_files 与通用文档检索关键词，用于 FORCED_PRELOAD vs OPTIONAL_TOOL），但不得执行 precise/comprehensive 分类、QueryPlan 构造或 sub-query 编排；这些 intent-routing 动作全部下沉到 RAG graph。
- `backend/rag/runtime_config.py`：新增 intent classifier 的模型、超时、启用配置、`RAG_COMPREHENSIVE_POSTPROCESS_PROFILE` 和 graph fanout 安全上限 `RAG_COMPREHENSIVE_MAX_SUB_QUERIES`；本 change 不增加 multi-turn 模式配置，也不为 profile 组件增加独立自由组合开关。
- `.env.rag-intent-routing-workflow.example`：工作流验证专用配置，显式成组开启 anchor 相关消费者；它不是默认配置或生产推荐，不能替代 A/B、成本与 fallback 行为验证。
- `tests/unit/backend/rag/` 与 `tests/eval/rag/`：分别验证 LLM 调用、规则降级、策略组合契约、并行后处理和意图/成本评测指标。

**接口影响：**
- 现有 `rag_trace` 增加字段：`intent`, `intent_confidence`, `query_plan_type`, `intent_llm_model`, `intent_llm_ms`, `intent_fallback_to_rules`；comprehensive 路径区分 LLM `sub_query_count` 与包含 baseline 的 `retrieval_branch_count`。
- `/chat` 响应体 schema 无破坏性变更（trace 是扩展字段）。

**依赖：**
- `rag-terminology-module` 保持独立 preflight：其 `term_matches`、`normalized_query`、`sparse_expansion`、`protected_tokens` 以及 chunk 侧 `entity_types` / `term_match_count` 不进入 QueryPlan，也不由 intent classifier 生成。preflight 在结构 span 归属确定后执行，并以 semantic query（comprehensive 时为各 sub-query）作为输入；dense/BM25 与可选 rerank 继续消费这些信号。
- 评测集落地依赖标注资源（10-20 小时人工标注）。

**明确排除：**
- Chat Agent 多次调用知识库工具、根据中间结果动态调整后续 sub-query 的 multi-turn 检索不在本 change 内。它作为候选 enhancement 单独记录，未来如计划上线，必须通过独立 change 设计并进行 A/B 验证。
- 已生成 sub-query 的 rewrite / replace / decompose 属于 `rag-multilevel-fallback` 的 Level 1 策略，不由 intent-routing 实现。
- 多个独立 anchor 相关开关的统一 capability configuration、query/confidence/chunk 的统一 anchor grammar/normalization，以及完整 comprehensive/Level 2 fallback anchor contract 不在本 change 重构；现有缺口由 `docs/known-issues/anchor-capability-configuration.md` 跟踪。
- 面向知识图谱预留的 product / equipment / component / action / parameter 等通用实体元数据，以及从 query 抽取对应 semantic entities 的能力，不在当前目标或未来愿景内。
