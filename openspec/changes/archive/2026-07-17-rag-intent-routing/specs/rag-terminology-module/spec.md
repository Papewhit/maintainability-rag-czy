## MODIFIED Requirements

### Requirement: 查询时术语扩展
Preflight 阶段 MUST 对本次实际检索文本进行术语扫描，输出 query term_matches、normalized_query、sparse_expansion 和 protected_tokens 供下游使用。实际检索文本 SHALL 是结构解析后的 semantic query；comprehensive 路径 SHALL 对由 clean_query 构造的 baseline branch 与每个实际 sub-query 独立执行 preflight。Intent LLM MUST NOT 生成、补全或建议 terminology normalization。

#### Scenario: comprehensive baseline 术语输入
- **WHEN** comprehensive graph 从 plan.clean_query 构造 stable `baseline` branch
- **THEN** baseline 先按 branch query preparation 生成 semantic query，再独立执行 terminology preflight；不得直接扫描 raw_query，也不得复用任一 LLM sub-query 的 term_matches、normalized_query 或 sparse_expansion

#### Scenario: query 包含变体
- **WHEN** semantic query 为 "MRG 拆卸怎么做"，术语表中 MRG 是 "主减速齿轮箱" 的 variant
- **THEN** term_matches 包含 `{type=component, canonical=主减速齿轮箱, surface=MRG}`、`{type=maintenance_action, canonical=拆卸, surface=拆卸}`；normalized_query 使用 canonical 替换命中 surface 并供 dense embedding 使用；sparse_expansion 以该 semantic query 为基底并包含所有命中术语 variants 的并集，供 BM25 sparse embedding 使用

#### Scenario: query 无术语命中
- **WHEN** 实际检索文本不含任何术语表内的词
- **THEN** term_matches 为空列表；normalized_query 与 sparse_expansion 都等于本次实际检索文本；不得回退或恢复为 raw query

#### Scenario: 已成功消费的结构 span
- **WHEN** 文档名或章节片段已经成功转成 scope/anchor 并从 semantic query 删除
- **THEN** terminology preflight 不再扫描该 span；其中词语不进入 query term_matches、normalized_query、sparse_expansion 或 query-side terminology rerank 信号

#### Scenario: 未消费的文档提示
- **WHEN** 外观为文档提示的片段没有匹配到文件且没有形成 scope
- **THEN** 该片段保留在 semantic query；preflight 正常扫描其中术语并将命中传入 dense 与 BM25 路径

#### Scenario: terminology 不可用
- **WHEN** terminology table 未加载或 preflight 失败并进入安全降级
- **THEN** dense 与 BM25 均使用本次实际检索文本；结构清洗结果不得丢失，hybrid retrieval 继续执行

#### Scenario: term match offset 坐标
- **WHEN** preflight 输出 term match 的 start/end
- **THEN** offset MUST 相对于该次 preflight 的实际检索文本；trace MUST 同时暴露或可确定该输入文本，消费者不得假设 offset 相对于 raw query
