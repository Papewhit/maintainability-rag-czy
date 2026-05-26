## ADDED Requirements

### Requirement: 术语表存储
系统 MUST 维护一份持久化的术语表，每条术语 MUST 包含 canonical 形式、entity_type、variants 列表、可选的描述和 metadata 扩展字段。术语表 SHALL 存储在数据库中，启动时全量加载到内存。

#### Scenario: 术语条目唯一性
- **WHEN** 管理员尝试创建一条 `(entity_type=component, canonical=主减速齿轮箱)` 的条目，但该 (entity_type, canonical) 组合已存在
- **THEN** API 返回 409 Conflict；现有条目保持不变；audit log 记录失败的尝试

#### Scenario: variants 自动归一化
- **WHEN** 管理员提交一条术语，variants 中包含重复值或空字符串
- **THEN** 系统自动去重并过滤空值后存储；返回 201 时附带实际存储的 variants 列表

#### Scenario: 启动时加载
- **WHEN** 服务进程启动，lifespan 钩子执行
- **THEN** TerminologyTable 从数据库读取所有条目，构建内存索引（by_canonical / surface_to_canonical / Aho-Corasick），耗时不超过 5 秒（5000 条规模）

### Requirement: jieba 分词保护
术语表中所有 canonical 形式和 variants MUST 注入 jieba 用户词典，确保 BM25 索引和 query 分词时多字术语 SHALL 保持完整。

#### Scenario: 索引时分词保护
- **WHEN** EmbeddingService 对包含 "主减速齿轮箱" 的 chunk 文本调用 BM25 indexing
- **THEN** "主减速齿轮箱" 作为单个 token 出现在 vocab 中；不会被切分为 "主"/"减速"/"齿轮箱"

#### Scenario: query 时分词保护
- **WHEN** 用户 query "主减速齿轮箱拆卸" 经过 BM25 查询路径
- **THEN** "主减速齿轮箱" 作为单个 token 与索引中的 token 直接匹配，召回包含该术语的 chunk

#### Scenario: 术语删除后分词
- **WHEN** 管理员删除术语 "主减速齿轮箱"，触发 rescan 完成
- **THEN** 新的 query 中 "主减速齿轮箱" 按 jieba 默认词典切分；旧 BM25 state 已重建为切碎后的形式

### Requirement: 索引时术语扫描
Chunker（或 DocumentLoader 后置处理）生成每个 chunk 时 MUST 扫描 chunk 的 retrieval_text，识别命中的术语并写入 metadata。扫描结果 SHALL 分两层存储：核心字段进 Milvus，完整 JSON 进 ParentChunkStore。

#### Scenario: 多术语命中
- **WHEN** chunk 文本 "XYZ123-A 主减速齿轮箱拆卸时使用扳手"，且术语表中包含相应条目
- **THEN** chunk.metadata 中 `entity_types = ["product_model", "component", "maintenance_action"]`、`term_match_count = 3`；parent store 中 `term_matches` 包含 3 条详细记录（带 surface/canonical/type/start/end）

#### Scenario: 最长匹配优先
- **WHEN** 术语表同时包含 "齿轮箱" 和 "主减速齿轮箱"，chunk 文本包含 "主减速齿轮箱"
- **THEN** 扫描结果中只包含 "主减速齿轮箱"（最长匹配），不重复记录 "齿轮箱"

#### Scenario: 无命中
- **WHEN** chunk 文本不包含任何术语
- **THEN** `entity_types = []`、`term_match_count = 0`；parent store 中 `term_matches = []`、`protected_tokens = []`

### Requirement: 查询时术语扩展
Preflight 阶段 MUST 对用户 query 进行术语扫描，输出 query_entities、normalized_query、sparse_expansion 三类结果供下游使用。

#### Scenario: query 包含变体
- **WHEN** 用户 query "MRG 拆卸怎么做"，术语表中 MRG 是 "主减速齿轮箱" 的 variant
- **THEN** query_entities 包含 `{type=component, canonical=主减速齿轮箱, surface=MRG}`、`{type=maintenance_action, canonical=拆卸, surface=拆卸}`；normalized_query 为 "主减速齿轮箱拆卸怎么做"；sparse_expansion 包含所有 variant 的并集（"主减速齿轮箱 主齿轮箱 主减速器 MRG main reduction gearbox 拆卸 分解 拆解 disassembly"）

