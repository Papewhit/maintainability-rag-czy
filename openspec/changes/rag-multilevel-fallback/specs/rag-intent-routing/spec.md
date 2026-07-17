## MODIFIED Requirements

### Requirement: 确定性 query preparation 与 dense+BM25 输入
RAG graph MUST 在检索前以确定性顺序执行结构解析、query cleaning、terminology preflight 和 hybrid query composition。`raw_query` MUST 保持不可变；只有已成功转成 scope 或 anchor 的结构 span MAY 从 `clean_query` / `semantic_query` 删除。terminology preflight MUST 消费结构处理后的 semantic query（comprehensive 时为 clean-query baseline 与每个实际 sub-query），MUST NOT 使用 raw query 覆盖该输入。正常检索 MUST 同时生成 dense embedding 与 BM25 sparse embedding，并执行 dense+sparse hybrid search；只有既有 sparse/hybrid failure degradation MAY 退化为 dense-only。

精确 planner 输出的 `scope_mode` MUST 是下游权威行为契约：`filter` 表示用户硬范围，`boost` 表示文件软偏好，`none` 表示无文件范围。只有 `context_files`、确定性解析成功且未被否定的明确封闭范围措辞，以及确定性解析成功的精确文档范围引用（如“《A》中……”）MAY 产生 filter。文件名字符串匹配分数本身 MUST NOT 产生 filter。classifier 的 `scope_hint` MUST NOT 单独将 boost/none 提升为 filter，也 MUST NOT 降级确定性 filter。PreciseQueryPlan MUST NOT 为 fallback 新增 `scope_source`。

#### Scenario: 成功限域的文档名只由 scope 消费
- **WHEN** query 为 "《主减速齿轮箱维修手册》中，MRG 拆卸怎么做"，文档提示成功匹配到文件并形成 filter scope
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
- **THEN** 每个扩展检索只以该扩展文本替换 semantic_query，并独立执行 terminology preflight；原 raw_query 与结构约束必须继承；`scope_mode="filter"` 在初始与全部扩展检索中都必须传为 hard filter，`boost` 才允许 global reserve；MUST NOT 因扩展文本不含原文档提示而重建为无约束 global plan；fallback Level 2 只能将 boost 降为 none 或在 filter/none 域内放宽候选参数，不得放宽 filter

#### Scenario: precise filter 不混入 global reserve
- **WHEN** PreciseQueryPlan 形成 `scope_mode="filter"`
- **THEN** candidate preparation 只执行 scoped filtered retrieval，不合并 unfiltered global reserve；fallback Level 2 MAY 放大 candidate_k、放宽 same_root_cap 等参数，但 MUST NOT 将 filter 改为 boost/none 或检索 matched_files 之外内容

#### Scenario: context_files 始终产生 filter
- **WHEN** precise 请求携带 context_files
- **THEN** scope_mode 为 filter、matched_files 精确等于去重后的 context_files；classifier hint 不得改变该范围

#### Scenario: 明确封闭措辞产生 filter
- **WHEN** precise query 使用解析成功且未被否定的“仅在”“只基于”等明确封闭措辞指向唯一可用文档
- **THEN** scope_mode 为 filter；已确认归属 scope 的文档 span 从 semantic query 消费

#### Scenario: 精确文档范围引用产生 filter
- **WHEN** precise query 使用可被确定性解析为范围选择的“《A》中……”且 A 成功匹配文件
- **THEN** scope_mode 为 filter；匹配分数只确认 A 对应的文件，不独立承担 hard-scope 语义

#### Scenario: 高字符串匹配分数本身最多产生 boost
- **WHEN** 文档标题与文件名匹配分数大于等于 `DOC_SCOPE_MATCH_FILTER`，但 query 没有 context_files、明确封闭措辞或确定性精确范围引用
- **THEN** planner MUST NOT 仅凭分数输出 filter；MAY 输出 boost

#### Scenario: classifier hint 不得创建 filter
- **WHEN** 确定性解析结果为 boost 或 none，而 classifier 输出 `scope_hint="filter"`
- **THEN** 最终 scope_mode MUST NOT 为 filter；classifier hint 在没有 hard-filter 信号时最多影响 boost 与 none 的选择

#### Scenario: precise scope 字段保持一致
- **WHEN** planner 或 fallback 产出 PreciseQueryPlan
- **THEN** scope_mode=filter/boost 时 matched_files MUST 非空且 route=scoped_hybrid；scope_mode=none 时 matched_files MUST 为空且 route=global_hybrid；范围状态变化 MUST 原子更新这些字段

### Requirement: comprehensive 共享 retrieval scope
ComprehensiveQueryPlan MUST 携带运行时确定性生成的 typed `retrieval_scope`。成功消费的文档提示对应的 `matched_files`、scope mode 与结构提示 MUST 保存在该 scope 中，并由 baseline 与全部生成 sub-query 共享；不得在删除文档名后把 branch 降为无约束全局检索。共享 scope MUST 区分 boost 与 filter，MUST NOT 把普通文档提示无条件升级为硬过滤。`retrieval_scope.scope_mode` MUST 是下游权威行为契约；`retrieval_scope.source` MAY 保留为 trace/provenance，但 MUST NOT 参与 fallback Level 2 的范围行为判断。

#### Scenario: 普通文档提示默认 boost
- **WHEN** comprehensive query 普通提及一个或多个可解析的 `《文档名》`，且没有明确封闭范围措辞，也没有 context_files
- **THEN** 文档 span 成功消费并写入 `retrieval_scope`，scope_mode 为 `boost`；baseline 与全部 sub-query 继续检索全局语料，并对匹配文档候选应用同一 boost

#### Scenario: 明确封闭范围使用 filter
- **WHEN** comprehensive query 使用“仅在”“仅限”“检索范围限定为”等明确封闭措辞指向可解析文档
- **THEN** `retrieval_scope.scope_mode=filter`；baseline 与全部 sub-query 使用同一文件 filter，不得由某个 branch 或 fallback Level 2 放宽

#### Scenario: context_files 始终硬过滤
- **WHEN** comprehensive 请求携带 context_files
- **THEN** `retrieval_scope` 来源为 context_files、scope_mode 为 filter、matched_files 精确等于 context_files；所有 branch 共享该硬约束

#### Scenario: source 仅用于诊断
- **WHEN** comprehensive retrieval_scope 包含 source
- **THEN** source 保留在 trace/provenance 中以解释 planner 输出，但 fallback MUST NOT 根据 source 决定 filter 是否可放宽；一旦 scope_mode=filter，下游统一视为硬范围

#### Scenario: scope 放宽不属于 intent-routing
- **WHEN** shared scope 下某个 branch 召回不足
- **THEN** intent-routing 只保留结果与诊断，不动态调整 scope；独立 fallback Level 2 对 filter 保持不变、对 boost 降为 none、对 none 仅放宽候选参数
