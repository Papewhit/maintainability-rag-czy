## ADDED Requirements

### Requirement: 意图分类入口
RAG 管线 SHALL 在执行检索之前先做意图分类，将查询归入 `precise_lookup` 或 `comprehensive_analysis` 二类之一。意图分类的实现 MAY 是 LLM 调用或规则降级路径，但管线对外暴露的行为 MUST 一致：所有下游节点 MUST 接受 `PreciseQueryPlan` 或 `ComprehensiveQueryPlan` 作为输入，不再接受裸 query 字符串。

#### Scenario: LLM 解析成功的精确查找
- **WHEN** 用户提交 query "《部署手册》第三章的回滚步骤" 且 LLM 分类器可用
- **THEN** 意图节点输出 `PreciseQueryPlan`，确定性 query preparation 在文档提示成功解析、anchor 成功识别后构造 semantic_query "回滚步骤"，plan 包含 doc_hints `[部署手册]`、anchors `[第三章]`、target_granularity `step_list`；LLM 不直接生成 semantic_query 或 terminology normalization；trace 字段 `intent="precise_lookup"`、`intent_fallback_to_rules=false`

#### Scenario: LLM 解析成功的综合分析
- **WHEN** 用户提交 query "对比两份架构方案的取舍并分析改进方向"
- **THEN** 意图节点输出 `ComprehensiveQueryPlan`，包含运行时确定性生成的 clean_query、analysis_type `comparison`、sub_queries 列表（至少 2 个独立 sub_query，每个带自己的 domain 和 priority）以及由运行时解析的 postprocess_profile `quality_first_v1`；LLM 不生成 clean_query，也不选择 merge/postprocess 算法；trace 字段 `intent="comprehensive_analysis"`、`sub_query_count >= 2`

#### Scenario: LLM 调用失败的规则降级
- **WHEN** LLM 调用超时、网络错误、或返回无法解析为目标 schema 的 JSON
- **THEN** 意图节点通过兼容适配器输出 `PreciseQueryPlan`（规则路径永不输出 ComprehensiveQueryPlan）；适配器遵守当前 `QUERY_PLAN_ENABLED` 语义；trace 字段 `intent_fallback_to_rules=true`、`intent_llm_error` 记录失败原因；不阻塞 RAG 流程

#### Scenario: 意图分类关闭
- **WHEN** 配置 `RAG_INTENT_CLASSIFIER_ENABLED=false`
- **THEN** 意图节点不发起 LLM 调用，并通过兼容适配器输出 PreciseQueryPlan；`QUERY_PLAN_ENABLED=false` 时保持 raw query + global route 且不启用新的内容/scope 规则，`QUERY_PLAN_ENABLED=true` 时无损映射现有 `parse_query_plan()` 结果；trace 不记录 LLM 错误或失败降级

#### Scenario: 默认关闭行为兼容
- **WHEN** intent classifier 和现有 QueryPlan 均保持默认关闭
- **THEN** semantic query、检索 filters、query route 和最终检索结果必须与引入 intent-routing 前一致；兼容性测试必须比较这些行为输出，而不只验证请求成功

### Requirement: 双 QueryPlan 数据结构
`PreciseQueryPlan` 和 `ComprehensiveQueryPlan` MUST 是两个独立的 frozen dataclass。RAGState 中 SHALL 通过 union type 表达，下游节点 MUST 用 isinstance 或 match 语句分支。两种结构 MUST NOT 包含 `EntityMatch` 或 `entities` 字段。

#### Scenario: PreciseQueryPlan 字段完整性
- **WHEN** 意图分类产出 PreciseQueryPlan
- **THEN** 该实例必须包含 raw_query、semantic_query、clean_query、doc_hints、scope_mode、matched_files、heading_hint、anchors、model_numbers、intent_type、target_granularity 和 route；兼容路径必须保留现有 QueryPlan 的同名字段语义，任意字段缺失视为非法状态

