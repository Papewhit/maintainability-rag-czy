## 1. Milestone M1：数据结构与降级路径骨架

- [x] 1.1 定义 `SubQuery`、`RetrievalScope`、`ComprehensiveRetrievalBranch`、`PreciseQueryPlan`、`ComprehensiveQueryPlan` 数据类（`backend/rag/query_plan.py`）；两种新 plan 不包含 `EntityMatch` / `entities`，PreciseQueryPlan 必须保留现有 QueryPlan 的检索字段，ComprehensiveQueryPlan 携带确定性 `clean_query`、共享 `retrieval_scope` 与运行时解析的 `postprocess_profile`，现有 QueryPlan 在迁移期间继续受支持
- [x] 1.2 实现兼容适配器：`QUERY_PLAN_ENABLED=false` 时构造 raw query + global route 的 PreciseQueryPlan，启用时无损映射现有 `parse_query_plan()` 结果；兼容路径永远不输出 ComprehensiveQueryPlan
- [x] 1.3 新增 `RAGState` 字段 `intent_result: IntentParseResult | None`、`query_plan_type: Literal["precise", "comprehensive"]`；删除现有不可达的 `intent_result.entities` / semantic `query_entities` 兼容读取，terminology term_matches 继续走独立 preflight 状态
- [x] 1.4 单元测试覆盖：两种 `QUERY_PLAN_ENABLED` 状态的字段映射、关闭 classifier 时不启用新规则、兼容路径不产生 ComprehensiveQueryPlan、两种 plan 均拒绝 entities 字段

**验收**：所有数据结构编译通过；兼容路径能产出合法 PreciseQueryPlan；关闭 classifier 不记录失败，classifier 已启用但 LLM 失败时 `intent_fallback_to_rules=true`。

## 2. Milestone M2：LLM 意图解析器接入

- [x] 2.1 实现 `IntentClassifier` 类（新文件 `backend/rag/intent.py`）：封装 LLM 调用、structured output schema、超时控制
- [x] 2.2 设计 prompt 模板（system + 3-5 个 few-shot 示例覆盖两种意图）
- [x] 2.3 接入 langchain `with_structured_output`，定义 Pydantic schema 约束 LLM 输出；精确路径 schema 不允许 LLM 输出 terminology canonical 值或直接生成 semantic_query，综合路径 schema 不允许 LLM 选择 postprocess profile；semantic_query 和 profile 分别由确定性 query preparation / runtime policy resolver 构造
- [x] 2.4 添加 `RAG_INTENT_CLASSIFIER_ENABLED`（默认 false）、`RAG_INTENT_CLASSIFIER_MODEL`、`RAG_INTENT_CLASSIFIER_TIMEOUT_SECONDS` 配置（`backend/rag/runtime_config.py`）
- [x] 2.5 LLM 调用失败/超时/解析错误时自动降级到 M1 的规则路径，trace 记录 `intent_llm_error` 和 `intent_llm_ms`
- [x] 2.6 集成测试：mock LLM 返回各种 schema 的 JSON，验证产出的 QueryPlan 结构正确；LLM 返回额外 entities 字段时不得将其写入 QueryPlan 或 terminology 状态

**验收**：`RAG_INTENT_CLASSIFIER_ENABLED=true` 时全链路能产出 PreciseQueryPlan 或 ComprehensiveQueryPlan；LLM 调用失败时降级到规则路径且不阻塞。

## 3. Milestone M3：RAG graph 入口集成

- [x] 3.1 在 `backend/rag/pipeline.py` 增加 `intent_parse_node`，作为 graph 的新入口节点
- [x] 3.2 添加条件边：`intent_parse → retrieve_initial`（precise 路径）或 `intent_parse → decompose_and_fanout`（comprehensive 路径）
- [x] 3.3 修改 `retrieve_initial` 接受 PreciseQueryPlan 作为输入而非 raw query
- [x] 3.4 实现 `decompose_and_fanout` 节点：comprehensive 路径下并发或顺序执行每个 sub_query 的检索
- [x] 3.5 实现 `merge_sub_query_results` 节点：只依赖 resolved ComprehensivePostprocessPolicy 接口合并多 sub-query 结果
- [x] 3.6 `plan_rag_turn` 保留既有 context_files / 通用文档检索关键词的 session 级触发规则，不参与 precise/comprehensive 分类、QueryPlan 或 sub-query 编排；trace 增加 `query_plan_type` 字段反映 graph 内 intent 解析结果

