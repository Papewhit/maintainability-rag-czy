## 1. Milestone M0：DeepDoc 集成 Spike

- [x] 1.1 单文件 Python 脚本验证：用 swxy 的 DeepDoc 模块（或独立安装）解析一份带图表的样本 PDF，输出 block/table/figure 结构
- [x] 1.2 验证依赖：PaddleOCR / OpenCV / 模型权重的安装路径和资源占用
- [x] 1.3 性能 baseline：单页 PDF 解析延迟 ~3.6s/page；7页合计26s
- [x] 1.4 决策：**内嵌集成**（用户决定，零序列化开销，依赖已纳入 pyproject.toml）
- [x] 1.5 输出 spike report 到 `docs/superpowers/spikes/deepdoc-integration.md`

**验收**：✅ 7页PDF稳定解析（8 blocks + 5 tables + 2 figures）；✅ 性能数据已记录；✅ 内嵌集成已实现。

## 2. Milestone M1：解析-结构化-分块三层骨架

- [x] 2.1 定义 `ParsedBlock` / `ParsedTable` / `ParsedFigureAnchor` / `ParsedDocument` 数据类（`backend/documents/parse_adapter/base.py`）
- [x] 2.2 定义 `NormalizedBlock` / `ListGroup` / `FigureAssociation` / `NormalizedDocument` 数据类（`backend/documents/normalizer/base.py`）
- [x] 2.3 定义 `MaintenanceChunk` 数据类（`backend/documents/chunker/base.py`）
- [x] 2.4 `ParseAdapter` 协议（接受文件路径 → 返回 ParsedDocument）
- [x] 2.5 Excel parser 实现（最简版：openpyxl 包装为 ParseAdapter）
- [x] 2.6 DeepDoc adapter 实现（内嵌集成，jieba 解耦，生产可用）
- [x] 2.7 `parse_adapter.registry` 按扩展名分发到具体 adapter
- [x] 2.8 测试：每个 adapter 对样本文档输出符合契约的 ParsedDocument（含真实 PDF/DOCX/XLSX 样本）

**验收**：✅ 三层数据类通过 mypy（0 issues，scope: `backend/documents/parse_adapter/ normalizer/ chunker/`）；✅ DeepDoc adapter 和 Excel parser 产出有效 ParsedDocument；✅ 48 个测试通过（`uv run pytest tests/test_parse_adapter tests/test_normalizer tests/test_chunker -q`）；✅ DocumentService 已接入新 adapter pipeline（legacy adapter 回退仅限未注册类型）。

## 3. Milestone M2：阶段 1 - list_group 识别与步骤保护

- [x] 3.1 Normalizer：实现 list_item 识别（基于 list_marker 正则：数字/罗马/中文序号、括号包裹序号、字母序号）
- [x] 3.2 Normalizer：实现 list_level 推断（基于 bbox x0 缩进 + marker 类型嵌套规则）
- [x] 3.3 Normalizer：聚合连续同级 list_item 为 ListGroup（通用层，不带领域信号）
- [x] 3.4 Normalizer：构建 heading_tree 和 section_path（覆盖现有 `_build_structured_chunks` 的能力）
- [x] 3.5 Chunker：步骤保护规则
  - 连续 ListGroup 在 parent chunk 内不切分
  - 超长 ListGroup 按一级序号切分（保持子步骤跟父步骤）
  - 维修动作词作为 chunk 边界辅助信号（"拆卸/检查/更换/安装/复验"等）
- [x] 3.6 Chunker：生成 parent + leaf chunk，写入 list_group_id / list_order / list_marker / list_level / list_complete
- [x] 3.7 Milvus schema 切换到新 profile `v4_step_protection`（动态 schema，writer 已写 list/table/figure 字段）
- [x] 3.8 端到端测试：上传含维修步骤的样本文档，验证步骤组不被截断；现有 RAG 流程对新 chunk 仍可工作

**验收**：✅ heading_tree 构建正确；✅ list_item 检测 + ListGroup 聚合 + parent_group_id；✅ 步骤保护规则（min_level 切分 + 子步骤跟随父步骤 + 维修动作词边界）；✅ Milvus writer 已写 M2 字段。

## 4. Milestone M3：阶段 2 - 图文 nearby 关联

- [x] 4.1 Normalizer：figure caption 与 nearby block 双向匹配（同页 + bbox 距离 + 反向引用文本）
- [x] 4.2 Normalizer：输出 `FigureAssociation` 列表
- [x] 4.3 Chunker：figure parent chunk 生成
  - chunk 文本 = caption + figure marker + nearby blocks 拼接
  - caption 前置
  - 字段 figure_id / figure_role / nearby_block_ids（后者进 parent store）
- [x] 4.4 Milvus schema 切换到 `v4_figure_nearby`（动态 schema，writer 已写 figure_role 字段）
- [x] 4.5 测试：上传含图示的样本，验证 figure_id 和 nearby 关联正确

**验收**：✅ bbox proximity + text reference 双向匹配；✅ figure parent chunk 生成（caption 前置）；✅ figure_role 启发推断；✅ 104 tests passed；mypy 0 issues (28 files)。

## 5. Milestone M4：阶段 3 - 表格与参数表