#### Scenario: ComprehensiveQueryPlan 字段完整性
- **WHEN** 意图分类产出 ComprehensiveQueryPlan
- **THEN** 该实例必须包含 raw_query、clean_query、analysis_type、sub_queries (至少 1 个)、coverage_domains、postprocess_profile、retrieval_scope 共 7 个字段；clean_query 与 retrieval_scope 由确定性 query preparation 写入，sub_queries 为空时视为非法状态（应降级到 PreciseQueryPlan）；postprocess_profile 由运行时 policy resolver 写入；clean_query、retrieval_scope 与 postprocess_profile 均不接受 LLM 自由生成

#### Scenario: terminology 与 QueryPlan 隔离
- **WHEN** terminology preflight 命中术语并输出 term_matches、normalized_query、sparse_expansion 或 protected_tokens
- **THEN** 这些字段保留在独立 terminology/RAG state 中并供检索消费；intent classifier MUST NOT 复制、生成或规范化 semantic entities，PreciseQueryPlan 和 ComprehensiveQueryPlan MUST NOT 写入 terminology 字段

### Requirement: 确定性 query preparation 与 dense+BM25 输入
RAG graph MUST 在检索前以确定性顺序执行结构解析、query cleaning、terminology preflight 和 hybrid query composition。`raw_query` MUST 保持不可变；只有已成功转成 scope 或 anchor 的结构 span MAY 从 `clean_query` / `semantic_query` 删除。terminology preflight MUST 消费结构处理后的 semantic query（comprehensive 时为 clean-query baseline 与每个实际 sub-query），MUST NOT 使用 raw query 覆盖该输入。正常检索 MUST 同时生成 dense embedding 与 BM25 sparse embedding，并执行 dense+sparse hybrid search；只有既有 sparse/hybrid failure degradation MAY 退化为 dense-only。

#### Scenario: 成功限域的文档名只由 scope 消费
- **WHEN** query 为 "《主减速齿轮箱维修手册》中，MRG 拆卸怎么做"，文档提示成功匹配到文件并形成 scope
- **THEN** `clean_query` / `semantic_query` 不包含已消费的文档名 span；terminology preflight 只对剩余检索文本命中 `MRG`、`拆卸` 等术语；文档名内部术语不进入 term_matches、dense query、BM25 expansion 或 query-side rerank terminology 信号

#### Scenario: 文档提示解析失败时保留文本
- **WHEN** query 包含 `《未知主减速齿轮箱手册》`，但该提示没有匹配到任何文件且没有形成 scope
- **THEN** 该文档提示及其中术语保留在 semantic query；terminology preflight MAY 命中其中已登记术语，并将其正确传入 dense normalization 与 BM25 expansion

#### Scenario: query 正文术语进入两路检索
- **WHEN** semantic query 为 "MRG 拆卸怎么做"，术语表将 MRG 映射到 "主减速齿轮箱" 并为 "拆卸" 配置 variants
- **THEN** dense embedding 输入为 canonicalized `normalized_query`；BM25 sparse embedding 输入为基于同一 semantic query、包含 canonical 与 variants 的 `sparse_expansion`；Milvus 同时接收 dense 与 sparse search request 并进行融合

#### Scenario: 无术语命中不恢复 raw query
- **WHEN** raw query 含已成功消费的文档名或 anchor，但剩余 semantic query 没有术语命中
- **THEN** `normalized_query` 与 `sparse_expansion` 都等于 semantic query；不得等于或恢复为 raw query；dense 和 BM25 都基于 semantic query 执行

#### Scenario: comprehensive sub-query 独立执行 preflight
- **WHEN** ComprehensiveQueryPlan 生成多个 sub-query 并进入并行 fan-out
- **THEN** runtime 先从 clean_query 构造 baseline branch；baseline 与每个实际 sub-query 在检索前独立执行 terminology preflight，并分别产出 dense normalized query 与 BM25 sparse expansion；LLM 生成值不得被当作 terminology canonicalization 结果

