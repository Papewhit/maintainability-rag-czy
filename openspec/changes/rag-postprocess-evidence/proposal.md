## Why

讨论中发现当前 RAG 后处理管线存在两个明确的问题：

1. **auto_merge 是死代码**：`backend/rag/context.py` 中定义了 `auto_merge_documents()`，`backend/rag/utils.py` 中也有 wrapper `_auto_merge_documents()`，但在 `_finish_retrieval_pipeline()` 的成功路径中**从未被调用**。配置项 `AUTO_MERGE_ENABLED` 默认 true、UI 通过 `emit_rag_step` 也声称"Auto-merging 合并 启用: true"，但 `auto_merge_applied` 字段永远是 false。这是真实的代码债务，需要修复。

2. **rerank 输出量与 top_k 强绑定**：`_effective_rerank_top_n()` 默认让 rerank 输出就是 top_k（5 个），导致后续的 auto_merge / structure_rerank / 任何"证据合并"步骤几乎没有素材可消化。

设计文档（`docs/superpowers/specs/2026-05-20-rag-fusion-design.md` 4.10）要求 Evidence Builder 做"按 parent_id 合并同一证据单元"、"维修步骤链完整性检查"、"图文关联合并"、"参数表 + 解释段合并"。讨论中你的关键澄清是：**EvidenceBuilder 不是新增模块，而是对整体后处理管线的 fancy 说法** —— rerank、auto_merge、structure_rerank、step_chain_check 应该被统一为一条连贯的证据组织流水线。

## What Changes

修复并重组 RAG 后处理管线，让"证据组织"职责真正落地：

1. **修复 auto_merge 死代码**：在 `_finish_retrieval_pipeline()` 的成功路径中，rerank 之后、structure_rerank 之前，加入 `_auto_merge_documents()` 调用。同时确保 `auto_merge_applied` 等 trace 字段反映真实状态（而非 hardcoded false）。

2. **rerank 候选预算解耦**：将 rerank 实际输出量与最终 top_k 分离：
   - 新增 `RERANK_CANDIDATE_POOL_SIZE`（默认 15-20）控制 rerank 输出量
   - `_effective_rerank_top_n()` 优先使用候选池大小，最终截断到 top_k 在 structure_rerank 之后
   - 给 auto_merge 和 step_chain_check 留出消化空间

3. **新增 step_chain_check 阶段**：依赖 `rag-maintainability-chunker` 的 list_group_id / list_order / list_complete 字段。在 auto_merge 之后、structure_rerank 之前检测：
   - top-K parent chunk 是否被截断（list_complete=false 且 list_order != 1）
   - 若是，拉取相邻 parent chunk（同 list_group_id，list_order 紧邻）补齐
   - 输出 trace 字段 `step_chain_completion_count`、`step_chain_repaired_groups`

4. **统一后处理管线契约**：把 rerank → auto_merge → step_chain_check → structure_rerank → confidence_gate → top_k_truncate 串成一条管线，每阶段输入输出明确、可单测，并在 trace 中暴露每阶段的耗时和操作统计。

5. **score fusion 引入 entity 信号**：当 chunk metadata 含 `entity_types` 和 `term_match_count`（来自 `rag-terminology-module`）时，rerank score fusion 的 metadata 分量使用这些信号；否则保持当前行为（score 占位）。

## Capabilities

### New Capabilities
- `rag-postprocess-pipeline`: 修复并重组后处理管线，提供 Evidence 组织契约

### Modified Capabilities
<!-- 现有 openspec/specs/ 无既有 spec -->

## Impact

**代码影响：**
- `backend/rag/utils.py`：
  - 在 `_finish_retrieval_pipeline()` 中加入 `_auto_merge_documents()` 调用
  - 重构 `_effective_rerank_top_n()` 引入候选池大小
  - 新增 `_step_chain_check()` 阶段
  - top_k 截断从 rerank 内部移到 structure_rerank 之后
- `backend/rag/runtime_config.py`：新增 `RERANK_CANDIDATE_POOL_SIZE`、`STEP_CHAIN_CHECK_ENABLED`、`STEP_CHAIN_ADJACENT_LOOKBACK`
- `backend/rag/context.py`：可能调整 `auto_merge_documents()` 接受 candidate_pool_size 参数
- `backend/rag/rerank.py`（如有）：score fusion 接入 entity_types / term_match_count
- `backend/rag/trace.py`：增加新 trace 字段
- `tests/test_rag_pipeline.py`：覆盖 auto_merge 实际生效、step_chain 修复、score fusion entity 分量
- 新增 `tests/test_postprocess_evidence.py` 专门测试后处理管线

**接口影响：**
- rag_trace 字段新增：`auto_merge_replaced_chunks` 真实化、`step_chain_check_enabled`、`step_chain_completion_count`、`step_chain_repaired_groups`、`rerank_candidate_pool_size`、`entity_metadata_score_applied`
- 现有 `auto_merge_applied` 字段语义不变，但首次能反映真实值

**依赖：**
- 软依赖 `rag-maintainability-chunker` 阶段 1（list_group_id 字段）—— step_chain_check 在缺少这些字段时降级为 no-op
- 软依赖 `rag-terminology-module`（entity_types / term_match_count）—— score fusion 在缺少这些字段时使用旧行为

**风险与回归：**
- auto_merge 修复后会改变检索结果（之前 top_k 是 5 个 leaf；之后可能是 3 个 leaf + 2 个 parent，整体 token 数变化）。需要评测验证回答质量不降。
- rerank 输出量增大会增加 structure_rerank 的计算量，需要监控 P95 延迟。
