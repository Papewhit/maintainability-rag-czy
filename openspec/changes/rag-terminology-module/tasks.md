## 1. Milestone M1：术语表存储与加载

- [ ] 1.1 定义 `TerminologyEntry` 数据类和数据库表 `terminology_entries`（`backend/infra/db/models.py`）
- [ ] 1.2 数据库 migration 脚本（如使用 alembic）或 `init_db()` 中创建表
- [ ] 1.3 `TerminologyTable` 内存表示：构建 `_by_canonical`、`_surface_to_canonical`、Aho-Corasick 自动机
- [ ] 1.4 启动时加载：在 `backend/app.py` 的 lifespan 中调用 `TerminologyTable.reload_from_db()`
- [ ] 1.5 单元测试：术语表 CRUD、加载性能、最长匹配正确性

**验收**：启动时术语表加载到内存；通过 API 添加/删除条目后内存与 DB 一致；scan_text 对样例文本返回正确的最长匹配结果。

## 2. Milestone M2：jieba userdict 注入

- [ ] 2.1 实现 `build_jieba_userdict(table)` 输出标准 jieba 词典文件
- [ ] 2.2 实现 `reload_jieba_with_terminology(table)` 调用 `jieba.load_userdict`
- [ ] 2.3 EmbeddingService 初始化前调用 reload 一次，保证 BM25 indexing 用受保护的分词
- [ ] 2.4 单元测试：注入前 "主减速齿轮箱" 被切碎；注入后保持完整
- [ ] 2.5 删除术语后重载，测试旧术语不再受保护（处理 jieba 累加问题）

**验收**：jieba 分词在术语注入前后行为可控；BM25 vocab 中包含完整术语作为独立 token。

## 3. Milestone M3：Query 时术语扫描（preflight）

- [ ] 3.1 在 `backend/rag/query_plan.py` 增加 `terminology_preflight(query) -> QueryTerminologyResult`
- [ ] 3.2 QueryTerminologyResult 字段：`query_entities`、`normalized_query`、`sparse_expansion`、`protected_tokens`
- [ ] 3.3 接入到 RAG preflight 阶段（在 intent classifier 之前或并行，preflight 不依赖 LLM）
- [ ] 3.4 trace 增加字段：`term_matches`、`sparse_expansion`、`normalized_query`
- [ ] 3.5 单元测试：覆盖中英文混合、变体替换、未命中场景

**验收**：用户 query 经过 preflight 后产出 normalized 形式和 sparse 扩展；trace 字段齐全；BM25 查询用 sparse_expansion 后召回率提升（用维修领域样例验证）。

## 4. Milestone M4：Index 时术语扫描（chunk metadata）

- [ ] 4.1 修改 `DocumentLoader`（或 Chunker 完成后由 chunker 调用）：每个 chunk 生成后调用 `matcher.scan_text(chunk.retrieval_text)`
- [ ] 4.2 Milvus schema 增加字段：`entity_types`（VARCHAR JSON）、`term_match_count`（INT64）
- [ ] 4.3 ParentChunkStore 增加字段：`term_matches`、`protected_tokens`
- [ ] 4.4 schema 变更通过新 `RAG_INDEX_PROFILE` 名称切换（如 `v4_terminology`），旧 collection 保留
- [ ] 4.5 索引服务的批量上传逻辑同步写入两层存储
- [ ] 4.6 集成测试：上传一篇含术语的样本文档，验证 chunk metadata 中 entities 正确

**验收**：新 profile collection 中 chunk 的 entity_types 和 term_match_count 字段正确；parent store 中 term_matches 完整。

## 5. Milestone M5：管理员 CRUD API

- [ ] 5.1 新增 `backend/routers/admin_terminology.py`：GET（列表 + 单条）、POST（新建）、PUT（更新）、DELETE
- [ ] 5.2 权限要求 admin（复用现有 admin guard）
- [ ] 5.3 批量导入接口 `POST /admin/terminology/bulk`，接受 CSV 或 JSON 数组
- [ ] 5.4 输入校验：canonical 非空、entity_type 在枚举内、variants 去重
- [ ] 5.5 写操作触发内存表重建（不触发 rescan，rescan 是独立动作）
- [ ] 5.6 audit log：每次写操作记录 user_id、动作、术语条目快照
- [ ] 5.7 API 测试：CRUD 全覆盖、权限校验、批量导入边界

**验收**：管理员可通过 API 维护术语表；变更立刻反映到内存表；查询不受影响（rescan 之前不更新 chunk metadata）。

## 6. Milestone M6：Rescan 任务

- [ ] 6.1 实现 `RescanTask`（异步后台任务，使用 asyncio 或独立线程池）
- [ ] 6.2 任务流程：加锁 → 重载 jieba → 遍历 chunk → 扫描更新 metadata → 重建 BM25 → 解锁
- [ ] 6.3 状态表 `rescan_tasks`：task_id、status、started_at、ended_at、processed_chunks、total_chunks、error
- [ ] 6.4 API `POST /admin/terminology/rescan` 触发任务，返回 task_id
- [ ] 6.5 API `GET /admin/terminology/rescan/{task_id}` 查询进度
- [ ] 6.6 BM25 重建用 `bm25_state.new.json` 临时文件，完成后原子 rename
- [ ] 6.7 失败时回滚（BM25 旧 state 保留备份）
- [ ] 6.8 集成测试：术语表新增条目 → 触发 rescan → 验证 chunk metadata 和 BM25 vocab 都更新

**验收**：rescan 任务能在 collection 上完整跑一遍；失败时不破坏现有状态；进度可查询。

## 7. Milestone M7：默认术语表 seed + 文档化

- [ ] 7.1 准备初始术语表 seed（船舶维修性领域常见术语，至少 200 条），落到 `data/terminology_seed.csv`
- [ ] 7.2 启动脚本检测术语表为空时自动加载 seed
- [ ] 7.3 撰写管理员文档：术语表管理流程、rescan 操作指南、常见问题
- [ ] 7.4 撰写开发者文档：terminology 模块 API、扩展新 entity_type 的步骤

**验收**：新部署的环境能开箱即用（带 seed 数据）；管理员能根据文档完成日常维护。