**验收**：完整 RAG 流程在 precise 和 comprehensive 两条路径下都能产出回答；现有测试 `tests/test_rag_pipeline.py` 全绿。

## 3A. Milestone M3A：结构清洗与 hybrid query composition

- [x] 3A.1 定义 query preparation 输出及 RAGState 字段：不可变 raw_query、clean_query、semantic_query，以及独立 terminology `term_matches` / `normalized_query` / `sparse_expansion` / `protected_tokens`；ComprehensiveQueryPlan.clean_query 由运行时确定性写入，不进入 LLM schema
- [x] 3A.2 重构结构解析：记录成功消费的 doc/scope/anchor span；只有成功形成 matched_files + scope 或 anchors 的 span 才从 clean/semantic query 删除，未匹配文档提示必须保留
- [x] 3A.3 修改 terminology preflight 接口，使其消费 semantic query（comprehensive 时消费 clean-query baseline 与各 sub-query）而非 raw query；无命中和 terminology 不可用时保持调用输入
- [x] 3A.4 修复 `backend/rag/utils.py` 的 query composition：dense 使用 normalized_query，BM25 使用 sparse_expansion；禁止 term_preflight 将 search_query 恢复为 raw query；保持既有 hybrid-to-dense failure degradation
- [x] 3A.5 组合单测覆盖：成功文档限域、文档提示未匹配、anchor 消费、正文术语命中、无术语命中、terminology 未加载，以及 dense/BM25 的实际调用参数
- [x] 3A.6 comprehensive 集成测试覆盖 baseline 与每个并行 sub-query 独立 terminology preflight、dense+BM25 输入和部分失败保留；断言 baseline 使用 clean_query 而非 raw_query
- [x] 3A.7 comprehensive 成功消费文档提示时把 typed retrieval_scope 共享给 baseline 与全部 sub-query；普通文档提示默认 boost，明确封闭措辞/context_files 才 filter；branch 不在 intent-routing 内放宽 filter

**验收**：任一检索请求的 dense 与 BM25 输入都从同一个结构处理后的 query 基底派生；成功消费的结构 span 不重复进入术语检索，未消费文本不丢失；加载术语表但无命中时不会恢复 raw query。

## 4. Milestone M4：综合分析 graph 内并行检索

