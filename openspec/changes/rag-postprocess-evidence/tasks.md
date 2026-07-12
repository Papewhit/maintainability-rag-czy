## 1. Milestone M1：修复 auto_merge 死代码

- [x] 1.1 在 `_finish_retrieval_pipeline()` 的成功路径中，rerank 之后、structure_rerank 之前，加入 `_auto_merge_documents()` 调用
- [x] 1.2 合并 merge_meta 到 rerank_meta，确保 `auto_merge_applied`、`auto_merge_replaced_chunks` 反映真实状态
- [x] 1.3 单元测试：构造一组带 parent_chunk_id 的 mock chunks，验证 auto_merge 真的合并
- [x] 1.4 集成测试：现有 RAG 流程在 `AUTO_MERGE_ENABLED=true` 时，trace 字段 `auto_merge_applied=true` 至少在某些查询下出现
- [x] 1.5 在 PR 描述中明确指出"修复死代码"，附带 grep 证据

**验收**：`auto_merge_applied` 在合适场景下为 true；emit_rag_step 显示的"应用"状态与实际一致。

## 2. Milestone M2：rerank 候选预算解耦

- [x] 2.1 新增配置 `RERANK_CANDIDATE_POOL_SIZE`（默认 20）
- [x] 2.2 重构 `_effective_rerank_top_n()` → `_effective_rerank_output_size()`，逻辑改为按 pool_size 计算
- [x] 2.3 修改 `_finish_retrieval_pipeline()`：rerank 输出 candidate_pool_size 个；最终 top_k 截断推迟到 structure_rerank 之后
- [x] 2.4 保留 `RERANK_TOP_N` 配置兼容（如已设置则覆盖默认 candidate_pool_size），添加 deprecation 注释
- [x] 2.5 trace 字段 `rerank_candidate_pool_size`、`rerank_output_count` 反映真实值
- [x] 2.6 性能测试：测量 candidate_pool_size=5/10/20 时的 P50/P95 延迟差异

**验收**：rerank 输出量可配置；性能数据明确；现有功能不破坏。

## 3. Milestone M3：step_chain_check 阶段

- [x] 3.1 新增配置 `STEP_CHAIN_CHECK_ENABLED`（默认 false，待 chunker 阶段 1 完成后开启）
- [x] 3.2 新增配置 `STEP_CHAIN_ADJACENT_LOOKBACK`（默认 2）
- [x] 3.3 实现 `_step_chain_check(docs, top_k)` 函数：检测 list_complete=false 的 chunk，拉取相邻 parent 补齐
- [x] 3.4 实现 `_fetch_adjacent_chunks(list_group_id, orders)`：通过 Milvus leaf metadata 定位 parent IDs，再从 ParentChunkStore 批量加载完整 parent
- [x] 3.5 接入 `_finish_retrieval_pipeline()`：auto_merge 之后、structure_rerank 之前
- [x] 3.6 trace 字段 `step_chain_check_enabled`、`step_chain_repaired_groups`、`step_chain_completion_count`、`step_chain_ms`
- [x] 3.7 单元测试：mock 不同的 chunk 序列（完整 / 中间断 / 头尾断 / 跨 group），验证修复正确
- [x] 3.8 缺失 list_group_id 时的降级测试：旧 profile 的 chunk 不触发任何 query，trace 中 repaired_groups 为空
- [x] 3.9 审查回归：leaf 写入 parent_list_order；真实 ingestion 契约下 Milvus 只返回 parent 引用，ParentChunkStore hydrate 完整 parent

**验收**：在带 list_group_id 的样本上 step_chain_check 工作；旧 profile 上是 no-op；trace 字段齐全。

## 4. Milestone M4：entity 信号融入 score fusion

- [x] 4.1 在 score fusion 中实现 `_metadata_score(doc, query_entities)`：基于 entity_types 覆盖率和 term_match_count 密度
- [x] 4.2 query_entities 从 RAGState（来自 `rag-intent-routing`）或 terminology preflight 结果传入
- [x] 4.3 缺失 query_entities 或 entity_types 时 metadata_score 返回 0（行为兼容）
- [x] 4.4 trace 字段 `entity_metadata_score_applied`、`entity_type_coverage`、`entity_match_density`
- [x] 4.5 单元测试：mock query_entities 和 entity_types，验证 fusion 分数排序正确

**验收**：entity 信号上线后参与 rerank 排序；不破坏现有 fusion 逻辑。

## 5. Milestone M5：trace 完整性与文档

- [x] 5.1 整合所有新增 trace 字段到 `backend/rag/trace.py` 的 schema
- [x] 5.2 更新 `contracts/schemas.py` 中的 RagTraceMeta 字段定义
- [x] 5.3 文档：在 `docs/` 下记录后处理管线的新形态、各阶段职责、trace 字段含义
- [x] 5.4 撰写"如何排查证据组织问题"指南：典型 trace 模式和对应原因

**验收**：trace 字段在所有路径下完整；开发者文档可用。

## 6. Milestone M6：回归评测

- [x] 6.1 建立修复前 baseline：跑 `tests/test_rag_pipeline.py` 记录 top_k 结果和回答质量
- [x] 6.2 应用本 change 后跑同样测试，对比差异
- [x] 6.3 维修步骤类样本评测：召回完整步骤组的比例（依赖 chunker 阶段 1）
- [x] 6.4 性能评测：P50/P95 延迟在 candidate_pool_size=20 时的变化
- [x] 6.5 写评测报告，决定 candidate_pool_size 默认值（20 vs 15 vs 10）

**验收**：评测报告完整；默认值有数据支撑；无明显回归。

## 7. Milestone M7：entity metadata 存储契约闭合

- [x] 7.1 定义共享 entity_types codec：Milvus wire format 为 JSON string，RAG runtime format 为去重后的 list[str]；读取兼容历史 list 值
- [x] 7.2 正常 ingestion writer 与 terminology rescan 统一使用 JSON string 写入
- [x] 7.3 hybrid / split / dense 三条 Milvus 检索路径透传并解码 entity_types / term_match_count
- [x] 7.4 rerank fusion 与 cache key 使用统一 runtime 表示，非法或缺失 metadata 安全降级
- [x] 7.5 补充 codec、writer、检索透传、fusion 与 cache key 等价性回归测试
- [x] 7.6 更新 OpenSpec 和运维文档；将显式 Milvus schema 与历史数据迁移记录到 docs

**验收**：正常 ingestion 与 rescan 产生等价的 entity metadata；所有检索路径向 rerank 提供 list[str]；等价 wire 表示产生相同 fusion 结果和 cache key。

## 8. Milestone M8：同 group 多截断点修复

- [x] 8.1 同一 filename / index_profile / list_group_id 累积全部不完整 parent order，并查询 lookback 邻域并集
- [x] 8.2 增加同 group 多个不连续 order 的回归测试，验证一次查询覆盖全部截断点且 trace 按 group 去重

**验收**：top-K 中同 group 的每个不完整 parent 都参与修复，后出现的 order 不再被忽略。