#### Scenario: precise fallback 保留结构约束
- **WHEN** 带有 filter/boost、matched_files 或 anchors 的 PreciseQueryPlan 进入 HyDE/step-back 扩展检索
- **THEN** 每个扩展检索只以该扩展文本替换 semantic_query，并独立执行 terminology preflight；原 raw_query 与结构约束必须继承；`scope_mode="filter"` 在初始与全部扩展检索中都必须传为 hard filter，`boost` 才允许 global reserve；MUST NOT 因扩展文本不含原文档提示而重建为无约束 global plan；scope relax 只由 fallback Level 2 执行

#### Scenario: precise filter 不混入 global reserve
- **WHEN** PreciseQueryPlan 由 context_files 或明确封闭语义形成 `scope_mode="filter"`
- **THEN** candidate preparation 只执行 scoped filtered retrieval，不合并 unfiltered global reserve；只有 fallback Level 2 可以显式放宽该 filter

### Requirement: comprehensive 共享 retrieval scope
ComprehensiveQueryPlan MUST 携带运行时确定性生成的 typed `retrieval_scope`。成功消费的文档提示对应的 `matched_files`、scope mode 与结构提示 MUST 保存在该 scope 中，并由 baseline 与全部生成 sub-query 共享；不得在删除文档名后把 branch 降为无约束全局检索。共享 scope MUST 区分 boost 与 filter，MUST NOT 把普通文档提示无条件升级为硬过滤。

#### Scenario: 普通文档提示默认 boost
- **WHEN** comprehensive query 普通提及一个或多个可解析的 `《文档名》`，且没有明确封闭范围措辞，也没有 context_files
- **THEN** 文档 span 成功消费并写入 `retrieval_scope`，scope_mode 为 `boost`；baseline 与全部 sub-query 继续检索全局语料，并对匹配文档候选应用同一 boost

#### Scenario: 明确封闭范围使用 filter
- **WHEN** comprehensive query 使用“仅在”“仅限”“检索范围限定为”等明确封闭措辞指向可解析文档
- **THEN** `retrieval_scope.scope_mode=filter`；baseline 与全部 sub-query 使用同一文件 filter，不得由某个 branch 自行放宽

#### Scenario: context_files 始终硬过滤
- **WHEN** comprehensive 请求携带 context_files
- **THEN** `retrieval_scope` 来源为 context_files、scope_mode 为 filter、matched_files 精确等于 context_files；所有 branch 共享该硬约束

#### Scenario: scope 放宽不属于 intent-routing
- **WHEN** shared filter 下某个 branch 召回不足
- **THEN** intent-routing 只保留结果与诊断，不动态改成 boost/global；scope relax 由独立 fallback Level 2 处理

### Requirement: comprehensive clean-query baseline branch
每个合法 ComprehensiveQueryPlan MUST 固定执行一个由运行时构造的 clean-query baseline branch。该 branch MUST 使用稳定 id `baseline` 与 kind `baseline`，MUST NOT 写入 LLM `sub_queries` 或 `coverage_domains`，并 MUST 与生成 sub-query 在同一 fan-out、共享预算和 merge 管线中执行。

#### Scenario: baseline 固定加入 fan-out
- **WHEN** ComprehensiveQueryPlan 包含 N 个 LLM sub-query
- **THEN** graph 执行 N+1 个 retrieval branch；`sub_query_count=N`，`retrieval_branch_count=N+1`；baseline 的源文本为 plan.clean_query，且仍经过 branch query preparation 与 terminology preflight

#### Scenario: 空 clean_query 不创建空检索
- **WHEN** 确定性 query preparation 产生空白 clean_query
- **THEN** ComprehensiveQueryPlan 视为非法并降级到兼容 PreciseQueryPlan；MUST NOT 用 raw_query 回填 baseline 或发送空 query，因此合法 comprehensive 执行时始终满足 `retrieval_branch_count=sub_query_count+1`