- [x] 4.1 在 RAG graph 内从 plan.clean_query 固定构造 stable id/kind 为 `baseline` 的 retrieval branch，并与 ComprehensiveQueryPlan 的全部 sub_query 并行执行；baseline 不写入 sub_queries/coverage_domains，不通过 Chat Agent 循环调用工具
- [x] 4.2 新增 `backend/rag/comprehensive_postprocess.py`：定义 branch rerank / cross-query merge / final selection / budget allocation protocols、frozen `ComprehensivePostprocessPolicy` 和 profile registry
- [x] 4.3 注册生产 profile `quality_first_v1`；新增 `RAG_COMPREHENSIVE_POSTPROCESS_PROFILE`，未知值原子降级到默认 profile 并记录 requested/effective/warning
- [x] 4.4 实现全局 rerank budget allocator：RERANK_CANDIDATE_POOL_SIZE 作为 baseline + 生成分支共享 output budget，device-tier RERANK_INPUT_K_CPU/GPU 作为共享 pair cap（未配置时回退 output budget）；先分支最小配额、再按 effective priority 分配（baseline 固定为 2）；不得按分支复制预算或执行 candidate × all-branch 笛卡尔积
- [x] 4.5 实现 branch-local rerank：使用各 retrieval branch query 和其 term_matches；无配额或局部失败时保留 Milvus local rank/candidates 并记录包含 branch_kind 的 diagnostics；baseline 失败不成为 Level 1 rewrite 目标
- [x] 4.6 实现 priority-weighted RRF merge、chunk_id 去重和 provenance union；跨 query 不直接比较 dense/BM25/CrossEncoder 原始 score；provenance 使用 matched_branch_ids/per_branch ranks/baseline_matched，coverage_count 只统计生成分支
- [x] 4.7 复用一次共享 auto_merge / step-chain / structure rerank；parent 替换 leaf 时合并 matched_branch_ids、baseline_matched 与 local-rank provenance
- [x] 4.8 实现 branch-aware final selection：容量允许时每个成功生成分支保留一条，否则按 priority + stable branch id + global rank 选择；baseline 不占 reservation，只按 global rank 竞争剩余位置；不隐式扩大 top_k
- [x] 4.9 实现一次 comprehensive confidence gate，消费 branch diagnostics 与 final representation；不在分支内执行独立 final confidence
- [x] 4.10 保持 `search_knowledge_base(query)` 单次调用接口及现有每轮一次调用限制，不增加 multi-turn 参数或模式开关
- [x] 4.11 trace 增加 profile、各策略 id、sub_query_count、retrieval_branch_count、baseline diagnostics/matched/selected、各 branch results、allocated/used rerank budget、rerank pairs、merge counts、生成分支 representation 和 branch-scoped errors
- [x] 4.12 单元/集成测试覆盖 baseline 固定加入且不进入 coverage/reservation、空 clean_query 降级而非 raw/empty 回填、profile registry、非法组合拒绝、预算分配、local rerank、weighted RRF、去重/provenance、共享后处理只执行一次、top-k reservation、部分失败保留，以及 graph 不包含 profile-specific if/else
- [x] 4.13 在 embedding/Milvus fanout 前按 priority 截断生成 sub-query：默认 4、配置范围 1-8，同 priority 保持原顺序；effective plan 与公共 trace 记录实际执行及丢弃项
- [x] 4.14 新增确定性 compiled-graph E2E，覆盖 intent classifier → ComprehensiveQueryPlan → baseline + sub-query 并行 dense/BM25 边界 → merge → 一次共享后处理 → 公共 trace；外部 LLM、embedding、reranker 与 Milvus 使用受控替身，不将其作为真实模型、release index 或成本/质量证据
- [x] 4.15 修复 comprehensive rerank device probe 非恢复异常：quality-first 探测失败时 pair budget 降为 0 并保留 Milvus-ranked output candidates，no-CrossEncoder profile 跳过探测；回归测试覆盖两条路径

**验收**：comprehensive 查询在一次 graph 调用内完成 branch-local relevance、跨 query merge 和一次共享后处理；策略通过 profile 组合且 graph 不感知具体算法；成本预算不会随 sub-query 数复制；部分失败不清空可用结果；无 Chat Agent multi-turn 调用路径。

## 5. Milestone M5：意图分类评测集

- [x] 5.1 设计评测样本 schema：`{query, expected_intent, expected_sub_queries?, expected_scope?, expected_granularity?, notes}`
- [x] 5.2 标注样本：100-200 条，70% precise + 30% comprehensive，覆盖结构限域、目标粒度和所有 analysis_type
- [x] 5.3 评测脚本 `tests/eval/rag/test_intent_classifier_eval.py`：跑当前模型，输出 intent accuracy / plan validity / sub-query 5 分制评分（人工部分用 LLM-as-judge）
- [x] 5.4 评测结果落地到 `eval/intent/{date}_{model}.json`（不进 git，gitignore 覆盖）
- [x] 5.5 在 `docs/` 下记录评测方法和指标定义；阈值在标注完成后根据初评结果设定

**验收**：评测脚本可重复跑；FAST_MODEL 评测结果达标（阈值由初评基线确定）；不达标时模型升级路径在 design.md 中记录。

## 5A. Milestone M5A：terminology / postprocess 边界收口

- [x] 5A.1 保留 terminology preflight 的 `term_matches`、`normalized_query`、`sparse_expansion`、`protected_tokens`，不得写入两种 QueryPlan；query-side term_matches 只来自结构处理后的实际检索文本
- [x] 5A.2 保留 chunk `entity_types` / `term_match_count` 与现有可选 rerank metadata fusion；query 侧信号只接受 terminology term matches，不接受 intent entities
- [x] 5A.3 更新 postprocess 契约、trace 和测试用语，明确 `term_match_count` 是 chunk 全部术语密度而非 query-specific 精确命中数
- [x] 5A.4 回归测试证明删除 semantic entity producer/consumer 后，terminology query expansion、score fusion 开关和既有排序行为不变；成功消费的结构 span 不得通过 query-side term_matches 参与 metadata fusion

