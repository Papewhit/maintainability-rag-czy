## 1. Milestone M1：Fallback Router 与决策骨架

- [ ] 1.1 新增 `backend/rag/fallback_router.py`：`FallbackDecision` 数据类、`route_fallback()` 函数
- [ ] 1.2 实现信号到 level 映射规则（无 LLM，纯规则）
- [ ] 1.3 预算检查逻辑：根据 remaining_budget 跳级到 Level 3
- [ ] 1.4 attempted_levels 追踪：防止重复进入同一 level
- [ ] 1.5 单元测试覆盖所有规则分支
- [ ] 1.6 新增配置 `RAG_FALLBACK_TOTAL_BUDGET_MS` / `RAG_FALLBACK_LEVEL1_BUDGET_MS` / `RAG_FALLBACK_LEVEL2_BUDGET_MS`

**验收**：fallback router 函数可独立测试；所有信号组合都有明确的 target_level；trace 字段齐全。

## 2. Milestone M2：Graph 结构调整

- [ ] 2.1 在 `backend/rag/pipeline.py` 重构 graph：
  - 新节点 `fallback_router_node`（消费 confidence gate 输出，决定 level）
  - 新节点 `level1_query_rewrite_node`（按 plan_type 内部分支）
  - 新节点 `level2_scope_relax_node`
  - 新节点 `level3_insufficient_evidence_node`
- [ ] 2.2 condition edges：从 grade_documents 之后调用 fallback_router_node；按其输出路由到对应 level node
- [ ] 2.3 每个 level node 完成后回到 fallback_router_node 再决定下一步（直到 Level 3 或预算耗尽）
- [ ] 2.4 RAGState 新增字段：`fallback_decisions: list[FallbackDecision]`、`attempted_levels: list[int]`
- [ ] 2.5 端到端测试：构造各种信号组合，验证 graph 走对路径
- [ ] 2.6 集成测试确认进入 fallback 前已完成结构清洗、terminology preflight 与 dense+BM25 query composition；Level 1/2 重检不得把检索输入恢复为 raw query

**验收**：graph 可视化输出清晰；多 level 路径在测试中正确执行；现有 RAG 测试不破坏。

## 3. Milestone M3：Level 1 - 精确管线 rewrite

- [ ] 3.1 沿用现有 `rewrite_question_node` 的 step_back / hyde / complex 逻辑
- [ ] 3.2 prompt 改写：把原始 query、PreciseQueryPlan 的 anchors、doc_hints 和 scope 状态注入 rewrite prompt
- [ ] 3.3 入口检查 budget：超预算直接降 Level 3
- [ ] 3.4 trace 字段：`level1_strategy`、`level1_ms`、`level1_rewritten_query`
- [ ] 3.5 测试：mock confidence 信号触发 Level 1，验证 strategy 选择和 rewritten_query 生成

**验收**：精确管线在 Level 1 触发后能产生合理 rewritten_query；现有 step_back/hyde 行为兼容。

## 4. Milestone M4：Level 1 - 综合管线 rewrite

- [ ] 4.1 新增 `backend/rag/comprehensive_rewriter.py`：合并的 router + rewriter LLM 调用
- [ ] 4.2 prompt 设计：以完整 plan、失败 LLM sub_query、failure_signal、succeeded_sub_queries 为输入；拒绝 branch_kind=baseline
- [ ] 4.3 输出 schema：strategy + new_sub_queries + reason
- [ ] 4.4 接入 `level1_query_rewrite_node` 的 comprehensive 分支
- [ ] 4.5 sub_query 级 fallback：只对失败的 LLM sub_query rewrite，其他保留；clean-query baseline 永不写入或替换 sub_queries，重试时从 plan.clean_query 原样重建
- [ ] 4.6 单元测试：mock LLM 输出各种 strategy，验证 plan 更新正确；baseline 失败只记录 diagnostics 且不会调用 rewriter
- [ ] 4.7 trace 字段：`level1_comprehensive_strategy`、`level1_new_sub_queries`、`level1_sub_query_replaced`

**验收**：综合管线在 Level 1 能针对失败 sub_query 做策略化重写；不重复其他成功 sub_query 的工作。

## 5. Milestone M5：Level 2 - Scope Relax

- [ ] 5.1 实现 `relax_scope(query_plan)` 纯规则函数（按 plan_type 分支）
- [ ] 5.2 candidate_k 放大 1.5x 的检索调用包装
- [ ] 5.3 同 root cap 临时放宽（structure_rerank 参数）
- [ ] 5.4 接入 `level2_scope_relax_node`
- [ ] 5.5 trace 字段：`level2_relaxations`（list[str]）、`level2_new_scope_mode`、`level2_ms`
- [ ] 5.6 综合管线版本：每个 LLM sub_query 独立放宽 structure scope；baseline 使用放宽后的共享结构约束重建但保持 plan.clean_query 文本；保持 intent-routing 已解析的 comprehensive postprocess profile 完整不变，不在 fallback 节点内替换 profile 组件
- [ ] 5.7 测试：scope_mode 从 filter → boost → none 的降级正确
- [ ] 5.8 测试：Level 2 不读取或修改 semantic entities，terminology 的 `entity_type_coverage` 不参与 scope-relax 路由