#### Scenario: baseline 不伪装成 coverage domain
- **WHEN** baseline 召回候选
- **THEN** provenance 标记 `branch_id="baseline"`、`branch_kind="baseline"` 和 `baseline_matched=true`；不得增加 coverage_count，不得将 baseline 写入 matched generated sub-query 集合

#### Scenario: baseline 局部失败
- **WHEN** baseline retrieval、terminology 或 local rerank 局部失败
- **THEN** 记录 baseline branch diagnostics 并保留其失败前可用候选；其他生成分支继续执行；baseline 不成为 fallback Level 1 的 rewrite 目标

### Requirement: comprehensive 多查询后处理边界
Comprehensive 路径 MUST 对 clean-query baseline 与每个 sub-query 执行 query-local hybrid retrieval 和 query-local rerank，再对 branch candidate pools 执行一次跨 query merge。auto_merge、step_chain_check、structure_rerank、最终 top_k 和 confidence gate MUST 在 merge 后全局各执行一次，MUST NOT 在每个分支完整执行后处理再 union 最终结果。

#### Scenario: branch-local relevance
- **WHEN** baseline 与多个 sub-query 并行返回 hybrid candidates
- **THEN** 每个分支只用本 branch query 文本及其 terminology term_matches 做 rerank/metadata fusion；分支输出 local ranks、候选、耗时和错误，不执行 final top_k 或独立 confidence gate

#### Scenario: 跨 query 分数融合
- **WHEN** merge_sub_query_results 接收各分支候选
- **THEN** merge 使用生成分支的 SubQuery.priority 与 baseline 固定中性 effective priority `2` 加权 local-rank RRF；MUST NOT 平均或直接比较不同 query 的 dense、BM25 或 CrossEncoder 原始 score；相同 chunk_id 去重并合并 `matched_branch_ids`、per-branch ranks/scores、`baseline_matched` 和生成分支 coverage provenance

#### Scenario: 共享结构后处理
- **WHEN** 跨 query merge 产生统一候选池
- **THEN** 按顺序执行 `auto_merge → step_chain_check → structure_rerank → branch-aware top_k → comprehensive confidence_gate`；parent 替换 leaf 时保留并合并 matched_branch_ids、baseline_matched 与 local-rank provenance

#### Scenario: branch-aware top-k
- **WHEN** successful_generated_branch_count 小于等于 top_k
- **THEN** final selection 为每个成功的 LLM sub-query 分支保留至少一个候选，再按全局排序填满剩余位置；baseline 不占 reservation 席位，只能通过 global rank 进入剩余位置；该选择是单次静态 selection，不创建证据账本、不发起 multi-turn 检索

#### Scenario: 分支数超过 top-k
- **WHEN** successful_generated_branch_count 大于 top_k
- **THEN** selection 按 SubQuery.priority、稳定 branch id 和 global rank 决定保留顺序；不得隐式扩大 top_k；trace 记录未获最终席位的成功分支

#### Scenario: comprehensive confidence
- **WHEN** final top-k 形成
- **THEN** 只执行一次全局 confidence gate；branch diagnostics 和 final branch representation 作为 comprehensive confidence/fallback 输入，空召回或失败分支可供 fallback Level 1 定位，但初始 intent-routing 不动态调整 sub-query

### Requirement: 版本化 comprehensive postprocess profile
系统 MUST 通过 typed `ComprehensivePostprocessPolicy` 和 registry 解析一个完整的版本化策略组合。Graph 节点 MUST 只依赖策略接口，MUST NOT 按 profile id 散落条件分支，也 MUST NOT 通过多个独立环境开关任意组合未经验证的 branch rerank、merge、selection 和 budget 策略。