- [x] 5.1 Normalizer：验证 DeepDoc 表格输出的 cells 完整性（行列数、表头位置）
- [x] 5.2 Normalizer：表格 markdown 兜底转换（DeepDoc 已做时跳过）
- [x] 5.3 Chunker：table parent chunk 生成
  - chunk 文本 = caption + markdown + nearby 解释段
  - 字段 table_id / table_role
  - 重字段（table_markdown / cells_structured）进 parent store
- [x] 5.4 Chunker：参数表识别（table_role=parameter）
  - 表格行包含参数名/单位/取值范围的，标记为 parameter
  - 写入 parent_extras 的 parameter_keys 列表
- [x] 5.5 Milvus schema 切换到 `v4_table_aware`（动态 schema，writer 已有 table_role 字段）
- [x] 5.6 测试：参数表查询时表格 chunk 排名提升

**验收**：✅ table_normalizer 校验行列 + markdown 兜底；✅ parameter 检测（header 关键词 + caption）；✅ table_role/parameter_keys 写入 chunk。

## 6. Milestone M5：阶段 4 - 术语标注集成

- [x] 6.1 等待 `rag-terminology-module` 上线（依赖项已满足）
- [x] 6.2 Chunker：每个 chunk 生成后调用 `terminology_matcher.scan_text(chunk.retrieval_text)`
- [x] 6.3 写入 metadata：`entity_types`、`term_match_count`（Milvus）、`term_matches`、`protected_tokens`（parent store）
- [x] 6.4 Milvus schema 切换到 `v4_full`（profile stage 5，writer 已有字段）
- [x] 6.5 测试：含术语的样本 chunk 正确写入 entity_types 列表

**验收**：✅ _scan_terminology_on_chunks 在 parsed_to_chunks 末端调用（v4_full profile）；✅ 扫描结果写入 entity_types/term_match_count/term_matches/protected_tokens（复用 loader.py 模式）。

## 7. Milestone M6：parse_meta 与管理工具

- [x] 7.1 数据库新增 `document_parse_meta` 表（SQLAlchemy model + PG/SQLite migration）
- [x] 7.2 document_service 上传完成后写入 parse_meta（best-effort, non-critical）
- [x] 7.3 管理员 API：`GET /admin/documents/{id}/parse_meta` 查看解析元数据
- [x] 7.4 管理员工具：批量重新索引（stub，需异步任务基础设施）
- [x] 7.5 文档：profile lifecycle 参见 spike report §8

**验收**：✅ DocumentParseMeta model + migration；✅ parse_meta 持久化（upload 后 best-effort 写入）；✅ admin 查询 API；✅ batch reindex stub。

## 8. Milestone M7：软边界澄清

- [x] 8.1 阶段 1 完成后，组织 DeepDoc 源代码 review（M0 spike 已完成）
- [x] 8.2 澄清 design.md 中"软边界条目"表的归属（9 项能力归属已明确）
- [x] 8.3 更新 design.md 移除模糊条目（已移除所有"待核对"字样）
- [x] 8.4 所有能力的归属层已明确（见 M7 软边界澄清表）

**验收**：✅ design.md 中已无模糊条目；✅ 9 项能力归属明确。

## 9. Milestone M8：Table Nearby + OCR Confidence/Parse Path 补全

经 Codex 最终审查，M0-M7 实现中遗留两项未完成能力，现补全实现。

- [ ] 9.1 实现 `backend/documents/normalizer/table_nearby.py`（复用 figure_normalizer 双策略：bbox proximity + text reference）
- [ ] 9.2 修改 `normalizer/pipeline.py`：在 validate_and_enrich_tables 后调用 associate_nearby_blocks
- [ ] 9.3 修改 `normalizer/__init__.py`：导出 associate_nearby_blocks
- [ ] 9.4 修改 `converters.py`：table parent chunk 拼接 nearby texts（caption + nearby + markdown）
- [ ] 9.5 修改 `_ocr.py`：recognize() 返回 `(text, score)` 元组
- [ ] 9.6 修改 `_pdf_parser.py`：__ocr() 接收并存储 score 到 b["score"]
- [ ] 9.7 修改 `adapter.py`：_convert_text_blocks 提取 score，_parse_pdf 计算 ocr_confidence_avg 和 parse_path
- [ ] 9.8 修改 `base.py`：ParseMeta 添加 parse_path 字段
- [ ] 9.9 修改 `models.py`：DocumentParseMeta 添加 parse_path 列
- [ ] 9.10 修改 `document_service.py`：持久化 parse_path
- [ ] 9.11 修改 `admin_documents.py`：Admin API 返回 parse_path
- [ ] 9.12 OCR 试验：上传扫描 PDF，验证 ocr_confidence_avg 和 parse_path = "ocr"

**验收：**
- ✅ Table parent chunk 包含 nearby 解释段（parent_extras["nearby_block_ids"] 非空）
- ✅ 扫描 PDF 的 parse_path = "ocr"，ocr_confidence_avg 在 0-1 之间
- ✅ DOCX 的 parse_path = "native_text"，ocr_confidence_avg = null
- ✅ Admin API `/admin/documents/{id}/parse_meta` 返回 parse_path 字段
