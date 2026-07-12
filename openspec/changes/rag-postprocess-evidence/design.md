## Context

当前 `_finish_retrieval_pipeline()`（位于 `backend/rag/utils.py` 第 265-396 行）的真实顺序：

```
rerank → structure_rerank → confidence_gate → 输出 top_k
```

`_auto_merge_documents()` 在 `backend/rag/utils.py:690` 定义、`backend/rag/context.py:49` 实现，但 grep 全仓没有任何调用点。`pipeline.py:281-285` 的 `emit_rag_step("🧩", "Auto-merging 合并", ...)` 显示的是 metadata 字段，而 metadata 永远填 false（来自 failure 模板）。

`_effective_rerank_top_n()` 实现：

```python
def _effective_rerank_top_n(top_k: int, candidate_count: int) -> int:
    if candidate_count <= 0:
        return 0
    requested = RERANK_TOP_N if RERANK_TOP_N > 0 else top_k
    requested = max(top_k, requested)
    return min(candidate_count, requested)
```

`RERANK_TOP_N` 默认 0，所以 rerank 输出就是 top_k（5）。这导致即使把 auto_merge 接入，可消化的素材也极少（5 个 leaf 全部合并到 1 个 parent 后，只剩 1 个证据）。

设计文档（融合方案 4.10）原本把 EvidenceBuilder 写成一个新增模块，但讨论中你的判断是：**它不是独立模块，而是后处理管线整体的代号**。因此本 change 修复管线本身，而不是添加新模块。

## Goals / Non-Goals

**Goals：**
- 让 auto_merge 真正工作：rerank 输出 → auto_merge 合并 → 后续阶段消化
- 给后处理管线留出消化候选的预算（rerank 输出 ≠ top_k）
- 引入步骤链完整性检查作为后处理的一环（不强行新增模块）
- 把所有后处理阶段的耗时和操作统计暴露到 trace
- 修复后回归覆盖：现有 RAG 测试集结果不显著变差，维修步骤召回质量提升

**Non-Goals：**
- 不重写 rerank 算法（仍用现有 CrossEncoder + score fusion）
- 不引入新的 LLM 调用（后处理保持纯算法）
- 不改变 Milvus 检索结果数量（candidate_k 不变；本 change 只动 rerank 之后的事）
- 不在本 change 引入 entity 信号的 score fusion 默认启用（保留为可选项，避免不可控回归）

## Decisions

### 决策 1：管线新顺序

```
retrieve_initial (Milvus hybrid retrieval, 输出 candidate_k=50)
    ↓
rerank (CrossEncoder, 输出 candidate_pool_size=20)
    ↓
auto_merge (leaf → parent 合并, 输出可能减少)
    ↓
step_chain_check (步骤链完整性, 可能拉取相邻 parent)
    ↓
structure_rerank (root 多样性, 应用 final_score)
    ↓
top_k_truncate (截断到 top_k=5)
    ↓
confidence_gate (评估 fallback_required 信号)
```

每阶段输入输出明确，可单独 unit test。

### 决策 2：rerank 候选池配置

新增 `RERANK_CANDIDATE_POOL_SIZE`（默认 20）。`_effective_rerank_top_n()` 重命名为 `_effective_rerank_output_size()` 并改逻辑：

```python
def _effective_rerank_output_size(top_k: int, candidate_count: int) -> int:
    """rerank 实际输出量,给后续阶段留消化空间"""
    if candidate_count <= 0:
        return 0
    pool_size = RERANK_CANDIDATE_POOL_SIZE if RERANK_CANDIDATE_POOL_SIZE > 0 else top_k * 4
    pool_size = max(top_k, pool_size)
    return min(candidate_count, pool_size)
```

`RERANK_TOP_N` 配置保留兼容（如果设置则覆盖 candidate_pool_size），并在 deprecation note 中标记 v2 废弃。

### 决策 3：auto_merge 接入位置和职责

修改 `_finish_retrieval_pipeline()`：

```python
# rerank
reranked, rerank_meta = _rerank_documents(query=query, docs=retrieved, top_k=candidate_pool_size)

# auto_merge (新增调用)
merged, merge_meta = _auto_merge_documents(reranked, top_k=candidate_pool_size)

# step_chain_check (新增)
repaired, chain_meta = _step_chain_check(merged, top_k=candidate_pool_size)

# structure_rerank
reranked_docs, structure_meta = _apply_structure_rerank(repaired, top_k=candidate_pool_size)

# top_k 截断
final_docs = reranked_docs[:top_k]

# confidence_gate
confidence_meta = _evaluate_retrieval_confidence(query=query, docs=final_docs)
```

