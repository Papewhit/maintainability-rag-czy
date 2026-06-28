# rag-maintainability-chunking

维修性文档分块策略：基于 NormalizedDocument 生成 parent/leaf 二级 chunk 结构，保护维修步骤组的完整性，为图文和表格生成专用 parent chunk，并通过阶段化 profile 控制能力上线节奏。所有 chunk 携带完整的 metadata 字段集，核心字段进 Milvus，重字段进 ParentChunkStore。

## Requirements

### Requirement: 维修步骤组保护
Chunker MUST 保证连续编号的维修步骤组不在中间被字符级硬切。当 ListGroup 的总长度超过 token budget 时，SHALL 按一级 list_item 边界切分（子步骤跟随父步骤）。

#### Scenario: 短步骤组单 parent
- **WHEN** ListGroup 总长度小于 token budget
- **THEN** 整个 ListGroup 作为单个 parent chunk；list_complete = true；list_group_id 在该 parent 和其下 leaf 中共享

#### Scenario: 长步骤组按一级切分
- **WHEN** ListGroup 总长度超过 token budget
- **THEN** 按一级 list_item 切分为多个 parent chunk；每个 parent 内子步骤完整保留；list_complete = false；list_group_id 跨 parent 保持一致；list_order 按一级 item 在原 group 中的位置标记

#### Scenario: 维修动作词边界增强
- **WHEN** 一个长段落（非编号列表）包含 "拆卸" "检查" "更换" 等维修动作词
- **THEN** Chunker 可选择在动作词出现位置作为 chunk 边界辅助信号（与字符长度信号共同决策）；动作词不强制切分，仅作为提示

### Requirement: 图文 parent chunk
Chunker MUST 为每个 FigureAssociation 生成一个 figure parent chunk，文本 SHALL 包含 caption + figure marker + nearby blocks，caption MUST 前置。

#### Scenario: figure chunk 文本结构
- **WHEN** Chunker 处理一个 FigureAssociation
- **THEN** 生成的 parent chunk 文本结构为：
  ```
  [图 X-Y caption 文本]
  [figure marker（占位符或元数据引用）]
  [nearby block 1 文本]
  [nearby block 2 文本]
  ...
  ```
  caption 始终在第一行

#### Scenario: figure 字段填充
- **WHEN** 生成 figure parent chunk
- **THEN** chunk 字段 `figure_id` = FigureAssociation.figure_id；`block_type` = "figure"；`figure_role` 根据 caption 启发推断（schematic / photo / assembly）；parent_extras 中 `nearby_block_ids` 保留原 block id 列表

#### Scenario: figure 的 leaf chunk
- **WHEN** figure parent chunk 内文本超长需要拆 leaf
- **THEN** caption 和 figure marker 必须在每个 leaf 的 retrieval_text 前缀中保留，确保单 leaf 检索时仍能识别 figure 归属

### Requirement: 表格 parent chunk
Chunker MUST 为每个有效的 ParsedTable 生成一个 table parent chunk，文本 SHALL 包含 caption + markdown + nearby 解释段。重字段 table_markdown 和 cells_structured SHALL 进 ParentChunkStore。

#### Scenario: 参数表识别
- **WHEN** ParsedTable 的表头或前几行包含参数名/单位/取值范围
- **THEN** Chunker 将 table_role 标记为 "parameter"；parent_extras 中 `parameter_keys` 列出识别到的参数名

#### Scenario: 表格 chunk 字段
- **WHEN** 生成 table parent chunk
- **THEN** chunk 字段 `table_id`、`table_role`、`block_type` = "table" 填充；retrieval_text 包含 caption 和 markdown 前 N 行的摘要（用于 sparse 索引）；完整 table_markdown 进 parent store

#### Scenario: 表格的 leaf chunk
- **WHEN** 表格内容过长需要拆 leaf
- **THEN** 按行切分（不按字符切），每个 leaf 至少包含完整的表头 + 若干数据行；不允许出现"半行"的 leaf