**验收**：Level 2 后召回数量明显增加；scope_mode 降级链路完整；trace 反映放宽细节。

## 6. Milestone M6：Level 3 - Insufficient Evidence

- [ ] 6.1 实现 `generate_level3_answer(query_plan, attempted_levels)` 模板化输出（无 LLM）
- [ ] 6.2 精确管线模板：明确告知当前 query 与结构范围没有足够匹配证据
- [ ] 6.3 综合管线模板：部分覆盖回答 + 未覆盖维度标注；baseline 不计完成维度，baseline-only 时显示 0/Y 并只可标为一般背景证据
- [ ] 6.4 prompt 注入：当 fallback_level=3 时跳过常规 RAG context，使用 Level 3 输出作为最终回答
- [ ] 6.5 trace 字段：`level3_reason`、`level3_attempted_levels`、`level3_uncovered_sub_queries`、`level3_baseline_evidence_used`（comprehensive）
- [ ] 6.6 测试区分：生成分支部分成功、baseline-only、baseline 与全部生成分支均为空；baseline-only 不增加 coverage count

**验收**：Level 3 输出明确、不误导；用户能从回答中看出哪些维度有/无证据。

## 7. Milestone M7：Level 2 prompt 注入

- [ ] 7.1 修改 `prepare_rag_answer_messages`：识别 fallback_level=2 时追加"非精确匹配"声明
- [ ] 7.2 RagTurnContext 增加 `fallback_level` 字段，从 RAGState 传递
- [ ] 7.3 测试：Level 2 触发后 LLM 答案中包含明确的"未找到精确匹配"声明
- [ ] 7.4 文档：在 design.md 或独立 prompt-templates 文档中固化这段 prompt

**验收**：Level 2 答案不误导用户；引用部分清晰标注"参考方案"而非"精确匹配"。

## 8. Milestone M8：emit_rag_step 集成与前端展示

- [ ] 8.1 每个 fallback 节点调用 `emit_rag_step` 发送步骤事件
- [ ] 8.2 步骤事件 schema：`{icon, label, detail, level, signal, strategy?}`
- [ ] 8.3 前端折叠"思考过程"组件：默认折叠，点击展开 fallback 路径
- [ ] 8.4 normal 流程（Level 0 成功）也显示简洁的"检索完成"步骤
- [ ] 8.5 用户体验测试：fallback 多次时前端不卡顿、不闪烁

**验收**：trace 可视化呈现 fallback 路径；用户能直观看到"试了哪些方法"。

## 9. Milestone M9：兼容性与配置迁移

- [ ] 9.1 保留 `RAG_FALLBACK_ENABLED` 作为总开关（=false 时所有 level 跳过，直接 Level 3）
- [ ] 9.2 新增 per-level 开关 `RAG_FALLBACK_LEVEL1_ENABLED` / `RAG_FALLBACK_LEVEL2_ENABLED`，默认 true
- [ ] 9.3 deprecation 警告：`RAG_FALLBACK_ENABLED` 标记 v2 移除
- [ ] 9.4 现有 `RAG_FALLBACK_TIMEOUT_SECONDS` 映射到 `RAG_FALLBACK_TOTAL_BUDGET_MS`（乘 1000）
- [ ] 9.5 文档：升级指南、配置迁移表

**验收**：现有 deployment 在不修改配置时行为不破坏；新配置项有清晰文档。

## 10. Milestone M10：回归与评测

- [ ] 10.1 现有 `tests/test_rag_pipeline.py` 在 fallback 关闭时通过
- [ ] 10.2 新增 `tests/test_multilevel_fallback.py`：mock 各种 confidence 信号组合
- [ ] 10.3 端到端评测：用包含各种失败模式的 query 集（精确未匹配/综合分析/术语变体等）跑完整 fallback 路径
- [ ] 10.4 评测指标：Level 0 命中率、Level 1/2 提升回答质量的比例、Level 3 触发的合理性、P95 延迟
- [ ] 10.5 调优默认 budget：根据评测数据调整 budget_ms

**验收**：评测报告显示 fallback 在合适场景下有效；P95 延迟可控；Level 0/1/2/3 比例符合预期（如 Level 0 ≥ 70%、Level 1+2 ≤ 25%、Level 3 ≤ 5%）。