#### Scenario: query 无术语命中
- **WHEN** 用户 query 不含任何术语表内的词
- **THEN** query_entities 为空列表；normalized_query 等于原 query；sparse_expansion 等于原 query

### Requirement: Metadata 字段分层存储
术语扫描的结果 MUST 按使用场景分层存储：参与检索/过滤的核心字段 SHALL 进 Milvus（保持定长），完整证据 JSON SHALL 进 ParentChunkStore。

#### Scenario: Milvus 字段
- **WHEN** 索引新 chunk 到 Milvus
- **THEN** Milvus schema 中包含 `entity_types`（VARCHAR）和 `term_match_count`（INT64）；entity_types 序列化为 JSON 字符串数组，长度不超过 512 字节

#### Scenario: ParentChunkStore 字段
- **WHEN** chunk 上传到 ParentChunkStore
- **THEN** 记录中包含 `term_matches`（完整 JSON 数组，每项含 surface/canonical/type/start/end）、`protected_tokens`（多字术语字符串列表）

### Requirement: Rescan 任务
术语表变更后，系统 SHALL 提供 rescan 任务用于更新 collection 全部 chunk 的 metadata 和 BM25 state，且 MUST NOT 重新切 chunk。任务 MUST 异步执行，进度 MUST 可查询。

#### Scenario: 触发 rescan
- **WHEN** 管理员调用 `POST /admin/terminology/rescan`
- **THEN** 系统返回 task_id；后台任务开始执行；写锁阻塞术语表 CRUD 和文档上传

#### Scenario: rescan 流程
- **WHEN** rescan 任务执行
- **THEN** 任务依次完成：重载 jieba userdict、遍历全部 chunk 重扫 metadata、upsert Milvus 和 ParentChunkStore、重建 BM25 state（用临时文件 + 原子 rename）、释放锁

#### Scenario: 进度查询
- **WHEN** 管理员调用 `GET /admin/terminology/rescan/{task_id}`
- **THEN** 返回任务当前 status（running/completed/failed）、processed_chunks、total_chunks、started_at、ended_at（如已结束）、error（如失败）

#### Scenario: 失败回滚
- **WHEN** rescan 任务中途失败
- **THEN** Milvus 和 BM25 状态回滚到任务开始前的快照；任务状态标记为 failed 并记录 error 详情；管理员可查看失败原因

### Requirement: 管理员 API
术语表 MUST 通过受 admin 权限保护的管理接口维护（具体风格 REST / CLI / Admin UI 由实现阶段决定），SHALL 支持基本 CRUD 和导入导出。所有写操作 MUST 记入 audit log。

#### Scenario: 单条 CRUD
- **WHEN** 管理员对术语表执行 GET/POST/PUT/DELETE
- **THEN** API 校验 admin 权限；变更同步到内存表；audit log 记录 user_id、操作类型、变更前后快照

#### Scenario: 批量导入
- **WHEN** 管理员上传 CSV 或 JSON 数组到 `POST /admin/terminology/bulk`
- **THEN** 系统逐条验证（canonical 非空、entity_type 在枚举内、variants 去重），返回每条的成功/失败状态；audit log 记录批量操作的 summary

#### Scenario: 权限校验
- **WHEN** 非 admin 用户访问任何 `/admin/terminology/*` 端点
- **THEN** 返回 403 Forbidden

### Requirement: Trace 字段
RAG 请求的 rag_trace MUST 包含术语扫描相关字段，用于调试和评测。

#### Scenario: Query 扫描 trace
- **WHEN** preflight 完成术语扫描
- **THEN** rag_trace 包含 `term_matches`（query 命中的术语列表）、`sparse_expansion`（扩展后的 sparse 查询字符串）、`normalized_query`、`protected_tokens`

#### Scenario: Chunk 扫描 trace（已落到 metadata）
- **WHEN** 检索结果包含 chunk
- **THEN** chunk 的 trace 表示中包含 `entity_types`、`term_match_count`（来自 Milvus metadata）；rerank 阶段可使用这两个字段