`_auto_merge_documents` 当前实现已能工作（context.py:49 的 `auto_merge_documents`），只需正确调用并把 merge_meta 合并到 rerank_meta。

### 决策 4：step_chain_check 算法

依赖 `list_group_id` / `list_order` / `list_complete` metadata（由 `rag-maintainability-chunker` 写入）。算法：

```python
def _step_chain_check(docs: list[dict], top_k: int) -> tuple[list[dict], dict]:
    """检查步骤链完整性，必要时拉取相邻 parent"""
    if not STEP_CHAIN_CHECK_ENABLED:
        return docs, {"step_chain_check_enabled": False}

    repaired_groups = []
    new_docs = list(docs)
    for doc in docs[:top_k]:
        list_group_id = doc.get("list_group_id")
        list_order = doc.get("list_order")
        list_complete = doc.get("list_complete", True)
        if not list_group_id or list_complete:
            continue
        # 不完整的列表组,拉取相邻 parent
        adjacent_orders = _adjacent_orders(list_order, STEP_CHAIN_ADJACENT_LOOKBACK)
        adjacent_chunks = _fetch_adjacent_chunks(list_group_id, adjacent_orders)
        for adj in adjacent_chunks:
            if adj["chunk_id"] not in {d["chunk_id"] for d in new_docs}:
                new_docs.append(adj)
        repaired_groups.append(list_group_id)

    return new_docs, {
        "step_chain_check_enabled": True,
        "step_chain_repaired_groups": repaired_groups,
        "step_chain_completion_count": len(repaired_groups),
    }
```

`_fetch_adjacent_chunks` 使用两跳查询。Milvus 正常只索引 leaf，不存储完整 parent：

1. leaf 保留原始列表项的 `list_order`，另写入 1-based `parent_list_order` 表示所属 parent subgroup；
2. Milvus 按 filename + index_profile + list_group_id + parent_list_order 查询 leaf metadata，只返回并去重 `parent_chunk_id`；
3. ParentChunkStore 按这些 ID 批量加载完整 parent，并按目标 parent order 返回。

因此“通过 Milvus query 拉取相邻 parent”是“Milvus 定位 + ParentChunkStore hydrate”的两跳契约，
不是要求 Milvus 直接存在 `chunk_level=1` 的记录。控制 lookback 窗口（默认 ±2）避免无限扩散。

同一 `(filename, index_profile, list_group_id)` 在 top-K 中可能同时出现多个不完整 parent。
实现必须累积该 scope/group 的全部 `list_order`，合并各自 lookback 邻域并去重后执行一次 Milvus
查询；不得只保留第一个 order。`step_chain_repaired_groups` 仍按 group 记录一次。

### 决策 5：metadata 缺失时的降级

当 chunk 没有 list_group_id（来自旧 profile 或 chunker 早期阶段）时：
- `_step_chain_check` 跳过该 chunk，不报错
- trace 字段 `step_chain_check_enabled = True` 但 `step_chain_repaired_groups = []`

当 chunk 没有 parent_chunk_id 时：
- `_auto_merge_documents` 跳过该 chunk（已实现）
- trace 字段 `auto_merge_applied = false` 反映真实状态

这保证本 change 在 chunker 早期阶段也能上线，不强依赖 chunker 完成。

### 决策 6：entity 信号的 score fusion 集成

`backend/rag/rerank.py`（或 `utils.py` 中的 score fusion 函数）当前 metadata 维度的实现是占位的（看了代码 `RERANK_FUSION_METADATA_WEIGHT=0.05` 但 fusion 函数对 metadata 分量没有真实计算逻辑）。

本 change 引入：

```python
def _metadata_score(doc: dict, query_entities: list[EntityMatch]) -> float:
    """基于 entity 命中密度计算 metadata 分量"""
    if not query_entities or not doc.get("entity_types"):
        return 0.0
    query_types = {e.type for e in query_entities}
    doc_types = set(doc.get("entity_types") or [])
    type_coverage = len(query_types & doc_types) / max(len(query_types), 1)
    match_density = min(doc.get("term_match_count", 0) / 5.0, 1.0)
    return 0.7 * type_coverage + 0.3 * match_density
```

接入到 score fusion：

```python
final_score = (
    rerank_w * normalized_rerank_score +
    rrf_w * rrf_score +
    scope_w * scope_score +
    metadata_w * metadata_score
)
```

默认行为：
- terminology 模块未上线时，`query_entities` 为空，`metadata_score = 0`，与现状等价
- terminology 上线后，自动接入，无需额外开关

#### entity_types 的存储与运行时边界

`rag-terminology-module` 已规定 Milvus 中的 `entity_types` wire format 为 VARCHAR JSON string；
后处理算法使用的 runtime format 则统一为去重后的 `list[str]`。两者 MUST 在 vector-store
适配边界完成转换：