#### Scenario: 默认 quality-first profile
- **WHEN** 未配置 `RAG_COMPREHENSIVE_POSTPROCESS_PROFILE`
- **THEN** effective profile 为 `quality_first_v1`，组合 `local_cross_encoder_with_term_fusion + priority_weighted_rrf + branch_reservation_then_global_rank + global_shared_priority_budget + shared-postprocess-v1`

#### Scenario: 未知 profile
- **WHEN** 配置未知 profile id
- **THEN** resolver 原子降级到完整 `quality_first_v1`，记录结构化 warning、requested/effective profile；不得部分采用未知组合中的任何组件

#### Scenario: 策略实现可替换
- **WHEN** 后续新增成本更低的 profile
- **THEN** 通过新的版本化 registry entry 组合已实现 protocol；graph topology 和节点业务代码无需修改；新增 profile 必须有组合契约测试和独立评测证据

### Requirement: comprehensive 共享预算与成本评测 gate
Comprehensive 路径的 `RERANK_CANDIDATE_POOL_SIZE` MUST 是 baseline 与全部生成分支共享的全局 rerank 输出候选预算，MUST NOT 为每个 branch 复制。CrossEncoder pair budget MUST 独立使用当前 device tier 的 `RERANK_INPUT_K_CPU/GPU` 上限；上限未配置时 SHALL 回退到全局输出候选预算。默认启用 comprehensive 路径前 MUST 完成质量与成本联合评测；没有评测结论时 `RAG_INTENT_CLASSIFIER_ENABLED` 默认值 MUST 保持 false。

Comprehensive 与 precise MUST 复用同一 effective rerank pool 规则：`RERANK_CANDIDATE_POOL_SIZE<=0` 时回退到 `top_k*4`，正值小于 final `top_k` 时提升到 `top_k`，随后再受实际候选总数上限约束；不得把未配置值解释为清空全部 comprehensive 候选。

#### Scenario: 全局 rerank 预算分配
- **WHEN** 多个分支竞争有限 rerank budget
- **THEN** budget policy 分别计算 output candidate budget 与 CrossEncoder pair budget，先分配每个可执行分支（含 baseline）的最小配额，再按 effective priority 分配剩余配额；baseline effective priority 固定为 2；未获 CrossEncoder 配额但拥有 output 配额的分支按 Milvus local rank 保留不超过该 output 配额的候选并标记 budget exhaustion；output 配额为 0 的分支不得向 merge 传入候选；任意成功、降级或异常路径传入 merge 的候选总数不得超过全局 output budget

#### Scenario: 禁止候选与查询笛卡尔积
- **WHEN** 一个 candidate 只由部分 sub-query 召回
- **THEN** relevance 计算只与其来源 sub-query 配对；不得默认执行 all candidates × all sub-queries CrossEncoder 组合

#### Scenario: 成本评测字段
- **WHEN** 运行 comprehensive 后处理评测
- **THEN** 报告至少包含 sub_query_count、retrieval_branch_count、baseline 独立命中/最终入选率、dense/sparse embedding calls、hybrid search calls、rerank pair count、branch/merged candidate counts、各阶段与端到端 P50/P95、CPU/GPU 峰值、错误/降级率，以及生成分支代表率、引用有效性和回答质量

#### Scenario: no-CrossEncoder 消融对照
- **WHEN** 评估 `quality_first_v1` 的成本收益
- **THEN** 使用相同 clean-query baseline + 生成分支 fan-out、parallel retrieval 与 weighted-RRF merge，运行关闭 branch CrossEncoder 的 eval-only profile 作为对照；报告同时给出质量差异与资源/延迟差异；消融 profile 不自动成为生产默认

### Requirement: RAG graph 入口分支
`run_rag_graph()` MUST 以 `intent_parse` 节点为入口；从 `intent_parse` SHALL 引出条件边到 `retrieve_initial`（precise 路径）或 `decompose_and_fanout`（comprehensive 路径）。两条路径在 `assemble_context` 之前 MUST NOT 交汇。