**验收**：intent-routing 不产生或消费 semantic entities；terminology 仍独立完成检索扩展，`RERANK_SCORE_FUSION_ENABLED=true` 时既有术语 metadata 分量可用。

## 5B. Milestone M5B：综合后处理质量 / 成本联合评测

- [x] 5B.1 增加 comprehensive postprocess eval harness，按 sub_query_count 与 retrieval_branch_count 分桶，单独统计 baseline 命中/最终入选率，并采集 embedding/hybrid 调用数、rerank pair、branch/merge pool、各阶段与端到端 P50/P95、CPU/GPU 峰值及错误/降级率
- [x] 5B.2 注册 eval-only no-CrossEncoder 消融 profile：保持相同 clean-query baseline + 生成分支 fan-out、parallel hybrid retrieval、priority-weighted RRF、selection 和共享后处理，仅关闭 branch CrossEncoder
- [ ] 5B.3 在相同数据集、commit、配置和 source fingerprint 下对比 `quality_first_v1` 与消融 profile 的分支代表率、引用有效性、回答质量、延迟和资源消耗
- [x] 5B.4 将报告写入 `docs/validation/` 的 governed validation 文档，记录 source_commit、source_fingerprint、executed_at、运行环境和 passed/partial/failed 结论
- [x] 5B.5 基于实测结果确定可接受阈值与生产 profile；没有结论时 intent classifier/comprehensive 默认保持关闭，消融 profile 不自动转为生产默认

> 2026-07-14：真实 FAST_MODEL / release Milvus 环境未配置，`docs/validation/rag-intent-routing-evaluation.md` 结论为 `partial`。5B.3 保持未完成，默认开关继续为 false；合成 trace 只验证 harness，不作为成本或质量结论。

**验收**：能够回答“质量优先 profile 相比便宜消融带来多少质量收益、增加多少延迟和资源成本”；报告可复现并成为启用 comprehensive 默认路径的 gate。

## 6. Milestone M6：上线开关与监控

- [x] 6.1 默认 `RAG_INTENT_CLASSIFIER_ENABLED=false`，开关由部署方控制
- [x] 6.2 监控指标：intent classifier 调用 P50/P95 延迟、LLM 失败率、规则降级率、各 intent 占比，以及 comprehensive profile、sub_query_count、retrieval_branch_count、baseline hit/selected、embedding/hybrid calls、rerank pairs、budget exhaustion、merge/postprocess 和端到端 P50/P95；公开 ChatResponse/历史消息 schema 保留这些 trace 字段
- [x] 6.3 灰度策略文档：先 10% 流量启用，观察延迟和准确率，逐步全量
- [x] 6.4 关闭开关时走兼容性 PreciseQueryPlan 路径；回归测试比较 semantic query、filters、route、检索结果和 `query_plan_enabled=false` telemetry，证明默认行为不变；另以显式回归用例记录并修复 `QUERY_PLAN_ENABLED=true` 时 terminology raw query 覆盖 semantic query 的既有缺陷
- [ ] 6.5 完成评测后将默认值改为 true，作为单独的小 change 上线
- [x] 6.6 提供 `.env.rag-intent-routing-workflow.example`，仅为工作流验证成组开启 intent routing / QueryPlan、heading lexical、confidence anchor gate 与 fallback；契约测试验证完整组合和非生产警示；将多开关冲突、anchor extraction mismatch 与 fallback contract gap 记录到 governed known issue，不改变 anchor span 消费规范

**验收**：在 `RAG_INTENT_CLASSIFIER_ENABLED=false` 状态下，所有现有测试通过、行为与改造前一致；监控字段在 rag_trace 中齐全。

## Evidence Disposition Gate

- [x] New findings classified, or `No new findings` recorded
- [x] Code, test, review, runtime, or invalidation evidence linked
- [x] Every confirmed Finding has a durable disposition or evidenced in-place closure
- [x] Residual risks have durable typed destinations
- [x] Planned work has an OpenSpec change or issue owner where required
- [x] ARCHITECTURE impact assessed
- [x] No undispositioned design ambiguity remains
