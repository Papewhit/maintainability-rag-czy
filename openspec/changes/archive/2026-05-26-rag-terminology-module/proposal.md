## Why

船舶维修性设计领域的专业术语存在大量变体表达：
- **同义别称**：主减速齿轮箱 ↔ 主齿轮箱 ↔ 主减速器
- **中英文互替**：主减速齿轮箱 ↔ main reduction gearbox ↔ MRG
- **内部语序交换**：齿轮箱主减速 ↔ 主减速齿轮箱
- **型号缩写**：XYZ123 ↔ XYZ123-A ↔ XYZ123A

当前 RAG 链路对这些变体完全无感：
1. embedder（bge-m3）未做领域微调，dense 向量不能稳定捕捉同义关系
2. sparse 索引基于 jieba 分词，多字术语被切碎（"主减速齿轮箱" → ["主", "减速", "齿轮箱"]），导致召回稀释和噪声放大
3. QueryPlan 没有规范化能力，无法把用户的变体输入映射到 canonical 形式
4. rerank 无领域信号，对"chunk 是否包含正确实体"无判断依据

结果是：用户用 A 形式查询，文档用 B 形式撰写时，召回率显著下降；fallback 也无法系统性地修复（因为 fallback 重写 LLM 也不知道哪些是同义词）。

## What Changes

引入贯穿索引和查询两侧的术语模块：

1. **术语表（Terminology Table）**：管理员维护的 canonical → variants 映射，分实体类型（产品型号/设备/组件/参数/维修动作），落到数据库表 + 启动时加载到内存。
2. **jieba userdict 注入**：术语表所有 canonical 和 variants 注入 jieba 用户词典，保证多字术语在 BM25 索引和 query 分词时不被切碎。
3. **索引时扫描（Chunker 内嵌）**：chunker 在生成 chunk 时顺手扫描 chunk body，记录命中的术语到 `chunk.metadata.entities`，包含 type/canonical/matched_surface/positions。
4. **查询时扩展（Preflight 阶段）**：preflight 阶段对 query 做最长匹配术语扫描，输出：
   - `query_entities`：query 中提取的实体（供 intent classifier 和 retrieval 使用）
   - `normalized_query`：替换变体为 canonical 后的查询（用于 dense 检索的语义聚焦）
   - `sparse_expansion`：所有变体并入的 sparse 查询字符串（用于 BM25 robust 召回）
5. **术语表更新触发 rescan**：管理员更新术语表后，后台任务遍历当前 collection 全部 chunk，重扫 metadata.entities，同时触发 BM25 state 重建。**不重切 chunk**。

## Capabilities

### New Capabilities
- `rag-terminology-module`: 术语表存储、jieba 注入、索引/查询双向扫描、rescan 任务

### Modified Capabilities
<!-- 当前 openspec/specs/ 为空 -->

## Impact

**代码影响：**
- 新增 `backend/rag/terminology/` 包：
  - `table.py`：术语表数据模型 + DB 表 + CRUD API
  - `matcher.py`：Aho-Corasick 多模式最长匹配实现（用 `pyahocorasick` 或纯 Python 兜底）
  - `jieba_dict.py`：jieba userdict 构建和热重载
  - `rescan.py`：术语表变更后的 collection 全量扫描任务
- 修改 `backend/infra/embedding.py`：BM25 初始化前先加载 jieba userdict
- 修改 `backend/documents/loader.py`（或后续 chunker 改造时）：chunk 生成后调用 matcher 写入 entities metadata
- 修改 `backend/rag/query_plan.py`：preflight 增加术语扫描，输出 query_entities + normalized_query + sparse_expansion
- 修改 `backend/infra/vector_store/milvus_client.py`：schema 增加 `entity_types`（JSON array）和 `term_match_count`（int）字段；parent chunk store 增加 `term_matches`（完整 JSON）和 `protected_tokens` 字段
- 新增 `backend/routers/admin_terminology.py`：管理员 API 用于增删改查术语
- 新增 `tests/test_terminology_matcher.py`、`tests/test_terminology_rescan.py`

**接口影响：**
- 新增管理员 API：`GET/POST/PUT/DELETE /admin/terminology/{entity_type}`，权限要求 admin
- 新增管理员 API：`POST /admin/terminology/rescan`，触发后台 rescan 任务，返回 task_id 用于轮询
- `rag_trace` 增加字段：`term_matches`（query 命中的术语列表）、`sparse_expansion`（扩展后的 sparse 查询）

**依赖：**
- 新依赖：`pyahocorasick`（可选优化，pure Python 兜底）
- 依赖现有 `jieba`、Milvus upsert 能力（chunk metadata 局部更新）

**数据迁移：**
- Milvus schema 变更需要重建 collection（通过 `RAG_INDEX_PROFILE` 切换新 profile）；术语模块上线前的旧 collection 保留兼容
- 初始术语表数据需要管理员手工导入或从既有词表 CSV 批量上传
