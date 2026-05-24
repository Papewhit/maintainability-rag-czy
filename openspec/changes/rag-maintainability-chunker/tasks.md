## 1. Milestone M0：DeepDoc 集成 Spike

- [ ] 1.1 单文件 Python 脚本验证：用 swxy 的 DeepDoc 模块（或独立安装）解析一份带图表的样本 PDF，输出 block/table/figure 结构
- [ ] 1.2 验证依赖：PaddleOCR / OpenCV / 模型权重的安装路径和资源占用
- [ ] 1.3 性能 baseline：单页 PDF 解析延迟 P50/P95；100 页 PDF 总解析时间
- [ ] 1.4 决策：DeepDoc 内嵌进程 vs 独立 HTTP 服务（基于资源占用和加载时间）
- [ ] 1.5 输出 spike report 到 `docs/superpowers/spikes/deepdoc-integration.md`

**验收**：能稳定解析至少一份样本 PDF；性能数据可参考；集成形态有明确决定。

## 2. Milestone M1：解析-结构化-分块三层骨架

- [ ] 2.1 定义 `ParsedBlock` / `ParsedTable` / `ParsedFigureAnchor` / `ParsedDocument` 数据类（`backend/documents/parse_adapter/base.py`）
- [ ] 2.2 定义 `NormalizedBlock` / `ListGroup` / `FigureAssociation` / `NormalizedDocument` 数据类（`backend/documents/normalizer/base.py`）
- [ ] 2.3 定义 `MaintenanceChunk` 数据类（`backend/documents/chunker/base.py`）
- [ ] 2.4 `ParseAdapter` 协议（接受文件路径 → 返回 ParsedDocument）
- [ ] 2.5 Excel parser 实现（最简版：UnstructuredExcelLoader 包装为 ParseAdapter）
- [ ] 2.6 DeepDoc adapter 实现（基于 M0 决定的集成形态）
- [ ] 2.7 `parse_adapter.registry` 按扩展名分发到具体 adapter
- [ ] 2.8 测试：每个 adapter 对样本文档输出符合契约的 ParsedDocument

**验收**：三层数据类通过 mypy 检查；DeepDoc adapter 和 Excel parser 都能产出有效 ParsedDocument。

## 3. Milestone M2：阶段 1 - list_group 识别与步骤保护

- [ ] 3.1 Normalizer：实现 list_item 识别（基于 list_marker 正则：数字/罗马/中文序号、括号包裹序号、字母序号）
- [ ] 3.2 Normalizer：实现 list_level 推断（基于缩进、marker 类型嵌套规则）
- [ ] 3.3 Normalizer：聚合连续同级 list_item 为 ListGroup（通用层，不带领域信号）
- [ ] 3.4 Normalizer：构建 heading_tree 和 section_path（覆盖现有 `_build_structured_chunks` 的能力）
- [ ] 3.5 Chunker：步骤保护规则
  - 连续 ListGroup 在 parent chunk 内不切分
  - 超长 ListGroup 按一级序号切分（保持子步骤跟父步骤）
  - 维修动作词作为 chunk 边界辅助信号（"拆卸/检查/更换/安装/复验"等）
- [ ] 3.6 Chunker：生成 parent + leaf chunk，写入 list_group_id / list_order / list_marker / list_level / list_complete
- [ ] 3.7 Milvus schema 切换到新 profile `v4_step_protection`
- [ ] 3.8 端到端测试：上传含维修步骤的样本文档，验证步骤组不被截断；现有 RAG 流程对新 chunk 仍可工作

**验收**：维修步骤类样本上传后，list_group_id 和 list_order 字段填充正确；步骤完整性测试通过；性能不显著退化（chunk 数量与旧 profile 相近）。

## 4. Milestone M3：阶段 2 - 图文 nearby 关联

- [ ] 4.1 Normalizer：figure caption 与 nearby block 双向匹配（同页 + bbox 距离 + 反向引用文本）
- [ ] 4.2 Normalizer：输出 `FigureAssociation` 列表
- [ ] 4.3 Chunker：figure parent chunk 生成
  - chunk 文本 = caption + figure marker + nearby blocks 拼接
  - caption 前置
  - 字段 figure_id / figure_role / nearby_block_ids（后者进 parent store）
- [ ] 4.4 Milvus schema 切换到 `v4_figure_nearby`
- [ ] 4.5 测试：上传含图示的样本，验证 figure_id 和 nearby 关联正确

**验收**：图文样本召回时返回完整 figure parent chunk；caption 和 nearby 段落在同一 chunk 内可见。

## 5. Milestone M4：阶段 3 - 表格与参数表

- [ ] 5.1 Normalizer：验证 DeepDoc 表格输出的 cells 完整性（行列数、表头位置）
- [ ] 5.2 Normalizer：表格 markdown 兜底转换（DeepDoc 已做时跳过）
- [ ] 5.3 Chunker：table parent chunk 生成
  - chunk 文本 = caption + markdown + nearby 解释段
  - 字段 table_id / table_role
  - 重字段（table_markdown / cells_structured）进 parent store
- [ ] 5.4 Chunker：参数表识别（table_role=parameter）
  - 表格行包含参数名/单位/取值范围的，标记为 parameter
  - 写入 parent_extras 的 parameter_keys 列表
- [ ] 5.5 Milvus schema 切换到 `v4_table_aware`
- [ ] 5.6 测试：参数表查询时表格 chunk 排名提升

**验收**：参数表样本查询命中正确的 table_chunk；markdown 渲染可用于回答展示。

## 6. Milestone M5：阶段 4 - 术语标注集成

- [ ] 6.1 等待 `rag-terminology-module` 上线（依赖项）
- [ ] 6.2 Chunker：每个 chunk 生成后调用 `terminology_matcher.scan_text(chunk.retrieval_text)`
- [ ] 6.3 写入 metadata：`entity_types`、`term_match_count`（Milvus）、`term_matches`、`protected_tokens`（parent store）
- [ ] 6.4 Milvus schema 切换到 `v4_full`
- [ ] 6.5 测试：含术语的样本 chunk 正确写入 entity_types 列表

**验收**：术语模块上线后，所有新索引的 chunk 都带 entity_types 字段；rerank 模块可使用 term_match_count 作为信号。

## 7. Milestone M6：parse_meta 与管理工具

- [ ] 7.1 数据库新增 `document_parse_meta` 表：document_id, parse_engine, parse_engine_version, watermark_filter_ratio, ocr_confidence_avg, hierarchy_validation_warnings (JSON), parse_warnings, parse_duration_ms
- [ ] 7.2 document_service 上传完成后写入 parse_meta
- [ ] 7.3 管理员 API：`GET /admin/documents/{id}/parse_meta` 查看解析元数据
- [ ] 7.4 管理员工具：批量重新索引（选定一批文档，重新跑当前 profile 的管线）
- [ ] 7.5 文档：profile lifecycle 管理（创建、标记 deprecated、删除旧 collection）

**验收**：每份文档的解析元数据可查询；管理员能触发批量重索引；profile 切换流程文档完整。

## 8. Milestone M7：软边界澄清

- [ ] 8.1 阶段 1 完成后，组织 DeepDoc 源代码 review
- [ ] 8.2 澄清 design.md 中"软边界条目"表的归属（标题树/表头合并/figure caption 等）
- [ ] 8.3 更新 design.md 移除模糊条目
- [ ] 8.4 必要时调整 Normalizer 或 Parse Adapter 的实现（避免重复或漏做）

**验收**：design.md 中无 "待 DeepDoc 源代码核对" 字样；每个能力的归属层明确。