### Requirement: parent / leaf 二级 chunk 结构
Chunker MUST 为每个 parent chunk 生成至少一个 leaf chunk（除非 parent 本身已足够小直接作为 retrieval 目标）。leaf MUST 共享 parent_id、root_chunk_id、section_path 等结构信号。

#### Scenario: parent / leaf 关系
- **WHEN** Chunker 处理一个 section
- **THEN** 生成 1 个 parent chunk（chunk_level=1, chunk_role="root"），下挂若干 leaf chunk（chunk_level=3, chunk_role="leaf"）；leaf 的 parent_chunk_id 指向 parent；leaf 的 root_chunk_id 也指向 parent（同 root_id）

#### Scenario: 单一 leaf 优化
- **WHEN** parent chunk 文本短于 leaf 切分阈值
- **THEN** Chunker 可选择直接生成 1 个 leaf = parent 全文；parent 和 leaf 内容相同但 chunk_id 不同

### Requirement: chunk metadata 字段集
Chunker 输出的每个 MaintenanceChunk MUST 包含完整的 metadata 字段集，进 Milvus 的字段 SHALL 定长化，重字段 SHALL 进 ParentChunkStore。

#### Scenario: Milvus 字段集
- **WHEN** chunk 索引到 Milvus
- **THEN** 写入字段包含：chunk_id, parent_chunk_id, root_chunk_id, chunk_level, chunk_role, chunk_idx, index_profile, filename, file_type, file_path, page_start, page_end, section_title, section_path, anchor_id, block_type, list_group_id, list_order, list_marker, list_level, list_complete, table_id, table_role, figure_id, figure_role, entity_types, term_match_count, text, retrieval_text

#### Scenario: ParentChunkStore 字段集
- **WHEN** chunk 写入 ParentChunkStore
- **THEN** 写入字段包含：full_text、child_chunk_ids、child_chunk_count、table_caption、table_markdown、table_cells_structured、figure_caption、nearby_block_ids、term_matches、protected_tokens；不包含已在 Milvus 中的核心字段（避免冗余）

#### Scenario: 缺失字段处理
- **WHEN** 某 chunk 不涉及表格或图示
- **THEN** table_id / table_role / figure_id / figure_role 字段为空字符串或 null；Milvus 接受 null 值；下游消费时按 null 处理

### Requirement: 阶段化 profile 支持
chunker 的能力 SHALL 分阶段引入，每阶段 MUST 对应一个 RAG_INDEX_PROFILE 名称。早期阶段 MUST NOT 写入晚期字段，但 schema 必须兼容（晚期字段在早期 profile 中为 null）。

#### Scenario: 阶段 1 profile
- **WHEN** RAG_INDEX_PROFILE = "v4_step_protection"
- **THEN** chunker 只写入 list_group_id 等步骤保护相关字段；figure_id / table_id / entity_types 字段为 null（即使 chunker 实现已支持后续阶段）

#### Scenario: profile 切换
- **WHEN** RAG_INDEX_PROFILE 从 "v4_step_protection" 改为 "v4_figure_nearby"
- **THEN** 新索引的 chunk 同时具备步骤保护和图文关联字段；旧 collection 保留不变；查询时按 profile 路由到对应 collection

### Requirement: terminology 集成
Chunker SHALL 在 chunk 生成后调用 terminology_matcher（由 `rag-terminology-module` 提供）扫描 retrieval_text，MUST 写入 entity_types / term_match_count 到 Milvus，term_matches / protected_tokens 到 ParentChunkStore。terminology 模块未上线时 SHALL 跳过此步骤。

#### Scenario: terminology 可用时
- **WHEN** terminology_matcher 已注册到系统
- **THEN** chunker 调用 `terminology_matcher.scan_text(chunk.retrieval_text)`；填充 entity_types 等字段

#### Scenario: terminology 不可用时
- **WHEN** terminology_matcher 未注册或调用失败
- **THEN** chunker 跳过术语扫描；entity_types 为空列表；term_match_count = 0；不阻断 chunking 流程