#### Scenario: 精确路径连通性
- **WHEN** intent_parse 产出 PreciseQueryPlan
- **THEN** 状态机依次执行 `intent_parse → retrieve_initial → grade_documents → [rewrite/answer]`；与改造前现有路径行为兼容

#### Scenario: 综合路径连通性
- **WHEN** intent_parse 产出 ComprehensiveQueryPlan
- **THEN** 状态机执行 `intent_parse → decompose_and_fanout → branch_rerank → merge_sub_query_results → shared_postprocess → assemble_context`；decompose_and_fanout 固定加入 clean-query baseline，每个 retrieval branch 独立完成 query preparation、dense+BM25 hybrid 检索和 local rerank，再由 effective postprocess profile 合并并执行一次共享后处理

### Requirement: 综合分析采用 graph 内并行检索
系统 SHALL 在同一次 RAG graph 调用内并行执行 ComprehensiveQueryPlan 的 clean-query baseline 与全部 sub-query，并在 graph 内合并结果。Chat Agent MUST NOT 逐个调度 branch 或根据中间结果发起额外知识库工具调用。本 capability MUST NOT 提供 multi-turn 执行模式或对应模式开关。

#### Scenario: 并行执行综合查询
- **WHEN** intent 为 comprehensive_analysis 且 plan 包含多个 sub-query
- **THEN** graph 并行执行 baseline 与全部 sub-query，通过 effective postprocess profile 完成 local rerank、merge 和共享后处理后一次性返回给 Chat Agent；trace 分别记录 baseline 和每个 sub-query 的命中数、耗时、预算和错误

#### Scenario: Chat Agent 不参与检索编排
- **WHEN** Chat Agent 调用 `search_knowledge_base(query)`
- **THEN** 工具只调用一次 `run_rag_graph()` 并返回合并后的最终检索结果；Chat Agent 不接收待执行 sub-query 列表，也不执行 multi-turn 检索

#### Scenario: sub-query 检索效果不足
- **WHEN** 某个已生成 sub-query 的检索结果不足
- **THEN** intent-routing 保留该 sub-query 的结果和失败 trace，但不动态调整该 sub-query；rewrite、replace 或 decompose 由独立的 fallback Level 1 capability 负责

### Requirement: 意图解析 trace 字段
每次 RAG 请求的 rag_trace MUST 包含意图解析相关字段，用于评测、监控、debug。

#### Scenario: 解析成功 trace
- **WHEN** 意图分类正常完成
- **THEN** rag_trace 包含 `intent`（精确或综合）、`intent_confidence`（0-1）、`query_plan_type`（precise/comprehensive）、`intent_llm_model`、`intent_llm_ms`、`intent_fallback_to_rules=false`、（comprehensive 时）`sub_query_count`、`retrieval_branch_count=sub_query_count+1`、`analysis_type`

#### Scenario: comprehensive 后处理与成本 trace
- **WHEN** comprehensive 路径完成或局部降级后返回
- **THEN** rag_trace 包含 requested/effective postprocess profile、各策略组件 id、baseline branch diagnostics、每个分支及总量的 allocated/used output budget 与 CrossEncoder pair budget、实际 rerank pair count、branch/merged/final candidate counts、各阶段耗时、分支错误与 budget exhaustion、baseline_matched/selected 及生成分支代表情况；这些字段即使局部阶段失败也保留已知值

#### Scenario: 规则降级 trace
- **WHEN** LLM 调用失败触发规则降级
- **THEN** rag_trace 包含 `intent_fallback_to_rules=true`、`intent_llm_error`（失败原因字符串）、`intent_llm_ms`（即使失败也记录消耗的时间）、`intent="precise_lookup"`（规则降级永远是 precise）