- ingestion writer 与 terminology rescan 统一调用共享 encoder，写入 JSON string；
- hybrid、split dense/sparse、dense fallback 的结果适配统一调用共享 decoder；
- decoder 在迁移期兼容历史 dynamic-field list 值，非法 JSON 安全降级为空列表；
- rerank fusion 与 rerank cache signature 使用同一个 decoder，避免 JSON 字符串被逐字符遍历；
- 本 change 不把 dynamic field 迁移为显式 VARCHAR schema，也不要求立即重建历史 collection。

这个边界保证“存储表示”不会泄漏到 score fusion，并允许旧 list 行与新 JSON-string 行在
同一个 collection 中平滑共存。

### 决策 7：trace 字段扩展

新增字段：

```
auto_merge_applied (bool, 真实值)
auto_merge_replaced_chunks (int, 真实值)
auto_merge_ms (float)

step_chain_check_enabled (bool)
step_chain_repaired_groups (list[str])
step_chain_completion_count (int)
step_chain_ms (float)

rerank_candidate_pool_size (int)
rerank_output_count (int, 真实值, 等于 candidate_pool_size 或 candidate_count)

entity_metadata_score_applied (bool, terminology 上线后为 true)
```

旧字段语义不变，只是首次能反映真实运行结果。

## Risks / Trade-offs

**风险 1：auto_merge 修复后召回内容变化**

之前 top_5 是 5 个 leaf chunk；修复后可能是 3 个 leaf + 2 个 parent chunk。parent chunk 文本更长、信息密度更高，但也可能稀释 query 相关性。回答质量可能升或降。

缓解：
- 用现有 `tests/test_rag_pipeline.py` 作为 baseline
- 加入 `tests/test_postprocess_evidence.py` 跑维修步骤类样本，对比修复前后召回质量
- 上线初期保留 `AUTO_MERGE_ENABLED=false` 的开关选项（虽然违背修复初衷），允许快速回滚

**风险 2：rerank 候选池扩大导致 P95 延迟上升**

CrossEncoder rerank 时间线性正比于输入数量。从 top_k=5 改为 pool_size=20，rerank 时间约 4 倍。

缓解：
- `RERANK_INPUT_K_CPU`、`RERANK_INPUT_K_GPU` 配置仍生效，可设上限
- structure_rerank 计算量也变大，但纯 Python 操作，影响小
- 监控 P95 延迟，必要时降低 `RERANK_CANDIDATE_POOL_SIZE` 到 10-15

**风险 3：step_chain_check 的两跳查询开销**

每次检测到不完整列表组都会先查询 Milvus leaf metadata，再批量读取 ParentChunkStore。极端情况（多个失败步骤组）会引入多次额外查询。

缓解：
- lookback 窗口默认 ±2 限制扩散
- Milvus 使用窄 metadata filter 且只返回 parent 引用；ParentChunkStore 按去重 ID 批量读取
- 监控 `step_chain_ms` trace 字段，超过阈值时告警

**风险 4：chunker 阶段 1 未完成时 step_chain_check 是空 op**

chunker 未上线前，所有 chunk 的 list_group_id 都为空，step_chain_check 永远不触发。本 change 在 chunker 之前上线时，step_chain_check 功能是死代码。

缓解：
- 本 change 在 chunker 之前上线时，把 STEP_CHAIN_CHECK_ENABLED 默认值设为 false
- chunker 阶段 1 完成后，发独立小 change 开启 STEP_CHAIN_CHECK_ENABLED
- step_chain_check 代码本身可独立测试（用 mock chunk 验证算法）

**Trade-off：candidate_pool_size 选 15 vs 20**

更大候选池 → 更多 auto_merge 素材 → 更完整证据合并；但成本更高。
更小候选池 → rerank 快但合并素材有限。

v1 选 20 作为默认，预期单次 RAG 增加 ~50ms（rerank 慢 30ms + 后处理慢 20ms）。如评测显示边际收益递减，下调到 15。

## 依赖与衔接

- **软依赖 `rag-maintainability-chunker` 阶段 1**：step_chain_check 需要 list_group_id / parent_list_order 字段；缺失时降级为 no-op
- **软依赖 `rag-terminology-module`**：score fusion 的 entity 分量需要 entity_types / term_match_count 字段；缺失时分量为 0
- **被 `rag-multilevel-fallback` 依赖**：Level 2 scope relax 依赖本 change 的 confidence_gate 输出
- **与 `rag-intent-routing` 协同**：intent 中的 entities 传给 score fusion 作为 query_entities

本 change 可独立先行（先修死代码 + 解耦候选池），step_chain 和 entity_score 部分待其他 change 推进后再开启。