#### Scenario: classifier 关闭 trace
- **WHEN** `RAG_INTENT_CLASSIFIER_ENABLED=false`
- **THEN** rag_trace 标明 classifier 未启用和 compatibility source，不包含 `intent_llm_error`，且 `intent_fallback_to_rules=false`

#### Scenario: API 响应保留 intent-routing trace
- **WHEN** graph 的 rag_trace 经 `ChatResponse` 或历史消息响应 schema 序列化
- **THEN** intent、query-plan、comprehensive profile、branch diagnostics、budget/cost、scope telemetry，以及 terminology preflight 的 `semantic_query`、`term_matches`、`normalized_query`、`sparse_expansion`、`protected_tokens` 必须保留，不得因响应模型未声明字段而被静默过滤；term match offset 以同一响应中的 semantic_query 为坐标空间；`retrieved_chunks` 中的 branch ids、per-branch ranks/scores、baseline 标记和 coverage provenance 同样必须通过 API/history schema 保留

### Requirement: 评测集与阈值
`tests/eval/data/intent_routing/` 下 MUST 存在意图分类评测集，包含至少 100 条标注样本（70% precise + 30% comprehensive），覆盖结构限域、目标粒度和所有 analysis_type。评测脚本 MUST 可重复运行，输出指标 MUST 达到既定阈值才允许将 `RAG_INTENT_CLASSIFIER_ENABLED` 默认值改为 true。

#### Scenario: 评测脚本可重复跑
- **WHEN** 运行 `pytest tests/eval/rag/test_intent_classifier_eval.py -m eval`
- **THEN** 脚本读取 `tests/eval/data/intent_routing/*.jsonl`，对每条样本调用当前 intent classifier，输出 intent accuracy / plan validity / sub-query quality 三类指标，写入 `eval/intent/{date}_{model}.json`

#### Scenario: 阈值达标
- **WHEN** 评测完成后查看输出 JSON
- **THEN** 各项指标达到预设基线时视为达标；不达标时配置项 `RAG_INTENT_CLASSIFIER_ENABLED` 默认保持 false。具体阈值在标注完成后根据初评结果设定，不在此处硬编码

### Requirement: 与 plan_rag_turn 的职责边界
`plan_rag_turn()` SHALL 保留既有 session 级 RAG 触发行为：context_files 和通用文档检索关键词 MAY 用于选择 FORCED_PRELOAD、OPTIONAL_TOOL 或 NO_RAG。该触发判断 MUST NOT 分类 `precise_lookup` / `comprehensive_analysis`，MUST NOT 构造 QueryPlan、生成 sub-query 或选择后处理策略；这些 intent-routing 动作 MUST 全部由 RAG graph 内部的 `intent_parse` 节点承担。

#### Scenario: 通用文档检索词只触发 session 路由
- **WHEN** unified execution 已启用且无 context_files 的 query 命中既有通用文档检索关键词
- **THEN** `plan_rag_turn` MAY 维持既有 FORCED_PRELOAD 行为，但不得产出 intent、QueryPlan 或 sub-query；进入 `run_rag_graph` 后仍由 `intent_parse` 独立完成 precise/comprehensive 分类

#### Scenario: FORCED_PRELOAD 仍然走意图解析
- **WHEN** 请求带 context_files，`plan_rag_turn` 判定为 FORCED_PRELOAD
- **THEN** 进入 run_rag_graph 后仍先执行 intent_parse 节点；precise intent 将 context_files 写入 PreciseQueryPlan，comprehensive intent 将其写入 ComprehensiveQueryPlan.retrieval_scope；两条路径均使用 `scope_mode=filter` 且 matched_files 来自 context_files

#### Scenario: OPTIONAL_TOOL 经工具调用进入
- **WHEN** Agent 调用 search_knowledge_base 工具
- **THEN** 工具内部调用 run_rag_graph 时也走 intent_parse 节点；Agent 不感知意图分类的存在，工具行为对外保持简单接口（输入 query 字符串）
